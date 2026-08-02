#!/usr/bin/env python3
import sys
from items import (
    load_items, save_items, format_item_line, format_market_hash_name,
    WEAPONS, find_weapon, split_name, capitalize_skin, normalize_wear,
)
from utils import validate_item, load_config, apply_suggestion, ValidationResult, SuggestionAction, resolve_suggestion_choice


def _safe_input(prompt=''):
    """Like input() but returns empty string on EOF instead of crashing."""
    try:
        return input(prompt)
    except EOFError:
        return ''


def _drain_stdin():
    """Discard any buffered stdin keystrokes to prevent stale input polluting the next prompt.

    Typing during a blocking operation (e.g., API call) leaves keystrokes in
    the kernel buffer. This function flushes them so the next input() waits
    for fresh input. Best-effort — silently no-ops on non-POSIX platforms
    or when stdin is not a TTY.
    """
    import sys
    try:
        import termios
    except ImportError:
        return  # Non-POSIX platform (e.g. Windows)
    try:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except Exception:
        pass  # stdin has no fileno, not a terminal, or termios error — best-effort


def get_all_items():
    """Return all tracked items from items.txt (the single source of truth)."""
    items = load_items()
    return items if items is not None else []


def cmd_list():
    items = get_all_items()
    if not items:
        print("No items tracked.")
        print("Run 'python3 manage.py add' to add one, or create items.txt.")
        return
    for i, item in enumerate(items):
        print(f"{i}: {format_item_line(item)}")


def _print_not_found(item, similar):
    """Print the 'not found' warning and numbered suggestions."""
    print(f"\n  ⚠  '{format_market_hash_name(item)}' not found in API.")
    if similar:
        print("  Did you mean one of these?")
        for i, s in enumerate(similar):
            print(f"    {i + 1}) {s}")


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
        skin = capitalize_skin(skin)

    name = f"{weapon} | {skin}"

    # Step 3: Wear
    wear = _safe_input("Wear (fn/mw/ft/ww/bs) [none]: ").strip()
    if not wear:
        wear = None
    else:
        wear = normalize_wear(wear)

    # Step 4: StatTrak
    response = _safe_input("StatTrak? (y/N): ").strip().lower()
    stattrak = response.startswith('y')

    # Step 5: Souvenir
    response = _safe_input("Souvenir? (y/N): ").strip().lower()
    souvenir = response.startswith('y')

    item = {"name": name, "wear": wear, "stattrak": stattrak, "souvenir": souvenir}
    line = format_item_line(item)
    print(f"\nPreview: {line}")

    # Step 5: API validation
    config_data = load_config()
    api_key = config_data.get('api_key')
    print("  Checking API...")
    validation = validate_item(item, api_key=api_key)
    _drain_stdin()  # Discard any keystrokes typed during the API wait

    # Validation + retry loop
    while True:
        if validation.status == "error":
            print(f"  {validation.data}")
            found = False
            break

        if validation.status == "found":
            result = validation.data
            prices_data = validation.prices
            found = True
            break

        # status == "not_found"
        similar = validation.data
        prices_data = validation.prices
        _print_not_found(item, similar)

        print()
        choice = _safe_input(
            "Choose a number, or (p)roceed anyway / (r)etry / (c)ancel: "
        ).strip().lower()

        action, idx = resolve_suggestion_choice(choice, len(similar))

        if action == SuggestionAction.CANCEL:
            print("Cancelled.")
            return

        if action == SuggestionAction.PROCEED:
            found = False
            break

        if action == SuggestionAction.RETRY:
            print()
            skin = _safe_input("Skin (e.g. 'Redline')> ").strip()
            if not skin:
                print("Cancelled.")
                return
            skin = capitalize_skin(skin)
            name = f"{weapon} | {skin}"
            item = {"name": name, "wear": wear, "stattrak": stattrak, "souvenir": souvenir}
            line = format_item_line(item)
            print(f"\nPreview: {line}")
            validation = validate_item(item, api_key=api_key)
            _drain_stdin()
            continue

        if action == SuggestionAction.PICK and idx is not None:
            item, result = apply_suggestion(similar, idx, prices_data, stattrak, souvenir)
            line = format_item_line(item)
            validation = ValidationResult("found", result, prices_data)
            continue

        print("  Invalid choice.")
        # Re-display suggestions
        _print_not_found(item, validation.data)

    # Step 6: Final confirmation
    if found:
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
