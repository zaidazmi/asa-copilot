"""Budget management commands."""

import json
import sys
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from ..api import SearchAdsClient
from ..config import (
    RulesLoadError,
    detect_campaign_type,
    filter_campaigns_for_app,
    get_current_app_config,
    is_multi_app,
    load_credentials,
    load_rules,
)
from ..decisions import log_manual_decision
from ..operator_reports import build_budget_pacing_actions, summarize_report_rows
from ..plans import ChangePlan, save_plan

app = typer.Typer(help="Budget management commands")
console = Console()


def _resolve_app_name() -> Optional[str]:
    """Get the app_name for campaign scoping (None if single-app)."""
    if not is_multi_app():
        return None
    app_config = get_current_app_config()
    return app_config.app_name if app_config else None


def _require_reason(reason: Optional[str], action: str) -> str:
    """Require a reason for spend-affecting direct commands."""
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


def _campaign_budget_summaries(
    client: SearchAdsClient,
    *,
    days: int,
    app_name: Optional[str],
) -> list[dict]:
    """Fetch campaign report summaries for budget pacing."""
    end = datetime.now()
    start = end - timedelta(days=days)
    campaigns = filter_campaigns_for_app(client.get_campaigns(), get_current_app_config())
    summaries = []

    for campaign in campaigns:
        ctype = detect_campaign_type(campaign.get("name", ""))
        if app_name and not ctype:
            continue
        rows = client.get_campaign_report(campaign.get("id"), start, end, granularity="DAILY")
        summaries.append(summarize_report_rows(campaign, rows, ctype))

    return summaries


def _display_pacing(summaries: list[dict], actions: list, days: int) -> None:
    """Render campaign budget pacing and recommendations."""
    console.print(Panel(f"[bold]Budget Pacing[/bold]\nLast {days} days", expand=False))

    table = Table(title="Campaign Pace", show_header=True, header_style="bold magenta")
    table.add_column("Campaign")
    table.add_column("Type")
    table.add_column("Daily Budget", justify="right")
    table.add_column("Spend", justify="right")
    table.add_column("Pace", justify="right")
    table.add_column("Inst", justify="right")
    table.add_column("CPA", justify="right")

    for summary in summaries:
        expected = (summary.get("daily_budget") or 0) * days
        pace = (summary.get("spend", 0) / expected * 100) if expected else 0
        cpa = summary.get("cpa")
        table.add_row(
            summary.get("campaign_name", "")[:36],
            (summary.get("campaign_type") or "-").upper(),
            f"${summary.get('daily_budget', 0):,.2f}",
            f"${summary.get('spend', 0):,.2f}",
            f"{pace:.0f}%",
            str(summary.get("installs", 0)),
            f"${cpa:,.2f}" if cpa is not None else "-",
        )

    console.print(table)

    if not actions:
        console.print("[green]No budget pacing actions recommended.[/green]")
        return

    action_table = Table(
        title="Recommended Plan Actions", show_header=True, header_style="bold cyan"
    )
    action_table.add_column("Type")
    action_table.add_column("Campaign")
    action_table.add_column("New Budget")
    action_table.add_column("Reason")
    for action in actions:
        action_table.add_row(
            action.type.value,
            action.campaign_name or str(action.campaign_id or "-"),
            (
                f"${action.daily_budget_amount:,.2f}"
                if action.daily_budget_amount is not None
                else "-"
            ),
            action.reason or "",
        )
    console.print(action_table)


