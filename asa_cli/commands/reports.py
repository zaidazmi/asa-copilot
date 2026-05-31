"""Reporting commands."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..api import SearchAdsClient
from ..config import (
    CampaignType,
    RulesLoadError,
    detect_campaign_type,
    filter_campaigns_for_app,
    get_current_app_config,
    is_multi_app,
    load_credentials,
    load_rules,
    parse_campaign_name,
)
from ..plans import ChangePlan, save_plan
from ..operator_reports import build_operator_report
from ..recommendations import build_keyword_recommendations, keyword_report_row_to_metrics

app = typer.Typer(help="Reporting and analytics commands")
console = Console()


def parse_date(date_str: str) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    return datetime.strptime(date_str, "%Y-%m-%d")


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format currency for display."""
    return f"${amount:,.2f}"


def format_number(num: float) -> str:
    """Format number with commas."""
    if num >= 1000:
        return f"{num:,.0f}"
    return f"{num:.2f}" if num % 1 else str(int(num))


def _resolve_app_name() -> Optional[str]:
    """Get the app_name for campaign scoping (None if single-app)."""
    if not is_multi_app():
        return None
    app_config = get_current_app_config()
    return app_config.app_name if app_config else None


def get_campaign_type_label(campaign_name: str, app_name: Optional[str] = None) -> str:
    """Get campaign type label from name, supporting both simple and managed naming."""
    ctype = detect_campaign_type(campaign_name)
    if ctype:
        return ctype.value.upper()
    return campaign_name[:15]


def _filter_current_app_campaigns(client: SearchAdsClient) -> tuple[list[dict], Optional[str]]:
    """Fetch campaigns, scoped to the active app when multi-app config is in use."""
    campaigns = client.get_campaigns()
    app_config = get_current_app_config()
    app_name = _resolve_app_name()
    campaigns = filter_campaigns_for_app(campaigns, app_config)
    return campaigns, app_name


def _scope_campaigns(campaigns: list[dict]) -> list[dict]:
    """Scope campaign lists to the active app by adamId."""
    return filter_campaigns_for_app(campaigns, get_current_app_config())


def _display_operator_report(report: dict, title: str) -> None:
    """Render a compact operator report."""
    totals = report["totals"]
    console.print(
        Panel(
            f"[bold]{title}[/bold]\n"
            f"{report['start_date']} to {report['end_date']} | Target CPA: {format_currency(report['target_cpa'])}",
            expand=False,
        )
    )
    console.print(
        f"Spend: [bold]{format_currency(totals['spend'])}[/bold] | "
        f"Installs: [bold]{format_number(totals['installs'])}[/bold] | "
        f"CPA: [bold]{format_currency(totals['cpa']) if totals['cpa'] is not None else '-'}[/bold]"
    )

    table = Table(title="Campaigns", show_header=True, header_style="bold magenta")
    table.add_column("Campaign")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Impr", justify="right")
    table.add_column("Taps", justify="right")
    table.add_column("Inst", justify="right")
    table.add_column("Spend", justify="right")
    table.add_column("CPA", justify="right")

    for campaign in report["campaigns"]:
        cpa = campaign["cpa"]
        table.add_row(
            campaign["campaign_name"][:36],
            (campaign["campaign_type"] or "-").upper(),
            campaign["display_status"],
            format_number(campaign["impressions"]),
            format_number(campaign["taps"]),
            format_number(campaign["installs"]),
            format_currency(campaign["spend"]),
            format_currency(cpa) if cpa is not None else "-",
        )

    console.print(table)

    if report["next_actions"]:
        action_table = Table(title="Next Actions", show_header=True, header_style="bold cyan")
        action_table.add_column("Type")
        action_table.add_column("Campaign")
        action_table.add_column("Reason")
        for action in report["next_actions"][:10]:
            action_table.add_row(
                action["type"],
                action.get("campaign_name") or str(action.get("campaign_id") or "-"),
                action.get("reason") or "",
            )
        console.print(action_table)
    else:
        console.print("[green]No pacing actions recommended.[/green]")


def _run_operator_report(
    *,
    title: str,
    days: int,
    output_json: bool,
    out: Optional[Path],
    rules_file: Optional[Path],
) -> None:
    """Shared implementation for daily and weekly reports."""
    if days <= 0:
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
    campaigns, app_name = _filter_current_app_campaigns(client)
    report = build_operator_report(
        client,
        campaigns=campaigns,
        days=days,
        app_name=app_name,
        rules=rules,
    )

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        if not output_json:
            console.print(f"[green]Report saved to {out}[/green]")
            return

    if output_json:
        print(json.dumps(report, indent=2))
        return

    _display_operator_report(report, title)


@app.command("daily")
def report_daily(
    days: int = typer.Option(1, "--days", "-d", help="Days to include"),
    output_json: bool = typer.Option(False, "--json", help="Output report JSON"),
    out: Optional[Path] = typer.Option(None, "--out", help="Write report JSON to this path"),
    rules_file: Optional[Path] = typer.Option(
        None, "--rules", help="JSON or YAML rule file overriding app config defaults"
    ),
):
    """Show a daily operator report with pacing next actions."""
    _run_operator_report(
        title="Daily Operator Report",
        days=days,
        output_json=output_json,
        out=out,
        rules_file=rules_file,
    )


@app.command("weekly")
def report_weekly(
    days: int = typer.Option(7, "--days", "-d", help="Days to include"),
    output_json: bool = typer.Option(False, "--json", help="Output report JSON"),
    out: Optional[Path] = typer.Option(None, "--out", help="Write report JSON to this path"),
    rules_file: Optional[Path] = typer.Option(
        None, "--rules", help="JSON or YAML rule file overriding app config defaults"
    ),
):
    """Show a weekly operator report with pacing next actions."""
    _run_operator_report(
        title="Weekly Operator Report",
        days=days,
        output_json=output_json,
        out=out,
        rules_file=rules_file,
    )


