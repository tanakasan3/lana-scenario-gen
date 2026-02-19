"""CLI for lana-scenario-gen."""

import click
import json
import os
from pathlib import Path

from .parser.rust_parser import parse_lana_events


# Cache schema in memory during session
_schema_cache = {}


def get_schema(lana_bank_path: str | None = None):
    """Get or parse schema, with caching."""
    from .parser.schema import EventSchema
    
    # Default path
    if not lana_bank_path:
        lana_bank_path = os.environ.get("LANA_BANK_PATH", os.path.expanduser("~/source/repos/lana-bank"))
    
    cache_path = Path("output/schema.json")
    
    # Check cache
    if str(lana_bank_path) in _schema_cache:
        return _schema_cache[str(lana_bank_path)]
    
    # Check file cache
    if cache_path.exists():
        schema = EventSchema.load(str(cache_path))
        _schema_cache[str(lana_bank_path)] = schema
        return schema
    
    # Parse fresh
    schema = parse_lana_events(lana_bank_path)
    
    # Save to cache
    cache_path.parent.mkdir(exist_ok=True)
    schema.save(str(cache_path))
    _schema_cache[str(lana_bank_path)] = schema
    
    return schema


@click.group()
def cli():
    """Lana Scenario Generator - Generate test SQL for lana-bank events."""
    pass


@cli.command()
@click.argument("lana_bank_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output path for schema.json")
@click.option("--show-type", "-t", multiple=True, help="Show resolved structure for specific type(s)")
@click.option("--show-event", "-e", help="Show specific event enum with resolved fields")
@click.option("--verbose", "-v", is_flag=True, help="Show full schema output")
def parse(lana_bank_path: str, output: str | None, show_type: tuple, show_event: str | None, verbose: bool):
    """Parse event definitions from lana-bank codebase."""
    
    click.echo(f"Parsing events from: {lana_bank_path}")
    
    schema = parse_lana_events(lana_bank_path)
    
    click.echo(f"Found {len(schema.events)} event enums")
    click.echo(f"Found {len(schema.type_registry.types)} type definitions")
    
    # Show specific types if requested
    for type_name in show_type:
        click.echo(f"\n=== Type: {type_name} ===")
        resolved = schema.type_registry.resolve(type_name)
        click.echo(json.dumps(resolved.to_dict(), indent=2))
    
    # Show specific event if requested
    if show_event:
        if show_event in schema.events:
            event = schema.events[show_event]
            click.echo(f"\n=== Event: {show_event} ===")
            click.echo(f"Table: {event.table_name}")
            click.echo(f"Source: {event.source_file}")
            for variant in event.variants:
                click.echo(f"\n  Variant: {variant.name}")
                for field in variant.fields:
                    resolved_info = ""
                    if field.resolved_type:
                        resolved_info = f" -> {field.resolved_type.kind}"
                        if field.resolved_type.kind == "struct" and field.resolved_type.fields:
                            resolved_info += f" ({len(field.resolved_type.fields)} fields)"
                    click.echo(f"    - {field.name}: {field.rust_type} [{field.category.value}]{resolved_info}")
        else:
            click.echo(f"Event not found: {show_event}")
            click.echo(f"Available: {', '.join(sorted(schema.events.keys()))}")
    
    # List all events
    if not show_type and not show_event:
        click.echo("\nEvents:")
        for name, event in sorted(schema.events.items()):
            variant_count = len(event.variants)
            click.echo(f"  {name}: {variant_count} variants -> {event.table_name}")
    
    # Save output
    output_path = output or "output/schema.json"
    Path(output_path).parent.mkdir(exist_ok=True)
    schema.save(output_path)
    click.echo(f"\nSchema saved to: {output_path}")
    
    if verbose:
        click.echo("\n=== Full Schema ===")
        click.echo(json.dumps(schema.to_dict(), indent=2))


@cli.command("list-events")
@click.option("--lana-bank", "-l", type=click.Path(exists=True), help="Path to lana-bank")
def list_events(lana_bank: str | None):
    """List all available events and their variants."""
    schema = get_schema(lana_bank)
    
    click.echo(f"Found {len(schema.events)} event enums:\n")
    
    for name, event in sorted(schema.events.items()):
        click.echo(f"📋 {name}")
        click.echo(f"   Table: {event.table_name}")
        click.echo(f"   Variants: {', '.join(v.name for v in event.variants)}")
        click.echo()


