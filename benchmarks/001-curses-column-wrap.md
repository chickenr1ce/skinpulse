# Benchmark 001: Fix Curses Column Wrapping at Minimum Terminal Width

## Problem Statement

When the terminal window is resized to near the minimum allowed width, the numbers
from the **90d Avg** column wrap around to the start of the next row and appear in
front of the item name on the following line.

The TUI defines a minimum terminal width (`MIN_WIDTH`) below which it refuses to
render. But at that minimum width, column wrapping still occurs — meaning the
minimum is set too low, and/or the column-width formulas are incorrect.

## Reproduction

1. Run the TUI: `python3 tui.py`
2. Resize the terminal to approximately **72 columns** wide (the current `MIN_WIDTH`).
3. Observe: 90d Avg price values appear at the start of the next row, overlapping
   the item name column.

### Requirements

- Python 3 with `requests` installed (`pip install requests`)
- A `config.json` file with a valid PriceEmpire API key (copy from `config.json.example`)

## Codebase

### Option A: Git checkout (recommended for coding agents)

```bash
git clone <repo-url>
git checkout benchmark-001-curses-column-wrap
```

All line numbers in this document refer to the state at this tag.

### Option B: Inline buggy code

The relevant buggy files are reproduced below with line numbers. The full codebase
contains additional files (`tui.py`, `items.py`, `price_empire_scraper.py`, etc.),
but the bug is confined to the files shown here.

---

#### `constants/display.py`

```python
# Minimum terminal dimensions before the TUI shows a "too small" message.
MIN_HEIGHT = 10
MIN_WIDTH = 72
```

---

#### `views.py` — the core rendering engine

