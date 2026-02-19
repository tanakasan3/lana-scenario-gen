"""Execute SQL against PostgreSQL database."""

import os
from pathlib import Path

import psycopg
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def get_connection_string() -> str:
    """Get PostgreSQL connection string from environment."""
    pg_con = os.environ.get("PG_CON")
    
    if not pg_con:
        raise EnvironmentError(
            "PG_CON environment variable not set.\n"
            "Set it to a PostgreSQL connection string, e.g.:\n"
            "  export PG_CON='postgresql://user:pass@localhost:5432/lana'"
        )
    
    return pg_con


def test_connection() -> bool:
    """Test database connection."""
    try:
        conn_str = get_connection_string()
        with psycopg.connect(conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception as e:
        console.print(f"[red]Connection failed:[/red] {e}")
        return False


def run_sql(sql_path: str | Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Execute SQL file against PostgreSQL database.
    
    Args:
        sql_path: Path to SQL file
        dry_run: If True, print SQL without executing
        
    Returns:
        Tuple of (success_count, error_count)
    """
    sql_path = Path(sql_path)
    
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")
    
    sql_content = sql_path.read_text()
    
    if dry_run:
        console.print("[yellow]Dry run - SQL not executed:[/yellow]")
        console.print(sql_content)
        return (0, 0)
    
    conn_str = get_connection_string()
    
    success_count = 0
    error_count = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Executing SQL...", total=None)
        
        try:
            with psycopg.connect(conn_str) as conn:
                with conn.cursor() as cur:
                    # Execute the entire SQL file as one transaction
                    # (it should already have BEGIN/COMMIT)
                    cur.execute(sql_content)
                    success_count = cur.rowcount if cur.rowcount > 0 else 1
                    
                conn.commit()
                progress.update(task, description="[green]SQL executed successfully[/green]")
                
        except psycopg.Error as e:
            error_count = 1
            progress.update(task, description=f"[red]SQL execution failed[/red]")
            console.print(f"[red]Error:[/red] {e}")
            
            # Try to show which statement failed
            if hasattr(e, 'diag') and e.diag:
                if e.diag.message_primary:
                    console.print(f"[red]Message:[/red] {e.diag.message_primary}")
                if e.diag.context:
                    console.print(f"[red]Context:[/red] {e.diag.context}")
    
    return (success_count, error_count)


def run_sql_statements(statements: list[str], dry_run: bool = False) -> tuple[int, int]:
    """
    Execute a list of SQL statements.
    
    Args:
        statements: List of SQL statements
        dry_run: If True, print SQL without executing
        
    Returns:
        Tuple of (success_count, error_count)
    """
    sql_content = "\n".join(statements)
    
    if dry_run:
        console.print("[yellow]Dry run - SQL not executed:[/yellow]")
        console.print(sql_content)
        return (0, 0)
    
    conn_str = get_connection_string()
    
    success_count = 0
    error_count = 0
    
    try:
        with psycopg.connect(conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_content)
                success_count = 1
            conn.commit()
            console.print("[green]✓ SQL executed successfully[/green]")
            
    except psycopg.Error as e:
        error_count = 1
        console.print(f"[red]Error executing SQL:[/red] {e}")
    
    return (success_count, error_count)
