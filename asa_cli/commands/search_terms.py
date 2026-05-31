"""Search-term mining commands."""

from __future__ import annotations

import json
from math import isinf
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..api import SearchAdsClient
from ..config import (
    CampaignType,
    MatchType,
    RulesLoadError,
    RulesConfig,
    cap_bid_change,
    get_current_app_config,
    is_multi_app,
    load_credentials,
    load_rules,
)
from ..guide_hygiene import build_guide_hygiene_actions
from ..plans import PlanAction, PlanActionType, save_plan
from .optimize import (
    analyze_search_terms,
    build_optimization_plan,
    get_campaigns_indexed,
    resolve_optimization_settings,
)

app = typer.Typer(help="Search-term mining and guide hygiene commands")
console = Console()


def _safe_term_metrics(term: dict) -> dict:
    """Return search-term metrics safe for strict JSON plan output."""
    metrics = dict(term)
    if metrics.get("cpa") == float("inf") or (
        isinstance(metrics.get("cpa"), float) and isinf(metrics["cpa"])
    ):
        metrics["cpa"] = None
    return metrics


def _resolve_app_name() -> Optional[str]:
    """Get the app_name for campaign scoping (None if single-app)."""
    if not is_multi_app():
        return None
    app_config = get_current_app_config()
    return app_config.app_name if app_config else None


def build_related_keyword_actions(
    *,
    costly_terms: list[dict],
    loser_terms: list[dict],
    rules: RulesConfig,
) -> list[PlanAction]:
    """Create conservative keyword bid/pause actions from search-term evidence."""
    actions: list[PlanAction] = []
    target_cpa = rules.goals.target_cpa or rules.optimization.cpa_threshold
    adjustment = rules.bids.bid_adjustment_pct / 100

    for term in costly_terms:
        current_bid = term.get("current_bid")
        cpa = term.get("cpa")
        if (
            term.get("keyword_id") is None
            or term.get("campaign_id") is None
            or term.get("ad_group_id") is None
            or current_bid is None
            or cpa is None
            or cpa <= target_cpa * rules.optimization.lower_bid_cpa_multiplier
        ):
            continue

        proposed = current_bid * (1 - adjustment)
        actions.append(
            PlanAction(
                type=PlanActionType.UPDATE_KEYWORD_BID,
                description=f"Lower bid for related keyword '{term.get('keyword') or term.get('term')}'",
                campaign_id=term.get("campaign_id"),
                campaign_name=term.get("campaign_name"),
                ad_group_id=term.get("ad_group_id"),
                ad_group_name=term.get("ad_group_name"),
                keyword_id=term.get("keyword_id"),
                bid_amount=cap_bid_change(current_bid, proposed, rules),
                reason=f"Search term CPA {cpa:g} is above bid-lowering threshold",
                source="search_terms_mine",
                before_metrics=_safe_term_metrics(term),
                metadata={"check_type": "costly_related_keyword"},
            )
        )

    pause_spend = rules.optimization.pause_keyword_min_spend or rules.optimization.min_spend
    for term in loser_terms:
        keyword = (term.get("keyword") or "").strip().lower()
        search_term = (term.get("term") or "").strip().lower()
        if (
            term.get("keyword_id") is None
            or term.get("campaign_id") is None
            or term.get("ad_group_id") is None
            or term.get("spend", 0) < pause_spend
            or keyword != search_term
            or str(term.get("keyword_match_type", "")).upper() != MatchType.EXACT.value
        ):
            continue

        actions.append(
            PlanAction(
                type=PlanActionType.PAUSE_KEYWORD,
                description=f"Pause exact keyword '{term.get('keyword')}'",
                campaign_id=term.get("campaign_id"),
                campaign_name=term.get("campaign_name"),
                ad_group_id=term.get("ad_group_id"),
                ad_group_name=term.get("ad_group_name"),
                keyword_id=term.get("keyword_id"),
                reason="Exact keyword spent with no installs in search-term report",
                source="search_terms_mine",
                before_metrics=_safe_term_metrics(term),
                metadata={"check_type": "losing_related_keyword"},
            )
        )

    return actions


