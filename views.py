"""Table rendering for watchlist and portfolio views.

Contains the rendering logic extracted from tui.py's draw_menu function
to keep the main loop focused on orchestration.
"""

import curses
from items import format_market_hash_name
from wizard import safe_addstr


def draw_price_col(stdscr, y, x, price, attr=0):
    safe_addstr(stdscr, y, x, f"{price:>9.2f}", attr)


def compute_scroll_indicator(total, scroll, max_visible):
    """Build a scroll-position string like '↑ 12-17/17 ↓' or empty string."""
    clamped = max(0, min(scroll, max(0, total - max_visible)))
    if total <= max_visible:
        return ""
    first = clamped + 1
    last = min(clamped + max_visible, total)
    parts = []
    if clamped > 0:
        parts.append("↑")
    parts.append(f"{first}-{last}/{total}")
    if last < total:
        parts.append("↓")
    return " | " + " ".join(parts)


def get_sort_value(item, prices, sort_column):
    market_name = format_market_hash_name(item)
    item_data = prices.get(market_name, {})
    price_dict = item_data.get('prices', {})

    if sort_column == 0:
        return market_name.lower()
    elif sort_column == 1:
        return price_dict.get('buff163', {}).get('price', 0.0) or 0.0
    elif sort_column == 2:
        return price_dict.get('skins', {}).get('price', 0.0) or 0.0
    elif sort_column == 3:
        all_prices = [v.get('price', 0.0) for k, v in price_dict.items()
                      if isinstance(v, dict) and v.get('price', 0.0) > 0]
        return min(all_prices) if all_prices else 0.0
    return 0.0


def get_live_price(market_name, prices, fallback=0.0):
    item_data = prices.get(market_name, {})
    price_dict = item_data.get('prices', {}) if isinstance(item_data, dict) else {}
    buff = price_dict.get('buff163', {}).get('price', 0.0) or 0.0
    return buff if buff > 0 else fallback


