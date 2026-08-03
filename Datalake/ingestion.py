import os
import time
import argparse
import duckdb
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).parent.resolve()
LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ingestion.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

DUCKDB_PATH = os.getenv("DUCKDB_PATH")
PG_CONN_STR = (
    f"dbname={os.getenv('PG_DBNAME')} "
    f"host={os.getenv('PG_HOST')} "
    f"port={os.getenv('PG_PORT')} "
    f"user={os.getenv('PG_USER')} "
    f"password={os.getenv('PG_PASSWORD')}"
)

DIM_TABLES = [
    "programs",
    "subjects",
    "semesters",
    "program_subjects",
    "subject_offerings",
    "assessments",
    "students",
]

# cursor_col: column used to filter/watermark. pk_col: used to dedup rows re-pulled in the lookback window.
FACT_TABLES = {
    "program_enrollments": {"cursor_col": "updated_at", "pk_col": "program_enrollment_id"},
    "subject_enrollments": {"cursor_col": "updated_at", "pk_col": "subject_enrollment_id"},
    "assessment_results":  {"cursor_col": "updated_at", "pk_col": "result_id"},
}

# Guards against missed rows from transactions that commit after their updated_at was set.
LOOKBACK_MINUTES = 10


def get_connection():
    con = duckdb.connect(DUCKDB_PATH)
    con.execute("INSTALL postgres;")
    con.execute("LOAD postgres;")
    con.execute(f"ATTACH '{PG_CONN_STR}' AS pg (TYPE postgres);")
    con.execute("CREATE SCHEMA IF NOT EXISTS raw_landed;")
    logger.info("Connected to DuckDB and attached Postgres source.")
    return con


def get_watermark(con, table, cursor_col, target):
    """Watermark = max cursor value already landed. No separate tracking table needed."""
    if not table_exists(con, table):
        return None
    return con.execute(f"SELECT max({cursor_col}) FROM {target}").fetchone()[0]


def table_exists(con, table):
    return con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='raw_landed' AND table_name=?",
        [f"raw_{table}"]
    ).fetchone() is not None


def land_table_full(con, table, target):
    source_count = con.execute(f"SELECT count(*) FROM pg.public.{table}").fetchone()[0]

    if source_count == 0 and table_exists(con, table):
        existing_count = con.execute(f"SELECT count(*) FROM {target}").fetchone()[0]
        if existing_count > 0:
            logger.warning(f"[{table}] Source returned 0 rows, {target} has {existing_count}. Skipping.")
            return

    con.execute(f"""
        CREATE OR REPLACE TABLE {target} AS
        SELECT *, current_timestamp AS _ingested_at
        FROM pg.public.{table};
    """)
    logger.info(f"[{table}] Full reload complete ({source_count} rows).")


def land_table_incremental(con, table, cursor_col, pk_col, target, force_full=False):
    watermark = None if force_full else get_watermark(con, table, cursor_col, target)

    if watermark is None:
        land_table_full(con, table, target)
        return

    lower_bound = f"TIMESTAMP '{watermark}' - INTERVAL '{LOOKBACK_MINUTES} minutes'"

    # Anti-join drops rows already landed inside the lookback window, avoiding duplicates.
    con.execute(f"""
        INSERT INTO {target}
        SELECT src.*, current_timestamp AS _ingested_at
        FROM pg.public.{table} src
        WHERE src.{cursor_col} > {lower_bound}
          AND NOT EXISTS (
              SELECT 1 FROM {target} t
              WHERE t.{pk_col} = src.{pk_col}
                AND t.{cursor_col} = src.{cursor_col}
          );
    """)

    row_count = con.execute(f"""
        SELECT count(*) FROM {target}
        WHERE _ingested_at >= current_timestamp - INTERVAL 5 SECOND;
    """).fetchone()[0]
    logger.info(f"[{table}] Incremental load: ~{row_count} new rows landed since {watermark}.")


def run_ingestion(force_full=False):
    con = get_connection()
    try:
        for table in DIM_TABLES:
            target = f"raw_landed.raw_{table}"
            t0 = time.time()
            logger.info(f"[DIM] Landing {table} -> {target}")
            land_table_full(con, table, target)
            logger.info(f"[{table}] Done in {time.time() - t0:.2f}s")

        for table, cfg in FACT_TABLES.items():
            target = f"raw_landed.raw_{table}"
            t0 = time.time()
            logger.info(f"[FACT] Landing {table} -> {target}")
            land_table_incremental(
                con, table, cfg["cursor_col"], cfg["pk_col"], target, force_full=force_full
            )
            logger.info(f"[{table}] Done in {time.time() - t0:.2f}s")

        logger.info("Ingestion completed successfully for all tables.")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise
    finally:
        con.execute("DETACH pg;")
        con.close()
        logger.info("Connection closed.")


def parse_args():
    parser = argparse.ArgumentParser(description="OLTP -> DuckDB lake ingestion")
    parser.add_argument(
        "--full-reload",
        action="store_true",
        help="Ignore stored watermarks and fully reload fact tables too (default: incremental).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_ingestion(force_full=args.full_reload)