```python
"""Table rendering for watchlist and portfolio views.

Contains the rendering logic extracted from tui.py's draw_menu function
to keep the main loop focused on orchestration.
"""

import curses
from items import format_market_hash_name
from curses_utils import safe_addstr



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
    price_dict = item_data.get('prices', {}) if isinstance(item_data, dict) else {}

    if sort_column == 0:
        return market_name.lower()
    elif sort_column == 1:
        return price_dict.get('buff163', {}).get('price', 0.0) or 0.0
    elif sort_column == 2:
        return (price_dict.get('buff163', {}).get('avg_7', 0.0) or 0.0)
    elif sort_column == 3:
        return (price_dict.get('buff163', {}).get('avg_30', 0.0) or 0.0)
    elif sort_column == 4:
        return (price_dict.get('buff163', {}).get('avg_60', 0.0) or 0.0)
    elif sort_column == 5:
        return (price_dict.get('buff163', {}).get('avg_90', 0.0) or 0.0)
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
        (y_after, clamped_scroll, clamped_cursor)
    """
    if error_message:
        safe_addstr(stdscr, banner_height, 2, f"Error: {error_message[:width - 10]}", curses.A_BOLD)

    y = (6 if banner_height else 0) + header_rows
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
            safe_addstr(stdscr, y, x, f"{val_str:{col['fmt']}}", row_attr | val_attr)
            x += col['width'] + len(" │ ")
        safe_addstr(stdscr, y, width - 1, "║", row_attr)
        y += 1

    # ── Bottom border ──
    safe_addstr(stdscr, y, 0, "╚" + "═" * (width - 2) + "╝")

    return y, scroll, cursor


def render_watchlist(stdscr, y, width, items_to_track, prices,
                     sort_column, sort_ascending, scroll, cursor,
                     max_visible, banner_height, error_message):
    """Render the full watchlist table."""
    price_width = 8
    trend_width = 5
    name_width = max(20, width - (price_width * 5 + trend_width + len(" │ ") * 6 + 4))

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
         "getter": lambda row: (_row_avg_price(row, prices, '7d'), _avg_color(row, prices, '7d'))},
        {"header": col_headers[3] + arrows[3], "width": price_width, "fmt": f">{price_width}.2f",
         "getter": lambda row: (_row_avg_price(row, prices, '30d'), _avg_color(row, prices, '30d'))},
        {"header": col_headers[4] + arrows[4], "width": price_width, "fmt": f">{price_width}.2f",
         "getter": lambda row: (_row_avg_price(row, prices, '60d'), _avg_color(row, prices, '60d'))},
        {"header": col_headers[5] + arrows[5], "width": price_width, "fmt": f">{price_width}.2f",
         "getter": lambda row: (_row_avg_price(row, prices, '90d'), _avg_color(row, prices, '90d'))},
        {"header": col_headers[6] + arrows[6], "width": trend_width, "fmt": f"^{trend_width}",
         "getter": lambda row: _render_sparkline(row, prices)},
    ]

    sorted_rows = sorted(items_to_track,
                         key=lambda i: get_sort_value(i, prices, sort_column),
                         reverse=not sort_ascending)

    return _render_table(stdscr, y, width, columns, sorted_rows, scroll, cursor,
                         max_visible, banner_height, error_message)


def _row_buff_price(row, prices):
    item_name = format_market_hash_name(row)
    item_data = prices.get(item_name, {})
    return item_data.get('prices', {}).get('buff163', {}).get('price', 0.0) or 0.0


def _avg_color(row, prices, period):
    """Return curses color_pair for an avg vs current buff163 price.
    Green (1) when avg < current (price rising), red (2) when avg > current (falling)."""
    avg = _row_avg_price(row, prices, period)
    current = _row_buff_price(row, prices)
    if avg <= 0 or current <= 0:
        return 0
    if current > avg:
        return curses.color_pair(1)
    elif current < avg:
        return curses.color_pair(2)
    return 0


def _row_avg_price(row, prices, period):
    """Extract a historical average price (7d/30d/60d/90d) for an item."""
    item_name = format_market_hash_name(row)
    item_data = prices.get(item_name, {})
    price_dict = item_data.get('prices', {}) if isinstance(item_data, dict) else {}
    # Averages live on the buff163 price entry
    buff_entry = price_dict.get('buff163', {})
    if isinstance(buff_entry, dict):
        return buff_entry.get(f'avg_{period.replace("d","")}', 0.0) or 0.0
    return 0.0


def _render_sparkline(row, prices):
    """Build a 4-char Unicode sparkline from 90d→60d→30d→7d averages.
    Returns (sparkline_str, color_attr)."""
    periods = ['90d', '60d', '30d', '7d']
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
    if portfolio_error:
        safe_addstr(stdscr, banner_height, 2, f"Portfolio error: {portfolio_error[:width - 20]}", curses.A_BOLD)

    y_after = 6 if banner_height else 0

    if not portfolio:
        safe_addstr(stdscr, y_after, 0, "╔" + "═" * (width - 2) + "╗")
        safe_addstr(stdscr, y_after + 1, 0, "║")
        safe_addstr(stdscr, y_after + 1, 2, "No portfolio data loaded. Press 'r' to refresh.")
        safe_addstr(stdscr, y_after + 1, width - 1, "║")
        safe_addstr(stdscr, y_after + 2, 0, "╚" + "═" * (width - 2) + "╝")
        return y_after + 2, scroll, cursor

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

    name_w = max(15, width - (3 + 8 + 9 + 10 + 9 + 6 + len(" │ ") * 6 + 4))
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

    return _render_table(stdscr, y, width, columns, sorted_rows, scroll, cursor,
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
```

---

## Architecture Note

All curses writes use `safe_addstr(stdscr, y, x, text)` from `curses_utils.py`, which
is a thin wrapper around `stdscr.addstr()` that silently catches `curses.error` for
out-of-bounds positions:

```python
def safe_addstr(stdscr, y, x, text, attr=0):
    """Add string to screen, silently ignoring curses.error if coords are out of bounds."""
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass
```

This means overflow characters beyond the terminal width are silently dropped — there
is no visible crash or error when rendering overflows.

## Task

