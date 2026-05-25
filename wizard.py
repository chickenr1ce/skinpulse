"""Add-item wizard for the curses TUI.

Contains the interactive add-item flow and shared curses rendering helpers
(safe_addstr, draw_centered_box, confirm_dialog, curses_input_blocking) that
are used by the main TUI loop as well.
"""

import curses
from items import (
    find_weapon, WEAPONS, _capitalize_skin, normalize_wear,
    format_item_line as fmt_item_line, format_market_hash_name,
)
from utils import validate_item, parse_suggestion_api_name, apply_suggestion


def safe_addstr(stdscr, y, x, text, attr=0):
    """Add string to screen, silently ignoring curses.error if coords are out of bounds."""
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def draw_centered_box(stdscr, box_y, box_x, box_h, box_w):
    """Draw a box with double-line corners at (box_y, box_x) with given dimensions."""
    if box_h < 3 or box_w < 4:
        return
    safe_addstr(stdscr, box_y, box_x, "╔" + "═" * (box_w - 2) + "╗")
    for row in range(1, box_h - 1):
        safe_addstr(stdscr, box_y + row, box_x, "║")
        safe_addstr(stdscr, box_y + row, box_x + box_w - 1, "║")
    safe_addstr(stdscr, box_y + box_h - 1, box_x, "╚" + "═" * (box_w - 2) + "╝")


def curses_input_blocking(stdscr, y, x, max_width, prompt="", initial=""):
    """Blocking text input widget. Returns the entered string or None on Escape.

    Renders 'prompt' + cursor at (y, x). Handles printable chars, Backspace,
    Enter (submit), Escape (cancel). Assumes nodelay(False) is already set.
    """
    buffer = list(initial)
    while True:
        # Render
        display = prompt + "".join(buffer)
        safe_addstr(stdscr, y, x, " " * (max_width + 2))
        safe_addstr(stdscr, y, x, display[:max_width])
        stdscr.refresh()
        ch = stdscr.getch()
        if ch == 27:  # Escape
            return None
        elif ch in (10, 13, curses.KEY_ENTER):  # Enter
            return "".join(buffer)
        elif ch in (127, curses.KEY_BACKSPACE, 8):  # Backspace
            if buffer:
                buffer.pop()
        elif 32 <= ch <= 126 and len("".join(buffer)) < max_width:  # Printable
            buffer.append(chr(ch))
        # else ignore


def confirm_dialog(stdscr, message):
    """Show a centered modal confirmation dialog. Returns True for yes, False for no.

    Operates in blocking mode (sets nodelay(False) temporarily).
    """
    height, width = stdscr.getmaxyx()
    stdscr.nodelay(False)
    stdscr.timeout(-1)
    curses.curs_set(0)

    # Dialog dimensions
    msg_lines = message.split('\n')
    box_w = max(40, min(60, width - 4))
    box_h = max(5, len(msg_lines) + 4)
    box_y = (height - box_h) // 2
    box_x = (width - box_w) // 2

    # Capture area underneath
    try:
        stdscr.refresh()
    except curses.error:
        pass

    result = False
    while True:
        draw_centered_box(stdscr, box_y, box_x, box_h, box_w)
        # Message
        for i, line in enumerate(msg_lines):
            safe_addstr(stdscr, box_y + 1 + i, box_x + 2, line[:box_w - 4])
        # Prompt
        prompt_y = box_y + box_h - 2
        safe_addstr(stdscr, prompt_y, box_x + 2, "(y)es  (n)o", curses.A_REVERSE)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (ord('y'), ord('Y')):
            result = True
            break
        elif ch in (ord('n'), ord('N'), 27):  # n, Escape
            result = False
            break

    # Restore state to standard TUI values
    stdscr.nodelay(True)
    stdscr.timeout(100)
    return result


def _wizard_draw_box(stdscr, box_h, box_w, box_y, box_x):
    """Draw a bordered box used by wizard steps."""
    draw_centered_box(stdscr, box_y, box_x, box_h, box_w)


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

        _wizard_draw_box(stdscr, box_h, box_w, box_y, box_x)

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


