#!/usr/bin/env python3
import sys
import re
from items import (
    load_items, save_items, format_item_line,
    WEAPONS, find_weapon, split_name, _capitalize_skin, normalize_wear,
)
from price_empire_scraper import PriceEmpireScraper, format_market_hash_name
from utils import _skin_similarity, validate_item, sync_config, load_config, save_config


def _safe_input(prompt=''):
    """Like input() but returns empty string on EOF instead of crashing."""
    try:
        return input(prompt)
    except EOFError:
        return ''


def get_all_items():
    items = load_items()
    if items is not None:
        return items
    config = load_config()
    if isinstance(config, list):
        return config
    return config.get('items', [])


def cmd_list():
    items = get_all_items()
    if not items:
        items_missing = load_items() is None
        if items_missing:
            print("No items.txt found and config.json has no items.")
        else:
            print("No items tracked.")
        print("Run 'python3 manage.py add' to add one.")
        return
    for i, item in enumerate(items):
        print(f"{i}: {format_item_line(item)}")


def _select_weapon():
    """Interactive weapon selection with fuzzy search.

    Returns the chosen weapon name or None if cancelled.
    """
    print("Weapon selection — type to search, or 'list' to see all weapons.")
    print("Press Enter with empty input to cancel.\n")

    while True:
        query = _safe_input("Weapon> ").strip()
        if not query:
            return None

        if query.lower() == 'list':
            print()
            for i, w in enumerate(WEAPONS):
                print(f"  {i:3d}: {w}")
            print()
            continue

        # Try direct index input
        try:
            idx = int(query)
            if 0 <= idx < len(WEAPONS):
                return WEAPONS[idx]
            else:
                print(f"  Index out of range (0-{len(WEAPONS) - 1}).\n")
                continue
        except ValueError:
            pass

        # Try splitting a full name like "AK-47 Redline"
        weapon, skin = split_name(query)
        if skin is not None and weapon in WEAPONS:
            # Store skin for later — we'll return a tuple
            return (weapon, skin)

        matches = find_weapon(query)
        if not matches:
            print("  No weapons found. Try again.\n")
            continue

        if len(matches) == 1:
            idx, w = matches[0]
            print(f"  Selected: {w}\n")
            return w

        # Show matches with indices
        print()
        for idx, w in matches:
            print(f"  {idx:3d}: {w}")
        print(f"\n  {len(matches)} matches. Pick a number or refine your search.\n")





