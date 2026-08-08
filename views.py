"""Table rendering for watchlist and portfolio views.

Contains the rendering logic extracted from tui.py's draw_menu function
to keep the main loop focused on orchestration.
"""

import curses
from items import format_market_hash_name
from curses_utils import safe_addstr
from constants.display import BANNER_HEIGHT


def _overhead(fixed_width_sum, n_columns):
    """Fixed space consumed by a table row: start offset 2 + all column widths
    + one 3-char separator advance after EVERY column (incl. the phantom gap
    after the last column)."""
    return 2 + fixed_width_sum + 3 * n_columns


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


def get_price(market_name, prices, source='buff163', field='price'):
    """Look up a numeric field from a source's price entry, 0.0 if missing/None."""
    item_data = prices.get(market_name, {})
    price_dict = item_data.get('prices', {}) if isinstance(item_data, dict) else {}
    entry = price_dict.get(source, {})
    if isinstance(entry, dict):
        return entry.get(field, 0.0) or 0.0
    return 0.0


def get_avg(market_name, prices, days):
    """Look up a buff163 historical average (days in {7, 30, 60, 90}), 0.0 if missing."""
    return get_price(market_name, prices, source='buff163', field=f'avg_{days}')


def get_sort_value(item, prices, sort_column):
    market_name = format_market_hash_name(item)

    if sort_column == 0:
        return market_name.lower()
    elif sort_column == 1:
        return get_price(market_name, prices)
    elif sort_column == 2:
        return get_avg(market_name, prices, 7)
    elif sort_column == 3:
        return get_avg(market_name, prices, 30)
    elif sort_column == 4:
        return get_avg(market_name, prices, 60)
    elif sort_column == 5:
        return get_avg(market_name, prices, 90)
    # Column 6 (Trend): 7d minus 90d — positive when rising, matching the
    # sparkline's green/red direction.
    return get_avg(market_name, prices, 7) - get_avg(market_name, prices, 90)


def get_live_price(market_name, prices, fallback=0.0):
    buff = get_price(market_name, prices)
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


def _render_table(stdscr, y_start, width, columns, rows, scroll, cursor,
                  max_visible, banner_height, error_message,
                  header_rows=0, render_header_cells=None):
    """Generic box-framed table renderer.

    Draws:
      - Error banner (if error_message)
      - Optional custom header rows (drawn before the column header)
      - Column header row with sort arrows
      - Separator line
      - Visible data rows with cursor highlighting
      - Bottom border

    Args:
        columns: list of dicts with keys: 'header', 'width', 'fmt', 'getter'.
                 'fmt' is a format-string like '<20' or '>9' or '>+9.2f' etc.
                 'getter' is a callable(row) returning a (str_value, attr) tuple.
        rows: list of opaque row objects.
        header_rows: number of custom header rows to reserve above the column header.
        render_header_cells: callable(stdscr, y, x) to draw the custom header cells,
                             or None. Called for each header row 0..header_rows-1.
    Returns:
        y_after — the row after the bottom border.
    """
    if error_message:
        safe_addstr(stdscr, banner_height, 2, f"Error: {error_message[:width - 10]}", curses.A_BOLD)

    # The error banner occupies banner_height, so the table starts one row
    # below it — otherwise the top border overwrites the banner text.
    y = (BANNER_HEIGHT if banner_height else 0) + header_rows + (1 if error_message else 0)
    # ── Top border ──
    safe_addstr(stdscr, y, 0, "╔" + "═" * (width - 2) + "╗")
    y += 1

    # ── Custom header rows (e.g. portfolio summary) ──
    if header_rows > 0 and render_header_cells:
        for h in range(header_rows):
            safe_addstr(stdscr, y, 0, "║")
            render_header_cells(stdscr, y, h)
            safe_addstr(stdscr, y, width - 1, "║")
            y += 1

    # ── Column header ──
    sep = " │ "
    header_parts = []
    for col in columns:
        hdr = col['header']
        align = col['fmt'][0] if col['fmt'] and col['fmt'][0] in '<>^' else '<'
        header_parts.append(f"{hdr:{align}{col['width']}}")
    header_str = sep.join(header_parts)
    safe_addstr(stdscr, y, 0, "║")
    safe_addstr(stdscr, y, 2, header_str, curses.A_BOLD)
    safe_addstr(stdscr, y, width - 1, "║")
    y += 1

    # ── Header/body separator ──
    safe_addstr(stdscr, y, 0, "╠" + "═" * (width - 2) + "╣")
    y += 1

    # ── Data rows ──
    scroll = max(0, min(scroll, max(0, len(rows) - max_visible)))
    visible_rows = rows[scroll:scroll + max_visible]

    for i, row in enumerate(visible_rows):
        abs_index = scroll + i
        is_cursor = (abs_index == cursor) and rows
        row_attr = curses.A_BOLD if is_cursor else curses.A_NORMAL

        safe_addstr(stdscr, y, 0, "║", row_attr)
        x = 2
        for col in columns:
            val_str, val_attr = col['getter'](row)
            formatted = f"{val_str:{col['fmt']}}"
            safe_addstr(stdscr, y, x, formatted[:col['width']], row_attr | val_attr)
            x += col['width'] + len(" │ ")
        safe_addstr(stdscr, y, width - 1, "║", row_attr)
        y += 1

    # ── Bottom border ──
    safe_addstr(stdscr, y, 0, "╚" + "═" * (width - 2) + "╝")

    return y


