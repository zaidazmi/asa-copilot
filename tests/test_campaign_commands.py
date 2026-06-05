"""Tests for campaign command request dispatch."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from asa_cli.config import AppConfig, Credentials
from asa_cli.main import app


runner = CliRunner()


def _credentials() -> Credentials:
    return Credentials(
        org_id=123456,
        client_id="test_client",
        team_id="test_team",
        key_id="test_key",
        private_key_path="/tmp/key.pem",
    )


def _app_config() -> AppConfig:
    return AppConfig(app_id=999999, app_name="TestApp", currency="EUR")


def test_campaigns_create_uses_daily_budget_only():
    """The create command should not silently add a lifetime budget."""
    client = MagicMock()
    client.create_campaign.return_value = {"id": 10, "name": "Brand"}

    with (
        patch("asa_cli.commands.campaigns.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.campaigns.get_current_app_config", return_value=_app_config()),
        patch("asa_cli.commands.campaigns.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.campaigns.log_manual_decision"),
    ):
        result = runner.invoke(
            app,
            [
                "campaigns",
                "create",
                "Brand",
                "--budget",
                "25",
                "--countries",
                "DE,FR",
                "--reason",
                "Test campaign creation",
            ],
        )

    assert result.exit_code == 0, result.output
    client.create_campaign.assert_called_once_with(
        name="Brand",
        daily_budget=25.0,
        countries=["DE", "FR"],
        status="ENABLED",
    )
    assert "budget" not in client.create_campaign.call_args.kwargs


def test_campaigns_setup_uses_daily_budget_only():
    """Four-campaign setup should not silently add lifetime budgets."""
    client = MagicMock()
    client.get_campaigns.return_value = []
    client.create_campaign.side_effect = [
        {"id": 10, "name": "Brand"},
        {"id": 20, "name": "Category"},
        {"id": 30, "name": "Competitor"},
        {"id": 40, "name": "Discovery"},
    ]
    client.create_ad_group.return_value = {"id": 100, "name": "Exact"}

    with (
        patch("asa_cli.commands.campaigns.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.campaigns.get_current_app_config", return_value=_app_config()),
        patch("asa_cli.commands.campaigns.is_multi_app", return_value=False),
        patch("asa_cli.commands.campaigns.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.campaigns.Confirm.ask", return_value=True),
        patch("asa_cli.commands.campaigns.log_manual_decision"),
    ):
        result = runner.invoke(
            app,
            [
                "campaigns",
                "setup",
                "--budget",
                "30",
                "--countries",
                "DE",
                "--reason",
                "Test setup",
            ],
        )

    assert result.exit_code == 0, result.output
    assert client.create_campaign.call_count == 4
    for call in client.create_campaign.call_args_list:
        assert call.kwargs["daily_budget"] == 30.0
        assert call.kwargs["countries"] == ["DE"]
        assert "budget" not in call.kwargs


def test_campaigns_update_uses_app_currency():
    """Campaign budget updates should use the active app currency."""
    client = MagicMock()
    client.update_campaign.return_value = {"id": 10, "name": "Brand"}
    campaign = {
        "id": 10,
        "name": "Brand",
        "adamId": 999999,
        "dailyBudgetAmount": {"amount": "20", "currency": "EUR"},
    }

    with (
        patch("asa_cli.commands.campaigns.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.campaigns.get_current_app_config", return_value=_app_config()),
        patch("asa_cli.commands.campaigns.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.campaigns.require_campaign_in_current_app", return_value=campaign),
        patch("asa_cli.commands.campaigns.log_manual_decision"),
    ):
        result = runner.invoke(
            app,
            [
                "campaigns",
                "update",
                "10",
                "--budget",
                "35",
                "--reason",
                "Budget adjustment",
            ],
        )

    assert result.exit_code == 0, result.output
    client.update_campaign.assert_called_once_with(
        10,
        {"dailyBudgetAmount": {"amount": "35.0", "currency": "EUR"}},
    )


def test_adgroups_update_uses_app_currency():
    """Ad group bid updates should use the active app currency."""
    client = MagicMock()
    client.update_ad_group.return_value = {"id": 20, "name": "Exact"}

    with (
        patch("asa_cli.commands.adgroups.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.adgroups.get_current_app_config", return_value=_app_config()),
        patch("asa_cli.commands.adgroups.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.adgroups.require_campaign_in_current_app", return_value={"id": 10}),
        patch("asa_cli.commands.adgroups.log_manual_decision"),
    ):
        result = runner.invoke(
            app,
            [
                "adgroups",
                "update",
                "20",
                "--campaign",
                "10",
                "--bid",
                "2.5",
                "--reason",
                "Bid adjustment",
            ],
        )

    assert result.exit_code == 0, result.output
    client.update_ad_group.assert_called_once_with(
        10,
        20,
        {"defaultBidAmount": {"amount": "2.5", "currency": "EUR"}},
    )
