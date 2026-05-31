"""Tests for Phase 4 guide hygiene/search mining and Phase 5 reports/pacing."""

from unittest.mock import MagicMock

from asa_cli.config import AppConfig, CampaignType, MatchType, load_rules
from asa_cli.commands.search_terms import build_related_keyword_actions
from asa_cli.guide_hygiene import build_guide_hygiene_actions
from asa_cli.operator_reports import (
    build_budget_pacing_actions,
    build_operator_report,
    summarize_report_rows,
)
from asa_cli.plans import PlanActionType


def test_guide_hygiene_pauses_duplicates_and_adds_discovery_negatives():
    client = MagicMock()
    campaigns = [
        {"id": 1, "name": "Noteo - Discovery - US", "countriesOrRegions": ["US"]},
        {"id": 2, "name": "Noteo - Category - US", "countriesOrRegions": ["US"]},
    ]

    client.get_ad_groups.side_effect = lambda campaign_id: {
        1: [{"id": 10, "name": "Discovery-Broad", "automatedKeywordsOptIn": False}],
        2: [{"id": 20, "name": "Category-Exact", "automatedKeywordsOptIn": False}],
    }[campaign_id]
    client.get_keywords.side_effect = lambda campaign_id, ad_group_id: {
        (1, 10): [
            {"id": 100, "text": "ai notes", "matchType": "EXACT", "status": "ACTIVE"},
        ],
        (2, 20): [
            {"id": 200, "text": "ai notes", "matchType": "EXACT", "status": "ACTIVE"},
            {"id": 201, "text": "meeting notes", "matchType": "EXACT", "status": "ACTIVE"},
        ],
    }[(campaign_id, ad_group_id)]
    client.get_negative_keywords.return_value = []

    rules = load_rules(app_config=AppConfig(app_id=123, app_name="Noteo"))

    actions = build_guide_hygiene_actions(client, campaigns, app_name=None, rules=rules)

    pause_actions = [action for action in actions if action.type == PlanActionType.PAUSE_KEYWORD]
    negative_actions = [
        action for action in actions if action.type == PlanActionType.ADD_NEGATIVE_KEYWORDS
    ]

    assert len(pause_actions) == 1
    assert pause_actions[0].keyword_id == 200
    assert pause_actions[0].reason == "Guide rule: one keyword should be active in one place"
    assert len(negative_actions) == 1
    assert negative_actions[0].campaign_id == 1
    assert negative_actions[0].keywords == ["ai notes", "meeting notes"]
    assert negative_actions[0].match_type == MatchType.EXACT


def test_guide_hygiene_flags_search_match_when_rules_disable_it():
    client = MagicMock()
    campaigns = [
        {"id": 1, "name": "Discovery", "countriesOrRegions": ["US"]},
        {"id": 2, "name": "Category", "countriesOrRegions": ["US"]},
    ]
    client.get_ad_groups.side_effect = lambda campaign_id: {
        1: [{"id": 10, "name": "Discovery-SearchMatch", "automatedKeywordsOptIn": True}],
        2: [{"id": 20, "name": "Category-Exact", "automatedKeywordsOptIn": True}],
    }[campaign_id]
    client.get_keywords.return_value = []
    client.get_negative_keywords.return_value = []
    rules = load_rules(app_config=AppConfig(app_id=123, app_name="TestApp"))

    actions = build_guide_hygiene_actions(client, campaigns, app_name=None, rules=rules)
    check_types = {action.metadata["check_type"] for action in actions}

    assert "search_match_disabled_by_rules" in check_types
    assert "search_match_outside_discovery" in check_types


def test_budget_pacing_recommends_raise_for_capped_winner_and_lower_for_waste():
    app_config = AppConfig(app_id=123, app_name="TestApp")
    app_config.optimization.cpa_threshold = 5
    app_config.optimization.min_spend = 10
    rules = load_rules(app_config=app_config)

    actions = build_budget_pacing_actions(
        [
            {
                "campaign_id": 1,
                "campaign_name": "Category",
                "campaign_type": CampaignType.CATEGORY.value,
                "daily_budget": 10.0,
                "spend": 10.0,
                "installs": 3,
                "impressions": 100,
                "cpa": 3.0,
            },
            {
                "campaign_id": 2,
                "campaign_name": "Discovery",
                "campaign_type": CampaignType.DISCOVERY.value,
                "daily_budget": 10.0,
                "spend": 10.0,
                "installs": 0,
                "impressions": 100,
                "cpa": None,
            },
        ],
        days=1,
        rules=rules,
    )

    assert [action.type for action in actions] == [
        PlanActionType.UPDATE_CAMPAIGN_BUDGET,
        PlanActionType.UPDATE_CAMPAIGN_BUDGET,
    ]
    assert actions[0].daily_budget_amount == 12.0
    assert actions[1].daily_budget_amount == 8.0


