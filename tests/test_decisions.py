"""Tests for decision log storage and rendering."""

import json
from pathlib import Path

from asa_cli.decisions import (
    DecisionRecord,
    decisions_to_markdown,
    find_decision,
    load_decisions,
    log_applied_plan_decisions,
    log_manual_decision,
)
from asa_cli.plans import ApplyActionResult, ApplyPlanResult, ChangePlan, PlanAction, PlanActionType


def test_log_manual_decision_writes_jsonl(tmp_path: Path, monkeypatch):
    path = tmp_path / "decision-log.jsonl"
    monkeypatch.setattr("asa_cli.decisions.DECISION_LOG_FILE", path)

    record = log_manual_decision(
        event_type="campaign_paused",
        reason="Poor CPA after 14 day test",
        command="campaigns pause",
        campaign_id=123,
        campaign_name="Category",
    )

    raw = json.loads(path.read_text().strip())
    assert raw["id"] == record.id
    assert raw["event_type"] == "campaign_paused"
    assert raw["reason"] == "Poor CPA after 14 day test"


def test_log_manual_decision_accepts_keyword_context(tmp_path: Path, monkeypatch):
    path = tmp_path / "decision-log.jsonl"
    monkeypatch.setattr("asa_cli.decisions.DECISION_LOG_FILE", path)

    log_manual_decision(
        event_type="keyword_bids_updated",
        reason="Raise bids to get impressions",
        command="keywords update-bids-bulk",
        keyword_id=123,
        keywords=["ai interior design"],
        evidence={"impressions": 0},
        follow_up_window="24 hours",
    )

    raw = json.loads(path.read_text().strip())
    assert raw["keyword_id"] == 123
    assert raw["keywords"] == ["ai interior design"]
    assert raw["evidence"]["impressions"] == 0
    assert raw["follow_up_window"] == "24 hours"


def test_load_and_find_decision_by_prefix(tmp_path: Path):
    path = tmp_path / "decision-log.jsonl"
    record = DecisionRecord(event_type="campaign_enabled", reason="App review resolved")
    path.write_text(record.model_dump_json() + "\n")

    records = load_decisions(path)
    found = find_decision(record.id[:8], path)

    assert records[0].id == record.id
    assert found is not None
    assert found.reason == "App review resolved"


def test_log_applied_plan_decisions_copies_action_reason_and_result(tmp_path: Path):
    path = tmp_path / "decision-log.jsonl"
    plan = ChangePlan(
        id="plan-1",
        source="test",
        actions=[
            PlanAction(
                id="action-1",
                type=PlanActionType.UPDATE_CAMPAIGN_BUDGET,
                description="Raise budget",
                campaign_id=123,
                campaign_name="Category",
                daily_budget_amount=20,
                reason="Campaign is capped with good CPA",
                before_metrics={"spend_pace": 0.95},
            )
        ],
    )
    result = ApplyPlanResult(
        plan_id=plan.id,
        success=True,
        results=[
            ApplyActionResult(
                action_id="action-1",
                action_type=PlanActionType.UPDATE_CAMPAIGN_BUDGET,
                success=True,
                message="Updated campaign budget",
            )
        ],
    )

    log_applied_plan_decisions(plan, result, approval_note="Approved by Zaid", path=path)
    loaded = load_decisions(path)

    assert len(loaded) == 1
    assert loaded[0].plan_id == "plan-1"
    assert loaded[0].reason == "Campaign is capped with good CPA"
    assert loaded[0].note == "Approved by Zaid"
    assert loaded[0].evidence["spend_pace"] == 0.95
    assert loaded[0].result["success"] is True


def test_decisions_to_markdown_contains_reasons():
    record = DecisionRecord(
        event_type="campaign_paused",
        reason="Duplicate campaign structure",
        campaign_id=123,
        campaign_name="Discovery",
    )

    markdown = decisions_to_markdown([record])

    assert "ASA Decision Log" in markdown
    assert "Duplicate campaign structure" in markdown
    assert "Discovery" in markdown
