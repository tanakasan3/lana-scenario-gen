"""CLI for Lana Scenario Generator."""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .parser import parse_lana_events, EventSchema
from .generator import generate_sql
from .runner import run_sql, test_connection
from .docs import generate_docs
from .docs.doc_generator import generate_scenario_template

console = Console()


@click.group()
@click.version_option(version=__version__)
def main():
    """Lana Scenario Generator - Generate SQL event data from scenario definitions."""
    pass


@main.command()
@click.argument("lana_bank_path", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default="output/schema.json",
              help="Output path for schema JSON")
@click.option("--docs", type=click.Path(path_type=Path), default="output/EVENTS.md",
              help="Output path for documentation")
@click.option("--template", type=click.Path(path_type=Path), default="output/scenario_template.yml",
              help="Output path for scenario template")
def parse(lana_bank_path: Path, output: Path, docs: Path, template: Path):
    """
    Parse event definitions from lana-bank repository.
    
    LANA_BANK_PATH: Path to lana-bank repository root
    """
    console.print(f"[blue]Parsing events from:[/blue] {lana_bank_path}")
    
    schema = parse_lana_events(lana_bank_path)
    
    # Save schema
    output.parent.mkdir(parents=True, exist_ok=True)
    schema.save(str(output))
    console.print(f"[green]✓[/green] Schema saved to: {output}")
    
    # Generate documentation
    generate_docs(schema, docs)
    console.print(f"[green]✓[/green] Documentation saved to: {docs}")
    
    # Generate scenario template
    generate_scenario_template(schema, template)
    console.print(f"[green]✓[/green] Scenario template saved to: {template}")
    
    # Print summary
    table = Table(title="Parsed Events Summary")
    table.add_column("Event Type", style="cyan")
    table.add_column("Table", style="green")
    table.add_column("Variants", justify="right")
    table.add_column("Source", style="dim")
    
    for name, event in sorted(schema.events.items()):
        table.add_row(
            name,
            event.table_name,
            str(len(event.variants)),
            event.source_file[:40] + "..." if len(event.source_file) > 40 else event.source_file,
        )
    
    console.print(table)
    console.print(f"\n[green]Total:[/green] {len(schema.events)} event types")


@main.command()
@click.argument("scenario_path", type=click.Path(exists=True, path_type=Path))
@click.option("-s", "--schema", "schema_path", type=click.Path(exists=True, path_type=Path),
              default="output/schema.json", help="Path to schema JSON")
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None,
              help="Output SQL file (default: output/<scenario_name>.sql)")
@click.option("--dry-run", is_flag=True, help="Print SQL without writing file")
def generate(scenario_path: Path, schema_path: Path, output: Path | None, dry_run: bool):
    """
    Generate SQL from a scenario definition.
    
    SCENARIO_PATH: Path to scenario YAML file
    """
    console.print(f"[blue]Loading schema from:[/blue] {schema_path}")
    schema = EventSchema.load(str(schema_path))
    
    console.print(f"[blue]Processing scenario:[/blue] {scenario_path}")
    
    if output is None:
        output = Path("output") / f"{scenario_path.stem}.sql"
    
    statements = generate_sql(schema, scenario_path, output)
    
    if dry_run:
        console.print("\n[yellow]Generated SQL:[/yellow]")
        console.print("\n".join(statements))
    else:
        console.print(f"[green]✓[/green] SQL written to: {output}")
        console.print(f"[dim]  {len(statements)} lines[/dim]")


@main.command()
@click.argument("sql_path", type=click.Path(exists=True, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Print SQL without executing")
def run(sql_path: Path, dry_run: bool):
    """
    Execute SQL file against PostgreSQL database.
    
    Requires PG_CON environment variable to be set.
    
    SQL_PATH: Path to SQL file to execute
    """
    if not dry_run:
        console.print("[blue]Testing database connection...[/blue]")
        if not test_connection():
            raise click.Abort()
        console.print("[green]✓[/green] Connected to database")
    
    console.print(f"[blue]Executing:[/blue] {sql_path}")
    success, errors = run_sql(sql_path, dry_run=dry_run)
    
    if errors > 0:
        console.print(f"[red]✗[/red] Execution failed with {errors} error(s)")
        raise SystemExit(1)
    else:
        console.print(f"[green]✓[/green] Execution complete")


@main.command()
@click.argument("scenario_path", type=click.Path(exists=True, path_type=Path))
@click.option("-s", "--schema", "schema_path", type=click.Path(exists=True, path_type=Path),
              default="output/schema.json", help="Path to schema JSON")
@click.option("--dry-run", is_flag=True, help="Generate and print SQL without executing")
def apply(scenario_path: Path, schema_path: Path, dry_run: bool):
    """
    Generate SQL from scenario and execute it (combines generate + run).
    
    Requires PG_CON environment variable to be set.
    
    SCENARIO_PATH: Path to scenario YAML file
    """
    # Load schema
    console.print(f"[blue]Loading schema from:[/blue] {schema_path}")
    schema = EventSchema.load(str(schema_path))
    
    # Generate SQL
    console.print(f"[blue]Processing scenario:[/blue] {scenario_path}")
    output = Path("output") / f"{scenario_path.stem}.sql"
    statements = generate_sql(schema, scenario_path, output)
    
    console.print(f"[green]✓[/green] Generated {len(statements)} SQL statements")
    
    if dry_run:
        console.print("\n[yellow]Dry run - SQL not executed:[/yellow]")
        console.print("\n".join(statements))
        return
    
    # Test connection
    console.print("[blue]Testing database connection...[/blue]")
    if not test_connection():
        raise click.Abort()
    
    # Execute
    console.print("[blue]Executing SQL...[/blue]")
    success, errors = run_sql(output, dry_run=False)
    
    if errors > 0:
        console.print(f"[red]✗[/red] Execution failed")
        raise SystemExit(1)
    else:
        console.print(f"[green]✓[/green] Scenario applied successfully")


@main.command()
@click.option("-s", "--schema", "schema_path", type=click.Path(exists=True, path_type=Path),
              default="output/schema.json", help="Path to schema JSON")
def list_events(schema_path: Path):
    """List all available event types from parsed schema."""
    schema = EventSchema.load(str(schema_path))
    
    for name, event in sorted(schema.events.items()):
        console.print(f"\n[cyan bold]{name}[/cyan bold] → {event.table_name}")
        for variant in event.variants:
            flow_fields = [f.name for f in variant.flow_control_fields]
            amount_fields = [f.name for f in variant.amount_fields]
            
            parts = [f"  [green]{variant.name}[/green]"]
            if flow_fields:
                parts.append(f"[blue]flow={flow_fields}[/blue]")
            if amount_fields:
                parts.append(f"[yellow]amounts={amount_fields}[/yellow]")
            
            console.print(" ".join(parts))


@main.command()
def test_db():
    """Test database connection using PG_CON environment variable."""
    console.print("[blue]Testing database connection...[/blue]")
    
    if test_connection():
        console.print("[green]✓[/green] Connection successful")
    else:
        console.print("[red]✗[/red] Connection failed")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
