FROM apache/airflow:3.3.0

USER airflow
RUN pip install --no-cache-dir \
    dbt-duckdb==1.10.1 \
    duckdb==1.5.5 \
    psycopg2-binary \
    python-dotenv
