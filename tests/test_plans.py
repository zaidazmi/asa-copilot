"""Tests for change plan serialization and apply dispatch."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from asa_cli.config import AppConfig, CampaignType, MatchType, load_rules
from asa_cli.plans import (
    ChangePlan,
    PlanAction,
    PlanActionType,
    PlanLoadError,
    apply_plan,
    load_plan,
    save_applied_plan,
    save_plan,
)
from asa_cli.commands.optimize import build_optimization_plan, resolve_optimization_settings


def test_plan_round_trip(tmp_path: Path):
    """Plans can be written to disk and loaded back."""
    path = tmp_path / "plan.json"
    plan = ChangePlan(
        source="test",
        summary="Add test negatives",
        actions=[
            PlanAction(
                type=PlanActionType.ADD_NEGATIVE_KEYWORDS,
                description="Block bad terms",
                campaign_id=123,
                keywords=["free notes"],
                match_type=MatchType.EXACT,
            )
        ],
    )

    save_plan(plan, path)
    loaded = load_plan(path)

    assert loaded.id == plan.id
    assert loaded.actions[0].type == PlanActionType.ADD_NEGATIVE_KEYWORDS
    assert loaded.actions[0].keywords == ["free notes"]


def test_load_plan_missing_file_raises_plan_load_error(tmp_path: Path):
    """Missing plan files raise a clean domain error."""
    missing = tmp_path / "missing.json"

    try:
        load_plan(missing)
    except PlanLoadError as exc:
        assert "Plan file not found" in str(exc)
    else:
        raise AssertionError("Expected PlanLoadError")


def test_load_plan_invalid_json_raises_plan_load_error(tmp_path: Path):
    """Malformed JSON raises a clean domain error."""
    path = tmp_path / "bad.json"
    path.write_text("{bad json")

    try:
        load_plan(path)
    except PlanLoadError as exc:
        assert "not valid JSON" in str(exc)
    else:
        raise AssertionError("Expected PlanLoadError")


def test_load_plan_invalid_schema_raises_plan_load_error(tmp_path: Path):
    """Invalid plan schema raises a clean domain error."""
    path = tmp_path / "bad-schema.json"
    path.write_text('{"actions": [{"type": "not_real", "description": "Bad"}]}')

    try:
        load_plan(path)
    except PlanLoadError as exc:
        assert "does not match the plan schema" in str(exc)
    else:
        raise AssertionError("Expected PlanLoadError")


def test_load_plan_top_level_array_raises_plan_load_error(tmp_path: Path):
    """JSON with the wrong top-level shape raises a clean domain error."""
    path = tmp_path / "bad-shape.json"
    path.write_text("[]")

    try:
        load_plan(path)
    except PlanLoadError as exc:
        assert "does not match the plan schema" in str(exc)
    else:
        raise AssertionError("Expected PlanLoadError")


def test_apply_plan_adds_keywords_and_negatives():
    """Apply dispatch calls the API methods for executable keyword actions."""
    client = MagicMock()
    client.add_keywords.return_value = ([{"id": 1}], [])
    client.add_negative_keywords.return_value = ([{"id": 2}], [])

    plan = ChangePlan(
        actions=[
            PlanAction(
                type=PlanActionType.ADD_KEYWORDS,
                description="Promote winners",
                campaign_id=10,
                ad_group_id=20,
                keywords=["meeting notes"],
                match_type=MatchType.EXACT,
            ),
            PlanAction(
                type=PlanActionType.ADD_NEGATIVE_KEYWORDS,
                description="Block losers",
                campaign_id=30,
                keywords=["bad fit"],
                match_type=MatchType.EXACT,
            ),
        ]
    )

    result = apply_plan(client, plan)

    assert result.success is True
    client.add_keywords.assert_called_once_with(
        campaign_id=10,
        ad_group_id=20,
        keywords=["meeting notes"],
        match_type=MatchType.EXACT,
        bid_amount=None,
    )
    client.add_negative_keywords.assert_called_once_with(
        campaign_id=30,
        keywords=["bad fit"],
        match_type=MatchType.EXACT,
    )


def test_apply_plan_duplicate_keyword_errors_are_success():
    """Duplicate keyword API errors are treated as already-applied."""
    client = MagicMock()
    client.add_negative_keywords.return_value = (
        [],
        [{"messageCode": "DUPLICATE_KEYWORD", "message": "duplicate"}],
    )
    plan = ChangePlan(
        actions=[
            PlanAction(
                type=PlanActionType.ADD_NEGATIVE_KEYWORDS,
                description="Block existing term",
                campaign_id=30,
                keywords=["already blocked"],
            )
        ]
    )

    result = apply_plan(client, plan)

    assert result.success is True
    assert "already existed" in result.results[0].message


def test_save_applied_plan_writes_jsonl(tmp_path: Path):
    """Applied plans are appended to local audit history."""
    audit_path = tmp_path / "applied-plans.jsonl"
    plan = ChangePlan(actions=[])
    result = apply_plan(MagicMock(), plan)

    with patch("asa_cli.plans.APPLIED_PLANS_FILE", audit_path):
        save_applied_plan(plan, result)

    records = audit_path.read_text().strip().splitlines()
    assert len(records) == 1
    record = json.loads(records[0])
    assert record["plan"]["id"] == plan.id
    assert record["result"]["plan_id"] == plan.id


def test_build_optimization_plan_creates_promotion_and_negative_actions():
    """Optimization analysis becomes concrete plan actions."""
    client = MagicMock()
    client.get_ad_groups.return_value = [{"id": 200, "name": "Category-Exact"}]

    plan = build_optimization_plan(
        client=client,
        winners=[{"term": "ai notes"}],
        losers=[{"term": "free games"}],
        discovery_campaign={"id": 1, "name": "Discovery"},
        target_campaign={"id": 2, "name": "Category"},
        managed_campaigns=[
            ({"id": 1, "name": "Discovery"}, CampaignType.DISCOVERY),
            ({"id": 2, "name": "Category"}, CampaignType.CATEGORY),
        ],
        days=14,
        target_type=CampaignType.CATEGORY,
        app_name="Test App",
    )

    assert plan.source == "optimize"
    assert len(plan.actions) == 4
    assert plan.actions[0].type == PlanActionType.ADD_KEYWORDS
    assert plan.actions[0].ad_group_id == 200
    assert plan.actions[0].keywords == ["ai notes"]
    assert plan.actions[0].before_metrics["term_count"] == 1
    assert plan.actions[0].metadata["search_terms"][0]["term"] == "ai notes"
    assert plan.actions[1].type == PlanActionType.ADD_NEGATIVE_KEYWORDS
    assert plan.actions[2].keywords == ["free games"]
    assert plan.actions[2].before_metrics["term_count"] == 1
    assert plan.actions[2].metadata["search_terms"][0]["term"] == "free games"


def test_resolve_optimization_settings_uses_rules_only_when_option_missing():
    """Explicit CLI values must win even when they equal old hard-coded defaults."""
    app_config = AppConfig(app_id=123, app_name="TestApp")
    app_config.reporting.search_terms_days = 30
    app_config.optimization.cpa_threshold = 2.0
    app_config.optimization.min_installs = 5
    app_config.optimization.min_spend = 10.0
    app_config.optimization.min_impressions = 25
    rules = load_rules(app_config=app_config)

    resolved = resolve_optimization_settings(
        days=14,
        lookback=None,
        cpa_threshold=5.0,
        min_installs=2,
        min_spend=1.0,
        min_impressions=0,
        rules=rules,
    )

    assert resolved == (14, 5.0, 2, 1.0, 0)


def test_resolve_optimization_settings_falls_back_to_rules():
    """Missing CLI values inherit the active rules."""
    app_config = AppConfig(app_id=123, app_name="TestApp")
    app_config.reporting.search_terms_days = 21
    app_config.optimization.cpa_threshold = 3.0
    app_config.optimization.min_installs = 1
    app_config.optimization.min_spend = 2.5
    app_config.optimization.min_impressions = 8
    rules = load_rules(app_config=app_config)

    resolved = resolve_optimization_settings(
        days=None,
        lookback=None,
        cpa_threshold=None,
        min_installs=None,
        min_spend=None,
        min_impressions=None,
        rules=rules,
    )

    assert resolved == (21, 3.0, 1, 2.5, 8)