def render_watchlist(stdscr, y, width, items_to_track, prices,
                     sort_column, sort_ascending, scroll, cursor,
                     max_visible, banner_height, error_message):
    """Render the full watchlist table."""
    price_width = 8
    trend_width = 5
    # Fixed overhead: start offset 2 + one 3-char separator after every column.
    name_width = max(20, width - _overhead(5 * price_width + trend_width, 7))

    col_headers = ["Item Name", "Buff163", "7d Avg", "30d Avg", "60d Avg", "90d Avg", "Trend"]
    arrows = [""] * 7
    if sort_column < len(col_headers):
        arrows[sort_column] = " ▲" if sort_ascending else " ▼"

    columns = [
        {"header": col_headers[0] + arrows[0], "width": name_width, "fmt": f"<{name_width}",
         "getter": lambda row: (format_market_hash_name(row), 0)},
        {"header": col_headers[1] + arrows[1], "width": price_width, "fmt": f">{price_width}.2f",
         "getter": lambda row: (_row_buff_price(row, prices), 0)},
        {"header": col_headers[2] + arrows[2], "width": price_width, "fmt": f">{price_width}.2f",
         "getter": lambda row: (_row_avg_price(row, prices, 7), _avg_color(row, prices, 7))},
        {"header": col_headers[3] + arrows[3], "width": price_width, "fmt": f">{price_width}.2f",
         "getter": lambda row: (_row_avg_price(row, prices, 30), _avg_color(row, prices, 30))},
        {"header": col_headers[4] + arrows[4], "width": price_width, "fmt": f">{price_width}.2f",
         "getter": lambda row: (_row_avg_price(row, prices, 60), _avg_color(row, prices, 60))},
        {"header": col_headers[5] + arrows[5], "width": price_width, "fmt": f">{price_width}.2f",
         "getter": lambda row: (_row_avg_price(row, prices, 90), _avg_color(row, prices, 90))},
        {"header": col_headers[6] + arrows[6], "width": trend_width, "fmt": f"^{trend_width}",
         "getter": lambda row: _render_sparkline(row, prices)},
    ]

    sorted_rows = sorted(items_to_track,
                         key=lambda i: get_sort_value(i, prices, sort_column),
                         reverse=not sort_ascending)

    _render_table(stdscr, y, width, columns, sorted_rows, scroll, cursor,
                  max_visible, banner_height, error_message)


def _row_buff_price(row, prices):
    return get_price(format_market_hash_name(row), prices)


def _avg_color(row, prices, days):
    """Return curses color_pair for an avg vs current buff163 price.
    Green (1) when avg < current (price rising), red (2) when avg > current (falling)."""
    avg = _row_avg_price(row, prices, days)
    current = _row_buff_price(row, prices)
    if avg <= 0 or current <= 0:
        return 0
    if current > avg:
        return curses.color_pair(1)
    elif current < avg:
        return curses.color_pair(2)
    return 0


def _row_avg_price(row, prices, days):
    """Extract a historical average price (7/30/60/90 days) for an item."""
    return get_avg(format_market_hash_name(row), prices, days)


def _render_sparkline(row, prices):
    """Build a 4-char Unicode sparkline from 90d→60d→30d→7d averages.
    Returns (sparkline_str, color_attr)."""
    periods = [90, 60, 30, 7]
    avgs = [_row_avg_price(row, prices, p) for p in periods]

    valid = [(i, v) for i, v in enumerate(avgs) if v and v > 0]
    if len(valid) < 2:
        return ("    ", 0)

    chars = " ▁▂▃▄▅▆▇█"
    min_v = min(v for _, v in valid)
    max_v = max(v for _, v in valid)

    if max_v == min_v:
        result = "▄▄▄▄"
    else:
        result = ""
        for i, v in enumerate(avgs):
            if v and v > 0:
                idx = int((v - min_v) / (max_v - min_v) * 7) + 1
                result += chars[idx]
            else:
                result += " "

    # Color: green if 7d > 90d (uptrend), red if down
    first_valid = next((v for v in avgs if v and v > 0), 0)
    last_valid = next((v for v in reversed(avgs) if v and v > 0), 0)
    if last_valid > first_valid:
        color = curses.color_pair(1)
    elif last_valid < first_valid:
        color = curses.color_pair(2)
    else:
        color = 0

    return (result, color)