@app.command("list")
def list_budget_orders():
    """List all budget orders."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    with console.status("[bold blue]Fetching budget orders..."):
        budget_orders = client.get_budget_orders()

    if not budget_orders:
        console.print("[yellow]No budget orders found.[/yellow]")
        return

    table = Table(title="Budget Orders", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Order Number")
    table.add_column("Budget")
    table.add_column("Start Date")
    table.add_column("End Date")
    table.add_column("Status")

    for bo in budget_orders:
        budget = bo.get("budget", {})
        amount = budget.get("amount", "?")
        currency = budget.get("currency", "USD")
        status = bo.get("status", "UNKNOWN")

        status_style = "green" if status == "ACTIVE" else "yellow" if status == "PAUSED" else "red"

        table.add_row(
            str(bo.get("id", "")),
            bo.get("name", ""),
            str(bo.get("orderNumber", "")),
            f"${amount} {currency}",
            bo.get("startDate", ""),
            bo.get("endDate", ""),
            f"[{status_style}]{status}[/{status_style}]",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(budget_orders)} budget orders[/dim]")


@app.command("get")
def get_budget_order(
    budget_order_id: int = typer.Argument(..., help="Budget order ID"),
):
    """Show details of a specific budget order."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    with console.status("[bold blue]Fetching budget order..."):
        bo = client.get_budget_order(budget_order_id)

    if not bo:
        console.print(f"[red]Budget order {budget_order_id} not found.[/red]")
        raise typer.Exit(1)

    budget = bo.get("budget", {})
    amount = budget.get("amount", "?")
    currency = budget.get("currency", "USD")

    console.print(Panel(f"[bold]Budget Order: {bo.get('name', '')}[/bold]", expand=False))
    console.print(f"  ID:           [cyan]{bo.get('id', '')}[/cyan]")
    console.print(f"  Order Number: [cyan]{bo.get('orderNumber', '')}[/cyan]")
    console.print(f"  Budget:       [cyan]${amount} {currency}[/cyan]")
    console.print(f"  Start Date:   [cyan]{bo.get('startDate', '')}[/cyan]")
    console.print(f"  End Date:     [cyan]{bo.get('endDate', '')}[/cyan]")
    console.print(f"  Status:       [cyan]{bo.get('status', '')}[/cyan]")


