"""
university_data_loader.py
─────────────────────────
Load 700,000 subject enrollments with retakes and multi‑program support.

Usage:
  pip install psycopg2-binary faker tqdm
  python university_data_loader.py
"""

import os
import sys
import random
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Tuple
from tqdm import tqdm

import psycopg2
import psycopg2.extras
from faker import Faker

# ── Config ────────────────────────────────────────────────────────
DB_CONFIG = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "university_oltp"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASS", "password"),
)

TARGET_ENROLLMENTS = 700_000
BATCH_SIZE = 5000
RESET_FIRST = True
DRY_RUN = False

# Degree distribution
BACHELOR_PCT = 0.70
MASTER_PCT = 0.25
PHD_PCT = 0.05

# Multi‑program probabilities
SINGLE_PROGRAM = 0.75
DOUBLE_PROGRAM = 0.20
TRIPLE_PROGRAM = 0.05

# Subjects per program (lifetime)
SUBJECTS_PER_BACHELOR = 27
SUBJECTS_PER_MASTER = 16
SUBJECTS_PER_PHD = 8

SEED = 2024
# ──────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)
fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

# ── Helpers ──────────────────────────────────────────────────────

def generate_program_id(i): return f"PROG-{i:04d}"
def generate_student_id(i): return f"STU-{i:05d}"
def generate_subject_code(dept, num): return f"{dept.upper()}{num:03d}"
def generate_semester_id(year, term): return f"SEM-{year}-{term}"

def random_date(start, end):
    return start + timedelta(seconds=random.randint(0, int((end - start).total_seconds())))

def grade_from_mark(mark, degree_level):
    if degree_level in ("Master's", "Doctoral"):
        thresholds = [(85,'A'),(80,'A-'),(75,'B+'),(70,'B'),(65,'B-'),(60,'C+'),(55,'C'),(0,'F')]
    else:
        thresholds = [(85,'A'),(80,'A-'),(75,'B+'),(70,'B'),(65,'B-'),(60,'C+'),(55,'C'),(50,'C-'),(45,'D+'),(40,'D'),(35,'D-'),(0,'F')]
    for t, g in thresholds:
        if mark >= t:
            return g
    return 'F'

# ── Generate reference data ─────────────────────────────────────

def generate_programs():
    programs = []
    depts = ["Engineering","Science","Business","Arts","Medicine","Law","Education"]
    bachelor = [("Computer Science",144),("Software Engineering",144),("Business",144),
                ("Economics",144),("Psychology",144),("Biology",144),("Chemistry",144),
                ("Physics",144),("Mathematics",144),("Nursing",144),("Education",144)]
    master = [("Computer Science",96),("Data Science",96),("MBA",96),("Public Health",96),
              ("Education",96),("Engineering Management",96),("Finance",96)]
    doctoral = [("CS",72),("Physics",72),("Chemistry",72),("Mathematics",72),
                ("Economics",72),("Psychology",72),("Neuroscience",72)]
    idx = 1000
    for name, cred in bachelor:
        programs.append({"program_id": generate_program_id(idx), "program_name": f"Bachelor of {name}",
                         "department": random.choice(depts), "degree_level": "Bachelor's",
                         "total_credit_points_required": cred}); idx += 1
    for name, cred in master:
        programs.append({"program_id": generate_program_id(idx), "program_name": f"Master of {name}",
                         "department": random.choice(depts), "degree_level": "Master's",
                         "total_credit_points_required": cred}); idx += 1
    for name, cred in doctoral:
        programs.append({"program_id": generate_program_id(idx), "program_name": f"PhD in {name}",
                         "department": random.choice(depts), "degree_level": "Doctoral",
                         "total_credit_points_required": cred}); idx += 1
    return programs

