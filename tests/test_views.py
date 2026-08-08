"""Tests for views.py: price accessors, sort values, and width math."""

import pytest

from views import (
    get_price, get_avg, get_sort_value, _overhead,
    _row_buff_price, _row_avg_price,
)

NAME = "AK-47 | Redline (Field-Tested)"
ITEM = {"name": "AK-47 | Redline", "wear": "Field-Tested",
        "stattrak": False, "souvenir": False}


def _prices():
    return {
        NAME: {
            "prices": {
                "buff163": {"price": 166.79, "avg_7": 166.58, "avg_30": 169.92,
                            "avg_60": 169.85, "avg_90": 167.24},
                "skins": {"price": 170.0},
            }
        }
    }


class TestGetPrice:
    def test_returns_buff163_price(self):
        assert get_price(NAME, _prices()) == 166.79

    def test_other_source(self):
        assert get_price(NAME, _prices(), source="skins") == 170.0

    def test_custom_field(self):
        assert get_price(NAME, _prices(), field="avg_30") == 169.92

    def test_missing_item_returns_zero(self):
        assert get_price("Nope", _prices()) == 0.0

    def test_none_price_returns_zero(self):
        prices = {NAME: {"prices": {"buff163": {"price": None}}}}
        assert get_price(NAME, prices) == 0.0

    def test_non_dict_entry_returns_zero(self):
        prices = {NAME: {"prices": {"buff163": "oops"}}}
        assert get_price(NAME, prices) == 0.0

    def test_item_data_not_dict(self):
        prices = {NAME: "not a dict"}
        assert get_price(NAME, prices) == 0.0


class TestGetAvg:
    def test_returns_avg(self):
        assert get_avg(NAME, _prices(), 7) == 166.58
        assert get_avg(NAME, _prices(), 90) == 167.24

    def test_missing_avg_returns_zero(self):
        prices = {NAME: {"prices": {"buff163": {"price": 1.0}}}}
        assert get_avg(NAME, prices, 60) == 0.0


class TestNullBuff163Row:
    def test_row_accessors_fall_back_to_zero(self):
        prices = {NAME: {"prices": {"skins": {"price": 170.0}}}}
        assert _row_buff_price(ITEM, prices) == 0.0
        assert _row_avg_price(ITEM, prices, 7) == 0.0


class TestGetSortValue:
    def test_name_column(self):
        assert get_sort_value(ITEM, _prices(), 0) == "ak-47 | redline (field-tested)"

    def test_price_column(self):
        assert get_sort_value(ITEM, _prices(), 1) == 166.79

    def test_avg_columns(self):
        assert get_sort_value(ITEM, _prices(), 2) == 166.58
        assert get_sort_value(ITEM, _prices(), 3) == 169.92
        assert get_sort_value(ITEM, _prices(), 4) == 169.85
        assert get_sort_value(ITEM, _prices(), 5) == 167.24

    def test_trend_column(self):
        """Trend sort = 7d − 90d: positive when rising (sparkline direction)."""
        prices = _prices()  # 166.58 − 167.24 = −0.66 (down)
        assert get_sort_value(ITEM, prices, 6) == pytest.approx(166.58 - 167.24)

    def test_missing_data_columns_fall_back(self):
        prices = {NAME: {"prices": {}}}
        assert get_sort_value(ITEM, prices, 1) == 0.0
        assert get_sort_value(ITEM, prices, 6) == 0.0


class TestWidthMath:
    def test_overhead_constant(self):
        # Start offset 2 + fixed widths 45 + one 3-char separator after all 7 columns.
        assert _overhead(45, 7) == 68

    def test_min_width_fits(self):
        width = 88
        name_w = max(20, width - _overhead(45, 7))
        assert name_w >= 20
        # Last data char and last header char (with a sort arrow overflowing a
        # narrow column by 2) stay left of the right border at width - 1.
        data_last = 2 + name_w + 6 * 3 + 45 - 1
        header_last = data_last + 2
        border = width - 1
        assert data_last <= border
        assert header_last < border

    def test_watchlist_width_matches_old_formula(self):
        # The helper-based formula equals the verified inline formula.
        assert max(20, 88 - _overhead(45, 7)) == max(20, 88 - 68) == 20