@app.command("summary")
def report_summary(
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Number of days to report"),
    start_date: Optional[str] = typer.Option(None, "--start", help="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--end", help="End date (YYYY-MM-DD)"),
    all_campaigns: bool = typer.Option(
        True, "--all/--managed-only", "-a", help="Include all campaigns (default) or only managed"
    ),
    rules_file: Optional[Path] = typer.Option(
        None, "--rules", help="JSON or YAML rule file overriding app config defaults"
    ),
):
    """Show performance summary across all campaigns."""
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
    if days is None:
        days = rules.reporting.summary_days
    if days <= 0:
        console.print("[red]Days must be a positive integer.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    # Determine date range
    end = parse_date(end_date) if end_date else datetime.now()
    start = parse_date(start_date) if start_date else (end - timedelta(days=days))

    console.print(
        Panel(
            f"[bold]Performance Summary[/bold]\n{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
            expand=False,
        )
    )

    with console.status("[bold blue]Fetching campaigns..."):
        campaigns = client.get_campaigns()

    app_name = _resolve_app_name()

    campaigns = _scope_campaigns(campaigns)

    # Filter campaigns based on flag
    if all_campaigns:
        campaign_list = [
            (c, get_campaign_type_label(c.get("name", ""), app_name=app_name)) for c in campaigns
        ]
    else:
        # Only managed campaigns with specific naming
        managed = [(c, parse_campaign_name(c.get("name", ""))) for c in campaigns]
        campaign_list = [(c, p[1].value.upper()) for c, p in managed if p]

    if not campaign_list:
        console.print("[yellow]No campaigns found.[/yellow]")
        return

    table = Table(title="Campaign Performance", show_header=True, header_style="bold magenta")
    table.add_column("Campaign")
    table.add_column("Status")
    table.add_column("Impressions", justify="right")
    table.add_column("Taps", justify="right")
    table.add_column("TTR", justify="right")
    table.add_column("Installs", justify="right")
    table.add_column("CVR", justify="right")
    table.add_column("Spend", justify="right")
    table.add_column("CPA", justify="right")

    totals = {
        "impressions": 0,
        "taps": 0,
        "installs": 0,
        "spend": 0.0,
    }

    for campaign, ctype_label in campaign_list:
        campaign_id = campaign.get("id")
        campaign_name = campaign.get("name", "Unknown")

        with console.status(f"[bold blue]Fetching {campaign_name} report..."):
            report_data = client.get_campaign_report(campaign_id, start, end, granularity="DAILY")

        # Aggregate metrics
        impressions = 0
        taps = 0
        installs = 0
        spend = 0.0

        for row in report_data:
            # Metrics are in 'total' key, not 'metadata'
            metrics = row.get("total", {})
            impressions += metrics.get("impressions", 0)
            taps += metrics.get("taps", 0)
            installs += metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0)
            spend_data = metrics.get("localSpend", {})
            spend += float(spend_data.get("amount", 0)) if spend_data else 0

        # Calculate rates
        ttr = (taps / impressions * 100) if impressions > 0 else 0
        cvr = (installs / taps * 100) if taps > 0 else 0
        cpa = (spend / installs) if installs > 0 else 0

        status = campaign.get("displayStatus", "UNKNOWN")
        status_style = "green" if status == "RUNNING" else "yellow" if status == "PAUSED" else "red"

        table.add_row(
            ctype_label,
            f"[{status_style}]{status}[/{status_style}]",
            format_number(impressions),
            format_number(taps),
            f"{ttr:.2f}%",
            format_number(installs),
            f"{cvr:.2f}%",
            format_currency(spend),
            format_currency(cpa) if installs > 0 else "-",
        )

        # Accumulate totals
        totals["impressions"] += impressions
        totals["taps"] += taps
        totals["installs"] += installs
        totals["spend"] += spend

    # Add totals row
    total_ttr = (totals["taps"] / totals["impressions"] * 100) if totals["impressions"] > 0 else 0
    total_cvr = (totals["installs"] / totals["taps"] * 100) if totals["taps"] > 0 else 0
    total_cpa = (totals["spend"] / totals["installs"]) if totals["installs"] > 0 else 0

    table.add_row(
        "[bold]TOTAL[/bold]",
        "",
        f"[bold]{format_number(totals['impressions'])}[/bold]",
        f"[bold]{format_number(totals['taps'])}[/bold]",
        f"[bold]{total_ttr:.2f}%[/bold]",
        f"[bold]{format_number(totals['installs'])}[/bold]",
        f"[bold]{total_cvr:.2f}%[/bold]",
        f"[bold]{format_currency(totals['spend'])}[/bold]",
        f"[bold]{format_currency(total_cpa)}[/bold]" if totals["installs"] > 0 else "-",
    )

    console.print(table)


