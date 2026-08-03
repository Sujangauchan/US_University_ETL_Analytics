CREATE DATABASE university_oltp;

-- Creating tables

-- subjects

CREATE TABLE programs (
    program_id VARCHAR(20) PRIMARY KEY,
    program_name VARCHAR(150) NOT NULL,
    department VARCHAR(100) NOT NULL,
    degree_level VARCHAR(20) NOT NULL
                                    CHECK (degree_level IN ('Associate', 'Bachelor''s', 'Master''s', 'Doctoral', 'Certificate')),
    total_credit_points_required INT NOT NULL CHECK (total_credit_points_required > 0)
);


-- subjects

CREATE TABLE subjects (
    subject_code VARCHAR(20) PRIMARY KEY,
    subject_title VARCHAR(150) NOT NULL,
    credit_points INT NOT NULL CHECK (credit_points > 0)
);


-- semesters

CREATE TABLE semesters (
    semester_id VARCHAR(20) PRIMARY KEY,
    semester_name VARCHAR(50) NOT NULL,
    academic_year INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    CONSTRAINT chk_semester_dates CHECK (end_date > start_date)
);


-- Bridge table connecting Programs with subjects
-- Resolves the many-to-many relationship between programs and
-- subjects (one subject can sit in several programs' curricula;
-- one program includes many subjects)

CREATE TABLE program_subjects (
    program_subject_id SERIAL PRIMARY KEY,
    program_id VARCHAR(20) NOT NULL REFERENCES programs(program_id) ON
    	DELETE
		CASCADE,
	subject_code VARCHAR(20) NOT NULL REFERENCES subjects(subject_code) ON
		DELETE
		CASCADE,
	subject_type VARCHAR(30) NOT NULL
                              CHECK (subject_type IN ('Core', 'Major Requirement', 'Elective', 'General Education', 'Prerequisite')),
    recommended_semester INT CHECK (recommended_semester > 0),
		UNIQUE (program_id,
		subject_code)
);


-- students

CREATE TABLE students (
    student_id VARCHAR(20) PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);



-- program_enrollments


CREATE TABLE program_enrollments (
    program_enrollment_id SERIAL PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL REFERENCES students(student_id),
    program_id VARCHAR(20) NOT NULL REFERENCES programs(program_id),
    enrollment_date DATE NOT NULL,
    completion_date DATE,
    status VARCHAR(30) NOT NULL DEFAULT 'Active'
                                  CHECK (status IN ('Active', 'Graduated', 'Withdrawn', 'Suspended', 'Dismissed', 'Leave of Absence')),
    final_degree_result VARCHAR(50),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_program_enrollment_dates CHECK (
        completion_date IS NULL
OR completion_date > enrollment_date
    )
);


-- subject_offerings

CREATE TABLE subject_offerings (
    offering_id SERIAL PRIMARY KEY,
    subject_code VARCHAR(20) NOT NULL REFERENCES subjects(subject_code),
    semester_id VARCHAR(20) NOT NULL REFERENCES semesters(semester_id),
    coordinator_name VARCHAR(100) NOT NULL,
    UNIQUE (subject_code,
semester_id)
);


-- subject_enrollments
CREATE TABLE subject_enrollments (
    subject_enrollment_id SERIAL PRIMARY KEY,
    program_enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(program_enrollment_id),
    offering_id INTEGER NOT NULL REFERENCES subject_offerings(offering_id),
    status VARCHAR(20) NOT NULL DEFAULT 'Enrolled'
                                CHECK (status IN ('Enrolled', 'Completed', 'Dropped', 'Withdrawn', 'Transferred')),
    final_mark NUMERIC(5, 2) CHECK (final_mark BETWEEN 0 AND 100),
    final_grade VARCHAR(5)
                                 CHECK (final_grade IN (
                                     'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F',
                                     'P', 'S', 'U', 'CR', 'NC', 'I', 'W'
                                 )),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (program_enrollment_id,
offering_id)
);


-- assessments

CREATE TABLE assessments (
    assessment_id SERIAL PRIMARY KEY,
    offering_id INTEGER NOT NULL REFERENCES subject_offerings(offering_id),
    title VARCHAR(100) NOT NULL,
    weight_percentage NUMERIC(5, 2) NOT NULL CHECK (weight_percentage BETWEEN 0 AND 100),
    max_score NUMERIC(5, 2) NOT NULL CHECK (max_score > 0)
);



-- assessment_results


CREATE TABLE assessment_results (
    result_id SERIAL PRIMARY KEY,
    subject_enrollment_id INTEGER NOT NULL REFERENCES subject_enrollments(subject_enrollment_id) ON
		DELETE CASCADE,
	assessment_id INTEGER NOT NULL REFERENCES assessments(assessment_id) ON
		DELETE CASCADE,
	raw_score NUMERIC(5, 2) CHECK (raw_score >= 0),
	submitted_at TIMESTAMP NOT NULL,
		UNIQUE (subject_enrollment_id,
		assessment_id)
);


-- INDEXES

-- For OLTP, building only indexes that support common transactional lookups.

CREATE INDEX idx_program_enrollments_student_status
    ON program_enrollments(student_id, status);

CREATE INDEX idx_subject_enrollments_offering_status
    ON subject_enrollments(offering_id, status);

CREATE INDEX idx_assessment_results_subject_enrollment
    ON assessment_results(subject_enrollment_id);

CREATE INDEX idx_assessment_results_assessment_id
    ON assessment_results(assessment_id);


------ Add updated_at field fillup trigger in fact tables to track changes like program status = 'graduated'so the warehouse can use incremental load  -----------------

-- updated_at function define

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- create updated_at field fillup trigger on each update

CREATE TRIGGER trg_program_enrollments_updated_at
BEFORE UPDATE ON program_enrollments
FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- Add updated_at field trigger in subject_enrollment table on each update

CREATE TRIGGER trg_subject_enrollments_updated_at
BEFORE UPDATE ON subject_enrollments
FOR EACH ROW EXECUTE FUNCTION set_updated_at();