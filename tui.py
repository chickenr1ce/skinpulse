import curses
import json
import os
import re
import time
import requests
from price_empire_scraper import PriceEmpireScraper, format_market_hash_name
from items import (
    load_items as load_items_file, save_items, get_items_mtime,
    find_weapon, split_name, _capitalize_skin, normalize_wear, WEAPONS,
    format_item_line as fmt_item_line,
)
from constants.display import MIN_HEIGHT, MIN_WIDTH
from utils import validate_item, sync_config, parse_suggestion_api_name

def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}

def safe_addstr(stdscr, y, x, text, attr=0):
    """Add string to screen, silently ignoring curses.error if coords are out of bounds."""
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def draw_price_col(stdscr, y, x, price, attr=0):
    safe_addstr(stdscr, y, x, f"{price:>8.2f}", attr)


def draw_centered_box(stdscr, box_y, box_x, box_h, box_w):
    """Draw a box with double-line corners at (box_y, box_x) with given dimensions."""
    if box_h < 3 or box_w < 4:
        return
    safe_addstr(stdscr, box_y, box_x, "╔" + "═" * (box_w - 2) + "╗")
    for r in range(1, box_h - 1):
        safe_addstr(stdscr, box_y + r, box_x, "║")
        safe_addstr(stdscr, box_y + r, box_x + box_w - 1, "║")
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


def get_sort_value(item, prices, sort_column):
    mhn = format_market_hash_name(item)
    item_data = prices.get(mhn, {})
    price_dict = item_data.get('prices', {})

    if sort_column == 0:
        return mhn.lower()
    elif sort_column == 1:
        return price_dict.get('buff163', {}).get('price', 0.0) or 0.0
    elif sort_column == 2:
        return price_dict.get('skins', {}).get('price', 0.0) or 0.0
    elif sort_column == 3:
        all_prices = [v.get('price', 0.0) for k, v in price_dict.items()
                      if isinstance(v, dict) and v.get('price', 0.0) > 0]
        return min(all_prices) if all_prices else 0.0
    return 0.0


def get_live_price(mhn, prices, fallback=0.0):
    item_data = prices.get(mhn, {})
    price_dict = item_data.get('prices', {}) if isinstance(item_data, dict) else {}
    buff = price_dict.get('buff163', {}).get('price', 0.0) or 0.0
    return buff if buff > 0 else fallback


def get_portfolio_sort_value(item, prices, sort_column):
    mhn = item.get('market_hash_name', '')
    stats = item.get('stats', {})

    if sort_column == 0:
        return mhn.lower()
    elif sort_column == 1:
        return stats.get('holdings', 0) or 0
    elif sort_column == 2:
        return stats.get('avgBuyPrice', 0.0) or 0.0
    elif sort_column in (3, 4, 5, 6):
        live = get_live_price(mhn, prices, item.get('currentPrice', 0.0) or 0.0)
        if sort_column == 3:
            return live
        hld = stats.get('holdings', 0) or 0
        if sort_column == 4:
            return live * hld
        avg = stats.get('avgBuyPrice', 0.0) or 0.0
        if sort_column == 5:
            return (live - avg) * hld
        if sort_column == 6:
            return ((live - avg) / avg * 100) if avg > 0 else 0.0
    return 0.0