def cmd_add():
    print("Add a new item. Press Enter with empty input to cancel at any prompt.\n")

    # Step 1: Select weapon
    weapon_result = _select_weapon()
    if weapon_result is None:
        print("Cancelled.")
        return

    # Handle case where _select_weapon returned (weapon, skin) from split
    if isinstance(weapon_result, tuple):
        weapon, skin = weapon_result
    else:
        weapon = weapon_result
        skin = None

    # Step 2: If skin wasn't already extracted, ask for it
    if skin is None:
        skin = _safe_input("Skin (e.g. 'Redline')> ").strip()
        if not skin:
            print("Cancelled.")
            return
        skin = _capitalize_skin(skin)

    name = f"{weapon} | {skin}"

    # Step 3: Wear
    wear = _safe_input("Wear (fn/mw/ft/ww/bs) [none]: ").strip()
    if not wear:
        wear = None
    else:
        wear = normalize_wear(wear)

    # Step 4: StatTrak
    st_input = _safe_input("StatTrak? (y/N): ").strip().lower()
    stattrak = st_input.startswith('y')

    item = {"name": name, "wear": wear, "stattrak": stattrak}
    line = format_item_line(item)
    print(f"\nPreview: {line}")

    # Step 5: API validation
    config_data = load_config()
    api_key = config_data.get('api_key')
    found, result, prices_data = validate_item(item, api_key=api_key)

    if found is None:
        # API error or no key — warn but let user proceed
        print(f"  {result}")
    elif not found:
        similar = result
        print(f"\n  ⚠  '{format_market_hash_name(item)}' not found in API.")
        if similar:
            print("  Did you mean one of these?")
            for i, s in enumerate(similar):
                print(f"    {i + 1}) {s}")

        # Loop until a definitive action is taken
        while True:
            print()
            choice = _safe_input(
                "Choose a number, or (p)roceed anyway / (r)etry / (c)ancel: "
            ).strip().lower()

            if not choice or choice in ('c',):
                print("Cancelled.")
                return

            if choice in ('p', 'y'):
                break  # proceed with original (unfound) item

            if choice in ('r',):
                # Re-prompt for skin name
                print()
                skin = _safe_input("Skin (e.g. 'Redline')> ").strip()
                if not skin:
                    print("Cancelled.")
                    return
                skin = _capitalize_skin(skin)
                name = f"{weapon} | {skin}"
                item = {"name": name, "wear": wear, "stattrak": stattrak}
                line = format_item_line(item)
                print(f"\nPreview: {line}")
                found, result, prices_data = validate_item(item, api_key=api_key)
                if found is None:
                    print(f"  {result}")
                    break
                if found:
                    break
                # Still not found — show suggestions again and loop
                similar = result
                print(f"\n  ⚠  '{format_market_hash_name(item)}' not found in API.")
                if similar:
                    print("  Did you mean one of these?")
                    for i, s in enumerate(similar):
                        print(f"    {i + 1}) {s}")
                continue

            # Try number selection — pick a suggestion
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(similar):
                    api_name = similar[idx]
                    # Parse name and wear from API market hash name
                    m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', api_name)
                    if m:
                        name = m.group(1).strip()
                        selected_wear = m.group(2).strip()
                    else:
                        name = api_name
                        selected_wear = None
                    item = {"name": name, "wear": selected_wear, "stattrak": stattrak}
                    line = format_item_line(item)
                    # Look up prices from cached API data
                    item_data = prices_data.get(api_name, {})
                    price_info = {}
                    for source in ('buff163', 'skins'):
                        src_data = item_data.get('prices', {}).get(source, {})
                        if isinstance(src_data, dict) and src_data.get('price') is not None:
                            price_info[source] = src_data['price']
                    result = price_info
                    found = True
                    break
            except (ValueError, IndexError):
                pass

            print("  Invalid choice.")

    # Step 6: Final confirmation
    if found is True:
        price_parts = []
        for source in ('buff163', 'skins'):
            if source in result:
                price_parts.append(f"{source}: €{result[source]:.2f}")
        if price_parts:
            print(f"\n  Prices: {', '.join(price_parts)}")
        else:
            print("\n  Item found but no price data available.")

    confirm = _safe_input("\nAdd this item? (Y/n): ").strip().lower()
    if confirm and confirm != 'y':
        print("Cancelled.")
        return

    items = get_all_items()
    items.append(item)
    save_items(items)
    sync_config(items)
    print(f"Added: {line}")


def cmd_remove(args):
    items = get_all_items()
    if not items:
        print("No items to remove.")
        return

    if not args:
        print("Usage: manage.py remove <index|name>")
        return

    target = ' '.join(args)

    # try index first
    try:
        idx = int(target)
        if 0 <= idx < len(items):
            item = items.pop(idx)
            save_items(items)
            sync_config(items)
            print(f"Removed: {format_item_line(item)}")
            return
        else:
            print(f"Index {idx} out of range (0-{len(items) - 1}).")
            return
    except ValueError:
        pass

    # search by name substring
    matches = []
    for i, item in enumerate(items):
        if target.lower() in format_item_line(item).lower():
            matches.append((i, item))

    if not matches:
        print(f"No items matching '{target}'.")
        return

    if len(matches) > 1:
        print("Multiple matches — use the index number:")
        for idx, item in matches:
            print(f"  {idx}: {format_item_line(item)}")
        return

    idx, item = matches[0]
    confirm = _safe_input(f"Remove '{format_item_line(item)}'? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    items.pop(idx)
    save_items(items)
    sync_config(items)
    print(f"Removed: {format_item_line(item)}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 manage.py <list|add|remove> [args]")
        print()
        print("Commands:")
        print("  list              List all tracked items")
        print("  add               Add an item interactively (weapon selection + skin)")
        print("  remove <idx|name> Remove an item by index or name substring")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == 'list':
        cmd_list()
    elif cmd == 'add':
        cmd_add()
    elif cmd == 'remove':
        cmd_remove(sys.argv[2:])
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 manage.py <list|add|remove> [args]")
        sys.exit(1)


if __name__ == '__main__':
    main()
