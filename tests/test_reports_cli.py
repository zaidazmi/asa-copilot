"""CLI regression tests for reporting automation surfaces."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from asa_cli.config import AppConfig, Credentials
from asa_cli.main import app


def _credentials() -> Credentials:
    return Credentials(
        org_id=123456,
        client_id="client",
        team_id="team",
        key_id="key",
        private_key_path="/tmp/key.pem",
    )


def test_bid_recommendations_json_is_non_interactive():
    """JSON bid recommendations should report all scoped campaigns, not prompt."""
    runner = CliRunner()
    client = MagicMock()
    client.get_campaigns.return_value = [
        {"id": 123, "name": "AppBeta - Category - US", "adamId": 999}
    ]
    client.get_ad_groups.return_value = [{"id": 456, "name": "Category-Exact"}]
    client.get_keywords.return_value = [
        {"id": 789, "text": "ai notes", "matchType": "EXACT", "status": "ACTIVE"}
    ]
    client.get_keyword_adgroup_report.return_value = []

    with (
        patch("asa_cli.commands.reports.load_credentials", return_value=_credentials()),
        patch(
            "asa_cli.commands.reports.get_current_app_config",
            return_value=AppConfig(app_id=999, app_name="AppBeta"),
        ),
        patch("asa_cli.commands.reports.SearchAdsClient", return_value=client),
    ):
        result = runner.invoke(app, ["reports", "bid-recommendations", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["source"] == "bid-recommendations"
    assert payload["app_id"] == 999
    client.get_campaigns.assert_called_once()


def test_bid_recommendations_out_is_non_interactive(tmp_path):
    """Writing a bid recommendation plan should not require campaign selection."""
    runner = CliRunner()
    client = MagicMock()
    client.get_campaigns.return_value = [
        {"id": 123, "name": "AppBeta - Category - US", "adamId": 999}
    ]
    client.get_ad_groups.return_value = []
    out = tmp_path / "bid-plan.json"

    with (
        patch("asa_cli.commands.reports.load_credentials", return_value=_credentials()),
        patch(
            "asa_cli.commands.reports.get_current_app_config",
            return_value=AppConfig(app_id=999, app_name="AppBeta"),
        ),
        patch("asa_cli.commands.reports.SearchAdsClient", return_value=client),
    ):
        result = runner.invoke(app, ["reports", "bid-recommendations", "--out", str(out)])

    assert result.exit_code == 0
    payload = json.loads(out.read_text())
    assert payload["source"] == "bid-recommendations"
    assert payload["app_id"] == 999


def test_compact_json_format_for_bid_recommendations():
    """Global --format compact should produce machine-compact JSON output."""
    runner = CliRunner()
    client = MagicMock()
    client.get_campaigns.return_value = [
        {"id": 123, "name": "AppBeta - Category - US", "adamId": 999}
    ]
    client.get_ad_groups.return_value = []

    with (
        patch("asa_cli.commands.reports.load_credentials", return_value=_credentials()),
        patch(
            "asa_cli.commands.reports.get_current_app_config",
            return_value=AppConfig(app_id=999, app_name="AppBeta"),
        ),
        patch("asa_cli.commands.reports.SearchAdsClient", return_value=client),
    ):
        result = runner.invoke(
            app,
            ["--format", "compact", "reports", "bid-recommendations", "--json"],
        )

    assert result.exit_code == 0
    assert json.loads(result.output)["source"] == "bid-recommendations"
    assert "\n  " not in result.output


def test_raw_report_cli_grouping_json():
    """Raw report CLI should scope the campaign and emit grouped report payloads."""
    runner = CliRunner()
    client = MagicMock()
    client.get_campaign.return_value = {"id": 123, "name": "AppBeta - Search - US", "adamId": 999}
    client.get_raw_campaign_report.return_value = {
        "data": {"reportingDataResponse": {"row": [{"metadata": {"countryOrRegion": "US"}}]}}
    }

    with (
        patch("asa_cli.commands.reports.load_credentials", return_value=_credentials()),
        patch(
            "asa_cli.commands.scope.get_current_app_config",
            return_value=AppConfig(app_id=999, app_name="AppBeta"),
        ),
        patch("asa_cli.commands.reports.SearchAdsClient", return_value=client),
    ):
        result = runner.invoke(
            app,
            [
                "reports",
                "raw",
                "--campaign",
                "123",
                "--group-by",
                "countryOrRegion,deviceClass",
                "--json",
            ],
        )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["campaign"]["id"] == 123
    assert payload["request"]["group_by"] == ["countryOrRegion", "deviceClass"]
    client.get_raw_campaign_report.assert_called_once()


def test_config_discover_app_json():
    """App discovery should expose adam_id data without interactive setup."""
    runner = CliRunner()
    client = MagicMock()
    client.search_apps.return_value = [
        {"adamId": 111, "appName": "AppBeta", "developerName": "Example Dev"}
    ]

    with (
        patch("asa_cli.commands.config.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.config.SearchAdsClient", return_value=client),
    ):
        result = runner.invoke(app, ["config", "discover-app", "beta", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["apps"][0]["adamId"] == 111
    client.search_apps.assert_called_once_with("beta", return_owned=True, limit=10)
