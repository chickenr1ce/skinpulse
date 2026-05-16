import curses
import json
import os
import time
import requests
from price_empire_scraper import PriceEmpireScraper, format_market_hash_name
from items import load_items as load_items_file, get_items_mtime

def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}

def draw_price_col(stdscr, y, x, price, prev_price):
    delta = None
    if prev_price is not None and price is not None:
        delta = price - prev_price

    if delta is not None and abs(delta) >= 0.01:
        price_part = f"{price:>7.2f}("
        delta_part = f"{delta:+.2f}"
        color = curses.color_pair(1) if delta > 0 else curses.color_pair(2)
        stdscr.addstr(y, x, price_part, curses.A_NORMAL)
        stdscr.addstr(y, x + len(price_part), delta_part, color)
        stdscr.addstr(y, x + len(price_part) + len(delta_part), ")", curses.A_NORMAL)
    else:
        text = f"{price:>7.2f}(  ~  )"
        stdscr.addstr(y, x, text, curses.A_NORMAL)


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
    prev_prices = {}
    loading = False
    error_message = ""
    sort_column = 0
    sort_ascending = True

    portfolio = {}
    portfolio_error = ""
    current_view = "watchlist"
    portfolio_sort_column = 0
    portfolio_sort_ascending = True

    while k != ord('q'):
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        header = "CS2 Skin Price Scraper (PriceEmpire API)"
        stdscr.addstr(0, (width - len(header)) // 2, header, curses.A_BOLD | curses.A_UNDERLINE)

        if current_view == "watchlist":
            help_text = "'q' quit | 'r' refresh | 'p' portfolio view | '1'-'4' sort"
            stdscr.addstr(height - 1, 0, help_text)
        else:
            help_text = "'q' quit | 'r' refresh | 'p' watchlist view | '1'-'7' sort"
            stdscr.addstr(height - 1, 0, help_text)

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
            if current_view == "portfolio" and portfolio_slug:
                stdscr.addstr(2, 2, "Fetching prices and portfolio...")
            else:
                stdscr.addstr(2, 2, "Fetching prices from PriceEmpire...")
            stdscr.refresh()

            prev_prices = prices
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
            elif current_view == "portfolio" and col < 7:
                if col == portfolio_sort_column:
                    portfolio_sort_ascending = not portfolio_sort_ascending
                else:
                    portfolio_sort_column = col
                    portfolio_sort_ascending = True

        new_mtime = get_items_mtime()
        if new_mtime and new_mtime != items_mtime:
            loaded = load_items_file()
            if loaded is not None:
                items_to_track = loaded
                items_mtime = new_mtime

        # ── WATCHLIST VIEW ──
        if current_view == "watchlist":
            if error_message:
                stdscr.addstr(2, 2, f"Error: {error_message[:width-10]}", curses.A_BOLD)

            y = 4
            col_headers = ["Item Name", "Buff 163", "Skins.com", "Lowest"]
            arrows = ["", "", "", ""]
            if sort_column < len(col_headers):
                arrows[sort_column] = " ▲" if sort_ascending else " ▼"

            price_width = 14
            name_width = max(20, width - (price_width * 3 + 3 * 3 + 2 + 2))

            header_fmt = f"{{:<{name_width}}} | {{:>{price_width}}} | {{:>{price_width}}} | {{:>{price_width}}}"
            header_str = header_fmt.format(
                col_headers[0] + arrows[0],
                col_headers[1] + arrows[1],
                col_headers[2] + arrows[2],
                col_headers[3] + arrows[3],
            )
            stdscr.addstr(y, 2, header_str, curses.A_REVERSE)
            y += 1

            sorted_items = sorted(items_to_track, key=lambda i: get_sort_value(i, prices, sort_column),
                                  reverse=not sort_ascending)

            for item in sorted_items:
                if y >= height - 3:
                    break

                mhn = format_market_hash_name(item)
                item_data = prices.get(mhn, {})
                prev_item_data = prev_prices.get(mhn, {})
                price_dict = item_data.get('prices', {})
                prev_price_dict = prev_item_data.get('prices', {})

                buff_price = price_dict.get('buff163', {}).get('price', 0.0) or 0.0
                skins_price = price_dict.get('skins', {}).get('price', 0.0) or 0.0
                all_provider_prices = [v.get('price', 0.0) for k, v in price_dict.items()
                                       if isinstance(v, dict) and v.get('price', 0.0) > 0]
                min_price = min(all_provider_prices) if all_provider_prices else 0.0

                prev_buff = prev_price_dict.get('buff163', {}).get('price') if prev_prices else None
                prev_skins = prev_price_dict.get('skins', {}).get('price') if prev_prices else None

                x = 2
                stdscr.addstr(y, x, f"{mhn[:name_width]:<{name_width}}")
                x += name_width + 3

                draw_price_col(stdscr, y, x, buff_price, prev_buff)
                x += price_width + 3

                draw_price_col(stdscr, y, x, skins_price, prev_skins)
                x += price_width + 3

                draw_price_col(stdscr, y, x, min_price, None)

                y += 1

        # ── PORTFOLIO VIEW ──
        else:
            if portfolio_error:
                stdscr.addstr(2, 2, f"Portfolio error: {portfolio_error[:width - 20]}", curses.A_BOLD)

            if not portfolio:
                stdscr.addstr(2, 2, "No portfolio data loaded. Press 'r' to refresh.")
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
                stdscr.addstr(2, 2, summary[:width - 4])

                y = 4
                p_cols = ["Item Name", "Qty", "Buy", "Now", "Total", "P&L", "ROI"]
                parrows = ["", "", "", "", "", "", ""]
                if portfolio_sort_column < len(p_cols):
                    parrows[portfolio_sort_column] = " ▲" if portfolio_sort_ascending else " ▼"

                p_name_width = max(15, width - (3 + 8 + 14 + 10 + 9 + 6 + 3 * 6 + 2 + 2))
                p_fmt = f"{{:<{p_name_width}}} | {{:>3}} | {{:>8}} | {{:>14}} | {{:>10}} | {{:>9}} | {{:>6}}"
                p_header_str = p_fmt.format(
                    p_cols[0] + parrows[0],
                    p_cols[1] + parrows[1],
                    p_cols[2] + parrows[2],
                    p_cols[3] + parrows[3],
                    p_cols[4] + parrows[4],
                    p_cols[5] + parrows[5],
                    p_cols[6] + parrows[6],
                )
                stdscr.addstr(y, 2, p_header_str, curses.A_REVERSE)
                y += 1

                p_items = portfolio.get("items", [])
                sorted_p = sorted(p_items, key=lambda i: get_portfolio_sort_value(i, prices, portfolio_sort_column),
                                  reverse=not portfolio_sort_ascending)

                for item in sorted_p:
                    if y >= height - 3:
                        break

                    mhn = item.get("market_hash_name", "")
                    p_stats = item.get("stats", {})
                    holdings = p_stats.get("holdings", 0) or 0
                    avg_buy = p_stats.get("avgBuyPrice", 0.0) or 0.0

                    live_price = get_live_price(mhn, prices, item.get("currentPrice", 0.0) or 0.0)

                    prev_p_entry = prev_prices.get(mhn, {})
                    prev_price_dict = prev_p_entry.get("prices", {}) if isinstance(prev_p_entry, dict) else {}
                    prev_live = prev_price_dict.get("buff163", {}).get("price") if prev_prices else None
                    if prev_live is None or prev_live <= 0:
                        prev_live = None

                    pl = (live_price - avg_buy) * holdings
                    roi_pct = ((live_price - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0

                    x = 2
                    stdscr.addstr(y, x, f"{mhn[:p_name_width]:<{p_name_width}}")
                    x += p_name_width + 3

                    stdscr.addstr(y, x, f"{holdings:>3}")
                    x += 3 + 3

                    stdscr.addstr(y, x, f"{avg_buy:>8.2f}")
                    x += 8 + 3

                    draw_price_col(stdscr, y, x, live_price, prev_live)
                    x += 14 + 3

                    total_val = live_price * holdings
                    stdscr.addstr(y, x, f"{total_val:>10.2f}")
                    x += 10 + 3

                    if pl > 0.01:
                        pl_color = curses.color_pair(1)
                    elif pl < -0.01:
                        pl_color = curses.color_pair(2)
                    else:
                        pl_color = curses.A_NORMAL
                    stdscr.addstr(y, x, f"{pl:>+9.2f}", pl_color)
                    x += 9 + 3

                    if roi_pct > 0.01:
                        roi_color = curses.color_pair(1)
                    elif roi_pct < -0.01:
                        roi_color = curses.color_pair(2)
                    else:
                        roi_color = curses.A_NORMAL
                    stdscr.addstr(y, x, f"{roi_pct:>+5.1f}%", roi_color)

                    y += 1

        if loading:
            stdscr.addstr(height - 2, 2, "Refreshing...")
        elif last_update > 0:
            time_since = int(current_time - last_update)
            stdscr.addstr(height - 2, 2, f"Last update: {time_since}s ago")
        else:
            stdscr.addstr(height - 2, 2, "No data loaded.")

        stdscr.refresh()
        k = stdscr.getch()

if __name__ == "__main__":
    curses.wrapper(draw_menu)
