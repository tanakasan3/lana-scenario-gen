"""Database runner module."""
from .pg_runner import execute_sql, test_connection

__all__ = ["execute_sql", "test_connection"]
