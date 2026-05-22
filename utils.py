"""Shared utility functions for item validation and config.

Extracted from manage.py so both manage.py and tui.py can use them.
"""

import json
import re

from price_empire_scraper import PriceEmpireScraper, format_market_hash_name

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


def _skin_similarity(a, b):
    """Return True if two skin names are likely the same item.

    Compares normalized strings (lowercase, no spaces/punctuation).
    Returns True if one is a substring of the other or they share
    >80% of characters in common.
    """
    def norm(s):
        return re.sub(r'[\s\'\-]+', '', s).lower()

    norm_a, norm_b = norm(a), norm(b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    if norm_a in norm_b or norm_b in norm_a:
        return True
    # Character overlap ratio
    common = sum(1 for c in norm_a if c in norm_b)
    return common / max(len(norm_a), len(norm_b)) > 0.8


def validate_item(item, api_key=None, scraper=None, prices_data=None):
    """Check if the item exists in the PriceEmpire API.

    Args:
        item: item dict with 'name', 'wear', 'stattrak' keys.
        api_key: API key string (used if scraper and prices_data not given).
        scraper: optional PriceEmpireScraper instance (used if prices_data not given).
        prices_data: optional pre-fetched prices dict (avoids extra API call).

    Returns:
        - (True, price_info, prices) if found — price_info is a dict with
          buff163/skins prices, prices is the full API response dict.
        - (False, similar_names, prices) if not found — similar_names is
          a list of up to 5 similar API names for suggestions.
        - (None, error_msg, None) if the API call failed or no key.
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
        return (None, "No api_key, scraper, or prices_data provided.", None)

    if isinstance(prices, dict) and 'error' in prices:
        return (None, f"API error: {prices['error']}", None)
    if not isinstance(prices, dict):
        return (None, f"Unexpected API response: {type(prices).__name__}", None)

    # 2. Check if our item exists
    market_name = format_market_hash_name(item)
    if market_name in prices:
        item_data = prices[market_name]
        price_info = {}
        for source in ('buff163', 'skins'):
            source_data = item_data.get('prices', {}).get(source, {})
            if isinstance(source_data, dict) and source_data.get('price') is not None:
                price_info[source] = source_data['price']
        return (True, price_info, prices)

    # 3. Not found — find similar items for suggestions
    similar = []
    item_name = item.get('name', '')
    weapon_part = item_name.split(' | ')[0].lower() if ' | ' in item_name else ''
    skin_part = item_name.split(' | ')[1].lower() if ' | ' in item_name else ''

    for api_name in prices:
        if weapon_part and weapon_part not in api_name.lower():
            continue
        if ' | ' in api_name:
            api_skin_full = api_name.split(' | ')[1].lower()
            api_skin = re.sub(r'\s*\(.*?\)\s*$', '', api_skin_full).strip()
            if _skin_similarity(skin_part, api_skin):
                similar.append(api_name)
                if len(similar) >= 5:
                    break

    return (False, similar, prices)


def parse_suggestion_api_name(api_name):
    """Parse an API market hash name back into item fields.

    Given something like 'AK-47 | Redline (Field-Tested)' or
    'StatTrak™ AK-47 | Redline (Field-Tested)', returns a dict with
    'name', 'wear', 'stattrak' suitable for use as an item.
    """
    stattrak = False
    rest = api_name
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

    return {"name": name, "wear": wear, "stattrak": stattrak}


def apply_suggestion(similar, idx, prices_data, stattrak=False):
    """Apply a suggestion pick from the API.

    Given a list of similar API names and a 0-based index, parse the
    selected name into item fields and look up prices from the API data.

    Returns:
        (item_dict, price_info) — item_dict has 'name', 'wear', 'stattrak';
        price_info is {source: price, ...} from prices_data.
    """
    api_name = similar[idx]
    parsed = parse_suggestion_api_name(api_name)
    parsed['stattrak'] = stattrak
    item_data = prices_data.get(api_name, {})
    price_info = {}
    for source in ('buff163', 'skins'):
        src_data = item_data.get('prices', {}).get(source, {})
        if isinstance(src_data, dict) and src_data.get('price') is not None:
            price_info[source] = src_data['price']
    return (parsed, price_info)
