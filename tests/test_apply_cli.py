"""CLI regression tests for applying failed plans."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from asa_cli.config import AppConfig, CampaignType, Credentials
from asa_cli.main import app
from asa_cli.plans import (
    ApplyActionResult,
    ApplyPlanResult,
    ChangePlan,
    PlanAction,
    PlanActionType,
)


runner = CliRunner()


def _credentials() -> Credentials:
    return Credentials(
        org_id=123456,
        client_id="test_client",
        team_id="test_team",
        key_id="test_key",
        private_key_path="/tmp/key.pem",
    )


def _failed_result(plan_id: str = "plan-1") -> ApplyPlanResult:
    return ApplyPlanResult(
        plan_id=plan_id,
        success=False,
        results=[
            ApplyActionResult(
                action_id="action-1",
                action_type=PlanActionType.ADD_KEYWORDS,
                success=False,
                message="api rejected",
            )
        ],
    )


def _plan(path: Path) -> ChangePlan:
    plan = ChangePlan(
        id="plan-1",
        app_id=999999,
        app_name="TestApp",
        actions=[
            PlanAction(
                id="action-1",
                type=PlanActionType.ADD_KEYWORDS,
                description="Promote keyword",
                campaign_id=10,
                ad_group_id=20,
                keywords=["winner"],
                reason="Regression test failed apply result",
            )
        ],
    )
    path.write_text(plan.model_dump_json())
    return plan


def test_apply_failed_result_exits_nonzero_after_saving_audit(tmp_path: Path):
    """asa apply should report failed action results with a failing process status."""
    plan_path = tmp_path / "plan.json"
    _plan(plan_path)

    with (
        patch("asa_cli.main.load_credentials", return_value=_credentials()),
        patch("asa_cli.main.SearchAdsClient", return_value=MagicMock()),
        patch("asa_cli.main.apply_plan", return_value=_failed_result()),
        patch("asa_cli.main.save_applied_plan") as save_applied,
    ):
        result = runner.invoke(app, ["apply", str(plan_path), "--auto-approve"])

    assert result.exit_code == 1
    save_applied.assert_called_once()
    assert "api rejected" in result.output


def test_apply_failed_json_result_exits_nonzero_after_printing_result(tmp_path: Path):
    """JSON apply output should still be emitted before the failed exit status."""
    plan_path = tmp_path / "plan.json"
    _plan(plan_path)

    with (
        patch("asa_cli.main.load_credentials", return_value=_credentials()),
        patch("asa_cli.main.SearchAdsClient", return_value=MagicMock()),
        patch("asa_cli.main.apply_plan", return_value=_failed_result()),
        patch("asa_cli.main.save_applied_plan"),
    ):
        result = runner.invoke(
            app,
            ["--format", "compact", "apply", str(plan_path), "--auto-approve", "--json"],
        )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["success"] is False
    assert payload["results"][0]["message"] == "api rejected"


def test_optimize_auto_approve_failed_apply_exits_nonzero():
    """optimize --auto-approve should fail the process when plan apply fails."""
    plan = ChangePlan(
        id="plan-1",
        actions=[
            PlanAction(
                id="action-1",
                type=PlanActionType.ADD_KEYWORDS,
                description="Promote keyword",
                campaign_id=10,
                ad_group_id=20,
                keywords=["winner"],
                reason="Regression test failed optimize apply",
            )
        ],
    )
    analysis = MagicMock()
    analysis.winners = [
        {
            "term": "winner",
            "installs": 2,
            "spend": 4.0,
            "cpa": 2.0,
            "impressions": 100,
        }
    ]
    analysis.losers = []
    analysis.total_terms = 1
    analysis.skipped_no_text = 0
    analysis.skipped_no_activity = 0

    with (
        patch("asa_cli.commands.optimize.load_credentials", return_value=_credentials()),
        patch(
            "asa_cli.commands.optimize.get_current_app_config",
            return_value=AppConfig(app_id=999999, app_name="TestApp"),
        ),
        patch("asa_cli.commands.optimize.SearchAdsClient", return_value=MagicMock()),
        patch(
            "asa_cli.commands.optimize.get_campaigns_indexed",
            return_value=(
                {
                    CampaignType.DISCOVERY: {"id": 11, "name": "Discovery"},
                    CampaignType.CATEGORY: {"id": 10, "name": "Category"},
                },
                [
                    ({"id": 11, "name": "Discovery"}, CampaignType.DISCOVERY),
                    ({"id": 10, "name": "Category"}, CampaignType.CATEGORY),
                ],
            ),
        ),
        patch("asa_cli.commands.optimize.analyze_search_terms", return_value=analysis),
        patch("asa_cli.commands.optimize.build_optimization_plan", return_value=plan),
        patch("asa_cli.commands.optimize.apply_plan", return_value=_failed_result()),
        patch("asa_cli.commands.optimize.save_applied_plan") as save_applied,
    ):
        result = runner.invoke(app, ["optimize", "--auto-approve"])

    assert result.exit_code == 1
    save_applied.assert_called_once()
    assert "api rejected" in result.output
