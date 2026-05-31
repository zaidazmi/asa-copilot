"""Plan review commands."""

from pathlib import Path

import typer
from rich.console import Console

from ..plans import PlanLoadError, display_plan, load_plan
from ..output import print_json, print_json_error

app = typer.Typer(help="Review saved change plans")
console = Console()


@app.command("show")
def show_plan(
    path: Path = typer.Argument(..., help="Path to a plan JSON file"),
    output_json: bool = typer.Option(False, "--json", help="Output plan as JSON"),
):
    """Show the changes in a saved plan."""
    try:
        plan = load_plan(path)
    except PlanLoadError as exc:
        if output_json:
            print_json_error(str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if output_json:
        print_json(plan.model_dump(mode="json"))
        return
    display_plan(plan)
