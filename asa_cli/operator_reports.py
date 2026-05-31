"""Shared operator report and budget pacing helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from .config import CampaignType, RulesConfig, detect_campaign_type
from .plans import PlanAction, PlanActionType


def money_amount(value: Any) -> float:
    """Return a float from Apple money dictionaries or scalar values."""
    if isinstance(value, dict):
        value = value.get("amount", 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def summarize_report_rows(
    campaign: dict, rows: list[dict], ctype: Optional[CampaignType] = None
) -> dict:
    """Aggregate Apple report rows into campaign-level operator metrics."""
    totals = {"impressions": 0, "taps": 0, "installs": 0, "spend": 0.0}

    for row in rows:
        metrics = row.get("total", {})
        totals["impressions"] += metrics.get("impressions", 0) or 0
        totals["taps"] += metrics.get("taps", 0) or 0
        totals["installs"] += metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0) or 0
        totals["spend"] += money_amount(metrics.get("localSpend"))

    impressions = totals["impressions"]
    taps = totals["taps"]
    installs = totals["installs"]
    spend = totals["spend"]
    daily_budget = money_amount(campaign.get("dailyBudgetAmount"))

    return {
        "campaign_id": campaign.get("id"),
        "campaign_name": campaign.get("name", ""),
        "campaign_type": ctype.value if ctype else None,
        "status": campaign.get("status", "UNKNOWN"),
        "display_status": campaign.get("displayStatus", "UNKNOWN"),
        "serving_status": campaign.get("servingStatus", "UNKNOWN"),
        "countries": campaign.get("countriesOrRegions", []),
        "daily_budget": daily_budget,
        "currency": (campaign.get("dailyBudgetAmount") or {}).get("currency", "USD"),
        "impressions": impressions,
        "taps": taps,
        "installs": installs,
        "spend": round(spend, 2),
        "ttr": (taps / impressions * 100) if impressions else 0.0,
        "cvr": (installs / taps * 100) if taps else 0.0,
        "cpa": (spend / installs) if installs else None,
    }


def build_operator_report(
    client,
    *,
    campaigns: list[dict],
    days: int,
    app_name: Optional[str],
    rules: RulesConfig,
) -> dict:
    """Build a compact daily/weekly operator report from campaign reports."""
    end = datetime.now()
    start = end - timedelta(days=days)
    campaign_summaries: list[dict] = []

    for campaign in campaigns:
        ctype = detect_campaign_type(campaign.get("name", ""))
        rows = client.get_campaign_report(campaign.get("id"), start, end, granularity="DAILY")
        campaign_summaries.append(summarize_report_rows(campaign, rows, ctype))

    target_cpa = rules.goals.target_cpa or rules.optimization.cpa_threshold
    winners = [
        c
        for c in campaign_summaries
        if c["installs"] > 0 and c["cpa"] is not None and c["cpa"] <= target_cpa
    ]
    losers = [
        c
        for c in campaign_summaries
        if c["spend"] >= rules.optimization.min_spend
        and (c["installs"] == 0 or (c["cpa"] is not None and c["cpa"] > target_cpa))
    ]
    pacing_actions = build_budget_pacing_actions(
        campaign_summaries,
        days=days,
        rules=rules,
        source="operator_report",
    )

    totals = {
        "impressions": sum(c["impressions"] for c in campaign_summaries),
        "taps": sum(c["taps"] for c in campaign_summaries),
        "installs": sum(c["installs"] for c in campaign_summaries),
        "spend": round(sum(c["spend"] for c in campaign_summaries), 2),
    }
    totals["ttr"] = (totals["taps"] / totals["impressions"] * 100) if totals["impressions"] else 0.0
    totals["cvr"] = (totals["installs"] / totals["taps"] * 100) if totals["taps"] else 0.0
    totals["cpa"] = (totals["spend"] / totals["installs"]) if totals["installs"] else None

    return {
        "days": days,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "target_cpa": target_cpa,
        "totals": totals,
        "campaigns": campaign_summaries,
        "winners": winners,
        "losers": losers,
        "next_actions": [action.model_dump(mode="json") for action in pacing_actions],
    }


def build_budget_pacing_actions(
    campaign_summaries: list[dict],
    *,
    days: int,
    rules: RulesConfig,
    source: str = "budget_pacing",
) -> list[PlanAction]:
    """Recommend budget changes from spend pace and quality metrics."""
    actions: list[PlanAction] = []
    target_cpa = rules.goals.target_cpa or rules.optimization.cpa_threshold
    min_spend = rules.optimization.min_spend
    currency = rules.currency

    for summary in campaign_summaries:
        campaign_id = summary.get("campaign_id")
        campaign_name = summary.get("campaign_name")
        daily_budget = summary.get("daily_budget") or 0.0
        if not campaign_id or daily_budget <= 0:
            continue

        spend = summary.get("spend", 0.0)
        expected_spend = daily_budget * days
        pace = spend / expected_spend if expected_spend else 0.0
        cpa = summary.get("cpa")
        installs = summary.get("installs", 0)
        impressions = summary.get("impressions", 0)
        ctype = summary.get("campaign_type")

        metrics = dict(summary)
        metrics["expected_spend"] = round(expected_spend, 2)
        metrics["spend_pace"] = round(pace, 4)

        if pace >= 0.9 and installs > 0 and cpa is not None and cpa <= target_cpa:
            new_budget = round(daily_budget * 1.2, 2)
            actions.append(
                PlanAction(
                    type=PlanActionType.UPDATE_CAMPAIGN_BUDGET,
                    description=f"Raise daily budget for capped winner '{campaign_name}'",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    daily_budget_amount=new_budget,
                    reason=f"Spend is pacing at {pace:.0%} with CPA {cpa:.2f} at or below target {target_cpa:.2f}",
                    source=source,
                    before_metrics=metrics,
                    metadata={"currency": currency, "current_daily_budget": daily_budget},
                )
            )
            continue

        poor_quality = (installs == 0 and spend >= min_spend) or (
            cpa is not None and cpa > target_cpa * rules.optimization.lower_bid_cpa_multiplier
        )
        discovery_waste = (
            ctype == CampaignType.DISCOVERY.value and installs == 0 and spend >= min_spend
        )
        if pace >= 0.5 and (poor_quality or discovery_waste):
            new_budget = round(max(daily_budget * 0.8, 1.0), 2)
            actions.append(
                PlanAction(
                    type=PlanActionType.UPDATE_CAMPAIGN_BUDGET,
                    description=f"Lower daily budget for inefficient campaign '{campaign_name}'",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    daily_budget_amount=new_budget,
                    reason="Campaign is consuming budget without enough acquisition quality",
                    source=source,
                    before_metrics=metrics,
                    metadata={"currency": currency, "current_daily_budget": daily_budget},
                )
            )
            continue

        if pace <= 0.2 and impressions < rules.reporting.min_impressions:
            actions.append(
                PlanAction(
                    type=PlanActionType.CREATIVE_MAPPING_CHECK,
                    description=f"Investigate under-delivery for '{campaign_name}'",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    reason="Campaign is far under budget pace with very low impression volume",
                    source=source,
                    before_metrics=metrics,
                    metadata={"check_type": "under_delivery"},
                )
            )

    return actions
