"""Command helpers for active-app safety checks."""

from __future__ import annotations

import typer
from rich.console import Console

from ..api import SearchAdsClient
from ..config import campaign_matches_app, get_current_app_config

console = Console()


def require_campaign_in_current_app(client: SearchAdsClient, campaign_id: int) -> dict:
    """Return a campaign only if it belongs to the active configured app."""
    campaign = client.get_campaign(campaign_id)
    if not campaign:
        console.print(f"[red]Campaign {campaign_id} not found.[/red]")
        raise typer.Exit(1)

    app_config = get_current_app_config()
    if not campaign_matches_app(campaign, app_config):
        active = f"{app_config.app_name} ({app_config.app_id})" if app_config else "current app"
        owner = campaign.get("adamId", "unknown app")
        console.print(
            f"[red]Campaign {campaign_id} belongs to app {owner}, not active app {active}.[/red]"
        )
        raise typer.Exit(1)

    return campaign