Find the root cause of the column wrapping bug and fix it.

### Constraints

- The fix must be minimal — change only what's necessary.
- After the fix, no column should wrap at any terminal width ≥ `MIN_WIDTH`.
- The fix must work for **both** the watchlist view (`render_watchlist`) and the
  portfolio view (`render_portfolio`) — they share the same `_render_table` render loop.

### Files that need changes

Based on the code above, the bug is in 3 locations across 2 files:

| File | What's wrong |
|---|---|
| `constants/display.py` | `MIN_WIDTH = 72` is too small |
| `views.py` line ~168 | `name_width` formula for watchlist |
| `views.py` line ~306 | `name_w` formula for portfolio |

---

## Hints

<details>
<summary><b>Hint 1</b> — Count the separators</summary>

In the `_render_table` data row loop (line ~148-152), `x` advances by
`col['width'] + len(" │ ")` after **every** column, including the last one.
How many `" │ "` separators appear in a 7-column row? How many does each
formula account for?

</details>

<details>
<summary><b>Hint 2</b> — Math it out at MIN_WIDTH=72</summary>

At `MIN_WIDTH=72` with `name_width = max(20, 72 - 67) = 20`:

| Column | x start | width | Characters occupy |
|---|---|---|---|
| Name (w=20) | 2 | 20 | 2-21 |
| `" │ "` | | | 22-24 |
| Buff163 (w=8) | 25 | 8 | 25-32 |
| `" │ "` | | | 33-35 |
| 7d Avg (w=8) | 36 | 8 | 36-43 |
| `" │ "` | | | 44-46 |
| 30d Avg (w=8) | 47 | 8 | 47-54 |
| `" │ "` | | | 55-57 |
| 60d Avg (w=8) | 58 | 8 | 58-65 |
| `" │ "` | | | 66-68 |
| **90d Avg (w=8)** | **69** | **8** | **69-76** ← wraps at col 72! |
| `" │ "` | | | 77-79 |
| Trend (w=5) | 80 | 5 | 80-84 |
| closing `║` | 72 | 1 | (width - 1 = 71) |

The 90d column writes at positions 69-76, but the terminal is only 72 columns wide.
Characters 72-76 wrap to the next row.

</details>

<details>
<summary><b>Hint 3</b> — The correct overhead</summary>

The data row consumes:
```
start_x ("║ ")       = 2
7 separators × 3     = 21
5 price cols × 8     = 40
1 trend col × 5      =  5
name_width           = variable
                        ───
Total                 = name_width + 68
```

For the row to fit without wrapping: `name_width + 68 ≤ width`.

The closing `║` sits at `width - 1`, so we also need `name_width + 68 - 3 ≤ width - 1`
(accounting for the trailing separator that isn't written), i.e., `name_width + 65 ≤ width - 1`,
i.e., `name_width + 66 ≤ width`. With `name_width ≥ 20`, `width ≥ 86`. Rounding up for
header text (which uses `sep.join()` with only 6 separators): `MIN_WIDTH ≥ 88`.

</details>

---

## Evaluation

### Automated grading

Run the grading script against the fixed codebase:

```bash
python3 benchmarks/grade_001.py
```

All checks must pass.

### Manual rubric

| Criterion | Pass condition |
|---|---|
| `MIN_WIDTH` | ≥ 88 |
| Watchlist formula | Uses 7 separators + 2, not 6 separators + 4 |
| Portfolio formula | Same correction |
| Math explanation | Shows that at `MIN_WIDTH`, `name_width + overhead ≤ width` |
| Both views fixed | Portfolio fix mirrors watchlist fix |

### Expected changes (approximate)

The fix should be roughly 3 lines changed across 2 files:

1. `constants/display.py`: `MIN_WIDTH = 72` → `MIN_WIDTH = 88`
2. `views.py` watchlist formula: `len(" │ ") * 6 + 4` → `7 * len(" │ ") + 2`
3. `views.py` portfolio formula: same change
