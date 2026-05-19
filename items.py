import os
import re

from constants.weapons import WEAPONS

ITEMS_FILE = 'items.txt'


def _normalize(s):
    """Strip hyphens, spaces, and lowercase for flexible matching."""
    return re.sub(r'[\s\-]+', '', s).lower()


def _capitalize_skin(s):
    """Title-case a skin name without capitalizing after apostrophes.

    'ramese's reach' → 'Ramese's Reach'  (not 'Ramese'S Reach')
    'neo-noir'       → 'Neo-Noir'
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

    # Try explicit separator first: " | " or "|"
    if ' | ' in raw:
        parts = raw.split(' | ', 1)
        weapon_part = parts[0].strip()
        skin_part = parts[1].strip() or None
        if skin_part:
            skin_part = _capitalize_skin(skin_part)
        # Normalize weapon part against known weapons
        for weapon in WEAPONS:
            if _normalize(weapon_part) == _normalize(weapon):
                return (weapon, skin_part)
        return (weapon_part, skin_part)
    if '|' in raw:
        parts = raw.split('|', 1)
        weapon_part = parts[0].strip()
        skin_part = parts[1].strip() or None
        if skin_part:
            skin_part = _capitalize_skin(skin_part)
        for weapon in WEAPONS:
            if _normalize(weapon_part) == _normalize(weapon):
                return (weapon, skin_part)
        return (weapon_part, skin_part)

    # Try matching against known weapons using normalized comparison.
    # Sort by length descending so "M4A1-S" matches before "M4A1".
    for weapon in sorted(WEAPONS, key=len, reverse=True):
        weapon_norm = _normalize(weapon)
        raw_norm = _normalize(raw)
        raw_lower = raw.lower()
        # Check if raw starts with the weapon name (with optional space/dash after)
        if raw_norm == weapon_norm:
            return (weapon, None)
        if raw_norm.startswith(weapon_norm):
            # Find where the weapon name ends in the original raw string
            # by scanning forward until we've consumed enough normalized chars
            consumed = 0
            pos = 0
            for ch in raw:
                if consumed >= len(weapon_norm):
                    break
                if _normalize(ch) == weapon_norm[consumed]:
                    consumed += 1
                pos += 1
            rest = raw[pos:].strip()
            # Strip leading separators like "-", "|", spaces
            rest = re.sub(r'^[\s\-|]+', '', rest).strip()
            if rest:
                return (weapon, _capitalize_skin(rest))

    # Fallback: try to split on the first " - " or " — "
    for sep in [' - ', ' — ']:
        if sep in raw:
            parts = raw.split(sep, 1)
            skin_part = parts[1].strip() or None
            if skin_part:
                skin_part = _capitalize_skin(skin_part)
            return (parts[0].strip(), skin_part)

    # Cannot split — return as-is (caller may treat the whole thing as a name)
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
    if line.upper().startswith('ST '):
        stattrak = True
        line = line[3:].strip()

    if ',' in line:
        parts = line.split(',', 1)
        name = parts[0].strip()
        wear = parts[1].strip() if parts[1].strip() else None
    else:
        name = line.strip()
        wear = None

    name = name.lstrip('\u2605 ').strip()

    if not name:
        return None

    return {"name": name, "wear": wear, "stattrak": stattrak}


def format_item_line(item):
    prefix = 'ST ' if item.get('stattrak') else ''
    name = item.get('name', '')
    wear = item.get('wear')
    if wear:
        return f"{prefix}{name}, {wear}"
    return f"{prefix}{name}"


def load_items(path=ITEMS_FILE):
    items = []
    try:
        with open(path, 'r') as f:
            for line in f:
                item = parse_item_line(line)
                if item:
                    items.append(item)
    except FileNotFoundError:
        return None
    return items


def save_items(items, path=ITEMS_FILE):
    with open(path, 'w') as f:
        for item in items:
            f.write(format_item_line(item) + '\n')


def get_items_mtime(path=ITEMS_FILE):
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return 0
