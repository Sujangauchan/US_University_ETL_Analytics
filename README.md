# US University ELT Analytics Platform

An end-to-end data platform that moves university enrollment, assessment, and program data from a transactional source system into an analytics-ready warehouse, with full historical tracking, automated data quality validation, and orchestrated scheduling.

> **Naming note**: this repository is named `US_University_ETL_Analytics` for historical reasons, but the pipeline is **ELT**, not ETL. Raw data is loaded before any transformation occurs. Repository rename pending.

## Architecture

- **OLTP (Postgres)**: transactional source system
- **Datalake (DuckDB, `raw_landed` schema)**: raw data landed as-is, before transformation (Bronze)
- **dbt snapshot**: SCD Type 2 history on `programs`
- **dbt run**: `staging` (views) to `warehouse` (galaxy/fact constellation schema, Silver) to `obt` (denormalized, dashboard-ready, Gold)
- **dbt test**: 100 automated data quality tests
- **Superset**: read-only dashboards on the `obt` schema
- **Orchestration**: Apache Airflow (LocalExecutor), all of the above as one DAG

Two separate execution environments:
- Airflow, its metadata database, and dbt run inside Docker containers (Docker Compose)
- OLTP Postgres runs on the host, reached from containers via `host.docker.internal`
- Mirrors a realistic deployment boundary: owned infrastructure vs. an external source system

![Architecture diagram](Docs/architecture.png)

```
                        ┌──────────────────┐
                        │   OLTP Source    │
                        │   (PostgreSQL)   │
                        └──────────────────┘
                                  │
                                  ▼
   ┌────────────────────────────────────────────────────────────┐
   │            DATALAKE LAYER  (raw_landed, DuckDB)            │
   │           [ BRONZE, raw, as-landed, unrefined ]             │
   │                                                            │
   │    ┌──────────────────────┐    ┌──────────────────────┐    │
   │    │      Dimensions      │    │        Facts         │    │
   │    │    (full reload)     │    │    (incremental,     │    │
   │    │                      │    │     watermarked)     │    │
   │    └──────────────────────┘    └──────────────────────┘    │
   │                                                            │
   └────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                        STAGING LAYER                         │
  │               [ SILVER, cleaned, conformed ]                 │
  │                                                              │
  │  ┌────────────────────────────────────────────────────────┐  │
  │  │ Lightly cleaned views, one per source table            │  │
  │  └────────────────────────────────────────────────────────┘  │
  └──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                       WAREHOUSE LAYER                        │
  │               [ SILVER, cleaned, conformed ]                 │
  │                                                              │
  │  ┌────────────────────────────────────────────────────────┐  │
  │  │ SCD Type 2 snapshot on programs (dbt snapshot)         │  │
  │  │ galaxy/fact constellation: 7 dimension + 3 fact tables │  │
  │  │ 3 incremental facts (new/changed rows only)            │  │
  │  └────────────────────────────────────────────────────────┘  │
  └──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
            ┌──────────────────────────────────────────┐
            │                 dbt test                 │
            │    100 automated data quality checks     │
            └──────────────────────────────────────────┘
                                  │
                                  ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                          OBT LAYER                           │
  │         [ GOLD, business-ready, consumption-ready ]          │
  │                                                              │
  │  ┌────────────────────────────────────────────────────────┐  │
  │  │ Wide, denormalized tables                              │  │
  │  │ One row per business entity                            │  │
  │  │ No joins needed at query time                          │  │
  │  │ Built for direct Superset consumption                  │  │
  │  └────────────────────────────────────────────────────────┘  │
  └──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                     ┌────────────────────────┐
                     │        Superset        │
                     │ (read-only dashboards) │
                     └────────────────────────┘
```

Orchestrated end to end by Apache Airflow: `ingest_oltp_to_datalake >> dbt_snapshot >> dbt_run >> dbt_test`.

## Demo video

A short screen recording of a full pipeline run, start to finish: Airflow triggering the DAG, the raw load landing in DuckDB, the dbt snapshot capturing an SCD Type 2 change on `programs`, and the resulting history showing up as new `dbt_valid_from` / `dbt_valid_to` rows.

https://github.com/user-attachments/assets/d06e6fa1-285b-409c-9dac-24b596ea4acf

## Dashboards

Built on the `obt` schema, refreshed by the pipeline above.

### Overall dashboards

**Active enrollment summary**
![Active enrollment summary](Docs/Active%20enrollment%20summary.png)
*[Insight: e.g., total active enrollment count, breakdown by status]*

**Program graduation trends**
![Program graduations trend](Docs/Program%20graduations%20trend.png)
*[Insight: trend direction over time, any visible effect from demo data updates]*

### Individual insights

Drill-downs from the summary dashboard, isolating one dimension at a time.

