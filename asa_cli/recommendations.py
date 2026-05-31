"""Optimization recommendations that can be converted into reviewable plans."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .config import CampaignType, MatchType, RulesConfig, cap_bid_change
from .plans import PlanAction, PlanActionType


class RecommendationType(str, Enum):
    """Structured optimization recommendation types."""

    PROMOTE_SEARCH_TERM = "promote_search_term"
    ADD_NEGATIVE = "add_negative"
    RAISE_BID = "raise_bid"
    LOWER_BID = "lower_bid"
    PAUSE_KEYWORD = "pause_keyword"
    INFO_CHECK = "info_check"


class Recommendation(BaseModel):
    """A recommendation produced by optimization rules."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: RecommendationType
    description: str
    reason: str
    campaign_id: Optional[int] = None
    campaign_name: Optional[str] = None
    ad_group_id: Optional[int] = None
    ad_group_name: Optional[str] = None
    keyword_id: Optional[int] = None
    keywords: list[str] = Field(default_factory=list)
    match_type: Optional[MatchType] = None
    bid_amount: Optional[float] = None
    source_metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_plan_action(self) -> PlanAction:
        """Convert a recommendation into an executable or informational plan action."""
        action_type = {
            RecommendationType.PROMOTE_SEARCH_TERM: PlanActionType.ADD_KEYWORDS,
            RecommendationType.ADD_NEGATIVE: PlanActionType.ADD_NEGATIVE_KEYWORDS,
            RecommendationType.RAISE_BID: PlanActionType.UPDATE_KEYWORD_BID,
            RecommendationType.LOWER_BID: PlanActionType.UPDATE_KEYWORD_BID,
            RecommendationType.PAUSE_KEYWORD: PlanActionType.PAUSE_KEYWORD,
            RecommendationType.INFO_CHECK: PlanActionType.CREATIVE_MAPPING_CHECK,
        }[self.type]

        metadata = dict(self.metadata)
        metadata["recommendation_id"] = self.id
        metadata["recommendation_type"] = self.type.value

        return PlanAction(
            type=action_type,
            description=self.description,
            campaign_id=self.campaign_id,
            campaign_name=self.campaign_name,
            ad_group_id=self.ad_group_id,
            ad_group_name=self.ad_group_name,
            keyword_id=self.keyword_id,
            keywords=self.keywords,
            match_type=self.match_type,
            bid_amount=self.bid_amount,
            reason=self.reason,
            source="rule",
            before_metrics=self.source_metrics,
            metadata=metadata,
        )


def _json_safe_metric(value: Any) -> Any:
    if value == float("inf"):
        return None
    return value


def term_evidence(terms: list[dict]) -> list[dict]:
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


def summarize_terms(terms: list[dict]) -> dict:
    """Summarize search-term metrics that justify a recommendation."""
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


def build_search_term_recommendations(
    *,
    winners: list[dict],
    losers: list[dict],
    discovery_campaign: dict,
    target_campaign: dict,
    exact_ad_group: Optional[dict],
    managed_campaigns: list[tuple[dict, CampaignType]],
    days: int,
    target_type: CampaignType,
) -> list[Recommendation]:
    """Convert analyzed search terms into promotion and negative recommendations."""
    recommendations: list[Recommendation] = []
    winner_terms = [w["term"] for w in winners]
    loser_terms = [l["term"] for l in losers]
    winner_evidence = term_evidence(winners)
    loser_evidence = term_evidence(losers)

    if winner_terms:
        if exact_ad_group:
            recommendations.append(
                Recommendation(
                    type=RecommendationType.PROMOTE_SEARCH_TERM,
                    description=f"Promote {len(winner_terms)} discovery terms to exact keywords",
                    campaign_id=target_campaign.get("id"),
                    campaign_name=target_campaign.get("name"),
                    ad_group_id=exact_ad_group.get("id"),
                    ad_group_name=exact_ad_group.get("name"),
                    keywords=winner_terms,
                    match_type=MatchType.EXACT,
                    reason=f"Search terms met winner criteria over {days} days",
                    source_metrics=summarize_terms(winners),
                    metadata={
                        "target_campaign_type": target_type.value,
                        "search_terms": winner_evidence,
                    },
                )
            )
            recommendations.append(
                Recommendation(
                    type=RecommendationType.ADD_NEGATIVE,
                    description=f"Add {len(winner_terms)} promoted terms as Discovery negatives",
                    campaign_id=discovery_campaign.get("id"),
                    campaign_name=discovery_campaign.get("name"),
                    keywords=winner_terms,
                    match_type=MatchType.EXACT,
                    reason="Prevent duplicate spend after promotion",
                    source_metrics=summarize_terms(winners),
                    metadata={
                        "paired_with": "promotion",
                        "search_terms": winner_evidence,
                    },
                )
            )
        else:
            recommendations.append(
                Recommendation(
                    type=RecommendationType.INFO_CHECK,
                    description="Target campaign has no ad group for keyword promotion",
                    campaign_id=target_campaign.get("id"),
                    campaign_name=target_campaign.get("name"),
                    reason="Optimization found winners but no target ad group exists",
                    source_metrics=summarize_terms(winners),
                    metadata={"search_terms": winner_evidence},
                )
            )

    if loser_terms:
        for campaign, ctype in managed_campaigns:
            recommendations.append(
                Recommendation(
                    type=RecommendationType.ADD_NEGATIVE,
                    description=f"Block {len(loser_terms)} inefficient search terms",
                    campaign_id=campaign.get("id"),
                    campaign_name=campaign.get("name"),
                    keywords=loser_terms,
                    match_type=MatchType.EXACT,
                    reason=f"Terms spent with no installs over {days} days",
                    source_metrics=summarize_terms(losers),
                    metadata={
                        "campaign_type": ctype.value,
                        "search_terms": loser_evidence,
                    },
                )
            )

    return recommendations