def get_portfolio_sort_value(item, prices, sort_column):
    market_name = item.get('market_hash_name', '')
    stats = item.get('stats', {})

    if sort_column == 0:
        return market_name.lower()
    elif sort_column == 1:
        return stats.get('holdings', 0) or 0
    elif sort_column == 2:
        return stats.get('avgBuyPrice', 0.0) or 0.0
    elif sort_column in (3, 4, 5, 6):
        live_price = get_live_price(market_name, prices, item.get('currentPrice', 0.0) or 0.0)
        if sort_column == 3:
            return live_price
        holdings = stats.get('holdings', 0) or 0
        if sort_column == 4:
            return live_price * holdings
        avg_buy = stats.get('avgBuyPrice', 0.0) or 0.0
        if sort_column == 5:
            return (live_price - avg_buy) * holdings
        if sort_column == 6:
            return ((live_price - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0.0
    return 0.0


def render_watchlist(stdscr, y, width, items_to_track, prices,
                     sort_column, sort_ascending, scroll, cursor,
                     max_visible, banner_height, error_message):
    """Render the full watchlist table (header + rows + footer).

    Returns the final y position below the table. Modifies scroll/cursor
    in place via the mutable list trick — we return the clamped scroll
    and cursor as a tuple (scroll, cursor).
    """
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

    header_fmt = f"{{:<{name_width}}} | {{:<{price_width}}} | {{:<{price_width}}} | {{:<{price_width}}}"
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

    sorted_items = sorted(items_to_track,
                          key=lambda i: get_sort_value(i, prices, sort_column),
                          reverse=not sort_ascending)

    scroll = max(0, min(scroll, max(0, len(sorted_items) - max_visible)))
    visible_items = sorted_items[scroll:scroll + max_visible]

    for i, item in enumerate(visible_items):
        abs_index = scroll + i
        is_cursor = (abs_index == cursor) and items_to_track
        row_attr = curses.A_BOLD if is_cursor else curses.A_NORMAL

        market_name = format_market_hash_name(item)
        item_data = prices.get(market_name, {})
        price_dict = item_data.get('prices', {})

        buff_price = price_dict.get('buff163', {}).get('price', 0.0) or 0.0
        skins_price = price_dict.get('skins', {}).get('price', 0.0) or 0.0
        all_provider_prices = [v.get('price', 0.0) for k, v in price_dict.items()
                               if isinstance(v, dict) and v.get('price', 0.0) > 0]
        min_price = min(all_provider_prices) if all_provider_prices else 0.0

        x = 2
        safe_addstr(stdscr, y, 0, "║", row_attr)
        safe_addstr(stdscr, y, x, f"{market_name[:name_width]:<{name_width}}", row_attr)
        x += name_width + 3

        draw_price_col(stdscr, y, x, buff_price, row_attr)
        x += price_width + 3

        draw_price_col(stdscr, y, x, skins_price, row_attr)
        x += price_width + 3

        draw_price_col(stdscr, y, x, min_price, row_attr)
        safe_addstr(stdscr, y, width - 1, "║", row_attr)

        y += 1

    safe_addstr(stdscr, y, 0, "╚" + "═" * (width - 2) + "╝")

    return y, scroll, cursor


def render_portfolio(stdscr, y, width, portfolio, portfolio_slug, prices,
                     sort_column, sort_ascending, scroll, cursor,
                     max_visible, banner_height, portfolio_error):
    """Render the full portfolio table (header + rows + footer).

    Returns the final y position below the table, plus clamped (scroll, cursor).
    """
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
        return y, scroll, cursor

    portfolio_info = portfolio.get("portfolio", {})
    portfolio_name = portfolio_info.get("name", portfolio_slug)[:18]
    portfolio_stats = portfolio.get("stats", {})
    total_value = portfolio_stats.get("totalValue", 0)
    total_profit = portfolio_stats.get("totalProfit", 0)
    total_roi = portfolio_stats.get("totalROI", 0)
    change_24h = portfolio_stats.get("change24h", 0)
    change_24h_pct = portfolio_stats.get("change24hPercentage", 0)

    summary = f"Portfolio: {portfolio_name} | Val: €{total_value:,.2f} | P&L: €{total_profit:+.2f} ({total_roi:+.2f}%) | 24h: €{change_24h:+.2f} ({change_24h_pct:+.2f}%)"
    safe_addstr(stdscr, y, 0, "║")
    safe_addstr(stdscr, y, 2, summary[:width - 4])
    safe_addstr(stdscr, y, width - 1, "║")
    y += 1

    portfolio_cols = ["Item Name", "Qty", "Buy", "Now", "Total", "P&L", "ROI"]
    portfolio_arrows = ["", "", "", "", "", "", ""]
    if sort_column < len(portfolio_cols):
        portfolio_arrows[sort_column] = " ▲" if sort_ascending else " ▼"

    portfolio_name_width = max(15, width - (3 + 8 + 9 + 10 + 9 + 6 + 3 * 6 + 2 + 2))
    portfolio_fmt = f"{{:<{portfolio_name_width}}} | {{:>3}} | {{:>8}} | {{:>9}} | {{:>10}} | {{:>9}} | {{:>6}}"
    portfolio_header_str = portfolio_fmt.format(
        portfolio_cols[0] + portfolio_arrows[0],
        portfolio_cols[1] + portfolio_arrows[1],
        portfolio_cols[2] + portfolio_arrows[2],
        portfolio_cols[3] + portfolio_arrows[3],
        portfolio_cols[4] + portfolio_arrows[4],
        portfolio_cols[5] + portfolio_arrows[5],
        portfolio_cols[6] + portfolio_arrows[6],
    )
    safe_addstr(stdscr, y, 0, "║")
    safe_addstr(stdscr, y, 2, portfolio_header_str, curses.A_BOLD)
    safe_addstr(stdscr, y, width - 1, "║")
    y += 1

    safe_addstr(stdscr, y, 0, "╠" + "═" * (width - 2) + "╣")
    y += 1

    portfolio_items = portfolio.get("items", [])
    sorted_portfolio = sorted(portfolio_items,
                      key=lambda i: get_portfolio_sort_value(i, prices, sort_column),
                      reverse=not sort_ascending)

    scroll = max(0, min(scroll, max(0, len(sorted_portfolio) - max_visible)))
    visible_portfolio = sorted_portfolio[scroll:scroll + max_visible]

    for i, item in enumerate(visible_portfolio):
        abs_index = scroll + i
        is_cursor = (abs_index == cursor)
        row_attr = curses.A_BOLD if is_cursor else curses.A_NORMAL

        market_name = item.get("market_hash_name", "")
        item_stats = item.get("stats", {})
        holdings = item_stats.get("holdings", 0) or 0
        avg_buy = item_stats.get("avgBuyPrice", 0.0) or 0.0

        live_price = get_live_price(market_name, prices, item.get("currentPrice", 0.0) or 0.0)

        profit_loss = (live_price - avg_buy) * holdings
        roi_pct = ((live_price - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0

        x = 2
        safe_addstr(stdscr, y, 0, "║", row_attr)
        safe_addstr(stdscr, y, x, f"{market_name[:portfolio_name_width]:<{portfolio_name_width}}", row_attr)
        x += portfolio_name_width + 3

        safe_addstr(stdscr, y, x, f"{holdings:>3}", row_attr)
        x += 3 + 3

        safe_addstr(stdscr, y, x, f"{avg_buy:>8.2f}", row_attr)
        x += 8 + 3

        draw_price_col(stdscr, y, x, live_price, row_attr)
        x += 9 + 3

        total_val = live_price * holdings
        safe_addstr(stdscr, y, x, f"{total_val:>10.2f}", row_attr)
        x += 10 + 3

        if profit_loss > 0.01:
            profit_loss_color = curses.color_pair(1)
        elif profit_loss < -0.01:
            profit_loss_color = curses.color_pair(2)
        else:
            profit_loss_color = curses.A_NORMAL
        safe_addstr(stdscr, y, x, f"{profit_loss:>+9.2f}", row_attr | profit_loss_color)
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
    return y, scroll, cursor
