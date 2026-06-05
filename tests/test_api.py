"""Tests for API client module."""

from unittest.mock import MagicMock, patch

import pytest

from asa_cli.api import SearchAdsClient
from asa_cli.config import AppConfig, Credentials, MatchType


@pytest.fixture
def mock_credentials():
    """Create mock credentials for testing."""
    return Credentials(
        org_id=123456,
        client_id="test_client",
        team_id="test_team",
        key_id="test_key",
        private_key_path="/path/to/key.pem",
    )


@pytest.fixture
def mock_app_config():
    """Create mock app config for testing."""
    return AppConfig(
        app_id=999999,
        app_name="TestApp",
        default_countries=["US"],
        default_bid=1.50,
    )


@pytest.fixture
def mock_client(mock_credentials, mock_app_config):
    """Create a mock SearchAdsClient."""
    with patch.object(SearchAdsClient, "_get_access_token", return_value="mock_token"):
        client = SearchAdsClient(mock_credentials, app_config=mock_app_config)
        return client


class TestPagination:
    """Tests for pagination support."""

    def test_get_all_paginated_single_page(self, mock_client):
        """Test pagination with single page of results."""
        mock_response = {
            "data": [{"id": 1}, {"id": 2}, {"id": 3}],
            "pagination": {"totalResults": 3, "startIndex": 0, "itemsPerPage": 20},
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            results = mock_client._get_all_paginated("/test/endpoint")

        assert len(results) == 3
        assert results[0]["id"] == 1

    def test_get_all_paginated_multiple_pages(self, mock_client):
        """Test pagination fetches all pages."""
        # First page
        page1 = {
            "data": [{"id": i} for i in range(20)],
            "pagination": {"totalResults": 35, "startIndex": 0, "itemsPerPage": 20},
        }
        # Second page
        page2 = {
            "data": [{"id": i} for i in range(20, 35)],
            "pagination": {"totalResults": 35, "startIndex": 20, "itemsPerPage": 20},
        }

        with patch.object(mock_client, "_request", side_effect=[page1, page2]):
            results = mock_client._get_all_paginated("/test/endpoint")

        assert len(results) == 35

    def test_get_all_paginated_empty_results(self, mock_client):
        """Test pagination with no results."""
        mock_response = {
            "data": [],
            "pagination": {"totalResults": 0, "startIndex": 0, "itemsPerPage": 20},
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            results = mock_client._get_all_paginated("/test/endpoint")

        assert len(results) == 0

    def test_get_keywords_uses_pagination(self, mock_client):
        """Test get_keywords uses pagination helper."""
        mock_response = {
            "data": [
                {"id": 1, "text": "keyword1", "deleted": False},
                {"id": 2, "text": "keyword2", "deleted": False},
            ],
            "pagination": {"totalResults": 2, "startIndex": 0, "itemsPerPage": 1000},
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            results = mock_client.get_keywords(123, 456)

        assert len(results) == 2

    def test_get_keywords_filters_deleted(self, mock_client):
        """Test get_keywords filters deleted keywords by default."""
        mock_response = {
            "data": [
                {"id": 1, "text": "active", "deleted": False},
                {"id": 2, "text": "deleted", "deleted": True},
            ],
            "pagination": {"totalResults": 2, "startIndex": 0, "itemsPerPage": 1000},
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            results = mock_client.get_keywords(123, 456, include_deleted=False)

        assert len(results) == 1
        assert results[0]["text"] == "active"

    def test_get_keywords_includes_deleted_when_requested(self, mock_client):
        """Test get_keywords can include deleted keywords."""
        mock_response = {
            "data": [
                {"id": 1, "text": "active", "deleted": False},
                {"id": 2, "text": "deleted", "deleted": True},
            ],
            "pagination": {"totalResults": 2, "startIndex": 0, "itemsPerPage": 1000},
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            results = mock_client.get_keywords(123, 456, include_deleted=True)

        assert len(results) == 2


class TestNegativeKeywordsErrorHandling:
    """Tests for add_negative_keywords error handling."""

    def test_add_negative_keywords_success(self, mock_client):
        """Test successful negative keyword addition."""
        mock_response = {
            "data": [{"id": 1, "text": "blocked"}],
            "pagination": None,
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            added, errors = mock_client.add_negative_keywords(123, ["blocked"])

        assert len(added) == 1
        assert len(errors) == 0

    def test_add_negative_keywords_duplicate_error(self, mock_client):
        """Test duplicate keyword returns error info."""
        mock_response = {
            "data": [],
            "pagination": None,
            "error": {
                "errors": [
                    {
                        "messageCode": "DUPLICATE_KEYWORD",
                        "message": "duplicate keyword found in the system",
                        "field": "NegativeKeywordImport[0].text:matchType",
                    }
                ]
            },
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            added, errors = mock_client.add_negative_keywords(123, ["existing"])

        assert len(added) == 0
        assert len(errors) == 1
        assert errors[0]["messageCode"] == "DUPLICATE_KEYWORD"

    def test_add_negative_keywords_empty_list(self, mock_client):
        """Test adding empty keyword list."""
        added, errors = mock_client.add_negative_keywords(123, [])

        assert len(added) == 0
        assert len(errors) == 0

    def test_add_negative_keywords_lowercases_input(self, mock_client):
        """Test keywords are lowercased before sending."""
        mock_response = {"data": [{"id": 1, "text": "test"}], "pagination": None}

        with patch.object(mock_client, "_request", return_value=mock_response) as mock_req:
            mock_client.add_negative_keywords(123, ["TEST", "MiXeD"])

            # Check the data sent to API was lowercased
            call_args = mock_req.call_args
            data = call_args.kwargs.get("data") or call_args[1].get("data")
            texts = [kw["text"] for kw in data]
            assert texts == ["test", "mixed"]


class TestAddKeywordsErrorHandling:
    """Tests for add_keywords error handling (tuple return)."""

    def test_add_keywords_success(self, mock_client):
        """Test successful keyword addition returns tuple."""
        mock_response = {
            "data": [{"id": 1, "text": "test keyword"}],
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            added, errors = mock_client.add_keywords(123, 456, ["test keyword"], MatchType.EXACT)

        assert len(added) == 1
        assert len(errors) == 0

    def test_add_keywords_duplicate_error(self, mock_client):
        """Test duplicate keyword returns error info."""
        mock_response = {
            "data": [],
            "error": {
                "errors": [
                    {
                        "messageCode": "DUPLICATE_KEYWORD",
                        "message": "duplicate keyword found",
                    }
                ]
            },
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            added, errors = mock_client.add_keywords(123, 456, ["existing"], MatchType.EXACT)

        assert len(added) == 0
        assert len(errors) == 1
        assert errors[0]["messageCode"] == "DUPLICATE_KEYWORD"

    def test_add_keywords_empty_list(self, mock_client):
        """Test adding empty keyword list."""
        added, errors = mock_client.add_keywords(123, 456, [], MatchType.EXACT)

        assert len(added) == 0
        assert len(errors) == 0


class TestCampaignOperations:
    """Tests for campaign operations."""

    def test_get_campaigns_uses_pagination(self, mock_client):
        """Test get_campaigns uses pagination."""
        mock_response = {
            "data": [{"id": 1, "name": "Brand"}, {"id": 2, "name": "Category"}],
            "pagination": {"totalResults": 2, "startIndex": 0, "itemsPerPage": 1000},
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            results = mock_client.get_campaigns()

        assert len(results) == 2

    def test_get_ad_groups_uses_pagination(self, mock_client):
        """Test get_ad_groups uses pagination."""
        mock_response = {
            "data": [{"id": 1, "name": "Exact"}, {"id": 2, "name": "Broad"}],
            "pagination": {"totalResults": 2, "startIndex": 0, "itemsPerPage": 1000},
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            results = mock_client.get_ad_groups(123)

        assert len(results) == 2

    def test_get_negative_keywords_uses_pagination(self, mock_client):
        """Test get_negative_keywords uses pagination."""
        mock_response = {
            "data": [{"id": 1, "text": "blocked1"}, {"id": 2, "text": "blocked2"}],
            "pagination": {"totalResults": 2, "startIndex": 0, "itemsPerPage": 1000},
        }

        with patch.object(mock_client, "_request", return_value=mock_response):
            results = mock_client.get_negative_keywords(123)

        assert len(results) == 2

    def test_client_uses_injected_app_config(self, mock_credentials, mock_app_config):
        """Test client uses the injected app_config instead of loading from file."""
        with patch.object(SearchAdsClient, "_get_access_token", return_value="mock_token"):
            client = SearchAdsClient(mock_credentials, app_config=mock_app_config)
            assert client.app_config.app_id == 999999
            assert client.app_config.app_name == "TestApp"

    def test_create_campaign_requires_daily_budget(self, mock_client):
        """API v5 campaign creation requires a daily budget."""
        with pytest.raises(ValueError, match="daily_budget is required"):
            mock_client.create_campaign(name="Brand", budget=1500)

    def test_create_campaign_uses_app_currency_without_lifetime_budget(self, mock_client):
        """Daily-budget-only campaign creates should not add a lifetime budget."""
        mock_client.app_config.currency = "EUR"
        mock_response = {"data": {"id": 1, "name": "Brand"}}

        with patch.object(mock_client, "_request", return_value=mock_response) as request:
            result = mock_client.create_campaign(
                name="Brand",
                daily_budget=50,
                countries=["DE"],
            )

        assert result == {"id": 1, "name": "Brand"}
        payload = request.call_args.kwargs["data"]
        assert payload["dailyBudgetAmount"] == {"amount": "50", "currency": "EUR"}
        assert "budgetAmount" not in payload

    def test_create_campaign_keeps_explicit_lifetime_budget(self, mock_client):
        """An explicit lifetime budget remains supported at campaign creation."""
        mock_client.app_config.currency = "GBP"
        mock_response = {"data": {"id": 1, "name": "Brand"}}

        with patch.object(mock_client, "_request", return_value=mock_response) as request:
            mock_client.create_campaign(name="Brand", daily_budget=50, budget=1500)

        payload = request.call_args.kwargs["data"]
        assert payload["dailyBudgetAmount"] == {"amount": "50", "currency": "GBP"}
        assert payload["budgetAmount"] == {"amount": "1500", "currency": "GBP"}

    def test_create_ad_group_and_keywords_use_app_currency(self, mock_client):
        """Bid payloads should use the configured app/org currency."""
        mock_client.app_config.currency = "NZD"

        with patch.object(mock_client, "_request", return_value={"data": {"id": 2}}) as request:
            mock_client.create_ad_group(123, "Exact", default_bid=2.5, cpa_goal=4.0)

        ad_group_payload = request.call_args.kwargs["data"]
        assert ad_group_payload["defaultBidAmount"] == {"amount": "2.5", "currency": "NZD"}
        assert ad_group_payload["cpaGoal"] == {"amount": "4.0", "currency": "NZD"}

        with patch.object(mock_client, "_request", return_value={"data": [{"id": 3}]}) as request:
            mock_client.add_keywords(123, 456, ["Test"], MatchType.EXACT, bid_amount=1.75)

        keyword_payload = request.call_args.kwargs["data"]
        assert keyword_payload[0]["bidAmount"] == {"amount": "1.75", "currency": "NZD"}

    def test_keyword_bid_update_and_budget_order_use_app_currency(self, mock_client):
        """Other spend-affecting API writes should use configured currency."""
        mock_client.app_config.currency = "CAD"

        with patch.object(mock_client, "_request", return_value={"data": [{"id": 3}]}) as request:
            mock_client.update_keyword_bid(123, 456, 789, 2.25)

        bid_payload = request.call_args.kwargs["data"]
        assert bid_payload[0]["bidAmount"] == {"amount": "2.25", "currency": "CAD"}

        with patch.object(mock_client, "_request", return_value={"data": {"id": 4}}) as request:
            mock_client.create_budget_order("June", 5000, "2026-06-01", "2026-06-30")

        budget_payload = request.call_args.kwargs["data"]
        assert budget_payload["budget"] == {"amount": "5000", "currency": "CAD"}

    def test_bulk_add_exceptions_return_api_error(self, mock_client):
        """Callers need a non-duplicate error when the request itself fails."""
        with patch.object(mock_client, "_request", side_effect=Exception("network down")):
            added, errors = mock_client.add_keywords(123, 456, ["test"], MatchType.EXACT)

        assert added == []
        assert errors == [{"message": "network down", "messageCode": "API_ERROR"}]

        with patch.object(mock_client, "_request", side_effect=Exception("api rejected")):
            added, errors = mock_client.add_negative_keywords(123, ["blocked"])

        assert added == []
        assert errors == [{"message": "api rejected", "messageCode": "API_ERROR"}]

    def test_raw_campaign_report_includes_group_by(self, mock_client):
        """Raw campaign reports should pass generic Apple groupBy fields through."""
        mock_response = {"data": {"reportingDataResponse": {"row": []}}}

        with patch.object(mock_client, "_request", return_value=mock_response) as request:
            result = mock_client.get_raw_campaign_report(
                123,
                group_by=["countryOrRegion", "deviceClass"],
                return_records_with_no_metrics=True,
            )

        assert result == mock_response
        method, endpoint = request.call_args.args
        payload = request.call_args.kwargs["data"]
        assert method == "POST"
        assert endpoint == "/reports/campaigns"
        assert payload["groupBy"] == ["countryOrRegion", "deviceClass"]
        assert payload["returnRecordsWithNoMetrics"] is True
        assert payload["selector"]["conditions"][0]["values"] == ["123"]
