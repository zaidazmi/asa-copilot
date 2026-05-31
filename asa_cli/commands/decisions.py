"""Decision log commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..decisions import decisions_to_markdown, find_decision, load_decisions

app = typer.Typer(help="Decision log commands")
console = Console()


@app.command("list")
def list_decisions(
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum records to show"),
    output_json: bool = typer.Option(False, "--json", help="Output records as JSON"),
):
    """List recent decision records."""
    records = load_decisions()
    records = records[-limit:] if limit > 0 else records

    if output_json:
        print(json.dumps([record.model_dump(mode="json") for record in records], indent=2))
        return

    if not records:
        console.print("[yellow]No decision records found.[/yellow]")
        return

    table = Table(title="Decision Log", show_header=True, header_style="bold magenta")
    table.add_column("ID")
    table.add_column("Created")
    table.add_column("Type")
    table.add_column("Target")
    table.add_column("Reason")

    for record in reversed(records):
        target = record.campaign_name or str(record.campaign_id or "-")
        if record.ad_group_name:
            target = f"{target} / {record.ad_group_name}"
        table.add_row(
            record.id[:8],
            record.created_at[:19],
            record.event_type,
            target[:32],
            record.reason[:72],
        )

    console.print(table)


@app.command("show")
def show_decision(
    decision_id: str = typer.Argument(..., help="Decision id or unique prefix"),
    output_json: bool = typer.Option(False, "--json", help="Output record as JSON"),
):
    """Show one decision record."""
    record = find_decision(decision_id)
    if record is None:
        if output_json:
            print(json.dumps({"error": "Decision not found or prefix is ambiguous"}))
        else:
            console.print("[red]Decision not found or prefix is ambiguous.[/red]")
        raise typer.Exit(1)

    if output_json:
        print(record.model_dump_json(indent=2))
        return

    console.print(f"[bold]Decision:[/bold] {record.id}")
    console.print(f"[bold]Created:[/bold] {record.created_at}")
    console.print(f"[bold]Type:[/bold] {record.event_type}")
    console.print(f"[bold]Source:[/bold] {record.source}")
    console.print(f"[bold]Actor:[/bold] {record.actor}")
    console.print(f"[bold]Reason:[/bold] {record.reason}")
    if record.note:
        console.print(f"[bold]Note:[/bold] {record.note}")
    if record.plan_id:
        console.print(f"[bold]Plan:[/bold] {record.plan_id}")
    if record.action_type:
        console.print(f"[bold]Action:[/bold] {record.action_type}")
    if record.campaign_id:
        console.print(f"[bold]Campaign:[/bold] {record.campaign_name or ''} ({record.campaign_id})")


@app.command("export")
def export_decisions(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write Markdown here"),
    output_json: bool = typer.Option(False, "--json", help="Output records as JSON"),
):
    """Export the local decision log."""
    records = load_decisions()

    if output_json:
        print(json.dumps([record.model_dump(mode="json") for record in records], indent=2))
        return

    markdown = decisions_to_markdown(records)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown)
        console.print(f"[green]Decision log exported to {output}[/green]")
        return

    console.print(markdown)
