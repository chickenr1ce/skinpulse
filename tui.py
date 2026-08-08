import curses
import threading
import time
from price_empire_scraper import PriceEmpireScraper
from items import (
    load_items, save_items, get_items_mtime,
    format_item_line,
)
from constants.display import MIN_HEIGHT, MIN_WIDTH, BANNER_HEIGHT, REFRESH_INTERVAL
from utils import load_config
from wizard import run_add_wizard
from curses_utils import safe_addstr, confirm_dialog
from views import (
    compute_scroll_indicator, render_watchlist, render_portfolio,
    get_sort_value,
)

from dataclasses import dataclass


@dataclass
class ViewState:
    scroll: int = 0
    cursor: int = 0
    sort_column: int = 0
    sort_ascending: bool = True


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
    api_key = config_data.get("api_key", "")
    portfolio_slug = config_data.get("portfolio_slug", "")

    items_mtime = get_items_mtime()
    items_to_track = load_items() or []

    scraper = PriceEmpireScraper(api_key)

    last_update = 0
    prices = {}
    loading = False
    error_message = "" if api_key else (
        "No API key in config.json — copy config.json.example to config.json"
    )
    views = {
        "watchlist": ViewState(sort_column=1),
        "portfolio": ViewState(),
    }

    portfolio = {}
    portfolio_error = ""
    current_view = "watchlist"

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
        banner_height = BANNER_HEIGHT if height >= 20 else 0
        content_rows = max(1, height - 8 - banner_height)

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
        max_visible = content_rows
        if current_view == "watchlist":
            scroll_indicator = compute_scroll_indicator(len(items_to_track), views["watchlist"].scroll, max_visible)
        else:
            scroll_indicator = compute_scroll_indicator(len(portfolio.get("items", [])), views["portfolio"].scroll, max_visible)

        if current_view == "watchlist":
            help_text = ("'q' quit | 'r' ref | 'p' port | 'a' add | 'd' del | "
                         "↑↓ nav | '1'-'7' sort | ^D/^U sc | g/G top/bot")
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
        elif current_time - last_update > REFRESH_INTERVAL:
            should_refresh = True

        if should_refresh and not loading and api_key:
            loading = True

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
            vs = views[current_view]
            if col == vs.sort_column:
                vs.sort_ascending = not vs.sort_ascending
            else:
                vs.sort_column = col
                vs.sort_ascending = True
            vs.scroll = 0
            vs.cursor = 0

        # ── Cursor navigation ──
        if k == curses.KEY_UP:
            views[current_view].cursor = max(0, views[current_view].cursor - 1)
        elif k == curses.KEY_DOWN:
            max_idx = max(0, len(items_to_track) - 1) if current_view == "watchlist" else max(0, len(portfolio.get("items", [])) - 1)
            views[current_view].cursor = min(max_idx, views[current_view].cursor + 1)

        # ── Delete selected item ──
        if k == ord('d') and current_view == "watchlist" and items_to_track:
            sorted_items = sorted(
                items_to_track,
                key=lambda i: get_sort_value(i, prices, views["watchlist"].sort_column),
                reverse=not views["watchlist"].sort_ascending,
            )
            if 0 <= views["watchlist"].cursor < len(sorted_items):
                selected = sorted_items[views["watchlist"].cursor]
                name_str = format_item_line(selected)
                if confirm_dialog(stdscr, f'Remove "{name_str}"?'):
                    items_to_track.remove(selected)
                    save_items(items_to_track)
                    views["watchlist"].cursor = min(views["watchlist"].cursor, max(0, len(items_to_track) - 1))
                    should_refresh = True

        # ── Add item wizard ──
        if k == ord('a') and current_view == "watchlist":
            new_item = run_add_wizard(stdscr, scraper, api_key, prices)
            if new_item is not None:
                items_to_track.append(new_item)
                save_items(items_to_track)
                views["watchlist"].cursor = len(items_to_track) - 1
                views["watchlist"].scroll = 0
                should_refresh = True

        # ── Scrolling ──
        vs = views[current_view]
        if k == curses.KEY_PPAGE:  # PgUp
            vs.scroll -= max(1, content_rows)
        elif k == curses.KEY_NPAGE:  # PgDn
            vs.scroll += max(1, content_rows)
        elif k == 21:  # Ctrl-U
            vs.scroll -= max(1, content_rows // 2)
        elif k == 4:  # Ctrl-D
            vs.scroll += max(1, content_rows // 2)
        elif k == ord('g'):
            vs.scroll = 0
            vs.cursor = 0
        elif k == ord('G'):
            data_len = len(items_to_track) if current_view == "watchlist" else len(portfolio.get("items", []))
            vs.scroll = data_len
            vs.cursor = max(0, data_len - 1)

        # ── Auto-scroll cursor into view ──
        vs = views[current_view]
        data_len = len(items_to_track) if current_view == "watchlist" else len(portfolio.get("items", []))
        if vs.cursor < vs.scroll:
            vs.scroll = vs.cursor
        elif vs.cursor >= vs.scroll + content_rows and data_len > 0:
            vs.scroll = vs.cursor - content_rows + 1

        # ── External file change detection ──
        new_mtime = get_items_mtime()
        if new_mtime and new_mtime != items_mtime:
            loaded = load_items()
            if loaded is not None:
                items_to_track = loaded
                items_mtime = new_mtime
                views["watchlist"].scroll = 0
                views["watchlist"].cursor = 0

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
            vs = views["watchlist"]
            render_watchlist(stdscr, 0, width, items_to_track, prices,
                            vs.sort_column, vs.sort_ascending, vs.scroll,
                            vs.cursor, max_visible, banner_height,
                            error_message)

        # ── PORTFOLIO VIEW ──
        else:
            vs = views["portfolio"]
            render_portfolio(stdscr, 0, width, portfolio, portfolio_slug,
                            prices, vs.sort_column,
                            vs.sort_ascending, vs.scroll,
                            vs.cursor, max_visible, banner_height,
                            portfolio_error)

        # ── Refresh status (top right) ──
        if loading:
            spinner_char = spinner_frames[spinner_frame]
            status_text = f"{spinner_char} Refreshing..."
        elif last_update > 0:
            elapsed = current_time - last_update
            remaining = max(0, REFRESH_INTERVAL - elapsed)
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            bar_width = 12
            filled = min(bar_width, int((elapsed / REFRESH_INTERVAL) * bar_width))
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