def render_portfolio(stdscr, y, width, portfolio, portfolio_slug, prices,
                     sort_column, sort_ascending, scroll, cursor,
                     max_visible, banner_height, portfolio_error):
    """Render the full portfolio table."""
    y_after = BANNER_HEIGHT if banner_height else 0

    if not portfolio:
        safe_addstr(stdscr, y_after, 0, "╔" + "═" * (width - 2) + "╗")
        safe_addstr(stdscr, y_after + 1, 0, "║")
        safe_addstr(stdscr, y_after + 1, 2, "No portfolio data loaded. Press 'r' to refresh.")
        safe_addstr(stdscr, y_after + 1, width - 1, "║")
        safe_addstr(stdscr, y_after + 2, 0, "╚" + "═" * (width - 2) + "╝")
        return

    portfolio_info = portfolio.get("portfolio", {})
    portfolio_name = portfolio_info.get("name", portfolio_slug)[:18]
    portfolio_stats = portfolio.get("stats", {})
    total_value = portfolio_stats.get("totalValue", 0)
    total_profit = portfolio_stats.get("totalProfit", 0)
    total_roi = portfolio_stats.get("totalROI", 0)
    change_24h = portfolio_stats.get("change24h", 0)
    change_24h_pct = portfolio_stats.get("change24hPercentage", 0)

    summary = f"Portfolio: {portfolio_name} | Val: €{total_value:,.2f} | P&L: €{total_profit:+.2f} ({total_roi:+.2f}%) | 24h: €{change_24h:+.2f} ({change_24h_pct:+.2f}%)"

    def _render_portfolio_header(stdscr, row_y, h_idx):
        safe_addstr(stdscr, row_y, 2, summary[:width - 4])

    portfolio_cols = ["Item Name", "Qty", "Buy", "Now", "Total", "P&L", "ROI"]
    portfolio_arrows = ["", "", "", "", "", "", ""]
    if sort_column < len(portfolio_cols):
        portfolio_arrows[sort_column] = " ▲" if sort_ascending else " ▼"

    # Fixed overhead: start offset 2 + one 3-char separator after every column.
    name_w = max(15, width - _overhead(45, 7))
    columns = [
        {"header": portfolio_cols[0] + portfolio_arrows[0], "width": name_w, "fmt": f"<{name_w}",
         "getter": lambda row: (row.get("market_hash_name", ""), 0)},
        {"header": portfolio_cols[1] + portfolio_arrows[1], "width": 3, "fmt": ">3",
         "getter": lambda row: (str(_pf_holdings(row)), 0)},
        {"header": portfolio_cols[2] + portfolio_arrows[2], "width": 8, "fmt": ">8.2f",
         "getter": lambda row: (_pf_avg_buy(row), 0)},
        {"header": portfolio_cols[3] + portfolio_arrows[3], "width": 9, "fmt": ">9.2f",
         "getter": lambda row: (_pf_live_price(row, prices), 0)},
        {"header": portfolio_cols[4] + portfolio_arrows[4], "width": 10, "fmt": ">10.2f",
         "getter": lambda row: (_pf_total_val(row, prices), 0)},
        {"header": portfolio_cols[5] + portfolio_arrows[5], "width": 9, "fmt": ">+9.2f",
         "getter": lambda row: _pf_pl(row, prices)},
        {"header": portfolio_cols[6] + portfolio_arrows[6], "width": 6, "fmt": ">+5.1f",
         "getter": lambda row: _pf_roi(row, prices)},
    ]

    sorted_rows = sorted(portfolio.get("items", []),
                         key=lambda i: get_portfolio_sort_value(i, prices, sort_column),
                         reverse=not sort_ascending)

    _render_table(stdscr, y, width, columns, sorted_rows, scroll, cursor,
                  max_visible, banner_height, portfolio_error,
                  header_rows=1, render_header_cells=_render_portfolio_header)


# ── Portfolio helper accessors ──

def _pf_holdings(row):
    return (row.get("stats", {}).get("holdings", 0) or 0)


def _pf_avg_buy(row):
    return row.get("stats", {}).get("avgBuyPrice", 0.0) or 0.0


def _pf_live_price(row, prices):
    market_name = row.get("market_hash_name", "")
    return get_live_price(market_name, prices, row.get("currentPrice", 0.0) or 0.0)


def _pf_total_val(row, prices):
    live = _pf_live_price(row, prices)
    return live * _pf_holdings(row)


def _pf_pl(row, prices):
    live = _pf_live_price(row, prices)
    holdings = _pf_holdings(row)
    avg_buy = _pf_avg_buy(row)
    profit = (live - avg_buy) * holdings
    color = curses.color_pair(1) if profit > 0.01 else (curses.color_pair(2) if profit < -0.01 else 0)
    return (profit, color)


def _pf_roi(row, prices):
    live = _pf_live_price(row, prices)
    avg_buy = _pf_avg_buy(row)
    roi_pct = ((live - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0
    color = curses.color_pair(1) if roi_pct > 0.01 else (curses.color_pair(2) if roi_pct < -0.01 else 0)
    return (roi_pct, color)
