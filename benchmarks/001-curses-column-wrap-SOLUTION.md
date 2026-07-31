# Solution: Benchmark 001 — Curses Column Wrapping

> **This file is for graders.** Do not share with benchmark participants.

## Root Cause

### Off-by-one in the column-width formulas

The `_render_table` data row loop advances `x` after **every** column, including
the last one:

```python
x = 2                               # after "║ "
for col in columns:
    safe_addstr(stdscr, y, x, ...)
    x += col['width'] + len(" │ ")   # +3 after EVERY column, 7 times
safe_addstr(stdscr, y, width - 1, "║")
```

This produces **7 separator advances** (one between each pair of 7 columns, plus
the trailing one after the last column).

But both width formulas only account for **6 separators + an arbitrary 4**:

```python
# Line 168 — watchlist (BUGGY)
name_width = max(20, width - (price_width * 5 + trend_width + len(" │ ") * 6 + 4))
#                             40             5              18             4 = 67

# Line 306 — portfolio (BUGGY)
name_w = max(15, width - (3 + 8 + 9 + 10 + 9 + 6 + len(" │ ") * 6 + 4))
#                         45                      18             4 = 67
```

Both compute to `width - 67`. But the loop actually consumes `name_width + 68`:

| Component | Chars |
|---|---|
| `x = 2` (start after `║ `) | 2 |
| 7 × `" │ "` (3 chars each) | 21 |
| 5 price columns × 8 | 40 |
| Trend column × 5 | 5 |
| name_width | variable |
| **Total** | **name_width + 68** |

### Why it manifests at MIN_WIDTH=72

At `width=72`:
- `name_width = max(20, 72 - 67) = max(20, 5) = 20`
- Total row width: `20 + 68 = 88` — but the terminal is only **72** columns wide
- The 90d column (positions 69-76) spills past column 72
- With ncurses wrap mode enabled (the default), `addstr` wraps at the right
  margin instead of erroring, so characters 72-76 land on the next row,
  appearing in front of the following item's name. (`safe_addstr`'s
  `try/except curses.error` only matters for the non-wrapping error case.)

### Why it only manifests near the minimum width

The buggy formula computes `name_width = max(20, width - 67)`. The real last
data character is at `name_width + 64`, so the row overflows only while the
name floor dominates:

- For `width ≤ 84`: `name_width = 20` (the floor), last char at `84` — wraps
  whenever the terminal is narrower than 85 columns.
- For `width ≥ 85`: `name_width = width - 67 ≥ 18`, last char at
  `width - 3` — the row always fits.

So the wrapping is confined to widths **72–84** — exactly the band around the
old `MIN_WIDTH = 72`. At large widths the row fits fine; the "201 > 200"
accounting some analyses cite comes from counting the phantom trailing
separator the loop advances past but never writes, which is not a real
overflow.

## Fix

Three changes across two files:

### 1. `constants/display.py` line 3

```diff
- MIN_WIDTH = 72
+ MIN_WIDTH = 88
```

### 2. `views.py` line 168 — watchlist formula

```diff
- name_width = max(20, width - (price_width * 5 + trend_width + len(" │ ") * 6 + 4))
+ name_width = max(20, width - (5 * price_width + trend_width + 7 * len(" │ ") + 2))
```

The corrected overhead: `5*8 + 5 + 7*3 + 2 = 40 + 5 + 21 + 2 = 68` ✓

### 3. `views.py` line 306 — portfolio formula

```diff
- name_w = max(15, width - (3 + 8 + 9 + 10 + 9 + 6 + len(" │ ") * 6 + 4))
+ name_w = max(15, width - (3 + 8 + 9 + 10 + 9 + 6 + 7 * len(" │ ") + 2))
```

The corrected overhead: `3+8+9+10+9+6 + 7*3 + 2 = 45 + 21 + 2 = 68` ✓

## Verification

At the new `MIN_WIDTH = 88`:

| Width | name_width | Last data char | Closing ║ | Wraps? |
|---|---|---|---|---|
| 72 (old MIN) | 20 | 84 | 71 | **Yes** |
| **88 (new MIN)** | **20** | **84** | **87** | **No** |
| 100 | 32 | 96 | 99 | No |
| 120 | 52 | 116 | 119 | No |

### Why the header (not the data row) sets the minimum at 88

The data row's last character is `name_width + 64`, so rows stop wrapping at
width 85. The binding constraint is the **column header with a sort arrow**:
Python's string format does not truncate, so `"Trend ▲"` (7 chars) overflows
the 5-wide trend column by 2 and `"Qty ▲"` (6 chars) overflows the 3-wide qty
column by 3. The last header character reaches:

- Watchlist: `name_width + 66` → needs `name_width + 67 ≤ width`
- Portfolio: `name_width + 67` → needs `name_width + 68 ≤ width`

With the name floor of 20, the portfolio header requires `width ≥ 88` — which
is exactly why `MIN_WIDTH = 88` is the correct (not conservative) minimum.

At width 88 with `name_width = max(20, 88 - 68) = 20`:
- Name col: positions 2-21
- Buff163: 25-32
- 7d: 36-43
- 30d: 47-54
- 60d: 58-65
- 90d: 69-76
- Trend: 80-84
- Closing ║ at 87

All data fits cleanly within the 88-column terminal, and the widest header
(`name_width + 67 = 87`) sits exactly at the right border.

## Acceptable variations

The grader (`benchmarks/grade_001.py`) is behavioral: it evaluates whatever
formulas are present, so any fix that achieves the following passes:

1. `MIN_WIDTH ≥ 88` (as a literal or a constant arithmetic expression)
2. Both width formulas subtract an overhead of **68** (7 separators + 2 start
   offset — i.e. 5 price columns × 8, trend × 5, 7 × 3, + 2)
3. At MIN_WIDTH, the data rows and the widest header fit without wrapping

Examples of acceptable alternative spellings (all pass the grader):
- Reordering the terms: `width - (7 * len(" │ ") + 5 * price_width + trend_width + 2)`
- A named overhead constant:
  ```python
  overhead = 2 + 7 * len(" │ ") + 5 * price_width + trend_width
  name_width = max(20, width - overhead)
  ```
- Computing MIN_WIDTH dynamically:
  `MIN_WIDTH = 20 + 2 + 7 * 3 + 5 * 8 + 5`
- Hard-coding the overhead: `name_width = max(20, width - 68)`
