"""Execute SQL against PostgreSQL using PG_CON."""

import psycopg
from typing import Any


def test_connection(pg_con: str) -> dict[str, Any]:
    """
    Test database connection.
    
    Args:
        pg_con: PostgreSQL connection string
        
    Returns:
        Dict with connection info or error
    """
    try:
        with psycopg.connect(pg_con) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version(), current_database()")
                version, database = cur.fetchone()
                
                return {
                    "success": True,
                    "database": database,
                    "server_version": version.split(",")[0],
                }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def execute_sql(pg_con: str, sql: str) -> dict[str, Any]:
    """
    Execute SQL statements against the database.
    
    Args:
        pg_con: PostgreSQL connection string
        sql: SQL to execute (may contain multiple statements)
        
    Returns:
        Dict with execution results
    """
    try:
        with psycopg.connect(pg_con) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows_affected = cur.rowcount
                
            conn.commit()
            
            return {
                "success": True,
                "rows_affected": rows_affected,
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "rows_affected": 0,
        }


def execute_sql_returning(pg_con: str, sql: str) -> dict[str, Any]:
    """
    Execute SQL and return results (for SELECT queries).
    
    Args:
        pg_con: PostgreSQL connection string
        sql: SQL to execute
        
    Returns:
        Dict with query results
    """
    try:
        with psycopg.connect(pg_con) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                    return {
                        "success": True,
                        "columns": columns,
                        "rows": rows,
                    }
                else:
                    return {
                        "success": True,
                        "rows_affected": cur.rowcount,
                    }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
