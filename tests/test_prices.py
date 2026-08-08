"""Tests for the watchlist price pipeline: API fetch → cents→EUR → row accessors.

Regression guard for the "everything is 0.00" failure: a valid API response
must produce real prices, and API error bodies (HTTP 200 with
{"status": false, "message": ...}) must never be treated as a prices dict —
that used to silently blank every watchlist row with no error banner.
"""

from unittest.mock import Mock, patch

from price_empire_scraper import PriceEmpireScraper
from views import _row_avg_price, _row_buff_price, get_live_price, get_sort_value, render_watchlist

ITEM = {"name": "M4A1-S | Printstream", "wear": "Field-Tested",
        "stattrak": False, "souvenir": False}
NAME = "M4A1-S | Printstream (Field-Tested)"


def _mock_response(status_code, body):
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = body
    return resp


def _raw_item():
    """A realistic raw API entry: prices as a list of provider entries with
    cent values and avg fields (as the v4 trader endpoint returns them)."""
    return {
        "market_hash_name": NAME,
        "prices": [
            {"provider_key": "buff163", "price": 16679,
             "avg_7": 16658, "avg_30": 16992, "avg_60": 16985, "avg_90": 16724},
            {"provider_key": "skins", "price": 17000, "avg_7": 16922},
        ],
    }


def _fetch(body):
    with patch("price_empire_scraper.requests.get",
               return_value=_mock_response(200, body)):
        return PriceEmpireScraper("test-key").get_prices()


class TestWatchlistPricesLoad:
    def test_valid_response_renders_real_prices_not_zero(self):
        """Watchlist rows must show real EUR values, never all-zero."""
        prices = _fetch([_raw_item()])
        assert NAME in prices
        assert _row_buff_price(ITEM, prices) == 166.79
        assert _row_avg_price(ITEM, prices, 7) == 166.58
        assert _row_avg_price(ITEM, prices, 90) == 167.24
        assert get_sort_value(ITEM, prices, 1) == 166.79
        assert get_sort_value(ITEM, prices, 2) == 166.58

    def test_get_live_price_uses_buff163_and_fallback(self):
        prices = {NAME: {"prices": {"buff163": {"price": 166.79}}}}
        assert get_live_price(NAME, prices, 0.0) == 166.79
        assert get_live_price("Not There", {}, 42.0) == 42.0

    def test_missing_average_falls_back_to_zero(self):
        raw = _raw_item()
        raw["prices"][0].pop("avg_90")
        prices = _fetch([raw])
        assert _row_avg_price(ITEM, prices, 90) == 0.0
        assert _row_buff_price(ITEM, prices) == 166.79

    def test_missing_provider_entry_falls_back_to_zero(self):
        prices = {NAME: {"prices": {"skins": {"price": 170.0}}}}
        assert _row_buff_price(ITEM, prices) == 0.0
        assert _row_avg_price(ITEM, prices, 7) == 0.0

    def test_none_price_falls_back_to_zero(self):
        prices = {NAME: {"prices": {"buff163": {"price": None}}}}
        assert _row_buff_price(ITEM, prices) == 0.0


class TestApiErrorHandling:
    def test_error_banner_is_not_overwritten_by_table_border(self):
        """The 'Error: ...' banner must stay visible: the table's top border
        must not be drawn on the same row as the banner."""
        scr = Mock()
        render_watchlist(scr, 0, 120, [ITEM], {}, 1, True, 0, 0, 30, 6,
                         "API status 401")
        calls = scr.addstr.call_args_list
        banner_drawn = any(c.args and c.args[0] == 6 and "Error:" in str(c.args[2])
                           for c in calls)
        border_on_banner_row = any(c.args and c.args[0] == 6
                                   and str(c.args[2]).startswith("╔")
                                   for c in calls)
        assert banner_drawn, "error banner not drawn at banner_height row"
        assert not border_on_banner_row, "top border overwrites the error banner"

    def test_error_body_with_status_false_is_not_treated_as_prices(self):
        """HTTP 200 + {"status": false, "message": ...} (auth/usage error)
        must surface as an error, otherwise every watchlist row silently
        renders 0.00 with no banner."""
        body = {"status": False, "message": "error.api_key_invalid_format"}
        with patch("price_empire_scraper.requests.get",
                   return_value=_mock_response(200, body)):
            out = PriceEmpireScraper("bad-key").get_prices()
        assert isinstance(out, dict) and "error" in out
        assert "api_key_invalid_format" in out["error"]

    def test_http_error_status_returns_error_dict(self):
        with patch("price_empire_scraper.requests.get",
                   return_value=_mock_response(401, {"status": False, "message": "x"})):
            out = PriceEmpireScraper("bad-key").get_prices()
        assert out == {"error": "API status 401"}

    def test_request_exception_returns_error_dict(self):
        with patch("price_empire_scraper.requests.get",
                   side_effect=RuntimeError("boom")):
            out = PriceEmpireScraper("bad-key").get_prices()
        assert "error" in out and "boom" in out["error"]
