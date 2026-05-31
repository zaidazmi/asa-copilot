"""Geo targeting commands."""

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from ..api import SearchAdsClient
from ..config import filter_campaigns_for_app, get_current_app_config, load_credentials
from ..decisions import log_manual_decision
from .scope import require_campaign_in_current_app

app = typer.Typer(help="Geo targeting commands")
console = Console()


def _require_reason(reason: Optional[str], action: str) -> str:
    """Require a reason for serving-affecting geo commands."""
    if reason and reason.strip():
        return reason.strip()
    if not sys.stdin.isatty():
        console.print(f"[red]A --reason is required for {action}.[/red]")
        raise typer.Exit(1)
    while True:
        reason_text = Prompt.ask(f"Reason for {action}").strip()
        if reason_text:
            return reason_text
        console.print("[red]A reason is required.[/red]")


@app.command("search")
def search_geo(
    query: str = typer.Argument(..., help="Search query for geo locations"),
    entity: Optional[str] = typer.Option(
        None, "--entity", "-e", help="Entity type: Country, AdminArea, or Locality"
    ),
    country_code: str = typer.Option("US", "--country", "-c", help="Country code to search within"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results to return"),
):
    """Search for geo locations (countries, states, cities)."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    with console.status("[bold blue]Searching geo locations..."):
        results = client.geo_search(
            query=query, entity=entity, country_code=country_code, limit=limit
        )

    if not results:
        console.print("[yellow]No geo locations found.[/yellow]")
        return

    table = Table(title=f"Geo Search: '{query}'", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan")
    table.add_column("Display Name")
    table.add_column("Entity")
    table.add_column("Country Code")

    for loc in results:
        table.add_row(
            str(loc.get("id", "")),
            loc.get("displayName", ""),
            loc.get("entity", ""),
            loc.get("countryOrRegion", ""),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(results)} results[/dim]")


@app.command("show")
def show_geo_targeting():
    """Show geo targeting for all campaigns."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    with console.status("[bold blue]Fetching campaigns..."):
        campaigns = filter_campaigns_for_app(client.get_campaigns(), get_current_app_config())

    if not campaigns:
        console.print("[yellow]No campaigns found.[/yellow]")
        return

    table = Table(title="Campaign Geo Targeting", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan")
    table.add_column("Campaign Name")
    table.add_column("Status")
    table.add_column("Countries/Regions")

    for campaign in campaigns:
        countries = ", ".join(campaign.get("countriesOrRegions", []))
        status = campaign.get("displayStatus", campaign.get("status", "UNKNOWN"))
        status_style = "green" if status == "RUNNING" else "yellow" if status == "PAUSED" else "red"

        table.add_row(
            str(campaign.get("id")),
            campaign.get("name", ""),
            f"[{status_style}]{status}[/{status_style}]",
            countries or "[dim]None[/dim]",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(campaigns)} campaigns[/dim]")


@app.command("set")
def set_geo_targeting(
    campaign_id: int = typer.Option(..., "--campaign", "-c", help="Campaign ID"),
    countries: str = typer.Option(
        ..., "--countries", help="Comma-separated country/region codes (e.g. US,CA,GB)"
    ),
    reason: Optional[str] = typer.Option(
        None, "--reason", help="Reason for changing geo targeting"
    ),
):
    """Set country targeting for a campaign."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    campaign = require_campaign_in_current_app(client, campaign_id)

    country_list = [c.strip().upper() for c in countries.split(",") if c.strip()]

    if not country_list:
        console.print("[red]No valid country codes provided.[/red]")
        raise typer.Exit(1)

    # Show current targeting
    with console.status("[bold blue]Fetching current targeting..."):
        current = client.get_campaign_geo_targeting(campaign_id)

    console.print(f"\nCampaign [cyan]{campaign_id}[/cyan]")
    console.print(
        f"  Current countries: [yellow]{', '.join(current) if current else 'None'}[/yellow]"
    )
    console.print(f"  New countries:     [cyan]{', '.join(country_list)}[/cyan]")

    reason_text = _require_reason(reason, "changing geo targeting")

    with console.status("[bold blue]Updating geo targeting..."):
        result = client.update_campaign_countries(campaign_id, country_list)

    if result:
        console.print(f"\n[green]Geo targeting updated successfully![/green]")
        log_manual_decision(
            event_type="campaign_geo_updated",
            reason=reason_text,
            command="geo set",
            campaign_id=campaign_id,
            campaign_name=campaign.get("name"),
            metadata={"previous_countries": current, "new_countries": country_list},
            result={"campaign": result},
        )
    else:
        console.print("[red]Failed to update geo targeting.[/red]")
        raise typer.Exit(1)
