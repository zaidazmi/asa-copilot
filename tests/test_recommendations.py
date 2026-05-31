"""Tests for optimization recommendation rules."""

from asa_cli.config import AppConfig, CampaignType, load_rules
from asa_cli.plans import PlanActionType
from asa_cli.recommendations import (
    RecommendationType,
    build_keyword_recommendations,
    build_search_term_recommendations,
    keyword_report_row_to_metrics,
)


def test_search_term_recommendations_convert_to_plan_actions():
    recommendations = build_search_term_recommendations(
        winners=[{"term": "ai notes", "installs": 3, "spend": 6, "cpa": 2}],
        losers=[{"term": "free games", "installs": 0, "spend": 4, "impressions": 100}],
        discovery_campaign={"id": 1, "name": "Discovery"},
        target_campaign={"id": 2, "name": "Category"},
        exact_ad_group={"id": 20, "name": "Category-Exact"},
        managed_campaigns=[
            ({"id": 1, "name": "Discovery"}, CampaignType.DISCOVERY),
            ({"id": 2, "name": "Category"}, CampaignType.CATEGORY),
        ],
        days=14,
        target_type=CampaignType.CATEGORY,
    )

    actions = [recommendation.to_plan_action() for recommendation in recommendations]

    assert [action.type for action in actions] == [
        PlanActionType.ADD_KEYWORDS,
        PlanActionType.ADD_NEGATIVE_KEYWORDS,
        PlanActionType.ADD_NEGATIVE_KEYWORDS,
        PlanActionType.ADD_NEGATIVE_KEYWORDS,
    ]
    assert actions[0].ad_group_id == 20
    assert actions[0].keywords == ["ai notes"]
    assert actions[0].metadata["recommendation_type"] == "promote_search_term"
    assert actions[2].keywords == ["free games"]


def test_keyword_rules_pause_lower_and_raise_bids():
    app_config = AppConfig(app_id=123, app_name="TestApp")
    app_config.optimization.cpa_threshold = 5
    app_config.optimization.pause_keyword_min_spend = 6
    app_config.optimization.lower_bid_cpa_multiplier = 1.5
    app_config.optimization.raise_bid_cpa_multiplier = 0.8
    app_config.optimization.raise_bid_min_installs = 2
    app_config.bids.bid_adjustment_pct = 10
    app_config.bids.max_bid_change_pct = 25
    rules = load_rules(app_config=app_config)

    recommendations = build_keyword_recommendations(
        [
            {
                "campaign_id": 1,
                "campaign_name": "Category",
                "ad_group_id": 10,
                "ad_group_name": "Category-Exact",
                "keyword_id": 100,
                "keyword": "bad keyword",
                "current_bid": 1.0,
                "installs": 0,
                "spend": 7.0,
                "cpa": None,
            },
            {
                "campaign_id": 1,
                "ad_group_id": 10,
                "keyword_id": 101,
                "keyword": "expensive keyword",
                "current_bid": 2.0,
                "installs": 2,
                "spend": 20.0,
                "cpa": 10.0,
            },
            {
                "campaign_id": 1,
                "ad_group_id": 10,
                "keyword_id": 102,
                "keyword": "winner keyword",
                "current_bid": 1.0,
                "installs": 3,
                "spend": 6.0,
                "cpa": 2.0,
            },
        ],
        rules,
    )

    assert [recommendation.type for recommendation in recommendations] == [
        RecommendationType.PAUSE_KEYWORD,
        RecommendationType.LOWER_BID,
        RecommendationType.RAISE_BID,
    ]

    actions = [recommendation.to_plan_action() for recommendation in recommendations]
    assert actions[0].type == PlanActionType.PAUSE_KEYWORD
    assert actions[1].type == PlanActionType.UPDATE_KEYWORD_BID
    assert actions[1].bid_amount == 1.8
    assert actions[2].type == PlanActionType.UPDATE_KEYWORD_BID
    assert actions[2].bid_amount == 1.1


def test_keyword_rules_skip_rows_without_actionable_ids():
    rules = load_rules(app_config=AppConfig(app_id=123, app_name="TestApp"))

    recommendations = build_keyword_recommendations(
        [{"keyword": "missing ids", "current_bid": 1, "installs": 0, "spend": 10}],
        rules,
    )

    assert recommendations == []


def test_keyword_report_row_to_metrics_normalizes_apple_report_shape():
    row = {
        "metadata": {
            "keywordId": 100,
            "keyword": "ai notes",
            "bidAmount": {"amount": "1.25", "currency": "USD"},
        },
        "total": {
            "impressions": 100,
            "taps": 10,
            "tapInstalls": 2,
            "localSpend": {"amount": "6.00", "currency": "USD"},
        },
    }

    metrics = keyword_report_row_to_metrics(
        row,
        campaign={"id": 1, "name": "Category"},
        ad_group={"id": 2, "name": "Category-Exact"},
    )

    assert metrics["campaign_id"] == 1
    assert metrics["ad_group_id"] == 2
    assert metrics["keyword_id"] == 100
    assert metrics["current_bid"] == 1.25
    assert metrics["cpa"] == 3.0
