"""Apple Ads guide hygiene checks that produce reviewable plan actions."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from .config import CampaignType, MatchType, RulesConfig, detect_campaign_type
from .plans import PlanAction, PlanActionType


def normalize_term(term: str) -> str:
    """Normalize keyword text for duplicate and negative checks."""
    return " ".join((term or "").strip().lower().split())


def _is_active_status(value: str) -> bool:
    status = (value or "").upper()
    return status not in {"PAUSED", "DELETED", "REMOVED"}


def _keyword_text(keyword: dict) -> str:
    return (
        keyword.get("text")
        or keyword.get("keyword")
        or keyword.get("metadata", {}).get("keyword")
        or ""
    )


def _keyword_match_type(keyword: dict) -> str:
    return (
        keyword.get("matchType")
        or keyword.get("match_type")
        or keyword.get("metadata", {}).get("matchType")
        or ""
    )


def _keyword_id(keyword: dict) -> Optional[int]:
    return (
        keyword.get("id")
        or keyword.get("keywordId")
        or keyword.get("metadata", {}).get("keywordId")
    )


def _keyword_status(keyword: dict) -> str:
    return (
        keyword.get("status")
        or keyword.get("keywordStatus")
        or keyword.get("metadata", {}).get("keywordStatus")
        or ""
    )


def _negative_key(negative: dict) -> tuple[str, str]:
    return (
        normalize_term(_keyword_text(negative)),
        (_keyword_match_type(negative) or MatchType.EXACT.value).upper(),
    )


def _campaign_countries(campaign: dict) -> tuple[str, ...]:
    return tuple(sorted(campaign.get("countriesOrRegions", []) or []))


def _countries_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if not left or not right:
        return True
    return bool(set(left).intersection(right))


def collect_keyword_inventory(
    client, campaigns: list[dict], *, app_name: Optional[str]
) -> list[dict]:
    """Fetch active keyword records for managed campaigns."""
    records: list[dict] = []
    for campaign in campaigns:
        ctype = detect_campaign_type(campaign.get("name", ""))
        if not ctype:
            continue
        for ad_group in client.get_ad_groups(campaign.get("id")):
            for keyword in client.get_keywords(campaign.get("id"), ad_group.get("id")):
                term = normalize_term(_keyword_text(keyword))
                if not term or not _is_active_status(_keyword_status(keyword)):
                    continue
                records.append(
                    {
                        "campaign_id": campaign.get("id"),
                        "campaign_name": campaign.get("name", ""),
                        "campaign_type": ctype,
                        "countries": _campaign_countries(campaign),
                        "ad_group_id": ad_group.get("id"),
                        "ad_group_name": ad_group.get("name", ""),
                        "keyword_id": _keyword_id(keyword),
                        "keyword": term,
                        "match_type": (
                            _keyword_match_type(keyword) or MatchType.EXACT.value
                        ).upper(),
                        "status": _keyword_status(keyword),
                    }
                )
    return records


def build_guide_hygiene_actions(
    client,
    campaigns: list[dict],
    *,
    app_name: Optional[str],
    rules: RulesConfig,
) -> list[PlanAction]:
    """Build safe guide hygiene actions from campaign/ad group/keyword state."""
    actions: list[PlanAction] = []
    managed_campaigns: list[tuple[dict, CampaignType]] = []
    discovery_campaigns: list[dict] = []

    for campaign in campaigns:
        ctype = detect_campaign_type(campaign.get("name", ""))
        if not ctype:
            continue
        managed_campaigns.append((campaign, ctype))
        if ctype == CampaignType.DISCOVERY:
            discovery_campaigns.append(campaign)

        countries = campaign.get("countriesOrRegions", []) or []
        if rules.campaign_strategy.one_country_per_campaign and len(countries) > 1:
            actions.append(
                PlanAction(
                    type=PlanActionType.CREATIVE_MAPPING_CHECK,
                    description=f"Review multi-country campaign '{campaign.get('name', '')}'",
                    campaign_id=campaign.get("id"),
                    campaign_name=campaign.get("name", ""),
                    reason="Guide prefers one country per campaign once structure is serious",
                    source="guide_hygiene",
                    metadata={"check_type": "multi_country_campaign", "countries": countries},
                )
            )

        for ad_group in client.get_ad_groups(campaign.get("id")):
            search_match = bool(ad_group.get("automatedKeywordsOptIn"))
            if search_match and ctype != CampaignType.DISCOVERY:
                actions.append(
                    PlanAction(
                        type=PlanActionType.CREATIVE_MAPPING_CHECK,
                        description=f"Review Search Match outside Discovery in '{ad_group.get('name', '')}'",
                        campaign_id=campaign.get("id"),
                        campaign_name=campaign.get("name", ""),
                        ad_group_id=ad_group.get("id"),
                        ad_group_name=ad_group.get("name", ""),
                        reason="Search Match should stay isolated from exact campaign types",
                        source="guide_hygiene",
                        metadata={"check_type": "search_match_outside_discovery"},
                    )
                )
            if (
                search_match
                and ctype == CampaignType.DISCOVERY
                and not rules.campaign_strategy.discovery_search_match_enabled
            ):
                actions.append(
                    PlanAction(
                        type=PlanActionType.CREATIVE_MAPPING_CHECK,
                        description=f"Review early Search Match usage in '{ad_group.get('name', '')}'",
                        campaign_id=campaign.get("id"),
                        campaign_name=campaign.get("name", ""),
                        ad_group_id=ad_group.get("id"),
                        ad_group_name=ad_group.get("name", ""),
                        reason="Rules currently disable Search Match until discovery quality is proven",
                        source="guide_hygiene",
                        metadata={"check_type": "search_match_disabled_by_rules"},
                    )
                )

    keyword_records = collect_keyword_inventory(client, campaigns, app_name=app_name)

    by_keyword: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in keyword_records:
        by_keyword[(record["keyword"], record["match_type"])].append(record)

    for (term, match_type), records in by_keyword.items():
        if len(records) <= 1:
            continue
        kept_records: list[dict] = []
        for record in records:
            overlapping = [
                kept
                for kept in kept_records
                if _countries_overlap(kept["countries"], record["countries"])
            ]
            if not overlapping:
                kept_records.append(record)
                continue

            duplicate = record
            countries = duplicate["countries"]
            country_text = ", ".join(countries) if countries else "unknown countries"
            if duplicate.get("keyword_id") is None:
                actions.append(
                    PlanAction(
                        type=PlanActionType.CREATIVE_MAPPING_CHECK,
                        description=f"Review duplicate keyword '{term}'",
                        campaign_id=duplicate["campaign_id"],
                        campaign_name=duplicate["campaign_name"],
                        ad_group_id=duplicate["ad_group_id"],
                        ad_group_name=duplicate["ad_group_name"],
                        reason="Duplicate keyword is active in more than one place but has no keyword ID to pause safely",
                        source="guide_hygiene",
                        metadata={
                            "check_type": "duplicate_keyword",
                            "match_type": match_type,
                            "countries": list(countries),
                        },
                    )
                )
                continue
            actions.append(
                PlanAction(
                    type=PlanActionType.PAUSE_KEYWORD,
                    description=f"Pause duplicate keyword '{term}'",
                    campaign_id=duplicate["campaign_id"],
                    campaign_name=duplicate["campaign_name"],
                    ad_group_id=duplicate["ad_group_id"],
                    ad_group_name=duplicate["ad_group_name"],
                    keyword_id=duplicate["keyword_id"],
                    reason="Guide rule: one keyword should be active in one place",
                    source="guide_hygiene",
                    before_metrics={
                        "keyword": term,
                        "match_type": match_type,
                        "country_scope": country_text,
                    },
                    metadata={"check_type": "duplicate_keyword", "countries": list(countries)},
                )
            )

    exact_non_discovery_records = [
        record
        for record in keyword_records
        if record["campaign_type"] != CampaignType.DISCOVERY
        and record["match_type"] == MatchType.EXACT.value
    ]

    for discovery in discovery_campaigns:
        discovery_countries = _campaign_countries(discovery)
        existing_negatives = {
            _negative_key(negative)
            for negative in client.get_negative_keywords(discovery.get("id"))
        }
        same_country_exact_terms = sorted(
            {
                record["keyword"]
                for record in exact_non_discovery_records
                if _countries_overlap(record["countries"], discovery_countries)
            }
        )
        missing = [
            term
            for term in same_country_exact_terms
            if (term, MatchType.EXACT.value) not in existing_negatives
        ]
        if missing:
            actions.append(
                PlanAction(
                    type=PlanActionType.ADD_NEGATIVE_KEYWORDS,
                    description=f"Add {len(missing)} exact keywords as Discovery negatives",
                    campaign_id=discovery.get("id"),
                    campaign_name=discovery.get("name", ""),
                    keywords=missing,
                    match_type=MatchType.EXACT,
                    reason="Prevent Discovery from competing with promoted exact keywords",
                    source="guide_hygiene",
                    metadata={
                        "check_type": "missing_discovery_negatives",
                        "countries": list(discovery_countries),
                    },
                )
            )

    return actions
