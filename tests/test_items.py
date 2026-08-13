"""Tests for items.py: parsing, formatting, and file round-trip."""

from items import (
    parse_item_line, format_item_line, split_name,
    format_market_hash_name, load_items, save_items,
)


class TestParseItemLine:
    def test_plain_name(self):
        assert parse_item_line("AK-47 | Redline") == {
            "name": "AK-47 | Redline", "wear": None,
            "stattrak": False, "souvenir": False,
        }

    def test_name_with_wear(self):
        item = parse_item_line("M4A1-S | Printstream, Field-Tested")
        assert item["wear"] == "Field-Tested"

    def test_wear_short_code_normalized(self):
        item = parse_item_line("AK-47 | Redline, ft")
        assert item["wear"] == "Field-Tested"

    def test_stattrak_prefix(self):
        assert parse_item_line("ST AK-47 | Redline")["stattrak"] is True

    def test_souvenir_prefix(self):
        assert parse_item_line("SV AK-47 | B the Monster")["souvenir"] is True

    def test_knife_star_stripped(self):
        item = parse_item_line("★ Karambit | Black Laminate")
        assert item["name"] == "Karambit | Black Laminate"

    def test_glove_star_stripped(self):
        item = parse_item_line("★ Sport Gloves | Nocts, Field-Tested")
        assert item["name"] == "Sport Gloves | Nocts"
        assert item["wear"] == "Field-Tested"

    def test_comment_and_blank_lines_ignored(self):
        assert parse_item_line("# comment") is None
        assert parse_item_line("") is None
        assert parse_item_line("   ") is None


class TestSplitName:
    def test_explicit_pipe(self):
        assert split_name("AK-47 | Redline") == ("AK-47", "Redline")

    def test_pipe_no_spaces(self):
        assert split_name("AK-47|Redline") == ("AK-47", "Redline")

    def test_combined_shortcut(self):
        assert split_name("AK-47 Redline") == ("AK-47", "Redline")

    def test_normalized_combined(self):
        assert split_name("ak47 redline") == ("AK-47", "Redline")

    def test_weapon_only(self):
        assert split_name("AK-47") == ("AK-47", None)

    def test_unknown_returns_raw(self):
        assert split_name("Not a Weapon") == ("Not a Weapon", None)


class TestFormatItemLine:
    def test_stattrak_and_wear(self):
        item = {"name": "AK-47 | Redline", "wear": "Field-Tested",
                "stattrak": True, "souvenir": False}
        assert format_item_line(item) == "ST AK-47 | Redline, Field-Tested"

    def test_souvenir_prefix(self):
        item = {"name": "AK-47 | B the Monster", "wear": None,
                "stattrak": False, "souvenir": True}
        assert format_item_line(item) == "SV AK-47 | B the Monster"


class TestFormatMarketHashName:
    def test_plain_with_wear(self):
        item = {"name": "AK-47 | Redline", "wear": "Field-Tested",
                "stattrak": False, "souvenir": False}
        assert format_market_hash_name(item) == "AK-47 | Redline (Field-Tested)"

    def test_stattrak(self):
        item = {"name": "AK-47 | Redline", "wear": None,
                "stattrak": True, "souvenir": False}
        assert format_market_hash_name(item) == "StatTrak™ AK-47 | Redline"

    def test_souvenir(self):
        item = {"name": "AK-47 | B the Monster", "wear": None,
                "stattrak": False, "souvenir": True}
        assert format_market_hash_name(item) == "Souvenir AK-47 | B the Monster"

    def test_knife_star(self):
        item = {"name": "Karambit | Black Laminate", "wear": "Well-Worn",
                "stattrak": False, "souvenir": False}
        assert format_market_hash_name(item) == "★ Karambit | Black Laminate (Well-Worn)"

    def test_glove_star(self):
        item = {"name": "Sport Gloves | Nocts", "wear": "Field-Tested",
                "stattrak": False, "souvenir": False}
        assert format_market_hash_name(item) == "★ Sport Gloves | Nocts (Field-Tested)"

    def test_glove_star_not_duplicated(self):
        item = {"name": "★ Sport Gloves | Nocts", "wear": None,
                "stattrak": False, "souvenir": False}
        assert format_market_hash_name(item) == "★ Sport Gloves | Nocts"

    def test_non_knife_not_starred(self):
        item = {"name": "AK-47 | Redline", "wear": None,
                "stattrak": False, "souvenir": False}
        assert not format_market_hash_name(item).startswith("★")


class TestLoadSaveRoundTrip:
    def test_round_trip(self, tmp_path):
        path = tmp_path / "items.txt"
        items = [
            {"name": "AK-47 | Redline", "wear": "Field-Tested",
             "stattrak": False, "souvenir": False},
            {"name": "M4A1-S | Printstream", "wear": None,
             "stattrak": True, "souvenir": False},
            {"name": "Karambit | Black Laminate", "wear": "Well-Worn",
             "stattrak": False, "souvenir": False},
        ]
        save_items(items, path)
        assert load_items(path) == items

    def test_missing_file_returns_none(self, tmp_path):
        assert load_items(tmp_path / "nope.txt") is None

    def test_comments_skipped_on_load(self, tmp_path):
        path = tmp_path / "items.txt"
        path.write_text("# a comment\n\nAK-47 | Redline\n", encoding="utf-8")
        assert load_items(path) == [
            {"name": "AK-47 | Redline", "wear": None,
             "stattrak": False, "souvenir": False},
        ]
