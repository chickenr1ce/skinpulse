"""Add-item wizard for the curses TUI.

Contains the interactive add-item flow and shared curses rendering helpers
(safe_addstr, draw_centered_box, confirm_dialog, curses_input_blocking) that
are used by the main TUI loop as well.
"""

import curses
from typing import Literal
from items import (
    find_weapon, WEAPONS, capitalize_skin, normalize_wear,
    format_item_line as fmt_item_line, format_market_hash_name,
)
from utils import validate_item, apply_suggestion, ValidationResult
from curses_utils import safe_addstr, draw_centered_box, curses_input_blocking, confirm_dialog



def _wizard_weapon_search(stdscr, width, height):
    """Step 0: Weapon selection with fuzzy search.

    Returns weapon name, or None to cancel.
    """
    box_w = max(40, min(50, width - 4))
    box_h = min(20, height - 4)
    box_y = (height - box_h) // 2
    box_x = (width - box_w) // 2

    query = ""
    cursor_idx = 0
    matches = [(i, w) for i, w in enumerate(WEAPONS)]  # full list initially

    while True:
        # Clear area
        for row in range(box_h):
            safe_addstr(stdscr, box_y + row, box_x, " " * box_w)

        draw_centered_box(stdscr, box_y, box_x, box_h, box_w)

        # Title
        safe_addstr(stdscr, box_y + 1, box_x + 2, "Weapon Selection", curses.A_BOLD)
        safe_addstr(stdscr, box_y + 2, box_x + 2, "Type to search, ↑↓ Enter, Esc to cancel")

        # Search bar
        search_label = "Search: "
        search_x = box_x + 2
        search_y = box_y + 3
        search_display = search_label + query
        safe_addstr(stdscr, search_y, search_x, " " * (box_w - 4))
        safe_addstr(stdscr, search_y, search_x, search_display[:box_w - 4])

        # Filter weapons
        if query:
            matches = find_weapon(query)
        else:
            matches = [(i, w) for i, w in enumerate(WEAPONS)]

        if not matches:
            matches = [(i, w) for i, w in enumerate(WEAPONS)]
            safe_addstr(stdscr, search_y + 2, box_x + 2, "  No matches — showing all weapons.")

        # Clamp cursor
        cursor_idx = min(cursor_idx, max(0, len(matches) - 1))

        # List area
        list_h = box_h - 6
        list_start_y = box_y + 5
        list_offset = max(0, cursor_idx - list_h + 1)
        visible_matches = matches[list_offset:list_offset + list_h]

        for i, (idx, w) in enumerate(visible_matches):
            y = list_start_y + i
            is_sel = (list_offset + i) == cursor_idx
            prefix = "▸ " if is_sel else "  "
            # Truncate name
            name_display = w
            max_name_w = box_w - 6
            if len(name_display) > max_name_w:
                name_display = name_display[:max_name_w - 1] + "…"
            line = f"{prefix}{name_display}"
            attr = curses.A_REVERSE if is_sel else curses.A_NORMAL
            safe_addstr(stdscr, y, box_x + 2, " " * (box_w - 4))
            safe_addstr(stdscr, y, box_x + 2, line[:box_w - 4], attr)

        # Help footer
        footer_y = box_y + box_h - 2
        safe_addstr(stdscr, footer_y, box_x + 2, "↑↓ nav  Enter select  Esc cancel")

        stdscr.refresh()
        ch = stdscr.getch()

        if ch == 27:  # Escape
            return None
        elif ch in (10, 13, curses.KEY_ENTER):  # Enter
            if matches:
                _, weapon = matches[cursor_idx]
                return weapon
        elif ch == curses.KEY_UP:
            cursor_idx = max(0, cursor_idx - 1)
        elif ch == curses.KEY_DOWN:
            cursor_idx = min(len(matches) - 1, cursor_idx + 1)
        elif ch in (127, curses.KEY_BACKSPACE, 8):  # Backspace
            if query:
                query = query[:-1]
                cursor_idx = 0
        elif 32 <= ch <= 126:  # Printable
            q = chr(ch)
            # Check if it's a digit for direct index selection
            if q.isdigit() and not query:
                idx = int(q)
                if idx < len(WEAPONS):
                    return WEAPONS[idx]
            query += q
            cursor_idx = 0
        # else ignore


