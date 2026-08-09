import atexit
import os

from dotenv import load_dotenv
from testcontainers.community.postgres import PostgresContainer

load_dotenv()

_postgres_container = PostgresContainer("postgres:16")
_postgres_container.start()
os.environ["DATABASE_URL"] = _postgres_container.get_connection_url(driver=None)
atexit.register(_postgres_container.stop)
