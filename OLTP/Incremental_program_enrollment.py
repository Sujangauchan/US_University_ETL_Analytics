"""
Adds 20 new students to a 2025 semester — enrolls each in a program
(weighted 70/25/5 Bachelor's/Master's/Doctoral) and their program's 
real first-semester subjects, with no grades yet since they just enrolled. 
One transaction, all or nothing.
"""

import os
import random
import psycopg2
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

PG_CONN = dict(
    dbname=os.getenv("PG_DBNAME"),
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
)

TARGET_SEMESTER_ID = "SEM-2025-S2"
N_STUDENTS = 20

# Same weighting data_loader.py uses for single-program students.
DEGREE_WEIGHTS = {"Bachelor's": 0.70, "Master's": 0.25, "Doctoral": 0.05}


def sync_sequence(cur, table, column):
    cur.execute(f"""
        SELECT setval(
            pg_get_serial_sequence('{table}', '{column}'),
            COALESCE((SELECT MAX({column}) FROM {table}), 1)
        );
    """)
    print(f"[SYNC] {table}.{column} sequence resynced to current MAX.")


def pick_program(cur):
    """Weighted by degree level, same distribution as data_loader.py."""
    degree = random.choices(
        list(DEGREE_WEIGHTS.keys()), weights=list(DEGREE_WEIGHTS.values())
    )[0]
    cur.execute(
        "SELECT program_id FROM programs WHERE degree_level = %s ORDER BY random() LIMIT 1;",
        (degree,),
    )
    row = cur.fetchone()
    return row[0], degree


def first_semester_subjects(cur, program_id):
    """Reuses the real program_subjects relation -- a student's subjects
    must actually belong to their program's curriculum."""
    cur.execute("""
        SELECT subject_code FROM program_subjects
        WHERE program_id = %s AND recommended_semester = 1;
    """, (program_id,))
    codes = [r[0] for r in cur.fetchall()]
    if not codes:
        # Fallback: no semester-1 subjects mapped for this program --
        # take up to 4 of whatever is mapped, rather than crash or skip.
        cur.execute("""
            SELECT subject_code FROM program_subjects
            WHERE program_id = %s ORDER BY random() LIMIT 4;
        """, (program_id,))
        codes = [r[0] for r in cur.fetchall()]
    return codes


def ensure_offering(cur, subject_code, semester_id):
    cur.execute("""
        INSERT INTO subject_offerings (subject_code, semester_id, coordinator_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (subject_code, semester_id) DO NOTHING
        RETURNING offering_id;
    """, (subject_code, semester_id, "Dr. Incoming Faculty"))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("""
        SELECT offering_id FROM subject_offerings
        WHERE subject_code = %s AND semester_id = %s;
    """, (subject_code, semester_id))
    return cur.fetchone()[0]


def add_new_intake(cur, n_students=N_STUDENTS):
    sync_sequence(cur, "subject_offerings", "offering_id")
    sync_sequence(cur, "program_enrollments", "program_enrollment_id")
    sync_sequence(cur, "subject_enrollments", "subject_enrollment_id")

    cur.execute("SELECT semester_id, start_date, end_date FROM semesters WHERE semester_id = %s;",
                (TARGET_SEMESTER_ID,))
    sem_row = cur.fetchone()
    if not sem_row:
        raise RuntimeError(f"{TARGET_SEMESTER_ID} not found in semesters table.")
    semester_id, sem_start, sem_end = sem_row
    enrollment_date = sem_start + timedelta(days=14)
    print(f"[NEW INTAKE] targeting {semester_id} ({sem_start} to {sem_end}); "
          f"enrollment_date={enrollment_date}")

    cur.execute("SELECT student_id FROM students ORDER BY student_id DESC LIMIT 1;")
    last_num = int(cur.fetchone()[0].split("-")[1])

    created_students, created_pe, created_se = 0, 0, 0

    for i in range(1, n_students + 1):
        sid = f"STU-{last_num + i:05d}"
        cur.execute("""
            INSERT INTO students (student_id, first_name, last_name, email, created_at)
            VALUES (%s, %s, %s, %s, %s);
        """, (sid, "New", f"Student{last_num + i}", f"new.student{last_num + i}@student.edu",
              enrollment_date))
        created_students += 1

        program_id, degree = pick_program(cur)
        cur.execute("""
            INSERT INTO program_enrollments (student_id, program_id, enrollment_date, status)
            VALUES (%s, %s, %s, 'Active')
            RETURNING program_enrollment_id;
        """, (sid, program_id, enrollment_date))
        pe_id = cur.fetchone()[0]
        created_pe += 1

        subject_codes = first_semester_subjects(cur, program_id)
        for subject_code in subject_codes:
            offering_id = ensure_offering(cur, subject_code, semester_id)
            cur.execute("""
                INSERT INTO subject_enrollments (program_enrollment_id, offering_id, status)
                VALUES (%s, %s, 'Enrolled')
                ON CONFLICT (program_enrollment_id, offering_id) DO NOTHING;
            """, (pe_id, offering_id))
            created_se += 1

        print(f"[NEW INTAKE] {sid} -> {degree} / {program_id}, "
              f"{len(subject_codes)} subject(s): {subject_codes}")

    print(f"[NEW INTAKE] totals: {created_students} students, "
          f"{created_pe} program_enrollments, {created_se} subject_enrollments")


def main():
    con = psycopg2.connect(**PG_CONN)
    con.autocommit = False
    cur = con.cursor()
    try:
        add_new_intake(cur)
        con.commit()
        print("New enrollments committed.")
    except Exception as e:
        con.rollback()
        print(f"Failed, rolled back: {e}")
        raise
    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    main()