def generate_subjects():
    subjects = []
    depts = {"CS":["Data Structures","Algorithms","DB","OS","Networks","AI","ML"],
             "MATH":["Calculus","Linear Algebra","Statistics","Diff Eq","Probability"],
             "PHYS":["Mechanics","E&M","Thermodynamics","Quantum","Optics"],
             "CHEM":["Organic","Inorganic","Physical","Biochem"],
             "BIO":["Molecular","Genetics","Ecology","Microbiology"],
             "ECON":["Micro","Macro","Econometrics","International"],
             "PSYC":["Cognitive","Developmental","Social","Clinical"],
             "ENG":["Circuits","Thermo","Fluids","Structural"],
             "BUS":["Accounting","Marketing","Finance","Strategy"],
             "EDU":["Curriculum","Pedagogy","Assessment"],
             "LAW":["Constitutional","Contract","Criminal"],
             "MED":["Anatomy","Physiology","Pharmacology"]}
    idx = 100
    for dept, titles in depts.items():
        for i, title in enumerate(titles):
            difficulty = random.choices([1,2,3,4,5], weights=[0.15,0.25,0.30,0.20,0.10])[0]
            subjects.append({"subject_code": generate_subject_code(dept, idx+i),
                             "subject_title": f"{dept} {i+1}: {title}",
                             "credit_points": random.choice([6,6,6,6,12]),
                             "difficulty": difficulty})      # kept for internal logic
        idx += 20
    return subjects[:250]

def generate_semesters():
    semesters = []
    for year in (2023,2024,2025):
        for term, month, day in [("S1",2,15),("S2",7,15),("Summer",11,1)]:
            start = datetime(year, month, day)
            end = start + timedelta(days=112)
            semesters.append({"semester_id": generate_semester_id(year, term),
                              "semester_name": f"Semester {term}" if term!="Summer" else "Summer Semester",
                              "academic_year": year, "start_date": start.date(), "end_date": end.date()})
    return semesters

# ── Helper to create a program enrollment ──────────────────────

def create_program_enrollment(prog_id, student_id, degree, enrollment_id,
                              students, prog_enrollments, planned_subject_enrollments,
                              prog_map, semesters, created, subjects):
    enroll_date = random_date(created + timedelta(days=30), created + timedelta(days=180))
    status = random.choices(["Active","Graduated","Withdrawn","Suspended","Dismissed","Leave of Absence"],
                            weights=[80,12,3,2,1,2])[0]
    comp_date = None
    if status == "Graduated":
        comp_date = enroll_date + timedelta(days=random.randint(1050,1460))
    elif status in ("Withdrawn","Dismissed"):
        comp_date = enroll_date + timedelta(days=random.randint(180,720))
    prog_enrollments.append({"program_enrollment_id": enrollment_id,
                             "student_id": student_id, "program_id": prog_id,
                             "enrollment_date": enroll_date.date(),
                             "completion_date": comp_date.date() if comp_date else None,
                             "status": status, "final_degree_result": None})

    available = prog_map.get(prog_id, [])
    if not available:
        return
    subs_per_student = {"Bachelor's": SUBJECTS_PER_BACHELOR,
                        "Master's": SUBJECTS_PER_MASTER,
                        "Doctoral": SUBJECTS_PER_PHD}[degree]
    chosen_subjects = random.sample(available, min(subs_per_student, len(available)))
    subject_difficulty = {s["subject_code"]: s["difficulty"] for s in subjects}
    for subj in chosen_subjects:
        difficulty = subject_difficulty.get(subj, 3)
        planned_subject_enrollments.append((enrollment_id, subj, degree, difficulty))

# ── Helper to create one subject enrollment attempt ─────────────

def create_attempt(se_id, pe_id, subject_code, semester_id, degree, difficulty,
                   subject_enrollments, assessment_results, offering_assessments,
                   get_or_create_assessments_for_offering, semester_lookup, offering_lookup):
    offering_id = offering_lookup.get((subject_code, semester_id))
    if not offering_id:
        return
    ass_list = get_or_create_assessments_for_offering(offering_id)

    # Submissions should fall within the offering's own semester window, not a
    # fixed calendar date range — otherwise submitted_at drifts arbitrarily far
    # from the semester the assessment actually belongs to.
    sem_info = semester_lookup.get(semester_id)
    if sem_info:
        sem_start = datetime.combine(sem_info["start_date"], datetime.min.time())
        sem_end = datetime.combine(sem_info["end_date"], datetime.min.time())
    else:
        sem_start, sem_end = datetime(2024, 1, 15), datetime(2024, 6, 30)

    ability = random.gauss(70, 12)
    ability = max(20, min(100, ability))
    difficulty_effect = - (difficulty - 1) * 3

    total_weighted = 0.0
    total_weight = 0.0
    for a in ass_list:
        noise = random.gauss(0, 8)
        raw_pct = ability + difficulty_effect + noise
        raw_pct = max(0, min(100, raw_pct))
        raw_score = round(raw_pct / 100 * a["max_score"], 2)
        raw_score = max(0, min(a["max_score"], raw_score))
        assessment_results.append({
            "subject_enrollment_id": se_id,
            "assessment_id": a["assessment_id"],
            "raw_score": raw_score,
            "submitted_at": random_date(sem_start, sem_end)
        })
        total_weighted += raw_score / a["max_score"] * a["weight"]
        total_weight += a["weight"]

    if total_weight > 0:
        final_mark = round(total_weighted / total_weight * 100, 2)
        final_mark = round(final_mark + random.uniform(-0.5, 0.5), 2)
        final_mark = max(0, min(100, final_mark))
    else:
        final_mark = None

    final_grade = grade_from_mark(final_mark, degree) if final_mark is not None else None
    status = "Completed"

    subject_enrollments.append({
        "subject_enrollment_id": se_id,
        "program_enrollment_id": pe_id,
        "offering_id": offering_id,
        "status": status,
        "final_mark": final_mark,
        "final_grade": final_grade,
    })

