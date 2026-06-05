"""Ad group management commands."""

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from ..api import SearchAdsClient
from ..config import get_current_app_config, load_credentials
from ..decisions import log_manual_decision
from .scope import require_campaign_in_current_app

app = typer.Typer(help="Ad group management commands")
console = Console()


def _require_reason(reason: Optional[str], action: str) -> str:
    """Require a reason for serving/spend-affecting direct commands."""
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
def list_adgroups(
    campaign_id: int = typer.Argument(..., help="Campaign ID to list ad groups for"),
):
    """List all ad groups for a campaign."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    # Verify campaign exists
    campaign = require_campaign_in_current_app(client, campaign_id)

    with console.status("[bold blue]Fetching ad groups..."):
        ad_groups = client.get_ad_groups(campaign_id)

    if not ad_groups:
        console.print(f"[yellow]No ad groups found for campaign {campaign_id}.[/yellow]")
        return

    table = Table(
        title=f"Ad Groups for {campaign.get('name', 'Unknown')}",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Default Bid")
    table.add_column("Search Match")

    for ag in ad_groups:
        status = ag.get("displayStatus", ag.get("status", "UNKNOWN"))
        status_style = "green" if status == "RUNNING" else "yellow" if status == "PAUSED" else "red"
        default_bid = ag.get("defaultBidAmount", {})
        bid_str = f"${default_bid.get('amount', '?')} {default_bid.get('currency', '')}"
        search_match = (
            "[green]ON[/green]" if ag.get("automatedKeywordsOptIn", False) else "[dim]OFF[/dim]"
        )

        table.add_row(
            str(ag.get("id")),
            ag.get("name", "Unknown"),
            f"[{status_style}]{status}[/{status_style}]",
            bid_str,
            search_match,
        )

    console.print(table)


@app.command("create")
def create_adgroup(
    campaign_id: int = typer.Option(..., "--campaign", "-c", help="Campaign ID"),
    name: str = typer.Argument(..., help="Ad group name"),
    bid: float = typer.Option(1.50, "--bid", "-b", help="Default bid amount"),
    search_match: bool = typer.Option(
        False, "--search-match/--no-search-match", help="Enable Search Match"
    ),
    status: str = typer.Option(
        "ENABLED", "--status", "-s", help="Initial status (ENABLED or PAUSED)"
    ),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason for creating the ad group"),
):
    """Create a new ad group in a campaign."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    # Verify campaign exists
    campaign = require_campaign_in_current_app(client, campaign_id)

    status_upper = status.upper()
    if status_upper not in ("ENABLED", "PAUSED"):
        console.print("[red]Status must be ENABLED or PAUSED.[/red]")
        raise typer.Exit(1)

    reason_text = _require_reason(reason, "creating ad group")

    console.print(f"\nCreating ad group in campaign [cyan]{campaign.get('name')}[/cyan]:")
    console.print(f"  Name: [cyan]{name}[/cyan]")
    console.print(f"  Default Bid: [cyan]${bid}[/cyan]")
    console.print(f"  Search Match: [cyan]{'ON' if search_match else 'OFF'}[/cyan]")
    console.print(f"  Status: [cyan]{status_upper}[/cyan]")

    with console.status("[bold blue]Creating ad group..."):
        ad_group = client.create_ad_group(
            campaign_id=campaign_id,
            name=name,
            default_bid=bid,
            search_match_enabled=search_match,
            status=status_upper,
        )

    if ad_group:
        console.print(f"\n[green]Ad group created successfully![/green]")
        console.print(f"  ID: [cyan]{ad_group.get('id')}[/cyan]")
        console.print(f"  Name: [cyan]{ad_group.get('name')}[/cyan]")
        log_manual_decision(
            event_type="ad_group_created",
            reason=reason_text,
            command="adgroups create",
            campaign_id=campaign_id,
            campaign_name=campaign.get("name"),
            ad_group_id=ad_group.get("id"),
            ad_group_name=ad_group.get("name"),
            metadata={
                "default_bid": bid,
                "search_match": search_match,
                "status": status_upper,
            },
            result={"ad_group": ad_group},
        )
    else:
        console.print("[red]Failed to create ad group.[/red]")
        raise typer.Exit(1)