def test_budget_pacing_flags_low_impression_under_delivery():
    app_config = AppConfig(app_id=123, app_name="TestApp")
    app_config.reporting.min_impressions = 10
    rules = load_rules(app_config=app_config)

    actions = build_budget_pacing_actions(
        [
            {
                "campaign_id": 1,
                "campaign_name": "Brand",
                "campaign_type": CampaignType.BRAND.value,
                "daily_budget": 20.0,
                "spend": 1.0,
                "installs": 0,
                "impressions": 2,
                "cpa": None,
            }
        ],
        days=1,
        rules=rules,
    )

    assert len(actions) == 1
    assert actions[0].type == PlanActionType.CREATIVE_MAPPING_CHECK
    assert actions[0].metadata["check_type"] == "under_delivery"


def test_operator_report_builds_totals_and_next_actions():
    client = MagicMock()
    campaigns = [
        {
            "id": 1,
            "name": "Category",
            "status": "ENABLED",
            "displayStatus": "RUNNING",
            "dailyBudgetAmount": {"amount": "10", "currency": "USD"},
            "countriesOrRegions": ["US"],
        }
    ]
    client.get_campaign_report.return_value = [
        {
            "total": {
                "impressions": 100,
                "taps": 10,
                "tapInstalls": 2,
                "localSpend": {"amount": "10.00"},
            }
        }
    ]
    rules = load_rules(app_config=AppConfig(app_id=123, app_name="TestApp"))

    report = build_operator_report(
        client,
        campaigns=campaigns,
        days=1,
        app_name=None,
        rules=rules,
    )

    assert report["totals"]["spend"] == 10.0
    assert report["totals"]["installs"] == 2
    assert report["campaigns"][0]["cpa"] == 5.0
    assert report["next_actions"][0]["type"] == "update_campaign_budget"


def test_summarize_report_rows_handles_missing_metrics():
    summary = summarize_report_rows(
        {"id": 1, "name": "Empty", "dailyBudgetAmount": {"amount": "5"}},
        [],
        None,
    )

    assert summary["spend"] == 0.0
    assert summary["cpa"] is None


def test_related_keyword_actions_lower_bid_and_pause_exact_loser():
    app_config = AppConfig(app_id=123, app_name="TestApp")
    app_config.optimization.cpa_threshold = 5
    app_config.optimization.lower_bid_cpa_multiplier = 1.5
    app_config.optimization.pause_keyword_min_spend = 6
    app_config.bids.bid_adjustment_pct = 10
    rules = load_rules(app_config=app_config)

    actions = build_related_keyword_actions(
        costly_terms=[
            {
                "campaign_id": 1,
                "campaign_name": "Category",
                "ad_group_id": 10,
                "ad_group_name": "Category-Exact",
                "keyword_id": 100,
                "keyword": "ai notes",
                "term": "ai notes app",
                "current_bid": 2.0,
                "cpa": 9.0,
                "spend": 18.0,
                "installs": 2,
            }
        ],
        loser_terms=[
            {
                "campaign_id": 1,
                "campaign_name": "Category",
                "ad_group_id": 10,
                "ad_group_name": "Category-Exact",
                "keyword_id": 101,
                "keyword": "bad notes",
                "term": "bad notes",
                "keyword_match_type": "EXACT",
                "spend": 7.0,
                "installs": 0,
                "cpa": float("inf"),
            },
            {
                "campaign_id": 1,
                "ad_group_id": 10,
                "keyword_id": 102,
                "keyword": "broad notes",
                "term": "bad broad notes",
                "keyword_match_type": "BROAD",
                "spend": 20.0,
                "installs": 0,
            },
        ],
        rules=rules,
    )

    assert [action.type for action in actions] == [
        PlanActionType.UPDATE_KEYWORD_BID,
        PlanActionType.PAUSE_KEYWORD,
    ]
    assert actions[0].bid_amount == 1.8
    assert actions[1].keyword_id == 101
    assert actions[1].before_metrics["cpa"] is None
