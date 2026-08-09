"""

Two demo scenarios, both realistic for the schema:
  1. Mid-cycle changes (SCD2 + incremental watermark mechanics):
     - Rename one `programs` row -> new SCD2 version on next `dbt snapshot`
     - UPDATE existing program_enrollments/subject_enrollments rows
       (their triggers auto-bump updated_at)
     - UPDATE one assessment_results row (no trigger there -> set
       updated_at explicitly)
  2. New intake: a new 2026 semester, new offerings, new students,
     new program/subject enrollments — genuinely new rows, dated 2026,
     inserted in FK-safe order (parents before children).

NOTE: data_loader.py bulk-inserts SERIAL primary keys explicitly (e.g.
off_id = 1, 2, 3... in Python), which never advances Postgres's internal
auto-increment sequence for those columns. sync_sequence() resyncs each
affected sequence to the real MAX(id) before we let Postgres auto-generate
any new ones here — otherwise new inserts collide with existing rows.

Run on your Mac, same as data_loader.py — NOT inside a container:
    python seed_incremental.py
"""

import os
import psycopg2
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

PG_CONN = dict(
    dbname=os.getenv("PG_DBNAME"),
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
)


# ── Utility ──────────────────────────────────────────────────────

def sync_sequence(cur, table, column):
    """
    Bulk loaders that insert explicit PK values (like data_loader.py) don't
    advance the table's underlying auto-increment sequence. This resyncs it
    to the actual current max, so future auto-generated inserts don't
    collide with existing rows.
    """
    cur.execute(f"""
        SELECT setval(
            pg_get_serial_sequence('{table}', '{column}'),
            COALESCE((SELECT MAX({column}) FROM {table}), 1)
        );
    """)
    print(f"[SYNC] {table}.{column} sequence resynced to current MAX.")


# ── Scenario 1: mid-cycle changes ───────────────────────────────

def update_program_for_snapshot(cur):
    cur.execute("SELECT program_id, program_name FROM programs ORDER BY program_id LIMIT 1;")
    program_id, program_name = cur.fetchone()
    base_name = program_name.split(" (Updated")[0]
    new_name = f"{base_name} (Updated {date.today().isoformat()})"
    cur.execute("UPDATE programs SET program_name = %s WHERE program_id = %s;", (new_name, program_id))
    print(f"[SNAPSHOT DEMO] programs.program_id={program_id} -> '{new_name}'")


def graduate_one_program_enrollment(cur):
    cur.execute("""
        SELECT program_enrollment_id FROM program_enrollments
        WHERE status = 'Active' ORDER BY program_enrollment_id LIMIT 1;
    """)
    row = cur.fetchone()
    if not row:
        print("[MID-CYCLE] No 'Active' program_enrollments left to graduate.")
        return
    pe_id = row[0]
    cur.execute("""
        UPDATE program_enrollments
        SET status = 'Graduated', completion_date = %s, final_degree_result = 'Pass'
        WHERE program_enrollment_id = %s;
    """, (date.today(), pe_id))
    print(f"[MID-CYCLE] program_enrollments.program_enrollment_id={pe_id} -> Graduated")


def bump_one_subject_enrollment(cur):
    cur.execute("""
        SELECT subject_enrollment_id, final_mark FROM subject_enrollments
        WHERE status = 'Completed' ORDER BY subject_enrollment_id DESC LIMIT 1;
    """)
    se_id, final_mark = cur.fetchone()
    new_mark = min(100, float(final_mark or 60) + 1)
    cur.execute("UPDATE subject_enrollments SET final_mark = %s WHERE subject_enrollment_id = %s;",
                (new_mark, se_id))
    print(f"[MID-CYCLE] subject_enrollments.subject_enrollment_id={se_id} final_mark -> {new_mark}")


def bump_one_assessment_result(cur):
    cur.execute("SELECT result_id, raw_score FROM assessment_results ORDER BY result_id DESC LIMIT 1;")
    result_id, raw_score = cur.fetchone()
    new_score = min(100, float(raw_score) + 1)
    cur.execute("""
        UPDATE assessment_results SET raw_score = %s, updated_at = NOW()
        WHERE result_id = %s;
    """, (new_score, result_id))
    print(f"[MID-CYCLE] assessment_results.result_id={result_id} raw_score -> {new_score}")


# ── Scenario 2: new intake ──────────────────────────────────────

