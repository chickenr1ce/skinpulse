import curses
import threading
import time
import requests
from price_empire_scraper import PriceEmpireScraper
from items import (
    load_items, save_items, get_items_mtime,
    format_item_line,
)
from constants.display import MIN_HEIGHT, MIN_WIDTH
from utils import load_config
from wizard import safe_addstr, confirm_dialog, run_add_wizard
from views import (
    compute_scroll_indicator, render_watchlist, render_portfolio,
    get_sort_value, get_portfolio_sort_value, get_live_price,
)


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
    api_key = config_data.get("api_key", "YOUR_API_KEY")
    portfolio_slug = config_data.get("portfolio_slug", "")

    items_mtime = get_items_mtime()
    items_to_track = load_items() or []

    scraper = PriceEmpireScraper(api_key)

    last_update = 0
    prices = {}
    loading = False
    error_message = ""
    sort_column = 1
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

    # Async fetch state
    price_thread = None
    price_data = None
    portfolio_thread = None
    portfolio_data = None

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
            max_banner_width = max(len(line) for line in banner_art)
            for i, line in enumerate(banner_art):
                x = (width - max_banner_width) // 2
                safe_addstr(stdscr, i, x, line, curses.A_BOLD)

        # ── Scroll indicator ──
        max_visible = max(1, height - 8 - banner_height)
        if current_view == "watchlist":
            scroll_indicator = compute_scroll_indicator(len(items_to_track), watchlist_scroll, max_visible)
        else:
            scroll_indicator = compute_scroll_indicator(len(portfolio.get("items", [])), portfolio_scroll, max_visible)

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

        if should_refresh and not loading:
            loading = True

            # Instant visual feedback (first frame; thread updates will animate)
            spinner_char = spinner_frames[spinner_frame]
            load_y = banner_height
            if current_view == "portfolio" and portfolio_slug:
                safe_addstr(stdscr, load_y, 2, f"{spinner_char} Fetching prices and portfolio...")
            else:
                safe_addstr(stdscr, load_y, 2, f"{spinner_char} Fetching prices from PriceEmpire...")
            stdscr.refresh()

            # Start async price fetch
            price_data = None
            def _fetch_prices():
                nonlocal price_data
                price_data = scraper.get_prices()
            price_thread = threading.Thread(target=_fetch_prices, daemon=True)
            price_thread.start()

            # Start async portfolio fetch if needed
            if portfolio_slug:
                portfolio_data = None
                def _fetch_portfolio():
                    nonlocal portfolio_data
                    portfolio_data = scraper.get_portfolio(portfolio_slug)
                portfolio_thread = threading.Thread(target=_fetch_portfolio, daemon=True)
                portfolio_thread.start()

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
                name_str = format_item_line(selected)
                if confirm_dialog(stdscr, f'Remove "{name_str}"?'):
                    items_to_track.remove(selected)
                    save_items(items_to_track)
                    watchlist_cursor = min(watchlist_cursor, max(0, len(items_to_track) - 1))
                    should_refresh = True

        # ── Add item wizard ──
        if k == ord('a') and current_view == "watchlist":
            new_item = run_add_wizard(stdscr, scraper, api_key, prices)
            if new_item is not None:
                items_to_track.append(new_item)
                save_items(items_to_track)
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
            portfolio_len = len(portfolio.get("items", []))
            if portfolio_cursor < portfolio_scroll:
                portfolio_scroll = portfolio_cursor
            elif portfolio_cursor >= portfolio_scroll + max_visible and portfolio_len > 0:
                portfolio_scroll = portfolio_cursor - max_visible + 1

        # ── External file change detection ──
        new_mtime = get_items_mtime()
        if new_mtime and new_mtime != items_mtime:
            loaded = load_items()
            if loaded is not None:
                items_to_track = loaded
                items_mtime = new_mtime
                watchlist_scroll = 0
                watchlist_cursor = 0

        # ── Async fetch completion check ──
        if loading:
            # Price fetch done?
            if price_thread and not price_thread.is_alive() and price_data is not None:
                api_response = price_data
                price_data = None
                price_thread = None
                last_update = time.time()
                if isinstance(api_response, dict) and "error" in api_response:
                    error_message = api_response["error"]
                else:
                    prices = api_response
                    error_message = ""

            # Portfolio fetch done?
            if portfolio_slug and portfolio_thread and not portfolio_thread.is_alive() and portfolio_data is not None:
                portfolio_response = portfolio_data
                portfolio_data = None
                portfolio_thread = None
                if isinstance(portfolio_response, dict) and "error" in portfolio_response:
                    portfolio_error = portfolio_response["error"]
                elif isinstance(portfolio_response, dict):
                    portfolio = portfolio_response
                    portfolio_error = ""

            # Both fetches complete → clear loading state
            if (price_thread is None) and (not portfolio_slug or portfolio_thread is None):
                loading = False

        # ── WATCHLIST VIEW ──
        if current_view == "watchlist":
            if loading:
                y = 6 if banner_height else 0
                msg = f"{spinner_frames[spinner_frame]} Fetching prices from PriceEmpire..."
                safe_addstr(stdscr, y, 2, msg[:width-4])
            else:
                render_watchlist(stdscr, 0, width, items_to_track, prices,
                                sort_column, sort_ascending, watchlist_scroll,
                                watchlist_cursor, max_visible, banner_height,
                                error_message)

        # ── PORTFOLIO VIEW ──
        else:
            if loading:
                y = 6 if banner_height else 0
                msg = f"{spinner_frames[spinner_frame]} Fetching prices and portfolio..."
                safe_addstr(stdscr, y, 2, msg[:width-4])
            else:
                render_portfolio(stdscr, 0, width, portfolio, portfolio_slug,
                                prices, portfolio_sort_column,
                                portfolio_sort_ascending, portfolio_scroll,
                                portfolio_cursor, max_visible, banner_height,
                                portfolio_error)

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

if __name__ == "__main__":
    curses.wrapper(draw_menu)
