"""Shared utility functions for item validation and config.

Extracted from manage.py so both manage.py and tui.py can use them.
"""

import json
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal

from items import format_market_hash_name
from price_empire_scraper import PriceEmpireScraper

CONFIG_FILE = 'config.json'


def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


class SuggestionAction(Enum):
    PICK = auto()
    PROCEED = auto()
    RETRY = auto()
    CANCEL = auto()


def resolve_suggestion_choice(choice: str, similar_count: int) -> tuple[SuggestionAction, int | None]:
    """Parse raw user input into an action and optional 0-based index."""
    choice = choice.strip().lower()
    if choice in ('p', 'y'):
        return SuggestionAction.PROCEED, None
    if choice in ('r',):
        return SuggestionAction.RETRY, None
    if choice in ('c', ''):
        return SuggestionAction.CANCEL, None
    try:
        idx = int(choice) - 1
        if 0 <= idx < similar_count:
            return SuggestionAction.PICK, idx
    except ValueError:
        pass
    return SuggestionAction.CANCEL, None


def _skin_similarity(a, b):
    """Return True if two skin names are likely the same item.

    Uses difflib.SequenceMatcher for positional similarity instead of
    the old character-set overlap metric (which scored "abcd" == "dcba").
    """
    import difflib

    def norm(s):
        return re.sub(r"[\s'\-]+", "", s).lower()

    norm_a, norm_b = norm(a), norm(b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b or norm_a in norm_b or norm_b in norm_a:
        return True
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio() > 0.8


@dataclass(frozen=True)
class ValidationResult:
    status: Literal["found", "not_found", "error"]
    data: dict | list | str
    prices: dict | None


def validate_item(item, api_key=None, scraper=None, prices_data=None):
    """Check if the item exists in the PriceEmpire API.

    Args:
        item: item dict with 'name', 'wear', 'stattrak' keys.
        api_key: API key string (used if scraper and prices_data not given).
        scraper: optional PriceEmpireScraper instance (used if prices_data not given).
        prices_data: optional pre-fetched prices dict (avoids extra API call).

    Returns:
        ValidationResult with:
        - status="found": data is price_info dict with buff163/skins prices,
          prices is the full API response dict.
        - status="not_found": data is a list of up to 5 similar API names.
        - status="error": data is an error message string, prices is None.
    """
    # 1. Get prices data
    if prices_data is not None:
        prices = prices_data
    elif scraper is not None:
        prices = scraper.get_prices()
    elif api_key:
        scraper = PriceEmpireScraper(api_key)
        prices = scraper.get_prices()
    else:
        return ValidationResult("error", "No api_key, scraper, or prices_data provided.", None)

    if isinstance(prices, dict) and 'error' in prices:
        return ValidationResult("error", f"API error: {prices['error']}", None)
    if not isinstance(prices, dict):
        return ValidationResult("error", f"Unexpected API response: {type(prices).__name__}", None)

    # 2. Check if our item exists
    market_name = format_market_hash_name(item)
    if market_name in prices:
        item_data = prices[market_name]
        price_info = {}
        for source in ('buff163', 'skins'):
            source_data = item_data.get('prices', {}).get(source, {})
            if isinstance(source_data, dict) and source_data.get('price') is not None:
                price_info[source] = source_data['price']
        return ValidationResult("found", price_info, prices)

    # 3. Not found — find similar items for suggestions
    similar = []
    item_name = item.get('name', '')
    weapon_part = item_name.split(' | ')[0].lower() if ' | ' in item_name else ''
    skin_part = item_name.split(' | ')[1].lower() if ' | ' in item_name else ''

    for api_name in prices:
        if weapon_part and weapon_part not in api_name.lower():
            continue
        # Filter out souvenir/non-souvenir mismatches so they don't
        # crowd out the correct item in the capped suggestion list.
        api_is_souvenir = api_name.lower().startswith('souvenir ')
        if not item.get('souvenir') and api_is_souvenir:
            continue
        if item.get('souvenir') and not api_is_souvenir:
            continue
        if ' | ' in api_name:
            api_skin_full = api_name.split(' | ')[1].lower()
            api_skin = re.sub(r'\s*\(.*?\)\s*$', '', api_skin_full).strip()
            if _skin_similarity(skin_part, api_skin):
                similar.append(api_name)
                if len(similar) >= 5:
                    break

    return ValidationResult("not_found", similar, prices)


def parse_suggestion_api_name(api_name):
    """Parse an API market hash name back into item fields.

    Given something like 'AK-47 | Redline (Field-Tested)' or
    'Souvenir AK-47 | B the Monster (Field-Tested)' or
    'StatTrak™ AK-47 | Redline (Field-Tested)', returns a dict with
    'name', 'wear', 'stattrak', 'souvenir' suitable for use as an item.
    """
    stattrak = False
    souvenir = False
    rest = api_name
    if rest.startswith('Souvenir '):
        souvenir = True
        rest = rest[len('Souvenir '):]
    if rest.startswith('StatTrak™ '):
        stattrak = True
        rest = rest[len('StatTrak™ '):]

    # Strip leading ★ for knives
    rest = rest.lstrip('★ ').strip()

    # Extract wear from trailing parentheses
    match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', rest)
    if match:
        name = match.group(1).strip()
        wear = match.group(2).strip()
    else:
        name = rest.strip()
        wear = None

    return {"name": name, "wear": wear, "stattrak": stattrak, "souvenir": souvenir}


def apply_suggestion(similar, idx, prices_data, stattrak=False, souvenir=False):
    """Apply a suggestion pick from the API.

    Given a list of similar API names and a 0-based index, parse the
    selected name into item fields and look up prices from the API data.

    Returns:
        (item_dict, price_info) — item_dict has 'name', 'wear', 'stattrak',
        'souvenir'; price_info is {source: price, ...} from prices_data.
    """
    api_name = similar[idx]
    parsed = parse_suggestion_api_name(api_name)
    parsed['stattrak'] = stattrak
    parsed['souvenir'] = souvenir
    item_data = prices_data.get(api_name, {})
    price_info = {}
    for source in ('buff163', 'skins'):
        src_data = item_data.get('prices', {}).get(source, {})
        if isinstance(src_data, dict) and src_data.get('price') is not None:
            price_info[source] = src_data['price']
    return (parsed, price_info)
