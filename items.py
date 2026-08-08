import os
import re

from constants.weapons import KNIFE_NAMES, WEAPONS
from constants.wear import WEAR_MAP

ITEMS_FILE = 'items.txt'


def normalize_wear(wear):
    """Convert short wear codes to full names. Pass through full names unchanged."""
    if not wear:
        return wear
    return WEAR_MAP.get(wear.lower().strip(), wear)


def _normalize(s):
    """Strip hyphens, spaces, and lowercase for flexible matching."""
    return re.sub(r'[\s\-]+', '', s).lower()


def capitalize_skin(s):
    """Title-case a skin name without capitalizing after apostrophes.

    'rameses reach' → 'Rameses Reach'
    'rameses's reach' → 'Rameses's Reach'  (not 'Rameses'S Reach')
    'neo-noir' → 'Neo-Noir'
    """
    # Split on spaces and hyphens, capitalize each word's first letter only
    parts = re.split(r'(\s+|-)', s)
    result = []
    for part in parts:
        if part in (' ', '-', '\t'):
            result.append(part)
        elif part:
            result.append(part[0].upper() + part[1:] if len(part) > 1 else part.upper())
        else:
            result.append(part)
    return ''.join(result)


def split_name(raw):
    """Split a raw item name into (weapon, skin) using flexible separators.

    Accepts formats like:
      "AK-47 | Redline"
      "AK-47 |Redline"
      "AK-47| Redline"
      "AK-47|Redline"
      "AK-47 Redline"
      "ak47 redline"
      "M4A1-S Printstream"

    Returns (weapon, skin) or (raw, None) if no split is possible.
    """
    raw = raw.strip()
    if not raw:
        return (raw, None)

    # Try explicit separators first: " | " or "|"
    for sep in (' | ', '|'):
        if sep in raw:
            weapon_part, skin_part = raw.split(sep, 1)
            weapon_part = weapon_part.strip()
            skin_part = skin_part.strip() or None
            if skin_part:
                skin_part = capitalize_skin(skin_part)
            for weapon in WEAPONS:
                if _normalize(weapon_part) == _normalize(weapon):
                    return (weapon, skin_part)
            return (weapon_part, skin_part)

    # Combined shortcut: "AK-47 Redline" or "ak47 redline"
    # Try each weapon as a prefix, longest first.
    raw_norm = _normalize(raw)
    for weapon in sorted(WEAPONS, key=len, reverse=True):
        weapon_norm = _normalize(weapon)

        # Exact normalized match: raw IS a weapon name
        if raw_norm == weapon_norm:
            return (weapon, None)

        # Literal prefix match (handles "AK-47 Redline", "M4A1-S Printstream")
        pattern = rf'({re.escape(weapon)})\s*(?:\||\s|-)\s*(.+)'
        m = re.match(pattern, raw, re.IGNORECASE)
        if m:
            return (weapon, capitalize_skin(m.group(2)))

        # Normalized prefix match (handles "ak47 redline", "m4a1s printstream")
        if raw_norm.startswith(weapon_norm) and len(raw_norm) > len(weapon_norm):
            consumed = 0
            pos = 0
            for ch in raw:
                if consumed >= len(weapon_norm):
                    break
                if _normalize(ch) == weapon_norm[consumed]:
                    consumed += 1
                pos += 1
            rest = raw[pos:].strip()
            rest = re.sub(r'^[\s\-|]+', '', rest).strip()
            if rest:
                return (weapon, capitalize_skin(rest))

    return (raw, None)


def find_weapon(query):
    """Fuzzy-match a query string against known weapon names.

    Returns a list of (index, weapon_name) matches sorted by relevance.
    Matches are found by:
      1. Exact match (case-insensitive, hyphens/spaces ignored)
      2. Prefix match (normalized)
      3. Substring match (normalized)
    """
    query_norm = _normalize(query)
    if not query_norm:
        return [(i, w) for i, w in enumerate(WEAPONS)]

    results = []
    seen = set()
    for i, w in enumerate(WEAPONS):
        w_norm = _normalize(w)
        if w_norm == query_norm:
            results.insert(0, (i, w))  # exact match first
            seen.add(i)
        elif w_norm.startswith(query_norm):
            results.append((i, w))
            seen.add(i)
    for i, w in enumerate(WEAPONS):
        if i not in seen and query_norm in _normalize(w):
            results.append((i, w))
    return results


def parse_item_line(line):
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    stattrak = False
    souvenir = False
    if line.upper().startswith('ST '):
        stattrak = True
        line = line[3:].strip()
    if line.upper().startswith('SV '):
        souvenir = True
        line = line[3:].strip()

    if ',' in line:
        parts = line.split(',', 1)
        name = parts[0].strip()
        wear = normalize_wear(parts[1].strip()) if parts[1].strip() else None
    else:
        name = line.strip()
        wear = None

    name = name.lstrip('\u2605 ').strip()

    if not name:
        return None

    return {"name": name, "wear": wear, "stattrak": stattrak, "souvenir": souvenir}


def format_item_line(item):
    prefix = 'ST ' if item.get('stattrak') else ''
    if item.get('souvenir'):
        prefix = 'SV ' + prefix
    name = item.get('name', '')
    wear = item.get('wear')
    if wear:
        return f"{prefix}{name}, {wear}"
    return f"{prefix}{name}"


def load_items(path=ITEMS_FILE):
    items = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                item = parse_item_line(line)
                if item:
                    items.append(item)
    except FileNotFoundError:
        return None
    return items


def save_items(items, path=ITEMS_FILE):
    with open(path, 'w', encoding='utf-8') as f:
        for item in items:
            f.write(format_item_line(item) + '\n')


def get_items_mtime(path=ITEMS_FILE):
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return 0


def format_market_hash_name(item):
    """Turn an item dict into a Steam Market Hash Name.

    Handles Souvenir prefix, StatTrak prefix, ★ prefix for knives, and wear suffix.
    Example: 'Souvenir AK-47 | B the Monster (Field-Tested)'
    Example: 'StatTrak™ ★ Karambit | Black Laminate (Well-Worn)'
    """
    name = item.get('name')
    wear = item.get('wear')
    stattrak = item.get('stattrak', False)
    souvenir = item.get('souvenir', False)

    # Prepend ★ for knives. Use exact weapon-part lookup (not substring — "Bayonet" and
    # "Shadow Daggers" don't contain "Knife", and the full name is "Weapon | Skin").
    full_name = name
    weapon_part = name.split(' | ')[0] if ' | ' in name else name
    if weapon_part in KNIFE_NAMES and not name.startswith("★"):
        full_name = "★ " + name

    if souvenir:
        full_name = "Souvenir " + full_name

    if stattrak:
        full_name = "StatTrak™ " + full_name

    if wear:
        full_name = f"{full_name} ({wear})"

    return full_name