**Active enrollment by department**
![Active enrollment by department](Docs/Active%20enrollment%20by%20department.png)

Law carries the largest active cohort by a wide margin (4,171 on track, 1,378 at risk), more than any other department's total enrollment. On raw at-risk rate rather than headcount, Education is actually the most exposed department at roughly 30% at risk, followed by Law at 25%. Medicine is the most stable at just under 18%.

**Active enrollment by program level**
![Active enrollment by program level](Docs/Active%20enrollment%20by%20program%20level.png)

At-risk rate rises sharply as program level becomes more foundational: Doctoral students sit at about 4% at risk, Master's at 14%, and Bachelor's at nearly 36%. Bachelor's also carries the largest total active population by far, so this is where academic-standing interventions would have the most impact in absolute terms.

**Active enrollment by graduation month**
![Active enrollment by graduation month](Docs/Active%20enrollment%20by%20graduation%20month.png)

The distribution of expected graduation dates is bimodal rather than a single smooth curve: an earlier peak around 2026 and a larger, later peak around 2028, before tapering toward zero by 2030. This shape reflects overlapping program durations across degree levels (shorter Master's/Bachelor's completions clustering earlier, longer-running cohorts pushing the second, larger peak outward), rather than a single uniform cohort progressing together. This also presents opportunity for staff engagements in additional promotional events and engagements such as workshops, hackathon during low graduation period.

## Data lineage

Generated lineage diagrams showing how each OBT table traces back through the warehouse and staging layers to its raw sources.

**Program summary lineage**
![Program summary lineage](Docs/Program%20summary%20lineage.png)

**Assessment result lineage**
![Assessment result lineage](Docs/Assessment%20Result%20Lineage.png)

## Data mapping

Complete field-level mapping for every transition (OLTP to datalake to staging to warehouse to OBT), including source/target columns, data types, and calculated-metric definitions.

