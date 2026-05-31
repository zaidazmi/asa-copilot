"""Ad variation and creative management commands."""

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from ..api import SearchAdsClient
from ..config import get_current_app_config, load_credentials
from ..decisions import log_manual_decision
from .scope import require_campaign_in_current_app

app = typer.Typer(help="Ad variation and creative management commands")
console = Console()


def _require_reason(reason: Optional[str], action: str) -> str:
    """Require a reason for serving-affecting ad commands."""
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


@app.command("list")
def list_ads(
    campaign_id: Optional[int] = typer.Option(None, "--campaign", "-c", help="Campaign ID"),
    ad_group_id: Optional[int] = typer.Option(None, "--adgroup", "-g", help="Ad group ID"),
):
    """List all ads. Provide campaign + ad group for a specific group, or search across all."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    if campaign_id and ad_group_id:
        require_campaign_in_current_app(client, campaign_id)
        with console.status("[bold blue]Fetching ads..."):
            ads = client.get_ads(campaign_id, ad_group_id)
    else:
        if campaign_id:
            require_campaign_in_current_app(client, campaign_id)
        with console.status("[bold blue]Finding ads..."):
            ads = client.find_ads(campaign_id=campaign_id)

    if not ads:
        console.print("[yellow]No ads found.[/yellow]")
        return

    table = Table(title="Ads", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Creative ID")
    table.add_column("Creative Type")

    for ad in ads:
        status = ad.get("status", "UNKNOWN")
        status_style = "green" if status == "ENABLED" else "yellow" if status == "PAUSED" else "red"

        table.add_row(
            str(ad.get("id", "")),
            ad.get("name", "Unknown"),
            f"[{status_style}]{status}[/{status_style}]",
            str(ad.get("creativeId", "")),
            ad.get("creativeType", "-"),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(ads)} ads[/dim]")


@app.command("create")
def create_ad(
    campaign_id: int = typer.Option(..., "--campaign", "-c", help="Campaign ID"),
    ad_group_id: int = typer.Option(..., "--adgroup", "-g", help="Ad group ID"),
    creative_id: int = typer.Option(..., "--creative", help="Creative ID"),
    name: str = typer.Argument(..., help="Ad name"),
    status: str = typer.Option(
        "ENABLED", "--status", "-s", help="Initial status (ENABLED or PAUSED)"
    ),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason for creating the ad"),
):
    """Create a new ad in an ad group."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    status_upper = status.upper()
    if status_upper not in ("ENABLED", "PAUSED"):
        console.print("[red]Status must be ENABLED or PAUSED.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    campaign = require_campaign_in_current_app(client, campaign_id)
    reason_text = _require_reason(reason, "creating ad")

    console.print(f"\nCreating ad:")
    console.print(f"  Name: [cyan]{name}[/cyan]")
    console.print(f"  Campaign: [cyan]{campaign_id}[/cyan]")
    console.print(f"  Ad Group: [cyan]{ad_group_id}[/cyan]")
    console.print(f"  Creative: [cyan]{creative_id}[/cyan]")
    console.print(f"  Status: [cyan]{status_upper}[/cyan]")

    with console.status("[bold blue]Creating ad..."):
        ad = client.create_ad(
            campaign_id=campaign_id,
            ad_group_id=ad_group_id,
            creative_id=creative_id,
            name=name,
            status=status_upper,
        )

    if ad:
        console.print(f"\n[green]Ad created successfully![/green]")
        console.print(f"  ID: [cyan]{ad.get('id')}[/cyan]")
        console.print(f"  Name: [cyan]{ad.get('name')}[/cyan]")
        log_manual_decision(
            event_type="ad_created",
            reason=reason_text,
            command="ads create",
            campaign_id=campaign_id,
            campaign_name=campaign.get("name"),
            ad_group_id=ad_group_id,
            metadata={"creative_id": creative_id, "status": status_upper},
            result={"ad": ad},
        )
    else:
        console.print("[red]Failed to create ad.[/red]")
        raise typer.Exit(1)


@app.command("delete")
def delete_ad(
    ad_id: int = typer.Argument(..., help="Ad ID to delete"),
    campaign_id: int = typer.Option(..., "--campaign", "-c", help="Campaign ID"),
    ad_group_id: int = typer.Option(..., "--adgroup", "-g", help="Ad group ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason for deleting the ad"),
):
    """Delete an ad. WARNING: This is irreversible."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    campaign = require_campaign_in_current_app(client, campaign_id)

    # Get ad info for confirmation
    ad = client.get_ad(campaign_id, ad_group_id, ad_id)
    if not ad:
        console.print(f"[red]Ad {ad_id} not found.[/red]")
        raise typer.Exit(1)

    reason_text = _require_reason(reason, "deleting ad")

    console.print(f"\n[bold red]WARNING: About to delete ad:[/bold red]")
    console.print(f"  Name: {ad.get('name', 'Unknown')}")
    console.print(f"  ID: {ad_id}")

    if not force and not Confirm.ask("\n[red]This is irreversible. Continue?[/red]"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    with console.status("[bold blue]Deleting ad..."):
        if client.delete_ad(campaign_id, ad_group_id, ad_id):
            console.print(f"[green]Ad {ad_id} deleted.[/green]")
            log_manual_decision(
                event_type="ad_deleted",
                reason=reason_text,
                command="ads delete",
                campaign_id=campaign_id,
                campaign_name=ad.get("campaignName") or campaign.get("name"),
                ad_group_id=ad_group_id,
                ad_group_name=ad.get("adGroupName"),
                metadata={"ad_id": ad_id, "ad_name": ad.get("name")},
                result={"success": True},
            )
        else:
            console.print(f"[red]Failed to delete ad {ad_id}.[/red]")
            raise typer.Exit(1)


@app.command("creatives")
def list_creatives(
    creative_id: Optional[int] = typer.Option(None, "--id", help="Get a specific creative by ID"),
):
    """List creatives or get details for a specific creative."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    if creative_id:
        with console.status("[bold blue]Fetching creative..."):
            creative = client.get_creative(creative_id)

        if not creative:
            console.print(f"[red]Creative {creative_id} not found.[/red]")
            raise typer.Exit(1)

        console.print(f"\n[bold]Creative Details[/bold]")
        console.print(f"  ID: [cyan]{creative.get('id')}[/cyan]")
        console.print(f"  Name: [cyan]{creative.get('name', 'Unknown')}[/cyan]")
        console.print(f"  Type: [cyan]{creative.get('type', '-')}[/cyan]")
        console.print(f"  State: [cyan]{creative.get('state', '-')}[/cyan]")
        console.print(f"  Adam ID: [cyan]{creative.get('adamId', '-')}[/cyan]")

        product_page_id = creative.get("productPageId")
        if product_page_id:
            console.print(f"  Product Page ID: [cyan]{product_page_id}[/cyan]")

        return

    with console.status("[bold blue]Fetching creatives..."):
        creatives = client.get_creatives()

    if not creatives:
        console.print("[yellow]No creatives found.[/yellow]")
        return

    table = Table(title="Creatives", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("State")
    table.add_column("Adam ID")

    for creative in creatives:
        state = creative.get("state", "UNKNOWN")
        state_style = "green" if state == "VALID" else "yellow" if state == "PENDING" else "red"

        table.add_row(
            str(creative.get("id", "")),
            creative.get("name", "Unknown"),
            creative.get("type", "-"),
            f"[{state_style}]{state}[/{state_style}]",
            str(creative.get("adamId", "")),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(creatives)} creatives[/dim]")


@app.command("product-pages")
def list_product_pages(
    adam_id: Optional[int] = typer.Option(
        None, "--adam-id", "-a", help="App Adam ID (uses current app if not set)"
    ),
):
    """List custom product pages for an app."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    app_config = get_current_app_config()

    resolved_adam_id = adam_id
    if not resolved_adam_id:
        if not app_config:
            console.print("[red]No app configured. Use --adam-id or run 'asa config setup'.[/red]")
            raise typer.Exit(1)
        resolved_adam_id = app_config.app_id

    client = SearchAdsClient(credentials)

    with console.status("[bold blue]Fetching product pages..."):
        pages = client.get_product_pages(resolved_adam_id)

    if not pages:
        console.print("[yellow]No custom product pages found.[/yellow]")
        return

    table = Table(title="Custom Product Pages", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Visible")

    for page in pages:
        state = page.get("state", "UNKNOWN")
        state_style = "green" if state == "VISIBLE" else "yellow"

        table.add_row(
            str(page.get("id", "")),
            page.get("name", "Unknown"),
            f"[{state_style}]{state}[/{state_style}]",
            str(page.get("isVisible", "-")),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(pages)} product pages[/dim]")


@app.command("rejections")
def show_rejections():
    """Show product page rejection reasons."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    with console.status("[bold blue]Fetching rejection reasons..."):
        reasons = client.find_rejection_reasons()

    if not reasons:
        console.print("[green]No rejection reasons found. All clear![/green]")
        return

    table = Table(title="Rejection Reasons", show_header=True, header_style="bold magenta")
    table.add_column("Creative ID", style="cyan")
    table.add_column("Reason")
    table.add_column("Comment")

    for reason in reasons:
        table.add_row(
            str(reason.get("creativeId", "")),
            reason.get("reasonText", "-"),
            reason.get("comment", "-"),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(reasons)} rejection reasons[/dim]")