def add_new_intake(cur, n_students=4):
    # Resync sequences first — these tables were bulk-loaded with explicit
    # PKs by data_loader.py, so their SERIAL sequences are stale.
    sync_sequence(cur, "subject_offerings", "offering_id")
    sync_sequence(cur, "program_enrollments", "program_enrollment_id")
    sync_sequence(cur, "subject_enrollments", "subject_enrollment_id")

    # 1. New semester
    semester_id = "SEM-2026-S1"
    start_date = date(2026, 2, 15)
    end_date = start_date + timedelta(days=112)
    cur.execute("""
        INSERT INTO semesters (semester_id, semester_name, academic_year, start_date, end_date)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (semester_id) DO NOTHING;
    """, (semester_id, "Semester S1", 2026, start_date, end_date))
    print(f"[NEW INTAKE] semester {semester_id} ensured.")

    # 2. Offerings for 2 existing subjects, tied to the new semester
    cur.execute("SELECT subject_code FROM subjects ORDER BY subject_code LIMIT 2;")
    subject_codes = [r[0] for r in cur.fetchall()]

    new_offering_ids = []
    for subject_code in subject_codes:
        cur.execute("""
            INSERT INTO subject_offerings (subject_code, semester_id, coordinator_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (subject_code, semester_id) DO NOTHING
            RETURNING offering_id;
        """, (subject_code, semester_id, "Dr. Incoming Faculty"))
        row = cur.fetchone()
        if row:
            new_offering_ids.append(row[0])

    if not new_offering_ids:
        cur.execute("""
            SELECT offering_id FROM subject_offerings
            WHERE semester_id = %s AND subject_code = ANY(%s);
        """, (semester_id, subject_codes))
        new_offering_ids = [r[0] for r in cur.fetchall()]
    print(f"[NEW INTAKE] offerings for {semester_id}: {new_offering_ids}")

    # 3. New students
    cur.execute("SELECT student_id FROM students ORDER BY student_id DESC LIMIT 1;")
    last_num = int(cur.fetchone()[0].split("-")[1])

    new_student_ids = []
    for i in range(1, n_students + 1):
        sid = f"STU-{last_num + i:05d}"
        cur.execute("""
            INSERT INTO students (student_id, first_name, last_name, email, created_at)
            VALUES (%s, %s, %s, %s, NOW());
        """, (sid, "New", f"Student{last_num + i}", f"new.student{last_num + i}@student.edu"))
        new_student_ids.append(sid)
    print(f"[NEW INTAKE] new students: {new_student_ids}")

    # 4. Program enrollments for the new students
    cur.execute("SELECT program_id FROM programs WHERE degree_level = 'Bachelor''s' ORDER BY program_id LIMIT 1;")
    program_id = cur.fetchone()[0]

    new_pe_ids = []
    for sid in new_student_ids:
        cur.execute("""
            INSERT INTO program_enrollments (student_id, program_id, enrollment_date, status)
            VALUES (%s, %s, %s, 'Active')
            RETURNING program_enrollment_id;
        """, (sid, program_id, date.today()))
        new_pe_ids.append(cur.fetchone()[0])
    print(f"[NEW INTAKE] new program_enrollments: {new_pe_ids} into {program_id}")

    # 5. Subject enrollments into the new offerings (no results yet — just enrolled)
    for idx, pe_id in enumerate(new_pe_ids):
        offering_id = new_offering_ids[idx % len(new_offering_ids)]
        cur.execute("""
            INSERT INTO subject_enrollments (program_enrollment_id, offering_id, status)
            VALUES (%s, %s, 'Enrolled')
            ON CONFLICT (program_enrollment_id, offering_id) DO NOTHING;
        """, (pe_id, offering_id))
    print(f"[NEW INTAKE] subject_enrollments created for {len(new_pe_ids)} new students")


def main():
    con = psycopg2.connect(**PG_CONN)
    con.autocommit = False
    cur = con.cursor()
    try:
        update_program_for_snapshot(cur)
        graduate_one_program_enrollment(cur)
        bump_one_subject_enrollment(cur)
        bump_one_assessment_result(cur)
        add_new_intake(cur)

        con.commit()
        print("Supplemental seeding complete — committed.")
    except Exception as e:
        con.rollback()
        print(f"Seeding failed, rolled back: {e}")
        raise
    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    main()