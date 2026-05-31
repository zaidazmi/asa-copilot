"""Tests for active-app command safety helpers."""

from unittest.mock import Mock

import pytest
import typer

from asa_cli.commands.scope import require_campaign_in_current_app
from asa_cli.config import AppConfig


def test_require_campaign_in_current_app_allows_matching_adam_id(monkeypatch):
    client = Mock()
    client.get_campaign.return_value = {"id": 1, "name": "Lofto - Category", "adamId": 123}
    monkeypatch.setattr(
        "asa_cli.commands.scope.get_current_app_config",
        lambda: AppConfig(app_id=123, app_name="Lofto"),
    )

    campaign = require_campaign_in_current_app(client, 1)

    assert campaign["id"] == 1


def test_require_campaign_in_current_app_blocks_other_app(monkeypatch):
    client = Mock()
    client.get_campaign.return_value = {"id": 1, "name": "Noteo - Category", "adamId": 456}
    monkeypatch.setattr(
        "asa_cli.commands.scope.get_current_app_config",
        lambda: AppConfig(app_id=123, app_name="Lofto"),
    )

    with pytest.raises(typer.Exit):
        require_campaign_in_current_app(client, 1)


def test_require_campaign_in_current_app_blocks_missing_campaign(monkeypatch):
    client = Mock()
    client.get_campaign.return_value = None
    monkeypatch.setattr(
        "asa_cli.commands.scope.get_current_app_config",
        lambda: AppConfig(app_id=123, app_name="Lofto"),
    )

    with pytest.raises(typer.Exit):
        require_campaign_in_current_app(client, 99)