@cli.command()
@click.argument("scenario_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output SQL file path")
@click.option("--lana-bank", "-l", type=click.Path(exists=True), help="Path to lana-bank")
def generate(scenario_path: str, output: str | None, lana_bank: str | None):
    """Generate SQL INSERT statements from a scenario YAML file."""
    import yaml
    from .generator.sql_generator import generate_sql
    
    schema = get_schema(lana_bank)
    
    # Load scenario
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)
    
    click.echo(f"Generating SQL from: {scenario_path}")
    
    # Generate SQL
    sql_statements = generate_sql(schema, scenario)
    
    # Output
    output_path = output or f"output/{Path(scenario_path).stem}.sql"
    Path(output_path).parent.mkdir(exist_ok=True)
    
    with open(output_path, "w") as f:
        f.write(sql_statements)
    
    click.echo(f"Generated {sql_statements.count('INSERT')} INSERT statements")
    click.echo(f"SQL saved to: {output_path}")


@cli.command()
@click.argument("scenario_path", type=click.Path(exists=True))
@click.option("--lana-bank", "-l", type=click.Path(exists=True), help="Path to lana-bank")
@click.option("--dry-run", is_flag=True, help="Generate SQL but don't execute")
def apply(scenario_path: str, lana_bank: str | None, dry_run: bool):
    """Generate and execute SQL from a scenario YAML file."""
    import yaml
    from .generator.sql_generator import generate_sql
    from .runner.pg_runner import execute_sql
    
    pg_con = os.environ.get("PG_CON")
    if not pg_con:
        raise click.ClickException("PG_CON environment variable not set")
    
    schema = get_schema(lana_bank)
    
    # Load scenario
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)
    
    click.echo(f"Generating SQL from: {scenario_path}")
    
    # Generate SQL
    sql_statements = generate_sql(schema, scenario)
    
    insert_count = sql_statements.count("INSERT")
    click.echo(f"Generated {insert_count} INSERT statements")
    
    if dry_run:
        click.echo("\n--- DRY RUN (SQL not executed) ---")
        click.echo(sql_statements)
        return
    
    # Execute
    click.echo(f"Executing against database...")
    result = execute_sql(pg_con, sql_statements)
    click.echo(f"✓ Applied {result['rows_affected']} rows")


@cli.command("test-db")
def test_db():
    """Test database connection using PG_CON environment variable."""
    from .runner.pg_runner import test_connection
    
    pg_con = os.environ.get("PG_CON")
    if not pg_con:
        raise click.ClickException("PG_CON environment variable not set")
    
    click.echo("Testing database connection...")
    
    result = test_connection(pg_con)
    
    if result["success"]:
        click.echo(f"✓ Connected to: {result['database']}")
        click.echo(f"  Server: {result['server_version']}")
    else:
        raise click.ClickException(f"Connection failed: {result['error']}")


@cli.command()
@click.argument("schema_path", type=click.Path(exists=True))
@click.argument("type_name")
def inspect_type(schema_path: str, type_name: str):
    """Inspect a resolved type from a schema file."""
    from .parser.schema import EventSchema
    
    schema = EventSchema.load(schema_path)
    
    if type_name not in schema.type_registry.types:
        click.echo(f"Type not found: {type_name}")
        click.echo(f"Available types (first 50):")
        for name in sorted(schema.type_registry.types.keys())[:50]:
            click.echo(f"  {name}")
        return
    
    resolved = schema.type_registry.resolve(type_name)
    click.echo(json.dumps(resolved.to_dict(), indent=2))


@cli.command()
@click.argument("schema_path", type=click.Path(exists=True))
@click.argument("event_name")
@click.argument("variant_name")
def inputs(schema_path: str, event_name: str, variant_name: str):
    """Show scenario inputs for an event variant."""
    from .parser.schema import EventSchema
    
    schema = EventSchema.load(schema_path)
    
    if event_name not in schema.events:
        click.echo(f"Event not found: {event_name}")
        return
    
    event = schema.events[event_name]
    variant = next((v for v in event.variants if v.name == variant_name), None)
    
    if not variant:
        click.echo(f"Variant not found: {variant_name}")
        click.echo(f"Available: {', '.join(v.name for v in event.variants)}")
        return
    
    click.echo(f"Scenario inputs for {event_name}::{variant_name}:\n")
    
    for field in variant.fields:
        is_input = field.is_scenario_input()
        marker = "📝" if is_input else "🔧"
        click.echo(f"{marker} {field.name}: {field.rust_type} [{field.category.value}]")
        
        if field.resolved_type and field.resolved_type.kind == "struct":
            for sub_input in field.resolved_type.get_scenario_inputs(field.name):
                click.echo(f"     └─ {sub_input['path']}: {sub_input['type']}")


def main():
    cli()


if __name__ == "__main__":
    main()