- Full mapping (read-only): [Google Sheet](https://docs.google.com/spreadsheets/d/1KNtPWFwnuou4snxDgdEr0M5RlZUQlSyc4-milvOgtno/edit?usp=sharing)
- Offline copy: `Docs/Data_Mapping_Sheet_US_ELT_ANALYTICS.xlsx`

## Why ELT

- Raw data lands in `raw_landed` untouched, before any transformation
- Transformation happens afterward, in-warehouse, via dbt SQL, not embedded in extraction code
- Benefits:
  - Raw layer preserves an unmodified source copy. Any downstream model can be rebuilt from it without re-querying the source
  - Transformation logic is version-controlled and testable through dbt

## Data flow

**Extraction and loading** (`Datalake/ingestion.py`)
- Dimension tables (`programs`, `subjects`, `semesters`, `students`, etc.): full reload every run
- Fact tables (`program_enrollments`, `subject_enrollments`, `assessment_results`): incremental, watermarked on `updated_at`, 10-minute lookback for late-committing transactions
- Raw fact layer is an append-only journal (every landed version kept), not formal SCD2, since there are no explicit validity boundaries. That curation happens deliberately at the snapshot step

**History capture**
- `programs` snapshotted via dbt's native SCD Type 2 snapshot functionality
- Every attribute change preserved as a new row (`dbt_valid_from` / `dbt_valid_to`)

**Transformation**: three schemas, increasing refinement
- `staging`: lightly cleaned views, one per source table
- `warehouse`: dimension and fact tables, galaxy/fact constellation schema. Three fact tables share conformed dimensions (`dim_student`, `dim_program`, etc.). Three incremental fact tables reprocess only new/changed rows
- `obt`: wide, denormalized tables built for direct Superset consumption, no joins at query time

**Validation**
- 100 automated tests: not-null, accepted values, uniqueness, referential integrity, numeric range checks

**Presentation**
- Superset connects read-only, never contends with the pipeline for a write lock
- Dashboards built directly on `obt`

## Engineering decisions

- **Surrogate keys via `hash(natural_id)`, not the natural key itself.** Source natural keys are inconsistent types (`program_id`/`student_id` are strings, `program_enrollment_id` is an integer). Hashing every key down to a uniform `UBIGINT` makes every warehouse join an integer comparison instead of a mix of string and integer comparisons, faster at query time, and it decouples the warehouse's join keys from whatever format the source system happens to use. Tradeoff worth naming: `hash()` isn't collision-proof the way a database sequence is, though at this data volume the risk is negligible.
- **`staging` materializes as views; `warehouse`/`obt` materialize as tables.** Staging is a thin, cheap passthrough with no reason to persist to disk. Warehouse and OBT are queried repeatedly by Superset, so they're physically materialized rather than recomputed on every dashboard refresh.
- **Incremental strategy is `delete+insert`, not `merge`.** DuckDB is a columnar engine, not optimized for row-level `UPDATE`/`MERGE` the way an OLTP row-store is. Deleting and reinserting the changed partition fits how DuckDB actually executes efficiently.
- **OBT is deliberately denormalized**, trading storage and duplication for zero joins at BI query time, the opposite tradeoff from the warehouse layer, made specifically because the consumption layer's job is fast dashboard reads, not storage efficiency.

## Orchestration

Single Airflow DAG (`Airflow/dags/university_etl_pipeline.py`), four tasks, strict order:

```
ingest_oltp_to_datalake >> dbt_snapshot >> dbt_run >> dbt_test
```

- Each task runs the same commands used for local development. Airflow behavior matches manual runs
- `max_active_runs=1`: prevents overlapping runs from contending for the DuckDB write lock (a real collision found and fixed during development)
- Retries once after a 2-minute delay on failure
- Exhausted retries write a structured failure entry to the task log (`on_failure_callback`), a hook point for future email/Slack alerting
- Airflow containers run with `TZ` explicitly set to match the OLTP host's timezone. A real bug surfaced during development where a container/host clock mismatch caused `updated_at` watermarks to appear ahead of the container's own clock, silently halting incremental loads

## Concurrency

DuckDB allows exactly one writer at a time, unlimited concurrent readers.

- Superset's connection is explicitly `read_only: true`, never competes with the pipeline for the write lock
- Any other tool inspecting the warehouse file directly (e.g., a database client) should connect read-only, especially while a pipeline run may be active

## Repository structure

```
US_University_ETL_Analytics/
├── OLTP/                    Source database schema and data generation
│   ├── prod_oltp_db.sql
│   ├── data_loader.py       Synthetic dataset generator (~577k subject
│   │                        enrollments, ~2.6M assessment results, with
│   │                        realistic retake and multi-program patterns)
│   └── Incremental_program_enrollment.py
│                            Small supplemental changes, for demonstrating
│                            incremental loads and SCD2 history
├── Datalake/
│   └── ingestion.py         OLTP -> DuckDB raw_landed extraction
├── Warehouse/                dbt project
│   ├── models/
│   │   ├── staging/
│   │   ├── warehouse/
│   │   └── obt/
│   ├── snapshots/
│   ├── tests/
│   └── docker_profiles/     Container-specific dbt profile
├── Storage/
│   └── warehouse.duckdb      Single-file analytical database
├── Airflow/
│   └── dags/
│       └── university_etl_pipeline.py
├── Superset/
│   └── Dockerfile
└── docker-compose.yaml
```

## Running the platform

Bring up the full stack:
```
docker compose up -d
```
- Starts Airflow (metadata DB, scheduler, DAG processor, API server) and Superset
- First run builds Airflow with `dbt-duckdb`, `duckdb`, `psycopg2-binary`; Superset with `duckdb-engine`, `psycopg2-binary`

Trigger a pipeline run, UI at `localhost:8080`, or:
```
docker exec -it airflow-scheduler airflow dags trigger university_etl_pipeline
```

Generate a small set of incremental changes for demonstration (run on host, OLTP at `localhost`):
```
cd OLTP
python Incremental_program_enrollment.py
```
Renames one program, graduates one enrollment, adjusts one mark and one assessment score, and inserts a new semester with new students, offerings, and enrollments, all in one transaction.

## Known limitations and future enhancements

**Scheduling and alerting**
- `@daily` schedule not yet validated against a production cadence
- Failure alerting limited to structured log entries. The `on_failure_callback` hook is in place; wiring it to email or Slack is the natural next step
- No SLA monitoring (e.g., alerting if a run takes meaningfully longer than usual)

**Naming and structure**
- Repository and DAG naming still reflect the earlier ETL framing. Rename pending, separate from pipeline logic

**Data and testing**
- Demonstration data (`Incremental_program_enrollment.py`) simulates mid-cycle changes to existing records rather than a genuine new-semester intake with current-dated enrollments. A true intake scenario (new semester, new students, new offerings, all dated to the present) would exercise the same incremental and SCD2 mechanisms with more realistic data
- Test coverage validates structure and constraints well. No tests currently check for data drift or unexpected volume changes between runs

**Operations**
- Credentials are managed via a plaintext `.env` file. A secrets manager (e.g., Docker secrets, AWS Secrets Manager) would be a more production-appropriate approach
- Single DuckDB file caps write concurrency at one writer. A team scaling beyond a single pipeline and a handful of read-only consumers would eventually outgrow this and need a client-server warehouse
- No CI: dbt tests and model compilation are not currently run automatically on pull requests

**Documentation and lineage**
- No generated dbt docs / lineage graph yet. `dbt docs generate` would produce an interactive, browsable version of the field-level mapping currently maintained by hand

https://github.com/user-attachments/assets/ad492b9f-da52-4946-98d2-e15543f970f4