def _wizard_validate_step(stdscr, width, height, item, api_key, scraper, prices_cache):
    """Step 4: Validate item against API, handle suggestions.

    Returns validated item dict, or None to cancel.
    """
    box_w = max(44, min(60, width - 4))
    box_h = min(16, height - 4)
    box_y = (height - box_h) // 2
    box_x = (width - box_w) // 2

    # Clear area
    for row in range(box_h):
        safe_addstr(stdscr, box_y + row, box_x, " " * box_w)
    _wizard_draw_box(stdscr, box_h, box_w, box_y, box_x)

    safe_addstr(stdscr, box_y + 1, box_x + 2, "Checking API...", curses.A_BOLD)
    stdscr.refresh()

    # Run validation (use cached prices for speed, fall back to fresh API call)
    found, result, prices_data = validate_item(item, api_key=api_key, scraper=scraper,
                                                prices_data=prices_cache)
    curses.flushinp()  # Discard any keystrokes typed during the blocking API call

    current_item = dict(item)  # mutable copy

    while True:
        # Clear and redraw
        for row in range(box_h):
            safe_addstr(stdscr, box_y + row, box_x, " " * box_w)
        _wizard_draw_box(stdscr, box_h, box_w, box_y, box_x)

        y = box_y + 1

        if found is True:
            # Found with prices
            safe_addstr(stdscr, y, box_x + 2, "✓ Item found in API!", curses.A_BOLD)
            y += 1
            safe_addstr(stdscr, y, box_x + 2,
                        f"{fmt_item_line(current_item):<{box_w - 4}}")
            y += 1
            price_info = result
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
                    return current_item
                elif ch == 27:
                    return None

        elif found is False:
            # Not found — show similar items
            similar = result
            safe_addstr(stdscr, y, box_x + 2,
                        f"⚠ '{format_market_hash_name(current_item)}' not found",
                        curses.A_BOLD)
            y += 1

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
            elif ch in (ord('p'), ord('P'), ord('y'), ord('Y')):
                return current_item
            elif ch in (ord('r'), ord('R')):
                # Signal retry by returning a special value — caller handles skin re-entry
                return "RETRY"
            elif 48 < ch <= 57:  # Number keys 1-9
                idx = ch - 49  # 0-based
                if similar and 0 <= idx < len(similar):
                    selected_item, price_info = apply_suggestion(similar, idx, prices_data, current_item.get('stattrak', False))
                    current_item = selected_item
                    found = True
                    result = price_info
                    # Loop to show updated info

        else:
            # API error or no key
            safe_addstr(stdscr, y, box_x + 2, "⚠ API validation unavailable", curses.A_BOLD)
            y += 1
            safe_addstr(stdscr, y, box_x + 2, str(result)[:box_w - 6])
            y += 1
            if y < box_y + box_h - 2:
                safe_addstr(stdscr, y, box_x + 2, "(p)roceed anyway  (c)ancel")
            stdscr.refresh()
            while True:
                ch = stdscr.getch()
                if ch in (ord('p'), ord('P'), ord('y'), ord('Y')):
                    return current_item
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

        for row in range(box_h):
            safe_addstr(stdscr, box_y + row, box_x, " " * box_w)
        _wizard_draw_box(stdscr, box_h, box_w, box_y, box_x)
        safe_addstr(stdscr, box_y + 1, box_x + 2, f"Weapon: {weapon}", curses.A_BOLD)
        skin = curses_input_blocking(stdscr, box_y + 2, box_x + 2, box_w - 12,
                                     prompt="Skin: ")
        if skin is None:
            return None
        skin = _capitalize_skin(skin.strip())
        if not skin:
            return None

        # ══════════════════════════════════════════════════════
        # STEP 2: Wear
        # ══════════════════════════════════════════════════════
        for row in range(box_h):
            safe_addstr(stdscr, box_y + row, box_x, " " * box_w)
        _wizard_draw_box(stdscr, box_h, box_w, box_y, box_x)
        safe_addstr(stdscr, box_y + 1, box_x + 2, f"Item: {weapon} | {skin}", curses.A_BOLD)
        wear_raw = curses_input_blocking(stdscr, box_y + 2, box_x + 2, box_w - 12,
                                         prompt="Wear [fn/mw/ft/ww/bs] none: ")
        wear = normalize_wear(wear_raw.strip()) if wear_raw and wear_raw.strip() else None

        # ══════════════════════════════════════════════════════
        # STEP 3: StatTrak
        # ══════════════════════════════════════════════════════
        for row in range(box_h):
            safe_addstr(stdscr, box_y + row, box_x, " " * box_w)
        _wizard_draw_box(stdscr, box_h, box_w, box_y, box_x)
        safe_addstr(stdscr, box_y + 1, box_x + 2,
                    f"Item: {fmt_item_line({'name': f'{weapon} | {skin}', 'wear': wear, 'stattrak': False})}",
                    curses.A_BOLD)
        safe_addstr(stdscr, box_y + 2, box_x + 2, "StatTrak? (y/N): ")

        stattrak = False
        stdscr.refresh()
        while True:
            ch = stdscr.getch()
            if ch in (ord('y'), ord('Y')):
                stattrak = True
                break
            elif ch in (10, 13, curses.KEY_ENTER, ord('n'), ord('N'), 27):
                break

        # ══════════════════════════════════════════════════════
        # STEP 4: API Validation (with retry loop)
        # ══════════════════════════════════════════════════════
        item = {"name": f"{weapon} | {skin}", "wear": wear, "stattrak": stattrak}

        while True:
            result_item = _wizard_validate_step(stdscr, width, height, item,
                                                 api_key, scraper, prices_cache)
            if result_item is None:
                return None
            if result_item == "RETRY":
                # Retry — re-enter skin name
                for row in range(min(8, height - 2)):
                    safe_addstr(stdscr, box_y + row, box_x, " " * box_w)
                _wizard_draw_box(stdscr, 5, box_w, box_y, box_x)
                safe_addstr(stdscr, box_y + 1, box_x + 2,
                            f"Weapon: {weapon}", curses.A_BOLD)
                skin = curses_input_blocking(stdscr, box_y + 2, box_x + 2, box_w - 12,
                                             prompt="Skin (retry): ")
                if skin is None:
                    return None
                skin = _capitalize_skin(skin.strip())
                if not skin:
                    return None
                item = {"name": f"{weapon} | {skin}", "wear": wear, "stattrak": stattrak}
                # Re-enter validation flow
                continue
            item = result_item
            break

        # ══════════════════════════════════════════════════════
        # STEP 5: Final Confirmation
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