def _wizard_skin_input(stdscr, box_y, box_x, box_w, weapon, prompt="Skin: "):
    """Draw the skin input box and return the entered skin string or None.

    Clears the box area, draws the border, shows the weapon name,
    and blocks for text input. Returns a title-cased skin name, or None
    on Escape / empty input.
    """
    box_h = 5
    _wizard_prompt_box(stdscr, box_y, box_x, box_h, box_w, f"Weapon: {weapon}")
    skin = curses_input_blocking(stdscr, box_y + 2, box_x + 2, box_w - 12, prompt=prompt)
    if skin is None:
        return None
    skin = capitalize_skin(skin.strip())
    return skin if skin else None


def _wizard_prompt_box(stdscr, box_y, box_x, box_h, box_w, title):
    """Clear the box area, draw the border, and write the title row."""
    for row in range(box_h):
        safe_addstr(stdscr, box_y + row, box_x, " " * box_w)
    draw_centered_box(stdscr, box_y, box_x, box_h, box_w)
    safe_addstr(stdscr, box_y + 1, box_x + 2, title, curses.A_BOLD)


def _wizard_yes_no(stdscr, box_y, box_x, box_w, prompt_text):
    """Blocking y/N prompt inside the wizard box. Returns True for yes, False otherwise."""
    safe_addstr(stdscr, box_y + 2, box_x + 2, prompt_text)
    stdscr.refresh()
    while True:
        ch = stdscr.getch()
        if ch in (ord('y'), ord('Y')):
            return True
        elif ch in (10, 13, curses.KEY_ENTER, ord('n'), ord('N'), 27):
            return False


def _wizard_validate_step(stdscr, width, height, item, api_key, scraper,
                          prices_cache) -> tuple[dict, Literal["ok", "retry"]] | None:
    """Step 4: Validate item against API, handle suggestions.

    Returns (item, status) with status in ('ok', 'retry'), or None to cancel.
    """
    box_w = max(44, min(60, width - 4))
    box_h = min(16, height - 4)
    box_y = (height - box_h) // 2
    box_x = (width - box_w) // 2

    _wizard_prompt_box(stdscr, box_y, box_x, box_h, box_w, "Checking API...")
    stdscr.refresh()

    # Run validation (use cached prices for speed, fall back to fresh API call)
    validation = validate_item(item, api_key=api_key, scraper=scraper,
                               prices_data=prices_cache)
    curses.flushinp()  # Discard any keystrokes typed during the blocking API call

    current_item = dict(item)  # mutable copy

    while True:
        y = box_y + 2

        if validation.status == "found":
            # Found with prices
            _wizard_prompt_box(stdscr, box_y, box_x, box_h, box_w, "✓ Item found in API!")
            safe_addstr(stdscr, y, box_x + 2,
                        f"{fmt_item_line(current_item):<{box_w - 4}}")
            y += 1
            price_info = validation.data
            for source in ('buff163', 'skins'):
                if source in price_info:
                    safe_addstr(stdscr, y, box_x + 2,
                                f"  {source}: €{price_info[source]:.2f}")
                    y += 1
            if y < box_y + box_h - 2:
                safe_addstr(stdscr, y + 1, box_x + 2, "Press Enter to continue or Esc to cancel")
            stdscr.refresh()
            while True:
                ch = stdscr.getch()
                if ch in (10, 13, curses.KEY_ENTER):
                    return current_item, "ok"
                elif ch == 27:
                    return None

        elif validation.status == "not_found":
            # Not found — show similar items
            similar = validation.data
            _wizard_prompt_box(stdscr, box_y, box_x, box_h, box_w,
                               f"⚠ '{format_market_hash_name(current_item)}' not found")

            if similar:
                safe_addstr(stdscr, y, box_x + 2, "Did you mean?")
                y += 1
                list_h = min(len(similar), box_h - 7)
                for idx, suggestion in enumerate(similar[:list_h]):
                    safe_addstr(stdscr, y + idx, box_x + 2, f"  {idx + 1}) {suggestion}")
                y += list_h

            if y < box_y + box_h - 2:
                safe_addstr(stdscr, y, box_x + 2,
                            "Number=pick  (p)roceed  (r)etry  (c)ancel")
            stdscr.refresh()

            ch = stdscr.getch()
            if ch == 27 or ch in (ord('c'), ord('C')):
                return None
            if ch in (ord('p'), ord('P'), ord('y'), ord('Y')):
                return current_item, "ok"
            if ch in (ord('r'), ord('R')):
                return current_item, "retry"
            # Number keys 1-9
            if 48 < ch <= 57:
                idx = ch - 49  # 0-based
                if similar and 0 <= idx < len(similar):
                    selected_item, price_info = apply_suggestion(similar, idx, validation.prices, current_item.get('stattrak', False), current_item.get('souvenir', False))
                    current_item = selected_item
                    validation = ValidationResult("found", price_info, validation.prices)

        else:
            # API error or no key
            _wizard_prompt_box(stdscr, box_y, box_x, box_h, box_w, "⚠ API validation unavailable")
            safe_addstr(stdscr, y, box_x + 2, str(validation.data)[:box_w - 6])
            y += 1
            if y < box_y + box_h - 2:
                safe_addstr(stdscr, y, box_x + 2, "(p)roceed anyway  (c)ancel")
            stdscr.refresh()
            while True:
                ch = stdscr.getch()
                if ch in (ord('p'), ord('P'), ord('y'), ord('Y')):
                    return current_item, "ok"
                elif ch in (27, ord('c'), ord('C')):
                    return None