@app.command("status")
def budget_status(
    rules_file: Optional[Path] = typer.Option(
        None, "--rules", help="JSON or YAML rule file overriding app config defaults"
    ),
):
    """Campaign budget health dashboard."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)
    app_config = get_current_app_config()
    try:
        rules = load_rules(rules_file, app_config=app_config)
    except RulesLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    app_name = _resolve_app_name()

    with console.status("[bold blue]Fetching campaign budget status..."):
        statuses = client.get_campaign_budget_status()
    statuses = filter_campaigns_for_app(statuses, app_config)

    if not statuses:
        console.print("[yellow]No campaigns found.[/yellow]")
        return

    if rules.goals.monthly_budget is not None:
        console.print(
            Panel(
                f"[bold]Budget Rules[/bold]\n"
                f"Monthly budget: ${rules.goals.monthly_budget:,.2f} {rules.currency}",
                expand=False,
            )
        )

    table = Table(
        title="Campaign Budget Health",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Campaign", max_width=35)
    table.add_column("Type", style="green")
    table.add_column("Daily Budget", justify="right")
    table.add_column("Lifetime Budget", justify="right")
    table.add_column("Total Spend", justify="right")
    table.add_column("Status")
    table.add_column("Display Status")

    for entry in statuses:
        name = entry.get("name", "")
        ctype = detect_campaign_type(name)
        ctype_str = ctype.value.upper() if ctype else "-"

        daily = entry.get("dailyBudgetAmount") or {}
        daily_amount = daily.get("amount", "-")
        daily_currency = daily.get("currency", "")
        daily_str = (
            f"${daily_amount} {daily_currency}".strip() if daily_amount != "-" else "[dim]-[/dim]"
        )

        lifetime = entry.get("budgetAmount") or {}
        lifetime_amount = lifetime.get("amount", "-")
        lifetime_currency = lifetime.get("currency", "")
        lifetime_str = (
            f"${lifetime_amount} {lifetime_currency}".strip()
            if lifetime_amount != "-"
            else "[dim]-[/dim]"
        )

        total_spend = entry.get("totalSpend", 0.0)
        spend_str = f"${total_spend:,.2f}"

        status = entry.get("status", "UNKNOWN")
        display_status = entry.get("displayStatus", "UNKNOWN")

        # Color-code status
        if status == "ENABLED":
            status_style = "green"
        elif status == "PAUSED":
            status_style = "yellow"
        else:
            status_style = "red"

        # Color-code display status for budget issues
        display_lower = display_status.lower()
        if "exhaust" in display_lower or "budget" in display_lower and "limit" in display_lower:
            display_style = "red"
        elif "pause" in display_lower or "limit" in display_lower:
            display_style = "yellow"
        elif display_status == "RUNNING":
            display_style = "green"
        else:
            display_style = "white"

        display_name = name[:35] + "..." if len(name) > 35 else name

        table.add_row(
            display_name,
            ctype_str,
            daily_str,
            lifetime_str,
            spend_str,
            f"[{status_style}]{status}[/{status_style}]",
            f"[{display_style}]{display_status}[/{display_style}]",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(statuses)} campaigns[/dim]")


@app.command("pacing")
def budget_pacing(
    daily: bool = typer.Option(False, "--daily", help="Use a 1-day pacing window"),
    month: bool = typer.Option(False, "--month", help="Use a 30-day pacing window"),
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Custom pacing window"),
    output_json: bool = typer.Option(False, "--json", help="Output pacing data as JSON"),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write budget change plan JSON to this path"
    ),
    rules_file: Optional[Path] = typer.Option(
        None, "--rules", help="JSON or YAML rule file overriding app config defaults"
    ),
):
    """Analyze budget pace and recommend budget plan actions."""
    if sum([bool(daily), bool(month), days is not None]) > 1:
        message = "Use only one of --daily, --month, or --days"
        if output_json:
            print(json.dumps({"error": message}))
        else:
            console.print(f"[red]{message}[/red]")
        raise typer.Exit(1)

    resolved_days = 1 if daily else 30 if month else days or 7
    if resolved_days <= 0:
        if output_json:
            print(json.dumps({"error": "Days must be a positive integer"}))
        else:
            console.print("[red]Days must be a positive integer.[/red]")
        raise typer.Exit(1)

    credentials = load_credentials()
    if not credentials:
        if output_json:
            print(json.dumps({"error": "No credentials configured"}))
        else:
            console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    app_config = get_current_app_config()
    try:
        rules = load_rules(rules_file, app_config=app_config)
    except RulesLoadError as exc:
        if output_json:
            print(json.dumps({"error": str(exc)}))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    app_name = _resolve_app_name()
    summaries = _campaign_budget_summaries(client, days=resolved_days, app_name=app_name)
    actions = build_budget_pacing_actions(
        summaries,
        days=resolved_days,
        rules=rules,
        source="budget_pacing",
    )
    plan = ChangePlan(
        source="budget_pacing",
        app_name=app_name,
        lookback_days=resolved_days,
        summary=f"{len(actions)} budget pacing actions over {resolved_days} days",
        actions=actions,
    )

    if out:
        save_plan(plan, out)
        if not output_json:
            console.print(f"[green]Plan saved to {out}[/green]")
            console.print(f"[dim]Review with: asa plan show {out}[/dim]")
            return

    if output_json:
        print(
            json.dumps(
                {
                    "days": resolved_days,
                    "campaigns": summaries,
                    "plan": plan.model_dump(mode="json"),
                },
                indent=2,
            )
        )
        return

    _display_pacing(summaries, actions, resolved_days)


@app.command("create")
def create_budget_order(
    name: str = typer.Option(..., "--name", "-n", help="Budget order name"),
    budget: float = typer.Option(..., "--budget", "-b", help="Budget amount (USD)"),
    start_date: str = typer.Option(..., "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Option(..., "--end", "-e", help="End date (YYYY-MM-DD)"),
    client_name: Optional[str] = typer.Option(None, "--client-name", help="Client name"),
    primary_buyer_email: Optional[str] = typer.Option(None, "--email", help="Primary buyer email"),
    reason: Optional[str] = typer.Option(
        None, "--reason", help="Reason for creating the budget order"
    ),
):
    """Create a new budget order."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    reason_text = _require_reason(reason, "creating budget order")

    kwargs = {}
    if client_name:
        kwargs["clientName"] = client_name
    if primary_buyer_email:
        kwargs["primaryBuyerEmail"] = primary_buyer_email

    console.print(f"\nCreating budget order: [cyan]{name}[/cyan]")
    console.print(f"  Budget:     [cyan]${budget:,.2f}[/cyan]")
    console.print(f"  Start Date: [cyan]{start_date}[/cyan]")
    console.print(f"  End Date:   [cyan]{end_date}[/cyan]")

    with console.status("[bold blue]Creating budget order..."):
        bo = client.create_budget_order(
            name=name,
            budget=budget,
            start_date=start_date,
            end_date=end_date,
            **kwargs,
        )

    if bo:
        console.print(f"\n[green]Budget order created successfully![/green]")
        console.print(f"  ID: [cyan]{bo.get('id')}[/cyan]")
        console.print(f"  Name: [cyan]{bo.get('name')}[/cyan]")
        log_manual_decision(
            event_type="budget_order_created",
            reason=reason_text,
            command="budget create",
            metadata={
                "budget": budget,
                "start_date": start_date,
                "end_date": end_date,
                "client_name": client_name,
                "primary_buyer_email": primary_buyer_email,
            },
            result={"budget_order": bo},
        )
    else:
        console.print("[red]Failed to create budget order.[/red]")
        raise typer.Exit(1)