def build_keyword_recommendations(
    keyword_rows: list[dict],
    rules: RulesConfig,
) -> list[Recommendation]:
    """Apply keyword-level bid and pause rules to normalized keyword rows."""
    recommendations: list[Recommendation] = []
    target_cpa = rules.goals.target_cpa or rules.optimization.cpa_threshold
    pause_spend = rules.optimization.pause_keyword_min_spend or rules.optimization.min_spend
    adjustment = rules.bids.bid_adjustment_pct / 100

    for row in keyword_rows:
        keyword_id = row.get("keyword_id")
        campaign_id = row.get("campaign_id")
        ad_group_id = row.get("ad_group_id")
        current_bid = row.get("current_bid")
        if keyword_id is None or campaign_id is None or ad_group_id is None or current_bid is None:
            continue

        installs = row.get("installs", 0)
        spend = row.get("spend", 0.0)
        cpa = row.get("cpa")
        metrics = {
            "keyword": row.get("keyword"),
            "impressions": row.get("impressions", 0),
            "taps": row.get("taps", 0),
            "installs": installs,
            "spend": spend,
            "cpa": _json_safe_metric(cpa),
            "current_bid": current_bid,
        }

        base_kwargs = {
            "campaign_id": campaign_id,
            "campaign_name": row.get("campaign_name"),
            "ad_group_id": ad_group_id,
            "ad_group_name": row.get("ad_group_name"),
            "keyword_id": keyword_id,
            "source_metrics": metrics,
            "metadata": {"keyword": row.get("keyword")},
        }

        if installs == 0 and spend >= pause_spend:
            recommendations.append(
                Recommendation(
                    type=RecommendationType.PAUSE_KEYWORD,
                    description=f"Pause keyword '{row.get('keyword')}'",
                    reason=f"Keyword spent {spend:g} with no installs",
                    **base_kwargs,
                )
            )
            continue

        if installs > 0 and cpa is not None and cpa >= target_cpa * rules.optimization.lower_bid_cpa_multiplier:
            proposed = current_bid * (1 - adjustment)
            recommendations.append(
                Recommendation(
                    type=RecommendationType.LOWER_BID,
                    description=f"Lower bid for keyword '{row.get('keyword')}'",
                    reason=f"CPA {cpa:g} is above bid-lowering threshold",
                    bid_amount=cap_bid_change(current_bid, proposed, rules),
                    **base_kwargs,
                )
            )
            continue

        if (
            installs >= rules.optimization.raise_bid_min_installs
            and cpa is not None
            and cpa <= target_cpa * rules.optimization.raise_bid_cpa_multiplier
        ):
            proposed = current_bid * (1 + adjustment)
            recommendations.append(
                Recommendation(
                    type=RecommendationType.RAISE_BID,
                    description=f"Raise bid for keyword '{row.get('keyword')}'",
                    reason=f"CPA {cpa:g} is below bid-raising threshold",
                    bid_amount=cap_bid_change(current_bid, proposed, rules),
                    **base_kwargs,
                )
            )

    return recommendations


def keyword_report_row_to_metrics(
    row: dict,
    *,
    campaign: dict,
    ad_group: dict,
) -> dict:
    """Normalize an Apple keyword report row for keyword recommendation rules."""
    metadata = row.get("metadata", {})
    metrics = row.get("total", {})
    spend_data = metrics.get("localSpend", {})
    spend = float(spend_data.get("amount", 0)) if spend_data else 0.0
    installs = metrics.get("totalInstalls", 0) or metrics.get("tapInstalls", 0)
    bid_data = metadata.get("bidAmount", {})
    current_bid = float(bid_data.get("amount", 0)) if bid_data else 0.0

    return {
        "campaign_id": campaign.get("id"),
        "campaign_name": campaign.get("name"),
        "ad_group_id": ad_group.get("id"),
        "ad_group_name": ad_group.get("name"),
        "keyword_id": metadata.get("keywordId"),
        "keyword": metadata.get("keyword"),
        "current_bid": current_bid,
        "impressions": metrics.get("impressions", 0),
        "taps": metrics.get("taps", 0),
        "installs": installs,
        "spend": spend,
        "cpa": (spend / installs) if installs else None,
    }