# ── Main ─────────────────────────────────────────────────────────

def main():
    log.info("="*60)
    log.info("Data Loader — 700k subject enrollments with retakes & multi‑programs")
    log.info("="*60)

    if DRY_RUN:
        log.info("DRY RUN – SQL will be written to file")
    else:
        conn = psycopg2.connect(**DB_CONFIG)
        if RESET_FIRST:
            log.info("Resetting tables...")
            conn.autocommit = True
            for t in ["assessment_results","assessments","subject_enrollments",
                      "program_enrollments","subject_offerings","program_subjects",
                      "students","semesters","subjects","programs"]:
                try: conn.cursor().execute(f"DELETE FROM {t}")
                except: pass

    # ---- 1. Reference data ----
    log.info("Generating reference data...")
    programs = generate_programs()
    subjects = generate_subjects()
    semesters = generate_semesters()

    # Program-subject links
    program_subjects = []
    prog_map = defaultdict(list)
    for prog in programs:
        chosen = random.sample(subjects, min(25, len(subjects)))
        for s in chosen:
            program_subjects.append({"program_id": prog["program_id"],
                                     "subject_code": s["subject_code"],
                                     "subject_type": random.choice(["Core","Elective","Major Requirement"]),
                                     "recommended_semester": random.randint(1,8)})
            prog_map[prog["program_id"]].append(s["subject_code"])

    # ---- 2. Students & program enrollments ----
    avg_subjects_per_program = (BACHELOR_PCT*SUBJECTS_PER_BACHELOR +
                                MASTER_PCT*SUBJECTS_PER_MASTER +
                                PHD_PCT*SUBJECTS_PER_PHD)
    retake_factor = 1.15
    total_program_enrollments_needed = int(TARGET_ENROLLMENTS / (avg_subjects_per_program * retake_factor))

    student_program_counts = []
    while sum(student_program_counts) < total_program_enrollments_needed:
        r = random.random()
        if r < SINGLE_PROGRAM:
            count = 1
        elif r < SINGLE_PROGRAM + DOUBLE_PROGRAM:
            count = 2
        else:
            count = 3
        student_program_counts.append(count)

    prog_by_level = defaultdict(list)
    for p in programs:
        prog_by_level[p["degree_level"]].append(p["program_id"])

    students = []
    prog_enrollments = []
    planned_subject_enrollments = []

    student_idx = 1
    enrollment_id = 1

    for count in student_program_counts:
        sid = generate_student_id(student_idx)
        first = fake.first_name()
        last = fake.last_name()
        email = f"{first.lower()}.{last.lower()}.{student_idx}@student.edu"
        created = random_date(datetime(2023,1,1), datetime(2024,6,1))
        students.append({"student_id": sid, "first_name": first, "last_name": last,
                         "email": email, "created_at": created})

        if count == 1:
            degree = random.choices(["Bachelor's","Master's","Doctoral"],
                                    weights=[0.70,0.25,0.05])[0]
            prog_ids = prog_by_level[degree]
            if prog_ids:
                prog_id = random.choice(prog_ids)
                create_program_enrollment(prog_id, sid, degree, enrollment_id,
                                          students, prog_enrollments, planned_subject_enrollments,
                                          prog_map, semesters, created, subjects)
                enrollment_id += 1
        elif count == 2:
            pair = random.choices([("Bachelor's","Master's"), ("Master's","Doctoral")],
                                  weights=[0.65,0.35])[0]
            for degree in pair:
                prog_ids = prog_by_level[degree]
                if prog_ids:
                    prog_id = random.choice(prog_ids)
                    create_program_enrollment(prog_id, sid, degree, enrollment_id,
                                              students, prog_enrollments, planned_subject_enrollments,
                                              prog_map, semesters, created, subjects)
                    enrollment_id += 1
        else:
            for degree in ["Bachelor's","Master's","Doctoral"]:
                prog_ids = prog_by_level[degree]
                if prog_ids:
                    prog_id = random.choice(prog_ids)
                    create_program_enrollment(prog_id, sid, degree, enrollment_id,
                                              students, prog_enrollments, planned_subject_enrollments,
                                              prog_map, semesters, created, subjects)
                    enrollment_id += 1

        student_idx += 1

    log.info(f"Generated {len(students):,} students with {len(prog_enrollments):,} program enrollments")
    log.info(f"Planned {len(planned_subject_enrollments):,} initial subject enrollments")

    # ---- 3. Subject offerings ----
    offerings = []
    off_id = 1
    for subj in subjects:
        num_sems = random.randint(3,5)
        for sem in random.sample(semesters, min(num_sems, len(semesters))):
            offerings.append({"offering_id": off_id, "subject_code": subj["subject_code"],
                              "semester_id": sem["semester_id"],
                              "coordinator_name": f"Dr. {fake.last_name()}"})
            off_id += 1
    log.info(f"Generated {len(offerings)} offerings")

    offering_lookup = {(o["subject_code"], o["semester_id"]): o["offering_id"] for o in offerings}

    # ---- 4. Assessments (generated on‑demand) ----
    assessment_id = 1
    offering_assessments = defaultdict(list)
    assessments = []

    def get_or_create_assessments_for_offering(offering_id):
        nonlocal assessment_id
        if offering_id in offering_assessments:
            return offering_assessments[offering_id]
        num = random.randint(3,6)
        titles = ["Assignment 1","Assignment 2","Midterm Exam","Final Exam","Project","Quiz 1","Quiz 2"]
        chosen_titles = random.sample(titles, min(num, len(titles)))
        weights = []
        rem = 100
        for i in range(len(chosen_titles)-1):
            w = round(random.uniform(10, rem - 10*(len(chosen_titles)-i-1)), 2)
            weights.append(w); rem -= w
        weights.append(round(rem,2))
        ass_list = []
        for title, weight in zip(chosen_titles, weights):
            max_score = random.choice([50,100,100,100,200]) if "Exam" in title else random.choice([20,50,100])
            assessments.append({"assessment_id": assessment_id, "offering_id": offering_id,
                                "title": title, "weight_percentage": weight, "max_score": max_score})
            ass_list.append({"assessment_id": assessment_id, "max_score": max_score, "weight": weight})
            assessment_id += 1
        offering_assessments[offering_id] = ass_list
        return ass_list

    # ---- 5. Generate subject enrollments with retakes ----
    semester_lookup = {sem["semester_id"]: sem for sem in semesters}

    subject_semesters = defaultdict(list)
    for off in offerings:
        subject_semesters[off["subject_code"]].append(off["semester_id"])
    for key in subject_semesters:
        subject_semesters[key].sort()

    subject_enrollments = []
    assessment_results = []
    se_id = 1

    for (pe_id, subject_code, degree, difficulty) in tqdm(planned_subject_enrollments, desc="Generating enrollments"):
        sem_list = subject_semesters.get(subject_code, [])
        if not sem_list:
            continue

        first_index = random.randint(0, len(sem_list)-1)
        first_sem = sem_list[first_index]

        # First attempt
        create_attempt(se_id, pe_id, subject_code, first_sem, degree, difficulty,
                       subject_enrollments, assessment_results, offering_assessments,
                       get_or_create_assessments_for_offering, semester_lookup, offering_lookup)
        se_id += 1

        last_se = subject_enrollments[-1]
        if last_se["final_mark"] is not None and last_se["final_mark"] >= 50:
            continue

        # Retry up to 2 more times
        attempt_count = 1
        current_index = first_index
        while attempt_count < 3:
            if current_index + 1 >= len(sem_list):
                break
            later_index = random.randint(current_index + 1, len(sem_list)-1)
            sem = sem_list[later_index]
            current_index = later_index

            create_attempt(se_id, pe_id, subject_code, sem, degree, difficulty,
                           subject_enrollments, assessment_results, offering_assessments,
                           get_or_create_assessments_for_offering, semester_lookup, offering_lookup)
            se_id += 1

            last_se = subject_enrollments[-1]
            if last_se["final_mark"] is not None and last_se["final_mark"] >= 50:
                break
            attempt_count += 1

    log.info(f"Generated {len(subject_enrollments):,} subject enrollments (including retakes)")
    log.info(f"Generated {len(assessment_results):,} assessment results")
    log.info(f"Generated {len(assessments):,} assessments")

    # ---- 6. Compute program final results ----
    prog_marks = defaultdict(list)
    for se in subject_enrollments:
        if se["status"] == "Completed" and se["final_mark"] is not None:
            prog_marks[se["program_enrollment_id"]].append(se["final_mark"])

    for pe in prog_enrollments:
        marks = prog_marks.get(pe["program_enrollment_id"], [])
        if marks:
            avg = sum(marks) / len(marks)
            if avg >= 85: result = "High Distinction"
            elif avg >= 75: result = "Distinction"
            elif avg >= 65: result = "Merit"
            else: result = "Pass"
            pe["final_degree_result"] = result

    # ---- 7. Insert into DB ----
    if DRY_RUN:
        log.info("Writing SQL to load_data.sql ...")
        with open("load_data.sql", "w") as f:
            f.write("BEGIN;\n")
            for table, rows in [("programs", programs), ("subjects", subjects),
                                ("semesters", semesters), ("program_subjects", program_subjects),
                                ("students", students), ("program_enrollments", prog_enrollments),
                                ("subject_offerings", offerings), ("assessments", assessments),
                                ("subject_enrollments", subject_enrollments),
                                ("assessment_results", assessment_results)]:
                if not rows: continue
                cols = list(rows[0].keys())
                for row in rows:
                    vals = []
                    for c in cols:
                        v = row.get(c)
                        if v is None: vals.append("NULL")
                        elif isinstance(v, str):
                            escaped = v.replace("'", "''")
                            vals.append(f"'{escaped}'")
                        elif isinstance(v, (datetime,)): vals.append(f"'{v.isoformat()}'")
                        else: vals.append(str(v))
                    f.write(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(vals)});\n")
            f.write("COMMIT;\n")
    else:
        log.info("Inserting data into database...")
        conn.autocommit = False
        cursor = conn.cursor()

        def insert_batch(table, rows, cols):
            if not rows: return
            sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})"
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i+BATCH_SIZE]
                data = [[r.get(c) for c in cols] for r in batch]
                psycopg2.extras.execute_batch(cursor, sql, data)
                conn.commit()

        insert_batch("programs", programs, ["program_id","program_name","department","degree_level","total_credit_points_required"])
        # ── FIX: exclude 'difficulty' column ──
        insert_batch("subjects", subjects, ["subject_code","subject_title","credit_points"])
        insert_batch("semesters", semesters, ["semester_id","semester_name","academic_year","start_date","end_date"])
        insert_batch("program_subjects", program_subjects, ["program_id","subject_code","subject_type","recommended_semester"])
        insert_batch("students", students, ["student_id","first_name","last_name","email","created_at"])
        insert_batch("program_enrollments", prog_enrollments, ["program_enrollment_id","student_id","program_id",
                                                               "enrollment_date","completion_date","status","final_degree_result"])
        insert_batch("subject_offerings", offerings, ["offering_id","subject_code","semester_id","coordinator_name"])
        insert_batch("assessments", assessments, ["assessment_id","offering_id","title","weight_percentage","max_score"])
        insert_batch("subject_enrollments", subject_enrollments, ["subject_enrollment_id","program_enrollment_id",
                                                                  "offering_id","status","final_mark","final_grade"])
        insert_batch("assessment_results", assessment_results, ["subject_enrollment_id","assessment_id","raw_score","submitted_at"])

        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM subject_enrollments")
        count_se = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM assessment_results")
        count_ar = cur.fetchone()[0]
        log.info(f"Final counts: subject_enrollments = {count_se:,}, assessment_results = {count_ar:,}")
        conn.close()

    log.info("Data loading complete.")

if __name__ == "__main__":
    main()