@app.command("keywords")
def report_keywords(
    campaign_id: Optional[int] = typer.Option(None, "--campaign", "-c", help="Campaign ID"),
    days: int = typer.Option(30, "--days", "-d", help="Number of days"),
    min_impressions: int = typer.Option(0, "--min-impressions", help="Minimum impressions filter"),
    sort_by: str = typer.Option(
        "spend", "--sort", "-s", help="Sort by: spend, impressions, taps, installs, cpa"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Max keywords to show"),
):
    """Show keyword performance report."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    end = datetime.now()
    start = end - timedelta(days=days)

    # Select campaign if not provided
    if campaign_id is None:
        campaigns = client.get_campaigns()
        app_name = _resolve_app_name()

        campaigns = _scope_campaigns(campaigns)

        if not campaigns:
            console.print("[yellow]No campaigns found.[/yellow]")
            return

        table = Table(show_header=True)
        table.add_column("#", style="cyan")
        table.add_column("Type")
        table.add_column("Name")

        for idx, c in enumerate(campaigns, 1):
            ctype = get_campaign_type_label(c.get("name", ""), app_name=app_name)
            table.add_row(str(idx), ctype, c.get("name", "")[:50])

        console.print(table)

        from rich.prompt import Prompt

        choice = Prompt.ask("Select campaign number")
        if not choice.isdigit() or not (1 <= int(choice) <= len(campaigns)):
            console.print("[red]Invalid selection.[/red]")
            return
        campaign_id = campaigns[int(choice) - 1].get("id")

    with console.status("[bold blue]Fetching keyword report..."):
        report_data = client.get_keyword_report(campaign_id, start, end)

    if not report_data:
        console.print("[yellow]No keyword data found.[/yellow]")
        return

    # Process and filter
    keywords = []
    for row in report_data:
        metadata = row.get("metadata", {})
        metrics = row.get("total", {})
        impressions = metrics.get("impressions", 0)

        if impressions < min_impressions:
            continue

        taps = metrics.get("taps", 0)
        installs = metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0)
        spend_data = metrics.get("localSpend", {})
        spend = float(spend_data.get("amount", 0)) if spend_data else 0

        keywords.append(
            {
                "keyword": metadata.get("keyword", "?"),
                "match_type": metadata.get("matchType", "?"),
                "impressions": impressions,
                "taps": taps,
                "installs": installs,
                "spend": spend,
                "ttr": (taps / impressions * 100) if impressions > 0 else 0,
                "cvr": (installs / taps * 100) if taps > 0 else 0,
                "cpa": (spend / installs) if installs > 0 else float("inf"),
            }
        )

    # Sort
    sort_key = {
        "spend": lambda x: -x["spend"],
        "impressions": lambda x: -x["impressions"],
        "taps": lambda x: -x["taps"],
        "installs": lambda x: -x["installs"],
        "cpa": lambda x: x["cpa"] if x["cpa"] != float("inf") else 999999,
    }.get(sort_by, lambda x: -x["spend"])

    keywords.sort(key=sort_key)
    keywords = keywords[:limit]

    console.print(
        Panel(
            f"[bold]Keyword Performance[/bold]\n"
            f"Last {days} days • Sorted by {sort_by} • Min impressions: {min_impressions}",
            expand=False,
        )
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Keyword")
    table.add_column("Match", style="dim")
    table.add_column("Impr", justify="right")
    table.add_column("Taps", justify="right")
    table.add_column("TTR", justify="right")
    table.add_column("Inst", justify="right")
    table.add_column("CVR", justify="right")
    table.add_column("Spend", justify="right")
    table.add_column("CPA", justify="right")

    for kw in keywords:
        cpa_str = format_currency(kw["cpa"]) if kw["cpa"] != float("inf") else "-"
        table.add_row(
            kw["keyword"][:30],
            kw["match_type"][:5],
            format_number(kw["impressions"]),
            format_number(kw["taps"]),
            f"{kw['ttr']:.1f}%",
            format_number(kw["installs"]),
            f"{kw['cvr']:.1f}%",
            format_currency(kw["spend"]),
            cpa_str,
        )

    console.print(table)


@app.command("adgroups")
def report_adgroups(
    campaign_id: Optional[int] = typer.Option(None, "--campaign", "-c", help="Campaign ID"),
    days: int = typer.Option(30, "--days", "-d", help="Number of days"),
    all_campaigns: bool = typer.Option(
        False, "--all", "-a", help="Show ad groups for all campaigns"
    ),
):
    """Show ad group performance report."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    end = datetime.now()
    start = end - timedelta(days=days)

    # Get campaigns to report on
    campaigns_to_report = []
    app_name = _resolve_app_name()

    def _filter_by_app(campaigns: list) -> list:
        return _scope_campaigns(campaigns)

    if all_campaigns:
        campaigns = _filter_by_app(client.get_campaigns())
        campaigns_to_report = campaigns
    elif campaign_id:
        campaign = client.get_campaign(campaign_id)
        if campaign:
            campaigns_to_report = [campaign]
        else:
            console.print(f"[red]Campaign {campaign_id} not found.[/red]")
            raise typer.Exit(1)
    else:
        # Interactive selection
        campaigns = _filter_by_app(client.get_campaigns())
        if not campaigns:
            console.print("[yellow]No campaigns found.[/yellow]")
            return

        table = Table(show_header=True)
        table.add_column("#", style="cyan")
        table.add_column("Type")
        table.add_column("Name")

        for idx, c in enumerate(campaigns, 1):
            ctype = get_campaign_type_label(c.get("name", ""), app_name=app_name)
            table.add_row(str(idx), ctype, c.get("name", "")[:50])

        console.print(table)

        from rich.prompt import Prompt

        choice = Prompt.ask("Select campaign number (or 'all')")
        if choice.lower() == "all":
            campaigns_to_report = campaigns
        elif choice.isdigit() and 1 <= int(choice) <= len(campaigns):
            campaigns_to_report = [campaigns[int(choice) - 1]]
        else:
            console.print("[red]Invalid selection.[/red]")
            return

    console.print(
        Panel(
            f"[bold]Ad Group Performance[/bold]\n" f"Last {days} days",
            expand=False,
        )
    )

    for campaign in campaigns_to_report:
        cid = campaign.get("id")
        cname = campaign.get("name", "Unknown")
        ctype = get_campaign_type_label(cname, app_name=_resolve_app_name())

        with console.status(f"[bold blue]Fetching {cname} ad group report..."):
            report_data = client.get_ad_group_report(cid, start, end)

        if not report_data:
            console.print(f"[yellow]{ctype}: No ad group data[/yellow]")
            continue

        table = Table(title=f"{ctype} - Ad Groups", show_header=True, header_style="bold magenta")
        table.add_column("Ad Group")
        table.add_column("Status")
        table.add_column("Impr", justify="right")
        table.add_column("Taps", justify="right")
        table.add_column("TTR", justify="right")
        table.add_column("Inst", justify="right")
        table.add_column("CVR", justify="right")
        table.add_column("Spend", justify="right")
        table.add_column("CPA", justify="right")

        campaign_totals = {"impressions": 0, "taps": 0, "installs": 0, "spend": 0.0}

        for row in report_data:
            metadata = row.get("metadata", {})
            metrics = row.get("total", {})

            ag_name = metadata.get("adGroupName", "Unknown")
            ag_status = metadata.get("adGroupStatus", "?")

            impressions = metrics.get("impressions", 0)
            taps = metrics.get("taps", 0)
            installs = metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0)
            spend_data = metrics.get("localSpend", {})
            spend = float(spend_data.get("amount", 0)) if spend_data else 0

            ttr = (taps / impressions * 100) if impressions > 0 else 0
            cvr = (installs / taps * 100) if taps > 0 else 0
            cpa = (spend / installs) if installs > 0 else 0

            status_style = (
                "green" if ag_status == "ENABLED" else "yellow" if ag_status == "PAUSED" else "dim"
            )

            table.add_row(
                ag_name[:25],
                f"[{status_style}]{ag_status}[/{status_style}]",
                format_number(impressions),
                format_number(taps),
                f"{ttr:.1f}%",
                format_number(installs),
                f"{cvr:.1f}%",
                format_currency(spend),
                format_currency(cpa) if installs > 0 else "-",
            )

            campaign_totals["impressions"] += impressions
            campaign_totals["taps"] += taps
            campaign_totals["installs"] += installs
            campaign_totals["spend"] += spend

        # Add campaign totals
        total_ttr = (
            (campaign_totals["taps"] / campaign_totals["impressions"] * 100)
            if campaign_totals["impressions"] > 0
            else 0
        )
        total_cvr = (
            (campaign_totals["installs"] / campaign_totals["taps"] * 100)
            if campaign_totals["taps"] > 0
            else 0
        )
        total_cpa = (
            (campaign_totals["spend"] / campaign_totals["installs"])
            if campaign_totals["installs"] > 0
            else 0
        )

        table.add_row(
            "[bold]Total[/bold]",
            "",
            f"[bold]{format_number(campaign_totals['impressions'])}[/bold]",
            f"[bold]{format_number(campaign_totals['taps'])}[/bold]",
            f"[bold]{total_ttr:.1f}%[/bold]",
            f"[bold]{format_number(campaign_totals['installs'])}[/bold]",
            f"[bold]{total_cvr:.1f}%[/bold]",
            f"[bold]{format_currency(campaign_totals['spend'])}[/bold]",
            (
                f"[bold]{format_currency(total_cpa)}[/bold]"
                if campaign_totals["installs"] > 0
                else "-"
            ),
        )

        console.print(table)
        console.print()


