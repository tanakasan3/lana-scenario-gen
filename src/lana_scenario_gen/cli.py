"""CLI for lana-scenario-gen."""

import click
import json
from pathlib import Path

from .parser.rust_parser import parse_lana_events


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
    if output:
        schema.save(output)
        click.echo(f"\nSchema saved to: {output}")
    
    if verbose:
        click.echo("\n=== Full Schema ===")
        click.echo(json.dumps(schema.to_dict(), indent=2))


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