@app.command("mine")
def mine_search_terms(
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Days to analyze"),
    lookback: Optional[str] = typer.Option(
        None, "--lookback", help="Lookback window, e.g. 14d. Overrides --days."
    ),
    target: str = typer.Option(
        "category", "--target", "-t", help="Target campaign for promoted terms"
    ),
    cpa_threshold: Optional[float] = typer.Option(
        None, "--cpa-threshold", help="Max CPA for winner terms"
    ),
    min_installs: Optional[int] = typer.Option(
        None, "--min-installs", help="Min installs for winner terms"
    ),
    min_spend: Optional[float] = typer.Option(
        None, "--min-spend", help="Min spend for loser terms"
    ),
    min_impressions: Optional[int] = typer.Option(
        None, "--min-impressions", help="Min impressions to consider a term"
    ),
    exclude_terms: Optional[str] = typer.Option(
        None, "--exclude", "-e", help="Comma-separated terms to exclude"
    ),
    include_hygiene: bool = typer.Option(
        True, "--hygiene/--no-hygiene", help="Include guide hygiene checks in the plan"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output plan JSON"),
    out: Optional[Path] = typer.Option(None, "--out", help="Write plan JSON to this path"),
    rules_file: Optional[Path] = typer.Option(
        None, "--rules", help="JSON or YAML rule file overriding app config defaults"
    ),
):
    """Mine Discovery search terms and produce a reviewable change plan."""
    app_config = get_current_app_config()
    try:
        rules = load_rules(rules_file, app_config=app_config)
        resolved = resolve_optimization_settings(
            days=days,
            lookback=lookback,
            cpa_threshold=cpa_threshold,
            min_installs=min_installs,
            min_spend=min_spend,
            min_impressions=min_impressions,
            rules=rules,
        )
    except (RulesLoadError, ValueError) as exc:
        if output_json:
            print(json.dumps({"error": str(exc)}))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    days, cpa_threshold, min_installs, min_spend, min_impressions = resolved

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
    target_type = target_type_map.get(target.lower())
    if target_type is None:
        if output_json:
            print(json.dumps({"error": f"Invalid target type: {target}"}))
        else:
            console.print("[red]Invalid target type. Use brand, category, or competitor.[/red]")
        raise typer.Exit(1)

    client = SearchAdsClient(credentials)
    app_name = _resolve_app_name()
    campaigns_by_type, managed_campaigns = get_campaigns_indexed(client, app_name=app_name)
    discovery_campaign = campaigns_by_type.get(CampaignType.DISCOVERY)
    target_campaign = campaigns_by_type.get(target_type)

    if not discovery_campaign or not target_campaign:
        missing = []
        if not discovery_campaign:
            missing.append("Discovery")
        if not target_campaign:
            missing.append(target_type.value)
        message = f"Missing required campaign(s): {', '.join(missing)}"
        if output_json:
            print(json.dumps({"error": message}))
        else:
            console.print(f"[red]{message}[/red]")
        raise typer.Exit(1)

    exclude_list = [term.strip() for term in (exclude_terms or "").split(",") if term.strip()]
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

    plan = build_optimization_plan(
        client=client,
        winners=analysis.winners,
        losers=analysis.losers,
        discovery_campaign=discovery_campaign,
        target_campaign=target_campaign,
        managed_campaigns=managed_campaigns,
        days=days,
        target_type=target_type,
        app_name=app_name,
        app_id=app_config.app_id if app_config else None,
    )
    plan.source = "search_terms_mine"
    plan.summary = (
        f"Mine Discovery terms: {len(analysis.winners)} promotions, "
        f"{len(analysis.losers)} negatives"
    )

    related_keyword_actions = build_related_keyword_actions(
        costly_terms=analysis.costly,
        loser_terms=analysis.losers,
        rules=rules,
    )
    plan.actions.extend(related_keyword_actions)
    if related_keyword_actions:
        plan.summary += f"; {len(related_keyword_actions)} related keyword bid/pause actions"

    if include_hygiene:
        campaigns = [campaign for campaign, _ctype in managed_campaigns]
        hygiene_actions = build_guide_hygiene_actions(
            client,
            campaigns,
            app_name=app_name,
            rules=rules,
        )
        plan.actions.extend(hygiene_actions)
        if hygiene_actions:
            plan.summary += f"; {len(hygiene_actions)} guide hygiene actions"

    for action in plan.actions:
        action.metadata.setdefault("rules", rules.model_dump(mode="json"))

    if output_json:
        print(plan.model_dump_json(indent=2))
        return

    if out:
        save_plan(plan, out)
        console.print(f"[green]Plan saved to {out}[/green]")
        console.print(f"[dim]Review with: asa plan show {out}[/dim]")
        console.print(f"[dim]Apply with: asa apply {out}[/dim]")
        return

    console.print(
        Panel(
            f"[bold]Search-Term Mining Plan[/bold]\n"
            f"Lookback: {days} days\n"
            f"Winners: {len(analysis.winners)} | Losers: {len(analysis.losers)} | "
            f"Actions: {len(plan.actions)}",
            expand=False,
        )
    )
    console.print(
        "[yellow]No changes applied. Use --out plan.json or --json to export the plan.[/yellow]"
    )
