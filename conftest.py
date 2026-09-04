import atexit
import os

import psycopg
import pytest
from dotenv import load_dotenv
from testcontainers.community.postgres import PostgresContainer

load_dotenv()

_postgres_container = PostgresContainer("postgres:16")
_postgres_container.start()
os.environ["DATABASE_URL"] = _postgres_container.get_connection_url(driver=None)
atexit.register(_postgres_container.stop)


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    from data.db import get_connection

    with get_connection() as conn:
        try:
            conn.execute("TRUNCATE users CASCADE")
            conn.commit()
        except psycopg.errors.UndefinedTable:
            conn.rollback()