@app.command("update")
def update_adgroup(
    adgroup_id: int = typer.Argument(..., help="Ad group ID to update"),
    campaign_id: int = typer.Option(..., "--campaign", "-c", help="Campaign ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New name"),
    bid: Optional[float] = typer.Option(None, "--bid", "-b", help="New default bid"),
    search_match: Optional[bool] = typer.Option(
        None, "--search-match/--no-search-match", help="Toggle Search Match"
    ),
    status: Optional[str] = typer.Option(
        None, "--status", "-s", help="New status (ENABLED or PAUSED)"
    ),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason for updating the ad group"),
):
    """Update an ad group's settings."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    if not any([name, bid, search_match is not None, status]):
        console.print(
            "[red]No updates provided. Use --name, --bid, --search-match, or --status.[/red]"
        )
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    campaign = require_campaign_in_current_app(client, campaign_id)
    reason_text = _require_reason(reason, "updating ad group")

    # Build updates
    updates = {}
    changes = []
    app_config = get_current_app_config()
    currency = app_config.currency if app_config else "USD"

    if name:
        updates["name"] = name
        changes.append(f"Name → {name}")

    if bid is not None:
        updates["defaultBidAmount"] = {"amount": str(bid), "currency": currency}
        changes.append(f"Default Bid → ${bid}")

    if search_match is not None:
        updates["automatedKeywordsOptIn"] = search_match
        changes.append(f"Search Match → {'ON' if search_match else 'OFF'}")

    if status:
        status_upper = status.upper()
        if status_upper not in ("ENABLED", "PAUSED"):
            console.print("[red]Status must be ENABLED or PAUSED.[/red]")
            raise typer.Exit(1)
        updates["status"] = status_upper
        changes.append(f"Status → {status_upper}")

    console.print(f"\nUpdating ad group {adgroup_id}:")
    for change in changes:
        console.print(f"  • {change}")

    with console.status("[bold blue]Updating ad group..."):
        result = client.update_ad_group(campaign_id, adgroup_id, updates)

    if result:
        console.print("\n[green]Ad group updated successfully![/green]")
        event_type = "ad_group_updated"
        if updates.get("status") == "PAUSED":
            event_type = "ad_group_paused"
        elif updates.get("status") == "ENABLED":
            event_type = "ad_group_enabled"
        log_manual_decision(
            event_type=event_type,
            reason=reason_text,
            command="adgroups update",
            campaign_id=campaign_id,
            campaign_name=campaign.get("name"),
            ad_group_id=adgroup_id,
            ad_group_name=result.get("name"),
            metadata={"updates": updates, "changes": changes},
            result={"ad_group": result},
        )
    else:
        console.print("[red]Failed to update ad group.[/red]")
        raise typer.Exit(1)


@app.command("pause")
def pause_adgroup(
    adgroup_id: int = typer.Argument(..., help="Ad group ID to pause"),
    campaign_id: int = typer.Option(..., "--campaign", "-c", help="Campaign ID"),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason for pausing the ad group"),
):
    """Pause an ad group."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    campaign = require_campaign_in_current_app(client, campaign_id)
    reason_text = _require_reason(reason, "pausing ad group")

    with console.status("[bold blue]Pausing ad group..."):
        result = client.update_ad_group(campaign_id, adgroup_id, {"status": "PAUSED"})

    if result:
        console.print(f"[green]Ad group {adgroup_id} paused.[/green]")
        log_manual_decision(
            event_type="ad_group_paused",
            reason=reason_text,
            command="adgroups pause",
            campaign_id=campaign_id,
            campaign_name=campaign.get("name"),
            ad_group_id=adgroup_id,
            ad_group_name=result.get("name"),
            result={"ad_group": result},
        )
    else:
        console.print(f"[red]Failed to pause ad group {adgroup_id}.[/red]")
        raise typer.Exit(1)


@app.command("enable")
def enable_adgroup(
    adgroup_id: int = typer.Argument(..., help="Ad group ID to enable"),
    campaign_id: int = typer.Option(..., "--campaign", "-c", help="Campaign ID"),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason for enabling the ad group"),
):
    """Enable an ad group."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    campaign = require_campaign_in_current_app(client, campaign_id)
    reason_text = _require_reason(reason, "enabling ad group")

    with console.status("[bold blue]Enabling ad group..."):
        result = client.update_ad_group(campaign_id, adgroup_id, {"status": "ENABLED"})

    if result:
        console.print(f"[green]Ad group {adgroup_id} enabled.[/green]")
        log_manual_decision(
            event_type="ad_group_enabled",
            reason=reason_text,
            command="adgroups enable",
            campaign_id=campaign_id,
            campaign_name=campaign.get("name"),
            ad_group_id=adgroup_id,
            ad_group_name=result.get("name"),
            result={"ad_group": result},
        )
    else:
        console.print(f"[red]Failed to enable ad group {adgroup_id}.[/red]")
        raise typer.Exit(1)


@app.command("delete")
def delete_adgroup(
    adgroup_id: int = typer.Argument(..., help="Ad group ID to delete"),
    campaign_id: int = typer.Option(..., "--campaign", "-c", help="Campaign ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason for deleting the ad group"),
):
    """Delete an ad group. WARNING: This is irreversible."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    campaign = require_campaign_in_current_app(client, campaign_id)

    # Get ad group info for confirmation
    ad_groups = client.get_ad_groups(campaign_id)
    ad_group = next((ag for ag in ad_groups if ag.get("id") == adgroup_id), None)

    if not ad_group:
        console.print(f"[red]Ad group {adgroup_id} not found in campaign {campaign_id}.[/red]")
        raise typer.Exit(1)

    reason_text = _require_reason(reason, "deleting ad group")

    console.print(f"\n[bold red]WARNING: About to delete ad group:[/bold red]")
    console.print(f"  Name: {ad_group.get('name', 'Unknown')}")
    console.print(f"  ID: {adgroup_id}")

    if not force:
        from rich.prompt import Confirm

        if not Confirm.ask("\n[red]This is irreversible. Continue?[/red]"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    with console.status("[bold blue]Deleting ad group..."):
        if client.delete_ad_group(campaign_id, adgroup_id):
            console.print(f"[green]Ad group {adgroup_id} deleted.[/green]")
            log_manual_decision(
                event_type="ad_group_deleted",
                reason=reason_text,
                command="adgroups delete",
                campaign_id=campaign_id,
                campaign_name=campaign.get("name"),
                ad_group_id=adgroup_id,
                ad_group_name=ad_group.get("name"),
                result={"success": True},
            )
        else:
            console.print(f"[red]Failed to delete ad group {adgroup_id}.[/red]")
            raise typer.Exit(1)