@app.command("impression-share")
def report_impression_share(
    campaign_id: Optional[int] = typer.Option(None, "--campaign", "-c", help="Campaign ID"),
    days: int = typer.Option(30, "--days", "-d", help="Number of days"),
    min_impressions: int = typer.Option(
        100, "--min-impressions", help="Minimum impressions filter"
    ),
    sort_by: str = typer.Option(
        "impressions", "--sort", "-s", help="Sort by: impressions, taps, spend, ttr"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Max keywords to show"),
    all_campaigns: bool = typer.Option(
        False, "--all", "-a", help="Show impression share for all campaigns"
    ),
):
    """Show impression share (Share of Voice) report for keywords.

    Displays how your keywords perform relative to the total available
    impressions in the market. Higher TTR (Tap-Through Rate) with low
    impression share suggests an opportunity to increase bids.
    """
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    end = datetime.now()
    start = end - timedelta(days=days)

    # Get campaigns to report on
    campaigns_to_report = []
    app_name = _resolve_app_name()

    def _filter_by_app(campaigns: list) -> list:
        return _scope_campaigns(campaigns)

    if all_campaigns:
        campaigns = _filter_by_app(client.get_campaigns())
        campaigns_to_report = campaigns
    elif campaign_id:
        campaign = client.get_campaign(campaign_id)
        if campaign:
            campaigns_to_report = [campaign]
        else:
            console.print(f"[red]Campaign {campaign_id} not found.[/red]")
            raise typer.Exit(1)
    else:
        # Interactive selection
        campaigns = _filter_by_app(client.get_campaigns())
        if not campaigns:
            console.print("[yellow]No campaigns found.[/yellow]")
            return

        table = Table(show_header=True)
        table.add_column("#", style="cyan")
        table.add_column("Type")
        table.add_column("Name")

        for idx, c in enumerate(campaigns, 1):
            ctype = get_campaign_type_label(c.get("name", ""), app_name=app_name)
            table.add_row(str(idx), ctype, c.get("name", "")[:50])

        console.print(table)

        from rich.prompt import Prompt

        choice = Prompt.ask("Select campaign number (or 'all')")
        if choice.lower() == "all":
            campaigns_to_report = campaigns
        elif choice.isdigit() and 1 <= int(choice) <= len(campaigns):
            campaigns_to_report = [campaigns[int(choice) - 1]]
        else:
            console.print("[red]Invalid selection.[/red]")
            return

    console.print(
        Panel(
            f"[bold]Impression Share Report[/bold]\n"
            f"Last {days} days • Min impressions: {min_impressions}",
            expand=False,
        )
    )

    for campaign in campaigns_to_report:
        cid = campaign.get("id")
        cname = campaign.get("name", "Unknown")
        ctype = get_campaign_type_label(cname, app_name=_resolve_app_name())

        with console.status(f"[bold blue]Fetching {cname} impression share data..."):
            report_data = client.get_impression_share_report(cid, start, end)

        if not report_data:
            console.print(f"[yellow]{ctype}: No impression share data[/yellow]")
            continue

        # Process and filter keywords
        keywords = []
        for row in report_data:
            metadata = row.get("metadata", {})
            metrics = row.get("total", {})

            impressions = metrics.get("impressions", 0)
            if impressions < min_impressions:
                continue

            taps = metrics.get("taps", 0)
            installs = metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0)
            spend_data = metrics.get("localSpend", {})
            spend = float(spend_data.get("amount", 0)) if spend_data else 0

            # Calculate metrics
            ttr = (taps / impressions * 100) if impressions > 0 else 0
            cvr = (installs / taps * 100) if taps > 0 else 0
            cpa = (spend / installs) if installs > 0 else 0

            keywords.append(
                {
                    "keyword": metadata.get("keyword", "?"),
                    "match_type": metadata.get("matchType", "?"),
                    "status": metadata.get("keywordStatus", "?"),
                    "impressions": impressions,
                    "taps": taps,
                    "ttr": ttr,
                    "installs": installs,
                    "cvr": cvr,
                    "spend": spend,
                    "cpa": cpa,
                }
            )

        # Sort
        sort_key = {
            "impressions": lambda x: -x["impressions"],
            "taps": lambda x: -x["taps"],
            "spend": lambda x: -x["spend"],
            "ttr": lambda x: -x["ttr"],
        }.get(sort_by, lambda x: -x["impressions"])

        keywords.sort(key=sort_key)
        keywords = keywords[:limit]

        if not keywords:
            console.print(f"[yellow]{ctype}: No keywords met filter criteria[/yellow]")
            continue

        table = Table(
            title=f"{ctype} - Impression Share", show_header=True, header_style="bold magenta"
        )
        table.add_column("Keyword")
        table.add_column("Match", style="dim")
        table.add_column("Status")
        table.add_column("Impr", justify="right")
        table.add_column("Taps", justify="right")
        table.add_column("TTR", justify="right")
        table.add_column("Inst", justify="right")
        table.add_column("CVR", justify="right")
        table.add_column("Spend", justify="right")
        table.add_column("CPA", justify="right")

        # Calculate totals
        total_impressions = sum(k["impressions"] for k in keywords)
        total_taps = sum(k["taps"] for k in keywords)
        total_installs = sum(k["installs"] for k in keywords)
        total_spend = sum(k["spend"] for k in keywords)

        for kw in keywords:
            # Impression share within this campaign (relative to top keyword)
            status_style = (
                "green"
                if kw["status"] == "ACTIVE"
                else "yellow" if kw["status"] == "PAUSED" else "dim"
            )

            # Color TTR based on performance
            ttr_str = f"{kw['ttr']:.1f}%"
            if kw["ttr"] >= 10:
                ttr_str = f"[green]{ttr_str}[/green]"
            elif kw["ttr"] >= 5:
                ttr_str = f"[yellow]{ttr_str}[/yellow]"

            table.add_row(
                kw["keyword"][:25],
                kw["match_type"][:5],
                f"[{status_style}]{kw['status'][:6]}[/{status_style}]",
                format_number(kw["impressions"]),
                format_number(kw["taps"]),
                ttr_str,
                format_number(kw["installs"]),
                f"{kw['cvr']:.1f}%",
                format_currency(kw["spend"]),
                format_currency(kw["cpa"]) if kw["installs"] > 0 else "-",
            )

        # Add totals
        total_ttr = (total_taps / total_impressions * 100) if total_impressions > 0 else 0
        total_cvr = (total_installs / total_taps * 100) if total_taps > 0 else 0
        total_cpa = (total_spend / total_installs) if total_installs > 0 else 0

        table.add_row(
            "[bold]Total[/bold]",
            "",
            "",
            f"[bold]{format_number(total_impressions)}[/bold]",
            f"[bold]{format_number(total_taps)}[/bold]",
            f"[bold]{total_ttr:.1f}%[/bold]",
            f"[bold]{format_number(total_installs)}[/bold]",
            f"[bold]{total_cvr:.1f}%[/bold]",
            f"[bold]{format_currency(total_spend)}[/bold]",
            f"[bold]{format_currency(total_cpa)}[/bold]" if total_installs > 0 else "-",
        )

        console.print(table)

        # Insights
        high_ttr_low_impr = [
            k for k in keywords if k["ttr"] >= 8 and k["impressions"] < total_impressions * 0.1
        ]
        if high_ttr_low_impr:
            console.print(
                "\n[bold cyan]💡 Opportunity:[/bold cyan] Keywords with high TTR but low impression share:"
            )
            for kw in high_ttr_low_impr[:3]:
                console.print(
                    f"  • {kw['keyword']} (TTR: {kw['ttr']:.1f}%) - Consider increasing bid"
                )

        console.print()