def run_add_wizard(stdscr, scraper, api_key, prices_cache):
    """Run the interactive add item wizard.

    Works in blocking mode (nodelay False), restores state on exit.
    Returns the new item dict, or None if cancelled.
    """
    height, width = stdscr.getmaxyx()

    # Save terminal state (curses has no getter for timeout, so use known values)
    stdscr.nodelay(False)
    stdscr.timeout(-1)
    curses.curs_set(1)

    try:
        # ══════════════════════════════════════════════════════
        # STEP 0: Weapon Selection
        # ══════════════════════════════════════════════════════
        weapon = _wizard_weapon_search(stdscr, width, height)
        if weapon is None:
            return None

        # ══════════════════════════════════════════════════════
        # STEP 1: Skin Input
        # ══════════════════════════════════════════════════════
        box_w = max(40, min(50, width - 4))
        box_h = 5
        box_y = (height - box_h) // 2
        box_x = (width - box_w) // 2

        skin = _wizard_skin_input(stdscr, box_y, box_x, box_w, weapon)
        if skin is None:
            return None

        # ══════════════════════════════════════════════════════
        # STEP 2: Wear
        # ══════════════════════════════════════════════════════
        _wizard_prompt_box(stdscr, box_y, box_x, box_h, box_w,
                           f"Item: {weapon} | {skin}")
        wear_raw = curses_input_blocking(stdscr, box_y + 2, box_x + 2, box_w - 12,
                                         prompt="Wear [fn/mw/ft/ww/bs] none: ")
        wear = normalize_wear(wear_raw.strip()) if wear_raw and wear_raw.strip() else None

        # ══════════════════════════════════════════════════════
        # STEP 3: StatTrak
        # ══════════════════════════════════════════════════════
        _wizard_prompt_box(stdscr, box_y, box_x, box_h, box_w,
                           f"Item: {fmt_item_line({'name': f'{weapon} | {skin}', 'wear': wear, 'stattrak': False})}")
        stattrak = _wizard_yes_no(stdscr, box_y, box_x, box_w, "StatTrak? (y/N): ")

        # ══════════════════════════════════════════════════════
        # STEP 4: Souvenir
        # ══════════════════════════════════════════════════════
        _wizard_prompt_box(stdscr, box_y, box_x, box_h, box_w,
                           f"Item: {fmt_item_line({'name': f'{weapon} | {skin}', 'wear': wear, 'stattrak': stattrak, 'souvenir': False})}")
        souvenir = _wizard_yes_no(stdscr, box_y, box_x, box_w, "Souvenir? (y/N): ")

        # ══════════════════════════════════════════════════════
        # STEP 5: API Validation (with retry loop)
        # ══════════════════════════════════════════════════════
        item = {"name": f"{weapon} | {skin}", "wear": wear, "stattrak": stattrak, "souvenir": souvenir}

        while True:
            result = _wizard_validate_step(stdscr, width, height, item,
                                           api_key, scraper, prices_cache)
            if result is None:
                return None
            item, status = result
            if status == "retry":
                # Retry — re-enter skin name
                skin = _wizard_skin_input(stdscr, box_y, box_x, box_w, weapon,
                                          prompt="Skin (retry): ")
                if skin is None:
                    return None
                item = {"name": f"{weapon} | {skin}", "wear": wear, "stattrak": stattrak, "souvenir": souvenir}
                continue
            break

        # ══════════════════════════════════════════════════════
        # STEP 6: Final Confirmation
        # ══════════════════════════════════════════════════════
        item_line = fmt_item_line(item)
        short_line = item_line[:50]
        if not confirm_dialog(stdscr, f'Add "{short_line}"?'):
            return None

        return item

    finally:
        stdscr.nodelay(True)
        stdscr.timeout(100)
        curses.curs_set(0)
