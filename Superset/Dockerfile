FROM apache/superset:latest

USER root
RUN /app/.venv/bin/python -m ensurepip --upgrade && \
    /app/.venv/bin/python -m pip install duckdb-engine psycopg2-binary

USER superset
