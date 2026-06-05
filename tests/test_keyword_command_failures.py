"""Regression tests for keyword mutation command failures."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from asa_cli.config import AppConfig, Credentials, CampaignType, MatchType
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
    return AppConfig(app_id=999999, app_name="TestApp")


def _campaign(campaign_id: int = 10, name: str = "TestApp - Category") -> dict:
    return {"id": campaign_id, "name": name, "adamId": 999999}


def test_update_bid_failure_exits_nonzero():
    """A failed keyword bid update should not look successful to automation."""
    client = MagicMock()
    client.update_keyword_bid.return_value = None

    with (
        patch("asa_cli.commands.keywords.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.keywords.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.keywords.require_campaign_in_current_app", return_value=_campaign()),
    ):
        result = runner.invoke(
            app,
            [
                "keywords",
                "update-bid",
                "--campaign",
                "10",
                "--ad-group",
                "20",
                "--keyword",
                "30",
                "--bid",
                "2.5",
                "--reason",
                "Regression test failed bid update",
            ],
        )

    assert result.exit_code == 1
    client.update_keyword_bid.assert_called_once_with(10, 20, 30, 2.5)


def test_add_negatives_api_error_exits_nonzero():
    """Non-duplicate negative-keyword add errors should fail the command."""
    client = MagicMock()
    client.add_negative_keywords.return_value = (
        [],
        [{"messageCode": "API_ERROR", "message": "api rejected"}],
    )

    with (
        patch("asa_cli.commands.keywords.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.keywords.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.keywords.require_campaign_in_current_app", return_value=_campaign()),
        patch("asa_cli.commands.keywords.Confirm.ask", return_value=True),
    ):
        result = runner.invoke(
            app,
            [
                "keywords",
                "add-negatives",
                "bad term",
                "--campaign",
                "10",
                "--reason",
                "Regression test failed negative add",
            ],
        )

    assert result.exit_code == 1
    client.add_negative_keywords.assert_called_once_with(10, ["bad term"])


def test_promote_keyword_api_error_exits_nonzero():
    """A failed exact promotion should not be hidden by the final success banner."""
    client = MagicMock()
    client.get_campaigns.return_value = [
        _campaign(10, "TestApp - Category"),
        _campaign(11, "TestApp - Discovery"),
    ]
    client.get_ad_groups.return_value = [{"id": 20, "name": "Category-Exact"}]
    client.add_keywords.return_value = (
        [],
        [{"messageCode": "API_ERROR", "message": "api rejected"}],
    )
    client.add_negative_keywords.return_value = (
        [],
        [{"messageCode": "DUPLICATE_KEYWORD", "message": "duplicate"}],
    )

    with (
        patch("asa_cli.commands.keywords.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.keywords.get_current_app_config", return_value=_app_config()),
        patch("asa_cli.commands.keywords.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.keywords.Confirm.ask", return_value=True),
    ):
        result = runner.invoke(
            app,
            [
                "keywords",
                "promote",
                "winner term",
                "--target",
                CampaignType.CATEGORY.value,
                "--reason",
                "Regression test failed promotion",
            ],
        )

    assert result.exit_code == 1
    client.add_keywords.assert_called_once_with(
        campaign_id=10,
        ad_group_id=20,
        keywords=["winner term"],
        match_type=MatchType.EXACT,
        bid_amount=None,
    )


def test_pause_keyword_failure_exits_nonzero():
    """A failed keyword pause should return a failing process status."""
    client = MagicMock()
    client.get_keywords.return_value = [
        {"id": 30, "text": "keyword", "status": "ACTIVE", "bidAmount": {"amount": "1.5"}}
    ]
    client.pause_keyword.return_value = False

    with (
        patch("asa_cli.commands.keywords.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.keywords.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.keywords.require_campaign_in_current_app", return_value=_campaign()),
    ):
        result = runner.invoke(
            app,
            [
                "keywords",
                "pause",
                "--campaign",
                "10",
                "--ad-group",
                "20",
                "--keyword",
                "30",
                "--reason",
                "Regression test failed pause",
            ],
        )

    assert result.exit_code == 1
    client.pause_keyword.assert_called_once_with(10, 20, 30)


def test_pause_all_keywords_partial_failure_exits_nonzero():
    """Bulk pause should fail the process if any keyword fails to pause."""
    client = MagicMock()
    client.get_keywords.return_value = [
        {"id": 30, "text": "first", "status": "ACTIVE", "bidAmount": {"amount": "1.5"}},
        {"id": 31, "text": "second", "status": "ACTIVE", "bidAmount": {"amount": "1.5"}},
    ]
    client.pause_keyword.side_effect = [True, False]

    with (
        patch("asa_cli.commands.keywords.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.keywords.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.keywords.require_campaign_in_current_app", return_value=_campaign()),
        patch("asa_cli.commands.keywords.log_manual_decision"),
    ):
        result = runner.invoke(
            app,
            [
                "keywords",
                "pause",
                "--campaign",
                "10",
                "--ad-group",
                "20",
                "--all",
                "--reason",
                "Regression test partial bulk pause failure",
            ],
        )

    assert result.exit_code == 1
    assert client.pause_keyword.call_count == 2
    assert "failed" in result.output


def test_enable_all_keywords_partial_failure_exits_nonzero():
    """Bulk enable should fail the process if any keyword fails to enable."""
    client = MagicMock()
    client.get_keywords.return_value = [
        {"id": 30, "text": "first", "status": "PAUSED", "bidAmount": {"amount": "1.5"}},
        {"id": 31, "text": "second", "status": "PAUSED", "bidAmount": {"amount": "1.5"}},
    ]
    client.enable_keyword.side_effect = [True, False]

    with (
        patch("asa_cli.commands.keywords.load_credentials", return_value=_credentials()),
        patch("asa_cli.commands.keywords.SearchAdsClient", return_value=client),
        patch("asa_cli.commands.keywords.require_campaign_in_current_app", return_value=_campaign()),
        patch("asa_cli.commands.keywords.log_manual_decision"),
    ):
        result = runner.invoke(
            app,
            [
                "keywords",
                "enable",
                "--campaign",
                "10",
                "--ad-group",
                "20",
                "--all",
                "--reason",
                "Regression test partial bulk enable failure",
            ],
        )

    assert result.exit_code == 1
    assert client.enable_keyword.call_count == 2
    assert "failed" in result.output