@app.command("search-terms")
def report_search_terms(
    campaign_id: Optional[int] = typer.Option(None, "--campaign", "-c", help="Campaign ID"),
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Number of days"),
    min_impressions: Optional[int] = typer.Option(
        None, "--min-impressions", help="Minimum impressions filter"
    ),
    show_winners: bool = typer.Option(
        False, "--winners", "-w", help="Show potential keywords to promote"
    ),
    show_negatives: bool = typer.Option(
        False, "--negatives", "-n", help="Show potential negative keywords"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Max terms to show"),
    rules_file: Optional[Path] = typer.Option(
        None, "--rules", help="JSON or YAML rule file overriding app config defaults"
    ),
):
    """Show search terms report - discover new keywords and negatives."""
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
    if days is None:
        days = rules.reporting.search_terms_days
    if min_impressions is None:
        min_impressions = rules.reporting.min_impressions
    if days <= 0:
        console.print("[red]Days must be a positive integer.[/red]")
        raise typer.Exit(1)
    if min_impressions < 0:
        console.print("[red]Minimum impressions must be zero or greater.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    end = datetime.now()
    start = end - timedelta(days=days)

    # Find Discovery campaign if not specified
    if campaign_id is None:
        campaigns = client.get_campaigns()
        app_name = _resolve_app_name()

        campaigns = _scope_campaigns(campaigns)

        discovery = None
        for c in campaigns:
            name = c.get("name", "")
            parsed = parse_campaign_name(name)
            # Support both managed naming and simple naming (e.g., "Discovery")
            if (parsed and parsed[1] == CampaignType.DISCOVERY) or "discovery" in name.lower():
                discovery = c
                break

        if discovery:
            campaign_id = discovery.get("id")
            console.print(f"Using Discovery campaign: {discovery.get('name')}")
        else:
            # Select any campaign
            if not campaigns:
                console.print("[yellow]No campaigns found.[/yellow]")
                return

            from rich.prompt import Prompt

            table = Table(show_header=True)
            table.add_column("#", style="cyan")
            table.add_column("Type")
            table.add_column("Name")

            for idx, c in enumerate(campaigns, 1):
                ctype = get_campaign_type_label(c.get("name", ""), app_name=app_name)
                table.add_row(str(idx), ctype, c.get("name", "")[:50])

            console.print(table)
            choice = Prompt.ask("Select campaign number")
            if not choice.isdigit() or not (1 <= int(choice) <= len(campaigns)):
                console.print("[red]Invalid selection.[/red]")
                return
            campaign_id = campaigns[int(choice) - 1].get("id")

    with console.status("[bold blue]Fetching search terms report..."):
        report_data = client.get_search_terms_report(campaign_id, start, end)

    if not report_data:
        console.print("[yellow]No search term data found.[/yellow]")
        return

    # Process terms
    terms = []
    for row in report_data:
        metadata = row.get("metadata", {})
        metrics = row.get("total", {})
        impressions = metrics.get("impressions", 0)

        if impressions < min_impressions:
            continue

        taps = metrics.get("taps", 0)
        installs = metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0)
        spend_data = metrics.get("localSpend", {})
        spend = float(spend_data.get("amount", 0)) if spend_data else 0

        # searchTermText may be None for keyword-level data; use keyword as fallback
        term_text = metadata.get("searchTermText") or metadata.get("keyword") or "?"
        terms.append(
            {
                "term": term_text,
                "source": metadata.get("searchTermSource", "?"),
                "impressions": impressions,
                "taps": taps,
                "installs": installs,
                "spend": spend,
                "ttr": (taps / impressions * 100) if impressions > 0 else 0,
                "cvr": (installs / taps * 100) if taps > 0 else 0,
                "cpa": (spend / installs) if installs > 0 else float("inf"),
            }
        )

    if show_winners:
        # Filter to terms with installs and reasonable CPA
        winners = [t for t in terms if t["installs"] >= 1]
        winners.sort(key=lambda x: x["cpa"] if x["cpa"] != float("inf") else 999999)
        terms = winners[:limit]
        title = "Potential Keywords to Promote"
    elif show_negatives:
        # Filter to terms with spend but no installs
        losers = [t for t in terms if t["installs"] == 0 and t["spend"] > 0]
        losers.sort(key=lambda x: -x["spend"])
        terms = losers[:limit]
        title = "Potential Negative Keywords"
    else:
        terms.sort(key=lambda x: -x["spend"])
        terms = terms[:limit]
        title = "Search Terms"

    console.print(
        Panel(
            f"[bold]{title}[/bold]\nLast {days} days • Min impressions: {min_impressions}",
            expand=False,
        )
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Search Term")
    table.add_column("Source", style="dim")
    table.add_column("Impr", justify="right")
    table.add_column("Taps", justify="right")
    table.add_column("Inst", justify="right")
    table.add_column("Spend", justify="right")
    table.add_column("CPA", justify="right")

    for t in terms:
        cpa_str = format_currency(t["cpa"]) if t["cpa"] != float("inf") else "-"

        # Color code based on performance
        if t["installs"] > 0 and t["cpa"] != float("inf"):
            term_style = "green" if t["cpa"] < 5 else "yellow" if t["cpa"] < 10 else ""
        elif t["spend"] > 1 and t["installs"] == 0:
            term_style = "red"
        else:
            term_style = ""

        term_display = (
            f"[{term_style}]{t['term'][:35]}[/{term_style}]" if term_style else t["term"][:35]
        )

        table.add_row(
            term_display,
            t["source"][:10],
            format_number(t["impressions"]),
            format_number(t["taps"]),
            format_number(t["installs"]),
            format_currency(t["spend"]),
            cpa_str,
        )

    console.print(table)

    if show_winners and terms:
        console.print("\n[bold]To promote these keywords:[/bold]")
        keyword_list = ",".join([t["term"] for t in terms[:10]])
        console.print(f'[cyan]asa keywords promote "{keyword_list}" --target category[/cyan]')
    elif show_negatives and terms:
        console.print("\n[bold]To add as negatives:[/bold]")
        keyword_list = ",".join([t["term"] for t in terms[:10]])
        console.print(f'[cyan]asa keywords add-negatives "{keyword_list}" --all[/cyan]')


@app.command("custom")
def report_custom(
    days: int = typer.Option(30, "--days", "-d", help="Number of days (max 30)"),
    name: str = typer.Option("Impression Share Report", "--name", "-n", help="Report name"),
):
    """Create a custom impression share report, poll until complete, and display results."""
    import time as _time

    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    # Cap at 30 days (API max)
    days = min(days, 30)
    end = datetime.now()
    start = end - timedelta(days=days)

    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    console.print(
        Panel(
            f"[bold]Custom Report[/bold]\n{start_str} to {end_str}",
            expand=False,
        )
    )

    with console.status("[bold blue]Creating custom report..."):
        report = client.create_custom_report(name, start_str, end_str)

    if not report:
        console.print("[red]Failed to create custom report.[/red]")
        raise typer.Exit(1)

    report_id = report.get("id")
    state = report.get("state", "UNKNOWN")
    console.print(f"Report created: [cyan]{report_id}[/cyan] (state: {state})")

    # Poll until complete (max 5 minutes)
    max_polls = 30
    poll_count = 0

    with console.status("[bold blue]Waiting for report to complete...") as status:
        while state not in ("COMPLETED", "FAILED") and poll_count < max_polls:
            _time.sleep(10)
            poll_count += 1
            status.update(f"[bold blue]Polling report status... ({poll_count}/{max_polls})")
            report = client.get_custom_report(report_id)
            if not report:
                console.print("[red]Failed to fetch report status.[/red]")
                raise typer.Exit(1)
            state = report.get("state", "UNKNOWN")

    if state == "FAILED":
        console.print("[red]Report generation failed.[/red]")
        raise typer.Exit(1)

    if state != "COMPLETED":
        console.print(
            f"[yellow]Report still processing after {max_polls * 10}s (state: {state}).[/yellow]"
        )
        console.print(f"Check later with: [cyan]asa reports custom-get {report_id}[/cyan]")
        return

    download_uri = report.get("downloadUri")
    if download_uri:
        console.print(f"[green]Report complete![/green] Download: {download_uri}")
    else:
        console.print("[green]Report complete![/green]")

    # Display available report data
    table = Table(title="Custom Report Results", show_header=True, header_style="bold magenta")
    table.add_column("Field")
    table.add_column("Value")

    for key, value in report.items():
        if key != "downloadUri":
            table.add_row(str(key), str(value)[:80])

    console.print(table)


@app.command("custom-list")
def report_custom_list():
    """List all custom reports."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    with console.status("[bold blue]Fetching custom reports..."):
        reports = client.get_all_custom_reports()

    if not reports:
        console.print("[yellow]No custom reports found.[/yellow]")
        return

    table = Table(title="Custom Reports", show_header=True, header_style="bold magenta")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Start")
    table.add_column("End")
    table.add_column("Granularity")

    for report in reports:
        state = report.get("state", "?")
        state_style = (
            "green"
            if state == "COMPLETED"
            else "yellow" if state == "QUEUED" else "blue" if state == "RUNNING" else "red"
        )

        table.add_row(
            str(report.get("id", "?")),
            report.get("name", "?")[:30],
            f"[{state_style}]{state}[/{state_style}]",
            report.get("startTime", "?")[:10],
            report.get("endTime", "?")[:10],
            report.get("granularity", "?"),
        )

    console.print(table)


@app.command("custom-get")
def report_custom_get(
    report_id: str = typer.Argument(..., help="Custom report ID"),
):
    """Get a specific custom report status and results."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    with console.status("[bold blue]Fetching custom report..."):
        report = client.get_custom_report(report_id)

    if not report:
        console.print(f"[red]Custom report {report_id} not found.[/red]")
        raise typer.Exit(1)

    state = report.get("state", "UNKNOWN")
    state_style = (
        "green"
        if state == "COMPLETED"
        else "yellow" if state == "QUEUED" else "blue" if state == "RUNNING" else "red"
    )

    console.print(
        Panel(
            f"[bold]Custom Report: {report.get('name', '?')}[/bold]\n"
            f"State: [{state_style}]{state}[/{state_style}]",
            expand=False,
        )
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Field")
    table.add_column("Value")

    for key, value in report.items():
        table.add_row(str(key), str(value)[:100])

    console.print(table)

    if state == "COMPLETED" and report.get("downloadUri"):
        console.print(f"\n[green]Download URI:[/green] {report['downloadUri']}")


@app.command("ads")
def report_ads(
    campaign_id: Optional[int] = typer.Option(None, "--campaign", "-c", help="Campaign ID"),
    days: int = typer.Option(14, "--days", "-d", help="Number of days"),
    all_campaigns: bool = typer.Option(
        False, "--all", "-a", help="Show ad report for all campaigns"
    ),
):
    """Show ad-level performance report."""
    credentials = load_credentials()
    if not credentials:
        console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)

    end = datetime.now()
    start = end - timedelta(days=days)

    # Get campaigns to report on
    campaigns_to_report = []
    app_name = _resolve_app_name()

    def _filter_by_app(campaigns: list) -> list:
        return _scope_campaigns(campaigns)

    if all_campaigns:
        campaigns = _filter_by_app(client.get_campaigns())
        campaigns_to_report = campaigns
    elif campaign_id:
        campaign = client.get_campaign(campaign_id)
        if campaign:
            campaigns_to_report = [campaign]
        else:
            console.print(f"[red]Campaign {campaign_id} not found.[/red]")
            raise typer.Exit(1)
    else:
        # Interactive selection
        campaigns = _filter_by_app(client.get_campaigns())
        if not campaigns:
            console.print("[yellow]No campaigns found.[/yellow]")
            return

        table = Table(show_header=True)
        table.add_column("#", style="cyan")
        table.add_column("Type")
        table.add_column("Name")

        for idx, c in enumerate(campaigns, 1):
            ctype = get_campaign_type_label(c.get("name", ""), app_name=app_name)
            table.add_row(str(idx), ctype, c.get("name", "")[:50])

        console.print(table)

        from rich.prompt import Prompt

        choice = Prompt.ask("Select campaign number (or 'all')")
        if choice.lower() == "all":
            campaigns_to_report = campaigns
        elif choice.isdigit() and 1 <= int(choice) <= len(campaigns):
            campaigns_to_report = [campaigns[int(choice) - 1]]
        else:
            console.print("[red]Invalid selection.[/red]")
            return

    console.print(
        Panel(
            f"[bold]Ad Performance Report[/bold]\nLast {days} days",
            expand=False,
        )
    )

    for campaign in campaigns_to_report:
        cid = campaign.get("id")
        cname = campaign.get("name", "Unknown")
        ctype = get_campaign_type_label(cname, app_name=_resolve_app_name())

        with console.status(f"[bold blue]Fetching {cname} ad report..."):
            report_data = client.get_ad_report(cid, start, end)

        if not report_data:
            console.print(f"[yellow]{ctype}: No ad data[/yellow]")
            continue

        table = Table(title=f"{ctype} - Ads", show_header=True, header_style="bold magenta")
        table.add_column("Ad Name")
        table.add_column("Status")
        table.add_column("Impr", justify="right")
        table.add_column("Taps", justify="right")
        table.add_column("TTR", justify="right")
        table.add_column("Inst", justify="right")
        table.add_column("CVR", justify="right")
        table.add_column("Spend", justify="right")
        table.add_column("CPA", justify="right")

        for row in report_data:
            metadata = row.get("metadata", {})
            metrics = row.get("total", {})

            ad_name = metadata.get("adName", "Unknown")
            ad_status = metadata.get("adStatus", "?")

            impressions = metrics.get("impressions", 0)
            taps = metrics.get("taps", 0)
            installs = metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0)
            spend_data = metrics.get("localSpend", {})
            spend = float(spend_data.get("amount", 0)) if spend_data else 0

            ttr = (taps / impressions * 100) if impressions > 0 else 0
            cvr = (installs / taps * 100) if taps > 0 else 0
            cpa = (spend / installs) if installs > 0 else 0

            status_style = (
                "green" if ad_status == "ENABLED" else "yellow" if ad_status == "PAUSED" else "dim"
            )

            table.add_row(
                ad_name[:30],
                f"[{status_style}]{ad_status}[/{status_style}]",
                format_number(impressions),
                format_number(taps),
                f"{ttr:.1f}%",
                format_number(installs),
                f"{cvr:.1f}%",
                format_currency(spend),
                format_currency(cpa) if installs > 0 else "-",
            )

        console.print(table)
        console.print()


@app.command("bid-recommendations")
def report_bid_recommendations(
    campaign_id: Optional[int] = typer.Option(None, "--campaign", "-c", help="Campaign ID"),
    days: int = typer.Option(14, "--days", "-d", help="Number of days"),
    all_campaigns: bool = typer.Option(False, "--all", "-a", help="Show bids for all campaigns"),
    rules_file: Optional[Path] = typer.Option(
        None, "--rules", help="JSON or YAML rule file overriding app config defaults"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output rule recommendations as JSON"),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write bid/pause recommendations to a plan JSON file"
    ),
):
    """Show Apple's suggested bid amounts vs current bids for keywords.

    For each campaign and ad group, fetches the keyword report with bid
    recommendation insights. Displays a color-coded table showing where
    your bids are below Apple's suggestions.
    """
    credentials = load_credentials()
    if not credentials:
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

    end = datetime.now()
    start = end - timedelta(days=days)

    # Get campaigns to report on
    campaigns_to_report = []
    app_name = _resolve_app_name()
    keyword_rows = []

    def _filter_by_app(campaigns: list) -> list:
        return _scope_campaigns(campaigns)

    if all_campaigns:
        campaigns = _filter_by_app(client.get_campaigns())
        campaigns_to_report = campaigns
    elif campaign_id:
        campaign = client.get_campaign(campaign_id)
        if campaign:
            campaigns_to_report = [campaign]
        else:
            console.print(f"[red]Campaign {campaign_id} not found.[/red]")
            raise typer.Exit(1)
    else:
        # Interactive selection
        campaigns = _filter_by_app(client.get_campaigns())
        if not campaigns:
            console.print("[yellow]No campaigns found.[/yellow]")
            return

        table = Table(show_header=True)
        table.add_column("#", style="cyan")
        table.add_column("Type")
        table.add_column("Name")

        for idx, c in enumerate(campaigns, 1):
            ctype = get_campaign_type_label(c.get("name", ""), app_name=app_name)
            table.add_row(str(idx), ctype, c.get("name", "")[:50])

        console.print(table)

        from rich.prompt import Prompt

        choice = Prompt.ask("Select campaign number (or 'all')")
        if choice.lower() == "all":
            campaigns_to_report = campaigns
        elif choice.isdigit() and 1 <= int(choice) <= len(campaigns):
            campaigns_to_report = [campaigns[int(choice) - 1]]
        else:
            console.print("[red]Invalid selection.[/red]")
            return

    if not output_json:
        console.print(
            Panel(
                f"[bold]Bid Recommendations[/bold]\nLast {days} days",
                expand=False,
            )
        )

    total_keywords = 0
    below_suggestion = 0

    for campaign in campaigns_to_report:
        cid = campaign.get("id")
        cname = campaign.get("name", "Unknown")
        ctype = get_campaign_type_label(cname, app_name=_resolve_app_name())

        if output_json:
            ad_groups = client.get_ad_groups(cid)
        else:
            with console.status(f"[bold blue]Fetching ad groups for {cname}..."):
                ad_groups = client.get_ad_groups(cid)

        if not ad_groups:
            if not output_json:
                console.print(f"[yellow]{ctype}: No ad groups found[/yellow]")
            continue

        for ag in ad_groups:
            ag_id = ag.get("id")
            ag_name = ag.get("name", "Unknown")

            keywords = client.get_keywords(cid, ag_id)
            if not keywords:
                continue

            if output_json:
                report_data = client.get_keyword_adgroup_report(cid, ag_id, start, end)
            else:
                with console.status(
                    f"[bold blue]Fetching keyword report for {cname} / {ag_name}..."
                ):
                    report_data = client.get_keyword_adgroup_report(cid, ag_id, start, end)

            if not report_data:
                continue

            # Build keyword rows with bid recommendations
            rows = []
            for row in report_data:
                metadata = row.get("metadata", {})
                insights = row.get("insights", {})
                metrics = row.get("total", {})

                keyword = metadata.get("keyword", "?")
                keyword_id = metadata.get("keywordId")

                # Current bid from metadata
                bid_data = metadata.get("bidAmount", {})
                current_bid = float(bid_data.get("amount", 0)) if bid_data else 0

                # Suggested bid from insights
                bid_rec = insights.get("bidRecommendation", {})
                suggested_data = bid_rec.get("suggestedBidAmount", {})
                suggested_bid = float(suggested_data.get("amount", 0)) if suggested_data else 0

                impressions = metrics.get("impressions", 0)
                taps = metrics.get("taps", 0)
                installs = metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0)

                rows.append(
                    {
                        "keyword": keyword,
                        "keyword_id": keyword_id,
                        "current_bid": current_bid,
                        "suggested_bid": suggested_bid,
                        "difference": suggested_bid - current_bid,
                        "impressions": impressions,
                        "taps": taps,
                        "installs": installs,
                    }
                )
                keyword_rows.append(
                    keyword_report_row_to_metrics(row, campaign=campaign, ad_group=ag)
                )

            if not rows:
                continue

            # Sort by difference (biggest gap first)
            rows.sort(key=lambda x: -x["difference"])

            if not output_json:
                table = Table(
                    title=f"{ctype} / {ag_name} - Bid Recommendations",
                    show_header=True,
                    header_style="bold magenta",
                )
                table.add_column("Keyword")
                table.add_column("Current Bid", justify="right")
                table.add_column("Suggested Bid", justify="right")
                table.add_column("Difference", justify="right")
                table.add_column("Impr", justify="right")
                table.add_column("Taps", justify="right")
                table.add_column("Inst", justify="right")

            for r in rows:
                total_keywords += 1
                diff = r["difference"]

                # Color code: green if current >= suggested, red if significantly below
                if diff <= 0:
                    bid_style = "green"
                elif diff < 0.50:
                    bid_style = "yellow"
                    below_suggestion += 1
                else:
                    bid_style = "red"
                    below_suggestion += 1

                if not output_json:
                    diff_str = f"[{bid_style}]{'+' if diff <= 0 else ''}{format_currency(abs(diff))}[/{bid_style}]"
                    if diff > 0:
                        diff_str = f"[{bid_style}]-{format_currency(diff)}[/{bid_style}]"

                    current_str = format_currency(r["current_bid"]) if r["current_bid"] > 0 else "-"
                    suggested_str = (
                        format_currency(r["suggested_bid"]) if r["suggested_bid"] > 0 else "-"
                    )

                    table.add_row(
                        r["keyword"][:30],
                        current_str,
                        suggested_str,
                        diff_str,
                        format_number(r["impressions"]),
                        format_number(r["taps"]),
                        format_number(r["installs"]),
                    )

            if not output_json:
                console.print(table)
                console.print()

    recommendations = build_keyword_recommendations(keyword_rows, rules)
    recommendation_plan = ChangePlan(
        source="bid-recommendations",
        app_name=app_name,
        lookback_days=days,
        summary=f"{len(recommendations)} keyword bid/pause recommendations",
        actions=[recommendation.to_plan_action() for recommendation in recommendations],
    )

    if output_json:
        print(json.dumps(recommendation_plan.model_dump(mode="json"), indent=2))
        return

    if out:
        save_plan(recommendation_plan, out)
        console.print(f"[green]Recommendation plan saved to {out}[/green]")
        console.print("[dim]Review with: asa plan show {path}[/dim]".format(path=out))

    # Summary
    if total_keywords > 0:
        console.print(
            Panel(
                f"[bold]Summary[/bold]\n"
                f"Total keywords: {total_keywords}\n"
                f"Below suggestion: [{'red' if below_suggestion > 0 else 'green'}]"
                f"{below_suggestion}[/{'red' if below_suggestion > 0 else 'green'}]\n"
                f"At or above: [green]{total_keywords - below_suggestion}[/green]\n"
                f"Rule recommendations: {len(recommendations)}",
                expand=False,
            )
        )
    else:
        console.print("[yellow]No keyword bid data found.[/yellow]")
