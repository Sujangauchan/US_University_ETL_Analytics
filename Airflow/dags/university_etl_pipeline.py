from datetime import timedelta
import pendulum
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator
import logging

logger = logging.getLogger("airflow.task")

def log_failure(context):
    task_id = context["task_instance"].task_id
    dag_id = context["dag"].dag_id
    run_id = context["run_id"]
    exception = context.get("exception")
    logger.error(
        f"[PIPELINE FAILURE] dag={dag_id} task={task_id} run_id={run_id} "
        f"error={exception}"
    )

default_args = {
    "owner": "sujan",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "on_failure_callback": log_failure,
}

with DAG(
    dag_id="university_etl_pipeline",
    description="OLTP -> DuckDB datalake -> dbt snapshot/run/test",
    default_args=default_args,
    schedule="@daily",
    start_date=pendulum.datetime(2026, 8, 9, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["university", "etl"],
) as dag:

    ingest = BashOperator(
        task_id="ingest_oltp_to_datalake",
        bash_command="cd /opt/airflow/project/Datalake && python ingestion.py",
    )

    dbt_snapshot = BashOperator(
        task_id="dbt_snapshot",
        bash_command="cd /opt/airflow/project/Warehouse && dbt snapshot",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command="cd /opt/airflow/project/Warehouse && dbt run",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/airflow/project/Warehouse && dbt test",
    )

    ingest >> dbt_snapshot >> dbt_run >> dbt_test