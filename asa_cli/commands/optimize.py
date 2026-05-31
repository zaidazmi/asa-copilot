"""Automated campaign optimization commands."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from ..api import SearchAdsClient
from ..config import (
    CampaignType,
    MatchType,
    RulesConfig,
    RulesLoadError,
    detect_campaign_type,
    get_current_app_config,
    is_multi_app,
    load_credentials,
    load_rules,
)
from ..plans import (
    ChangePlan,
    PlanAction,
    PlanActionType,
    apply_plan,
    display_apply_result,
    save_applied_plan,
    save_plan,
)

app = typer.Typer(help="Automated campaign optimization")
console = Console()


def format_currency(amount: float) -> str:
    """Format currency for display."""
    return f"${amount:,.2f}"


def _resolve_app_name() -> Optional[str]:
    """Get the app_name for campaign scoping (None if single-app)."""
    if not is_multi_app():
        return None
    app_config = get_current_app_config()
    return app_config.app_name if app_config else None


def get_campaigns_indexed(
    client: SearchAdsClient,
    app_name: Optional[str] = None,
) -> tuple[dict[CampaignType, dict], list[tuple[dict, CampaignType]]]:
    """Get all campaigns, indexed by type and as a list.

    Returns (campaigns_by_type, managed_list) where:
    - campaigns_by_type: dict mapping CampaignType to campaign dict
    - managed_list: list of (campaign, type) tuples for all managed campaigns

    This fetches campaigns once and organizes them for different use cases.
    """
    campaigns = client.get_campaigns()
    by_type: dict[CampaignType, dict] = {}
    managed: list[tuple[dict, CampaignType]] = []

    for c in campaigns:
        ctype = detect_campaign_type(c.get("name", ""), app_name=app_name)
        if ctype:
            by_type[ctype] = c
            managed.append((c, ctype))

    return by_type, managed


class AnalysisResult:
    """Results from search term analysis."""

    def __init__(self):
        self.winners: list[dict] = []
        self.losers: list[dict] = []
        self.total_terms: int = 0
        self.skipped_no_text: int = 0
        self.skipped_no_activity: int = 0


def analyze_search_terms(
    client: SearchAdsClient,
    campaign_id: int,
    days: int,
    cpa_threshold: float,
    min_installs: int,
    min_spend: float,
    min_impressions: int = 0,
    exclude_terms: Optional[list[str]] = None,
) -> AnalysisResult:
    """Analyze search terms and categorize into winners and losers.

    Returns AnalysisResult with:
    - winners: terms with installs >= min_installs AND CPA <= cpa_threshold
    - losers: terms with spend >= min_spend AND installs == 0
    - stats about skipped terms

    Args:
        min_impressions: Minimum impressions required to consider a term (default 0)
        exclude_terms: List of terms to exclude from analysis (case-insensitive)
    """
    end = datetime.now()
    start = end - timedelta(days=days)

    report_data = client.get_search_terms_report(campaign_id, start, end)

    result = AnalysisResult()
    result.total_terms = len(report_data)

    # Normalize exclude terms for case-insensitive matching
    exclude_set = {t.lower() for t in (exclude_terms or [])}

    for row in report_data:
        metadata = row.get("metadata", {})
        metrics = row.get("total", {})

        impressions = metrics.get("impressions", 0)
        taps = metrics.get("taps", 0)
        installs = metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0)
        spend_data = metrics.get("localSpend")
        spend = float(spend_data.get("amount", 0)) if isinstance(spend_data, dict) else 0.0

        term_text = metadata.get("searchTermText") or metadata.get("keyword") or ""
        if not term_text:
            result.skipped_no_text += 1
            continue

        # Skip excluded terms
        if term_text.lower() in exclude_set:
            continue

        if impressions == 0 and taps == 0 and spend == 0:
            result.skipped_no_activity += 1
            continue

        # Skip terms below minimum impressions threshold
        if impressions < min_impressions:
            continue

        term_data = {
            "term": term_text,
            "source": metadata.get("searchTermSource", "?"),
            "impressions": impressions,
            "taps": taps,
            "installs": installs,
            "spend": spend,
            "cpa": (spend / installs) if installs > 0 else float("inf"),
        }

        if installs >= min_installs and term_data["cpa"] <= cpa_threshold:
            result.winners.append(term_data)
        elif installs == 0 and spend >= min_spend:
            result.losers.append(term_data)

    result.winners.sort(key=lambda x: x["cpa"])
    result.losers.sort(key=lambda x: -x["spend"])

    return result


def display_optimization_summary(
    winners: list[dict],
    losers: list[dict],
    discovery_campaign: dict,
    target_campaign: dict,
    days: int,
) -> None:
    """Display the optimization summary with rich tables."""
    console.print(
        Panel(
            f"[bold]ASA Optimization Report[/bold]\nLast {days} days",
            expand=False,
            border_style="cyan",
        )
    )

    console.print(f"\nDiscovery Campaign: [cyan]{discovery_campaign.get('name')}[/cyan]")
    console.print(f"Target Campaign: [cyan]{target_campaign.get('name')}[/cyan]")

    console.print(f"\n[bold green]📈 WINNERS TO PROMOTE ({len(winners)} terms)[/bold green]")
    if winners:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Search Term")
        table.add_column("Installs", justify="right")
        table.add_column("Spend", justify="right")
        table.add_column("CPA", justify="right")

        for w in winners[:20]:
            table.add_row(
                w["term"][:35],
                str(w["installs"]),
                format_currency(w["spend"]),
                format_currency(w["cpa"]),
            )

        if len(winners) > 20:
            table.add_row(f"... and {len(winners) - 20} more", "", "", "")

        console.print(table)
    else:
        console.print("[dim]No terms meet the winner criteria.[/dim]")

    console.print(f"\n[bold red]🚫 TERMS TO BLOCK ({len(losers)} terms)[/bold red]")
    if losers:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Search Term")
        table.add_column("Installs", justify="right")
        table.add_column("Spend", justify="right")
        table.add_column("Impressions", justify="right")

        for l in losers[:20]:
            table.add_row(
                l["term"][:35],
                str(l["installs"]),
                format_currency(l["spend"]),
                str(l["impressions"]),
            )

        if len(losers) > 20:
            table.add_row(f"... and {len(losers) - 20} more", "", "", "")

        console.print(table)
    else:
        console.print("[dim]No terms meet the negative criteria.[/dim]")


def execute_promotions(
    client: SearchAdsClient,
    winners: list[dict],
    target_campaign: dict,
    discovery_campaign: dict,
) -> tuple[int, int]:
    """Promote winning keywords to target campaign.

    Returns (success_count, failure_count).
    """
    if not winners:
        return 0, 0

    target_id = target_campaign.get("id")
    discovery_id = discovery_campaign.get("id")

    ad_groups = client.get_ad_groups(target_id)
    exact_ad_group = next(
        (ag for ag in ad_groups if "Exact" in ag.get("name", "")),
        ad_groups[0] if ad_groups else None,
    )

    if not exact_ad_group:
        console.print("[red]No ad group found in target campaign.[/red]")
        return 0, len(winners)

    keyword_list = [w["term"] for w in winners]

    with console.status("[bold blue]Adding keywords to target campaign..."):
        added, errors = client.add_keywords(
            campaign_id=target_id,
            ad_group_id=exact_ad_group.get("id"),
            keywords=keyword_list,
            match_type=MatchType.EXACT,
        )

    if added and len(added) > 0:
        console.print(f"[green]✓ Added {len(added)} keywords to {target_campaign.get('name')}[/green]")
    elif errors:
        all_duplicates = all(e.get("messageCode") == "DUPLICATE_KEYWORD" for e in errors)
        if all_duplicates:
            console.print(f"[dim]↳ {len(errors)} keywords already exist in {target_campaign.get('name')}[/dim]")
            # Continue with negative keyword addition even if duplicates
            added = keyword_list  # Treat as success for flow purposes
        else:
            console.print(f"[red]✗ Failed: {errors[0].get('message', 'Unknown error')}[/red]")
            return 0, len(winners)
    else:
        console.print(f"[red]✗ Failed to add keywords to target campaign[/red]")
        return 0, len(winners)

    with console.status("[bold blue]Adding negatives to Discovery..."):
        neg_added, neg_errors = client.add_negative_keywords(discovery_id, keyword_list)

    if neg_added and len(neg_added) > 0:
        console.print(f"[green]✓ Added {len(neg_added)} negatives to Discovery[/green]")
    elif neg_errors:
        # Check if all errors are duplicates (which is fine)
        all_duplicates = all(e.get("messageCode") == "DUPLICATE_KEYWORD" for e in neg_errors)
        if all_duplicates:
            console.print(f"[dim]↳ {len(neg_errors)} negatives already exist in Discovery[/dim]")
        else:
            console.print(f"[yellow]⚠ Could not add negatives to Discovery: {neg_errors[0].get('message', 'Unknown error')}[/yellow]")
    else:
        console.print(f"[yellow]⚠ Could not add negatives to Discovery[/yellow]")

    # Return count based on what was actually promoted
    promoted_count = len(added) if isinstance(added, list) else len(keyword_list)
    return promoted_count, 0


def execute_negatives(
    client: SearchAdsClient,
    losers: list[dict],
    managed_campaigns: list[tuple[dict, CampaignType]],
) -> tuple[int, int]:
    """Block losing keywords across all managed campaigns.

    Returns (campaigns_succeeded, campaigns_failed).
    """
    if not losers:
        return 0, 0

    keyword_list = [l["term"] for l in losers]
    success_count = 0
    failure_count = 0

    for campaign, ctype in managed_campaigns:
        cid = campaign.get("id")
        cname = campaign.get("name")

        with console.status(f"[bold blue]Adding negatives to {cname}..."):
            added, errors = client.add_negative_keywords(cid, keyword_list)

        if added and len(added) > 0:
            console.print(f"[green]✓ Added {len(added)} negatives to {cname}[/green]")
            success_count += 1
        elif errors:
            all_duplicates = all(e.get("messageCode") == "DUPLICATE_KEYWORD" for e in errors)
            if all_duplicates:
                console.print(f"[dim]↳ {len(errors)} negatives already exist in {cname}[/dim]")
                success_count += 1  # Count as success since keywords are blocked
            else:
                console.print(f"[red]✗ Failed to add negatives to {cname}: {errors[0].get('message', 'Unknown')}[/red]")
                failure_count += 1
        else:
            console.print(f"[red]✗ Failed to add negatives to {cname}[/red]")
            failure_count += 1

    return success_count, failure_count


def _parse_lookback_days(lookback: str) -> int:
    """Parse simple lookback strings like '14d' or '14'."""
    value = lookback.strip().lower()
    if value.endswith("d"):
        value = value[:-1]
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("Lookback must be a positive number of days, e.g. 14d")
    return int(value)


def resolve_optimization_settings(
    *,
    days: Optional[int],
    lookback: Optional[str],
    cpa_threshold: Optional[float],
    min_installs: Optional[int],
    min_spend: Optional[float],
    min_impressions: Optional[int],
    rules: RulesConfig,
) -> tuple[int, float, int, float, int]:
    """Resolve CLI options over rule defaults for optimization analysis."""
    if lookback:
        resolved_days = _parse_lookback_days(lookback)
    elif days is not None:
        resolved_days = days
    else:
        resolved_days = rules.reporting.search_terms_days

    if resolved_days <= 0:
        raise ValueError("Days must be a positive integer")

    resolved_cpa = cpa_threshold if cpa_threshold is not None else rules.optimization.cpa_threshold
    resolved_installs = min_installs if min_installs is not None else rules.optimization.min_installs
    resolved_spend = (
        min_spend
        if min_spend is not None
        else rules.optimization.loser_min_spend or rules.optimization.min_spend
    )
    resolved_impressions = (
        min_impressions if min_impressions is not None else rules.optimization.min_impressions
    )

    return resolved_days, resolved_cpa, resolved_installs, resolved_spend, resolved_impressions


def _json_safe_metric(value):
    """Return metrics in JSON-safe form, avoiding Infinity in plan files."""
    if value == float("inf"):
        return None
    return value


def _term_evidence(terms: list[dict]) -> list[dict]:
    """Extract compact search-term evidence for plan metadata."""
    evidence = []
    for term in terms:
        evidence.append(
            {
                "term": term.get("term"),
                "source": term.get("source"),
                "impressions": term.get("impressions", 0),
                "taps": term.get("taps", 0),
                "installs": term.get("installs", 0),
                "spend": term.get("spend", 0),
                "cpa": _json_safe_metric(term.get("cpa")),
            }
        )
    return evidence


def _summarize_term_evidence(terms: list[dict]) -> dict:
    """Summarize metrics used to justify a plan action."""
    installs = sum(term.get("installs", 0) for term in terms)
    spend = sum(term.get("spend", 0) for term in terms)
    taps = sum(term.get("taps", 0) for term in terms)
    impressions = sum(term.get("impressions", 0) for term in terms)
    return {
        "term_count": len(terms),
        "impressions": impressions,
        "taps": taps,
        "installs": installs,
        "spend": spend,
        "cpa": (spend / installs) if installs else None,
    }


def build_optimization_plan(
    client: SearchAdsClient,
    winners: list[dict],
    losers: list[dict],
    discovery_campaign: dict,
    target_campaign: dict,
    managed_campaigns: list[tuple[dict, CampaignType]],
    days: int,
    target_type: CampaignType,
    app_name: Optional[str],
) -> ChangePlan:
    """Build a durable plan from optimization analysis."""
    actions: list[PlanAction] = []
    winner_terms = [w["term"] for w in winners]
    loser_terms = [l["term"] for l in losers]
    winner_evidence = _term_evidence(winners)
    loser_evidence = _term_evidence(losers)

    if winner_terms:
        ad_groups = client.get_ad_groups(target_campaign.get("id"))
        exact_ad_group = next(
            (ag for ag in ad_groups if "Exact" in ag.get("name", "")),
            ad_groups[0] if ad_groups else None,
        )
        if exact_ad_group:
            actions.append(
                PlanAction(
                    type=PlanActionType.ADD_KEYWORDS,
                    description=f"Promote {len(winner_terms)} discovery terms to exact keywords",
                    campaign_id=target_campaign.get("id"),
                    campaign_name=target_campaign.get("name"),
                    ad_group_id=exact_ad_group.get("id"),
                    ad_group_name=exact_ad_group.get("name"),
                    keywords=winner_terms,
                    match_type=MatchType.EXACT,
                    reason=f"Search terms met winner criteria over {days} days",
                    source="rule",
                    before_metrics=_summarize_term_evidence(winners),
                    metadata={
                        "target_campaign_type": target_type.value,
                        "search_terms": winner_evidence,
                    },
                )
            )
            actions.append(
                PlanAction(
                    type=PlanActionType.ADD_NEGATIVE_KEYWORDS,
                    description=f"Add {len(winner_terms)} promoted terms as Discovery negatives",
                    campaign_id=discovery_campaign.get("id"),
                    campaign_name=discovery_campaign.get("name"),
                    keywords=winner_terms,
                    match_type=MatchType.EXACT,
                    reason="Prevent duplicate spend after promotion",
                    source="rule",
                    before_metrics=_summarize_term_evidence(winners),
                    metadata={
                        "paired_with": "promotion",
                        "search_terms": winner_evidence,
                    },
                )
            )
        else:
            actions.append(
                PlanAction(
                    type=PlanActionType.CREATIVE_MAPPING_CHECK,
                    description="Target campaign has no ad group for keyword promotion",
                    campaign_id=target_campaign.get("id"),
                    campaign_name=target_campaign.get("name"),
                    reason="Optimization found winners but no target ad group exists",
                    source="rule",
                    before_metrics=_summarize_term_evidence(winners),
                    metadata={"search_terms": winner_evidence},
                )
            )

    if loser_terms:
        for campaign, ctype in managed_campaigns:
            actions.append(
                PlanAction(
                    type=PlanActionType.ADD_NEGATIVE_KEYWORDS,
                    description=f"Block {len(loser_terms)} inefficient search terms",
                    campaign_id=campaign.get("id"),
                    campaign_name=campaign.get("name"),
                    keywords=loser_terms,
                    match_type=MatchType.EXACT,
                    reason=f"Terms spent with no installs over {days} days",
                    source="rule",
                    before_metrics=_summarize_term_evidence(losers),
                    metadata={
                        "campaign_type": ctype.value,
                        "search_terms": loser_evidence,
                    },
                )
            )

    return ChangePlan(
        source="optimize",
        app_name=app_name,
        lookback_days=days,
        summary=(
            f"Promote {len(winner_terms)} terms to {target_type.value}; "
            f"block {len(loser_terms)} inefficient terms across managed campaigns"
        ),
        actions=actions,
    )


@app.callback(invoke_without_command=True)
def optimize_cmd(
    ctx: typer.Context,
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Days to analyze"),
    lookback: Optional[str] = typer.Option(
        None, "--lookback", help="Lookback window, e.g. 14d. Overrides --days."
    ),
    cpa_threshold: Optional[float] = typer.Option(
        None, "--cpa-threshold", "-c", help="Max CPA for winners (USD)"
    ),
    min_installs: Optional[int] = typer.Option(
        None, "--min-installs", "-i", help="Min installs to promote"
    ),
    min_spend: Optional[float] = typer.Option(
        None, "--min-spend", "-s", help="Min spend to consider blocking (USD)"
    ),
    min_impressions: Optional[int] = typer.Option(
        None, "--min-impressions", help="Min impressions to consider a term"
    ),
    exclude_terms: Optional[str] = typer.Option(
        None, "--exclude", "-e", help="Comma-separated terms to exclude from analysis"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Preview changes without applying"
    ),
    auto_approve: bool = typer.Option(
        False, "--auto-approve", "-y", help="Skip confirmation prompts"
    ),
    target: str = typer.Option(
        "category",
        "--target",
        "-t",
        help="Target campaign for promotions: brand, category, competitor",
    ),
    output_json: bool = typer.Option(
        False, "--json", help="Output results as JSON (implies --dry-run)"
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write proposed changes to a plan JSON file"
    ),
    rules_file: Optional[Path] = typer.Option(
        None, "--rules", help="JSON or YAML rule file overriding app config defaults"
    ),
):
    """Run automated optimization on Discovery campaign.

    This command performs the weekly ASA optimization workflow:

    1. Pull search terms from Discovery campaign
    2. Identify winners (good CPA, installs) to promote
    3. Identify losers (spend, no installs) to block
    4. Execute changes (with dry-run support)

    \b
    Examples:
        asa optimize --dry-run           # Preview changes
        asa optimize --days 7            # Analyze last 7 days
        asa optimize --cpa-threshold 3   # Stricter winner criteria
        asa optimize --auto-approve      # Skip confirmation
        asa optimize --json              # Output plan as JSON
        asa optimize --lookback 14d --out plan.json
        asa optimize --min-impressions 10  # Only terms with 10+ impressions
        asa optimize --exclude "test,demo" # Exclude specific terms
    """
    if ctx.invoked_subcommand is not None:
        return

    app_config = get_current_app_config()
    try:
        rules = load_rules(rules_file, app_config=app_config)
    except RulesLoadError as exc:
        if output_json:
            print(json.dumps({"error": str(exc)}))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    try:
        days, cpa_threshold, min_installs, min_spend, min_impressions = (
            resolve_optimization_settings(
                days=days,
                lookback=lookback,
                cpa_threshold=cpa_threshold,
                min_installs=min_installs,
                min_spend=min_spend,
                min_impressions=min_impressions,
                rules=rules,
            )
        )
    except ValueError as exc:
        if output_json:
            print(json.dumps({"error": str(exc)}))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    # JSON output implies dry-run
    if output_json:
        dry_run = True

    # Parse exclude terms
    exclude_list = [t.strip() for t in (exclude_terms or "").split(",") if t.strip()]

    credentials = load_credentials()
    if not credentials:
        if output_json:
            print(json.dumps({"error": "No credentials configured"}))
        else:
            console.print("[red]No credentials configured. Run 'asa config setup' first.[/red]")
        raise typer.Exit(1)

    target_type_map = {
        "brand": CampaignType.BRAND,
        "category": CampaignType.CATEGORY,
        "competitor": CampaignType.COMPETITOR,
    }

    if target.lower() not in target_type_map:
        if output_json:
            print(json.dumps({"error": f"Invalid target type: {target}"}))
        else:
            console.print(f"[red]Invalid target type: {target}. Use brand, category, or competitor.[/red]")
        raise typer.Exit(1)

    target_type = target_type_map[target.lower()]

    client = SearchAdsClient(credentials)
    app_name = _resolve_app_name()

    if not output_json:
        with console.status("[bold blue]Finding campaigns..."):
            campaigns_by_type, managed_campaigns = get_campaigns_indexed(client, app_name=app_name)
            discovery_campaign = campaigns_by_type.get(CampaignType.DISCOVERY)
            target_campaign = campaigns_by_type.get(target_type)
    else:
        campaigns_by_type, managed_campaigns = get_campaigns_indexed(client, app_name=app_name)
        discovery_campaign = campaigns_by_type.get(CampaignType.DISCOVERY)
        target_campaign = campaigns_by_type.get(target_type)

    if not discovery_campaign:
        if output_json:
            print(json.dumps({"error": "No Discovery campaign found"}))
        else:
            console.print("[red]No Discovery campaign found.[/red]")
            console.print("[yellow]Tip: Create a campaign with 'Discovery' in the name.[/yellow]")
        raise typer.Exit(1)

    if not target_campaign:
        if output_json:
            print(json.dumps({"error": f"No {target_type.value} campaign found"}))
        else:
            console.print(f"[red]No {target_type.value} campaign found.[/red]")
            console.print(f"[yellow]Tip: Create a campaign with '{target_type.value}' in the name.[/yellow]")
        raise typer.Exit(1)

    if not output_json:
        settings_text = (
            f"[bold]Optimization Settings[/bold]\n"
            f"Days: {days} | CPA Threshold: {format_currency(cpa_threshold)} | "
            f"Min Installs: {min_installs} | Min Spend: {format_currency(min_spend)}"
        )
        settings_text += f" | Max Bid Change: {rules.bids.max_bid_change_pct:g}%"
        if min_impressions > 0:
            settings_text += f" | Min Impressions: {min_impressions}"
        if rules_file:
            settings_text += f"\nRules: {rules_file}"
        if exclude_list:
            settings_text += f"\nExcluding: {', '.join(exclude_list)}"
        console.print(Panel(settings_text, expand=False))

    if not output_json:
        with console.status("[bold blue]Analyzing search terms..."):
            analysis = analyze_search_terms(
                client,
                discovery_campaign.get("id"),
                days,
                cpa_threshold,
                min_installs,
                min_spend,
                min_impressions,
                exclude_list if exclude_list else None,
            )
    else:
        analysis = analyze_search_terms(
            client,
            discovery_campaign.get("id"),
            days,
            cpa_threshold,
            min_installs,
            min_spend,
            min_impressions,
            exclude_list if exclude_list else None,
        )

    winners = analysis.winners
    losers = analysis.losers

    optimization_plan = build_optimization_plan(
        client=client,
        winners=winners,
        losers=losers,
        discovery_campaign=discovery_campaign,
        target_campaign=target_campaign,
        managed_campaigns=managed_campaigns,
        days=days,
        target_type=target_type,
        app_name=app_name,
    )
    for action in optimization_plan.actions:
        action.metadata.setdefault("rules", rules.model_dump(mode="json"))

    # JSON output mode
    if output_json:
        output_data = optimization_plan.model_dump(mode="json")
        print(json.dumps(output_data, indent=2))
        return

    if out:
        save_plan(optimization_plan, out)
        console.print(f"[green]Plan saved to {out}[/green]")
        console.print("[dim]Review with: asa plan show {path}[/dim]".format(path=out))
        console.print("[dim]Apply with: asa apply {path}[/dim]".format(path=out))
        return

    display_optimization_summary(
        winners, losers, discovery_campaign, target_campaign, days
    )

    analyzed_count = analysis.total_terms - analysis.skipped_no_text - analysis.skipped_no_activity
    console.print(f"\n[dim]Analysis: {analysis.total_terms} terms from API, "
                  f"{analyzed_count} analyzed, "
                  f"{analysis.skipped_no_text} skipped (no text), "
                  f"{analysis.skipped_no_activity} skipped (no activity)[/dim]")

    if not winners and not losers:
        console.print("\n[yellow]No optimization actions to take.[/yellow]")
        if analysis.skipped_no_text > 0:
            console.print("[dim]Note: Some Search Match terms don't expose their text in Apple's API.[/dim]")
        return

    if dry_run:
        console.print("\n[yellow][DRY RUN] No changes applied. Remove --dry-run to execute.[/yellow]")
        return

    if not auto_approve:
        console.print()
        if not Confirm.ask(
            f"[bold]Apply changes?[/bold] "
            f"({len(winners)} promotions, {len(losers)} negatives)"
        ):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    console.print("\n[bold]Executing optimization plan...[/bold]\n")
    result = apply_plan(client, optimization_plan)
    save_applied_plan(optimization_plan, result)
    display_apply_result(result)