def draw_menu(stdscr):
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)

    k = 0

    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(100)

    config_data = load_config()
    api_key = "YOUR_API_KEY"
    items_to_track = []
    portfolio_slug = ""

    if isinstance(config_data, dict):
        api_key = config_data.get("api_key", api_key)
        portfolio_slug = config_data.get("portfolio_slug", "")

    items_loaded = load_items_file()
    items_mtime = get_items_mtime()
    if items_loaded is not None:
        items_to_track = items_loaded
    else:
        if isinstance(config_data, dict):
            items_to_track = config_data.get("items", [])
        elif isinstance(config_data, list):
            items_to_track = config_data

    scraper = PriceEmpireScraper(api_key)

    last_update = 0
    prices = {}
    loading = False
    error_message = ""
    sort_column = 0
    sort_ascending = True

    portfolio = {}
    portfolio_error = ""
    current_view = "watchlist"
    portfolio_sort_column = 0
    portfolio_sort_ascending = True

    watchlist_scroll = 0
    portfolio_scroll = 0
    watchlist_cursor = 0
    portfolio_cursor = 0

    spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    spinner_frame = 0

    mode = "normal"  # "normal" | "wizard"

    while k != ord('q'):
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        banner_height = 6 if height >= 20 else 0

        if height < MIN_HEIGHT or width < MIN_WIDTH:
            msg = f"Terminal too small — need at least {MIN_WIDTH}x{MIN_HEIGHT}, got {width}x{height}"
            try:
                stdscr.addstr(0, 0, msg[:width])
            except curses.error:
                pass
            stdscr.refresh()
            k = stdscr.getch()
            continue

        if banner_height:
            banner_art = [
                "         __   _                   __        ",
                "   _____/ /__(_)___  ____  __  __/ /_______ ",
                "  / ___/ //_/ / __ \\/ __ \\/ / / / / ___/ _ \\",
                " (__  ) ,< / / / / / /_/ / /_/ / (__  )  __/",
                "/____/_/|_/_/_/ /_/ .___/\\__,_/_/____/\\___/ ",
                "                 /_/                        ",
            ]
            max_bw = max(len(line) for line in banner_art)
            for i, line in enumerate(banner_art):
                x = (width - max_bw) // 2
                safe_addstr(stdscr, i, x, line, curses.A_BOLD)

        # ── Scroll indicator ──
        scroll_indicator = ""
        if current_view == "watchlist":
            total = len(items_to_track)
            max_visible = max(1, height - 8 - banner_height)
            clamped = max(0, min(watchlist_scroll, max(0, total - max_visible)))
            if total > max_visible:
                first = clamped + 1
                last = min(clamped + max_visible, total)
                parts = []
                if clamped > 0:
                    parts.append("↑")
                parts.append(f"{first}-{last}/{total}")
                if last < total:
                    parts.append("↓")
                scroll_indicator = " | " + " ".join(parts)
        else:
            total = len(portfolio.get("items", []))
            max_visible = max(1, height - 8 - banner_height)
            clamped = max(0, min(portfolio_scroll, max(0, total - max_visible)))
            if total > max_visible:
                first = clamped + 1
                last = min(clamped + max_visible, total)
                parts = []
                if clamped > 0:
                    parts.append("↑")
                parts.append(f"{first}-{last}/{total}")
                if last < total:
                    parts.append("↓")
                scroll_indicator = " | " + " ".join(parts)

        if current_view == "watchlist":
            help_text = ("'q' quit | 'r' ref | 'p' port | 'a' add | 'd' del | "
                         "↑↓ nav | '1'-'4' sort | ^D/^U sc | g/G top/bot")
            safe_addstr(stdscr, height - 1, 0, (help_text + scroll_indicator)[:width])
        else:
            help_text = ("'q' quit | 'r' ref | 'p' watch | "
                         "↑↓ nav | '1'-'7' sort | ^D/^U sc | g/G top/bot")
            safe_addstr(stdscr, height - 1, 0, (help_text + scroll_indicator)[:width])

        current_time = time.time()

        should_refresh = False
        if last_update == 0:
            should_refresh = True
        elif k == ord('r'):
            should_refresh = True
        elif current_time - last_update > 300:
            should_refresh = True

        if should_refresh:
            loading = True
            spinner_char = spinner_frames[spinner_frame]
            load_y = banner_height
            if current_view == "portfolio" and portfolio_slug:
                safe_addstr(stdscr, load_y, 2, f"{spinner_char} Fetching prices and portfolio...")
            else:
                safe_addstr(stdscr, load_y, 2, f"{spinner_char} Fetching prices from PriceEmpire...")
            stdscr.refresh()

            api_response = scraper.get_prices()

            if portfolio_slug:
                portfolio_response = scraper.get_portfolio(portfolio_slug)
                if isinstance(portfolio_response, dict) and "error" in portfolio_response:
                    portfolio_error = portfolio_response["error"]
                elif isinstance(portfolio_response, dict):
                    portfolio = portfolio_response
                    portfolio_error = ""

            last_update = current_time

            if isinstance(api_response, dict) and "error" in api_response:
                error_message = api_response["error"]
            else:
                prices = api_response
                error_message = ""
            loading = False

        if k == ord('p'):
            if portfolio_slug:
                current_view = "portfolio" if current_view == "watchlist" else "watchlist"
            elif current_view == "portfolio":
                current_view = "watchlist"

        if k in (ord('1'), ord('2'), ord('3'), ord('4'), ord('5'), ord('6'), ord('7')):
            col = k - ord('1')
            if current_view == "watchlist" and col < 4:
                if col == sort_column:
                    sort_ascending = not sort_ascending
                else:
                    sort_column = col
                    sort_ascending = True
                watchlist_scroll = 0
                watchlist_cursor = 0
            elif current_view == "portfolio" and col < 7:
                if col == portfolio_sort_column:
                    portfolio_sort_ascending = not portfolio_sort_ascending
                else:
                    portfolio_sort_column = col
                    portfolio_sort_ascending = True
                portfolio_scroll = 0
                portfolio_cursor = 0

        # ── Normal mode key handling ──
        if mode == "normal":
            # ── Cursor navigation ──
            if k == curses.KEY_UP:
                if current_view == "watchlist":
                    # sorted_items is defined later during rendering; compute here.
                    # We'll use items_to_track to approximate (sort happens in render).
                    watchlist_cursor = max(0, watchlist_cursor - 1)
                else:
                    portfolio_cursor = max(0, portfolio_cursor - 1)
            elif k == curses.KEY_DOWN:
                if current_view == "watchlist":
                    max_idx = max(0, len(items_to_track) - 1)
                    watchlist_cursor = min(max_idx, watchlist_cursor + 1)
                else:
                    max_idx = max(0, len(portfolio.get("items", [])) - 1)
                    portfolio_cursor = min(max_idx, portfolio_cursor + 1)

            # ── Delete selected item ──
            if k == ord('d') and current_view == "watchlist" and items_to_track:
                # Build sorted list to find what's at cursor
                sorted_items = sorted(
                    items_to_track,
                    key=lambda i: get_sort_value(i, prices, sort_column),
                    reverse=not sort_ascending,
                )
                if 0 <= watchlist_cursor < len(sorted_items):
                    selected = sorted_items[watchlist_cursor]
                    name_str = fmt_item_line(selected)
                    if confirm_dialog(stdscr, f'Remove "{name_str}"?'):
                        items_to_track.remove(selected)
                        save_items(items_to_track)
                        sync_config(items_to_track)
                        watchlist_cursor = min(watchlist_cursor, max(0, len(items_to_track) - 1))
                        should_refresh = True

            # ── Add item wizard ──
            if k == ord('a') and current_view == "watchlist":
                new_item = run_add_wizard(stdscr, scraper, api_key, prices)
                if new_item is not None:
                    items_to_track.append(new_item)
                    save_items(items_to_track)
                    sync_config(items_to_track)
                    watchlist_cursor = len(items_to_track) - 1
                    watchlist_scroll = 0
                    should_refresh = True

            # ── Scrolling ──
            if k == curses.KEY_PPAGE:  # PgUp
                if current_view == "watchlist":
                    watchlist_scroll -= max(1, height - 8 - banner_height)
                else:
                    portfolio_scroll -= max(1, height - 8 - banner_height)
            elif k == curses.KEY_NPAGE:  # PgDn
                if current_view == "watchlist":
                    watchlist_scroll += max(1, height - 8 - banner_height)
                else:
                    portfolio_scroll += max(1, height - 8 - banner_height)
            elif k == 21:  # Ctrl-U (half page up)
                if current_view == "watchlist":
                    watchlist_scroll -= max(1, (height - 8 - banner_height) // 2)
                else:
                    portfolio_scroll -= max(1, (height - 8 - banner_height) // 2)
            elif k == 4:  # Ctrl-D (half page down)
                if current_view == "watchlist":
                    watchlist_scroll += max(1, (height - 8 - banner_height) // 2)
                else:
                    portfolio_scroll += max(1, (height - 8 - banner_height) // 2)
            elif k == ord('g'):
                if current_view == "watchlist":
                    watchlist_scroll = 0
                    watchlist_cursor = 0
                else:
                    portfolio_scroll = 0
                    portfolio_cursor = 0
            elif k == ord('G'):
                if current_view == "watchlist":
                    watchlist_scroll = 10**9
                    watchlist_cursor = max(0, len(items_to_track) - 1)
                else:
                    portfolio_scroll = 10**9
                    portfolio_cursor = max(0, len(portfolio.get("items", [])) - 1)

            # ── Auto-scroll cursor into view ──
            max_visible = max(1, height - 8 - banner_height)
            if current_view == "watchlist":
                if watchlist_cursor < watchlist_scroll:
                    watchlist_scroll = watchlist_cursor
                elif watchlist_cursor >= watchlist_scroll + max_visible and len(items_to_track) > 0:
                    watchlist_scroll = watchlist_cursor - max_visible + 1
            else:
                p_len = len(portfolio.get("items", []))
                if portfolio_cursor < portfolio_scroll:
                    portfolio_scroll = portfolio_cursor
                elif portfolio_cursor >= portfolio_scroll + max_visible and p_len > 0:
                    portfolio_scroll = portfolio_cursor - max_visible + 1

        # ── External file change detection ──
        new_mtime = get_items_mtime()
        if new_mtime and new_mtime != items_mtime:
            loaded = load_items_file()
            if loaded is not None:
                items_to_track = loaded
                items_mtime = new_mtime
                watchlist_scroll = 0
                watchlist_cursor = 0

        # ── WATCHLIST VIEW ──
        if current_view == "watchlist":
            if error_message:
                safe_addstr(stdscr, banner_height, 2, f"Error: {error_message[:width-10]}", curses.A_BOLD)

            y = 6 if banner_height else 0
            safe_addstr(stdscr, y, 0, "╔" + "═" * (width - 2) + "╗")
            y += 1

            col_headers = ["Item Name", "Buff 163", "Skins.com", "Lowest"]
            arrows = ["", "", "", ""]
            if sort_column < len(col_headers):
                arrows[sort_column] = " ▲" if sort_ascending else " ▼"

            price_width = 9
            name_width = max(20, width - (price_width * 3 + 3 * 3 + 2 + 2))

            header_fmt = f"{{:<{name_width}}} | {{:>{price_width}}} | {{:>{price_width}}} | {{:>{price_width}}}"
            header_str = header_fmt.format(
                col_headers[0] + arrows[0],
                col_headers[1] + arrows[1],
                col_headers[2] + arrows[2],
                col_headers[3] + arrows[3],
            )
            safe_addstr(stdscr, y, 0, "║")
            safe_addstr(stdscr, y, 2, header_str, curses.A_BOLD)
            safe_addstr(stdscr, y, width - 1, "║")
            y += 1

            safe_addstr(stdscr, y, 0, "╠" + "═" * (width - 2) + "╣")
            y += 1

            sorted_items = sorted(items_to_track, key=lambda i: get_sort_value(i, prices, sort_column),
                                  reverse=not sort_ascending)

            max_visible = max(1, height - 8 - banner_height)
            watchlist_scroll = max(0, min(watchlist_scroll, max(0, len(sorted_items) - max_visible)))
            visible_items = sorted_items[watchlist_scroll:watchlist_scroll + max_visible]

            for i, item in enumerate(visible_items):
                abs_index = watchlist_scroll + i
                is_cursor = (abs_index == watchlist_cursor) and items_to_track
                row_attr = curses.A_BOLD if is_cursor else curses.A_NORMAL

                mhn = format_market_hash_name(item)
                item_data = prices.get(mhn, {})
                price_dict = item_data.get('prices', {})

                buff_price = price_dict.get('buff163', {}).get('price', 0.0) or 0.0
                skins_price = price_dict.get('skins', {}).get('price', 0.0) or 0.0
                all_provider_prices = [v.get('price', 0.0) for k, v in price_dict.items()
                                       if isinstance(v, dict) and v.get('price', 0.0) > 0]
                min_price = min(all_provider_prices) if all_provider_prices else 0.0

                x = 2
                safe_addstr(stdscr, y, 0, "║", row_attr)
                safe_addstr(stdscr, y, x, f"{mhn[:name_width]:<{name_width}}", row_attr)
                x += name_width + 3

                draw_price_col(stdscr, y, x, buff_price, row_attr)
                x += price_width + 3

                draw_price_col(stdscr, y, x, skins_price, row_attr)
                x += price_width + 3

                draw_price_col(stdscr, y, x, min_price, row_attr)
                safe_addstr(stdscr, y, width - 1, "║", row_attr)

                y += 1

            safe_addstr(stdscr, y, 0, "╚" + "═" * (width - 2) + "╝")

        # ── PORTFOLIO VIEW ──
        else:
            if portfolio_error:
                safe_addstr(stdscr, banner_height, 2, f"Portfolio error: {portfolio_error[:width - 20]}", curses.A_BOLD)

            y = 6 if banner_height else 0
            safe_addstr(stdscr, y, 0, "╔" + "═" * (width - 2) + "╗")
            y += 1

            if not portfolio:
                safe_addstr(stdscr, y, 0, "║")
                safe_addstr(stdscr, y, 2, "No portfolio data loaded. Press 'r' to refresh.")
                safe_addstr(stdscr, y, width - 1, "║")
                y += 1
                safe_addstr(stdscr, y, 0, "╚" + "═" * (width - 2) + "╝")
            else:
                p_info = portfolio.get("portfolio", {})
                p_name = p_info.get("name", portfolio_slug)[:18]
                p_stats = portfolio.get("stats", {})
                tv = p_stats.get("totalValue", 0)
                tp = p_stats.get("totalProfit", 0)
                troi = p_stats.get("totalROI", 0)
                chg = p_stats.get("change24h", 0)
                chg_pct = p_stats.get("change24hPercentage", 0)

                summary = f"Portfolio: {p_name} | Val: €{tv:,.2f} | P&L: €{tp:+.2f} ({troi:+.2f}%) | 24h: €{chg:+.2f} ({chg_pct:+.2f}%)"
                safe_addstr(stdscr, y, 0, "║")
                safe_addstr(stdscr, y, 2, summary[:width - 4])
                safe_addstr(stdscr, y, width - 1, "║")
                y += 1

                p_cols = ["Item Name", "Qty", "Buy", "Now", "Total", "P&L", "ROI"]
                parrows = ["", "", "", "", "", "", ""]
                if portfolio_sort_column < len(p_cols):
                    parrows[portfolio_sort_column] = " ▲" if portfolio_sort_ascending else " ▼"

                p_name_width = max(15, width - (3 + 8 + 9 + 10 + 9 + 6 + 3 * 6 + 2 + 2))
                p_fmt = f"{{:<{p_name_width}}} | {{:>3}} | {{:>8}} | {{:>9}} | {{:>10}} | {{:>9}} | {{:>6}}"
                p_header_str = p_fmt.format(
                    p_cols[0] + parrows[0],
                    p_cols[1] + parrows[1],
                    p_cols[2] + parrows[2],
                    p_cols[3] + parrows[3],
                    p_cols[4] + parrows[4],
                    p_cols[5] + parrows[5],
                    p_cols[6] + parrows[6],
                )
                safe_addstr(stdscr, y, 0, "║")
                safe_addstr(stdscr, y, 2, p_header_str, curses.A_BOLD)
                safe_addstr(stdscr, y, width - 1, "║")
                y += 1

                safe_addstr(stdscr, y, 0, "╠" + "═" * (width - 2) + "╣")
                y += 1

                p_items = portfolio.get("items", [])
                sorted_p = sorted(p_items, key=lambda i: get_portfolio_sort_value(i, prices, portfolio_sort_column),
                                  reverse=not portfolio_sort_ascending)

                max_visible = max(1, height - 8 - banner_height)
                portfolio_scroll = max(0, min(portfolio_scroll, max(0, len(sorted_p) - max_visible)))
                visible_p = sorted_p[portfolio_scroll:portfolio_scroll + max_visible]

                for i, item in enumerate(visible_p):
                    abs_index = portfolio_scroll + i
                    is_cursor = (abs_index == portfolio_cursor)
                    row_attr = curses.A_BOLD if is_cursor else curses.A_NORMAL

                    mhn = item.get("market_hash_name", "")
                    p_stats = item.get("stats", {})
                    holdings = p_stats.get("holdings", 0) or 0
                    avg_buy = p_stats.get("avgBuyPrice", 0.0) or 0.0

                    live_price = get_live_price(mhn, prices, item.get("currentPrice", 0.0) or 0.0)

                    pl = (live_price - avg_buy) * holdings
                    roi_pct = ((live_price - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0

                    x = 2
                    safe_addstr(stdscr, y, 0, "║", row_attr)
                    safe_addstr(stdscr, y, x, f"{mhn[:p_name_width]:<{p_name_width}}", row_attr)
                    x += p_name_width + 3

                    safe_addstr(stdscr, y, x, f"{holdings:>3}", row_attr)
                    x += 3 + 3

                    safe_addstr(stdscr, y, x, f"{avg_buy:>8.2f}", row_attr)
                    x += 8 + 3

                    draw_price_col(stdscr, y, x, live_price, row_attr)
                    x += 9 + 3

                    total_val = live_price * holdings
                    safe_addstr(stdscr, y, x, f"{total_val:>10.2f}", row_attr)
                    x += 10 + 3

                    if pl > 0.01:
                        pl_color = curses.color_pair(1)
                    elif pl < -0.01:
                        pl_color = curses.color_pair(2)
                    else:
                        pl_color = curses.A_NORMAL
                    safe_addstr(stdscr, y, x, f"{pl:>+9.2f}", row_attr | pl_color)
                    x += 9 + 3

                    if roi_pct > 0.01:
                        roi_color = curses.color_pair(1)
                    elif roi_pct < -0.01:
                        roi_color = curses.color_pair(2)
                    else:
                        roi_color = curses.A_NORMAL
                    safe_addstr(stdscr, y, x, f"{roi_pct:>+5.1f}%", row_attr | roi_color)

                    safe_addstr(stdscr, y, width - 1, "║", row_attr)

                    y += 1

                safe_addstr(stdscr, y, 0, "╚" + "═" * (width - 2) + "╝")

        # ── Refresh status (top right) ──
        if loading:
            spinner_char = spinner_frames[spinner_frame]
            status_text = f"{spinner_char} Refreshing..."
        elif last_update > 0:
            elapsed = current_time - last_update
            remaining = max(0, 300 - elapsed)
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            bar_width = 12
            filled = min(bar_width, int((elapsed / 300) * bar_width))
            bar = "█" * filled + "░" * (bar_width - filled)
            status_text = f"Next {mins}:{secs:02d} [{bar}]"
        else:
            status_text = "No data loaded."

        status_x = max(0, width - len(status_text) - 2)
        safe_addstr(stdscr, 0, status_x, status_text)

        if loading:
            spinner_frame = (spinner_frame + 1) % len(spinner_frames)

        stdscr.refresh()
        k = stdscr.getch()

# ════════════════════════════════════════════════════════════════════
# ADD ITEM WIZARD
# ════════════════════════════════════════════════════════════════════

def _wizard_draw_box(stdscr, h, w, y0, x0):
    """Draw a bordered box used by wizard steps."""
    draw_centered_box(stdscr, y0, x0, h, w)


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
        for r in range(box_h):
            safe_addstr(stdscr, box_y + r, box_x, " " * box_w)

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
    for r in range(box_h):
        safe_addstr(stdscr, box_y + r, box_x, " " * box_w)
    _wizard_draw_box(stdscr, box_h, box_w, box_y, box_x)

    safe_addstr(stdscr, box_y + 1, box_x + 2, "Checking API...", curses.A_BOLD)
    stdscr.refresh()

    # Run validation (use cached prices for speed, fall back to fresh API call)
    found, result, prices_data = validate_item(item, api_key=api_key, scraper=scraper,
                                                prices_data=prices_cache)

    current_item = dict(item)  # mutable copy

    while True:
        # Clear and redraw
        for r in range(box_h):
            safe_addstr(stdscr, box_y + r, box_x, " " * box_w)
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
                for si, s in enumerate(similar[:list_h]):
                    safe_addstr(stdscr, y + si, box_x + 2, f"  {si + 1}) {s}")
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
                    api_name = similar[idx]
                    parsed = parse_suggestion_api_name(api_name)
                    # Look up prices from cached data
                    item_data = prices_data.get(api_name, {})
                    price_info = {}
                    for source in ('buff163', 'skins'):
                        src_data = item_data.get('prices', {}).get(source, {})
                        if isinstance(src_data, dict) and src_data.get('price') is not None:
                            price_info[source] = src_data['price']
                    current_item = parsed
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

        for r in range(box_h):
            safe_addstr(stdscr, box_y + r, box_x, " " * box_w)
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
        for r in range(box_h):
            safe_addstr(stdscr, box_y + r, box_x, " " * box_w)
        _wizard_draw_box(stdscr, box_h, box_w, box_y, box_x)
        safe_addstr(stdscr, box_y + 1, box_x + 2, f"Item: {weapon} | {skin}", curses.A_BOLD)
        wear_raw = curses_input_blocking(stdscr, box_y + 2, box_x + 2, box_w - 12,
                                         prompt="Wear [fn/mw/ft/ww/bs] none: ")
        wear = normalize_wear(wear_raw.strip()) if wear_raw and wear_raw.strip() else None

        # ══════════════════════════════════════════════════════
        # STEP 3: StatTrak
        # ══════════════════════════════════════════════════════
        for r in range(box_h):
            safe_addstr(stdscr, box_y + r, box_x, " " * box_w)
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
                for r in range(min(8, height - 2)):
                    safe_addstr(stdscr, box_y + r, box_x, " " * box_w)
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


if __name__ == "__main__":
    curses.wrapper(draw_menu)
