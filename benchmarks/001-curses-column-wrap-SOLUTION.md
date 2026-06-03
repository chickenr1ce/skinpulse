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
- `safe_addstr` silently drops characters 72-76, but curses wraps them to the
  next row, appearing in front of the following item's name

### Why it's hidden at larger widths

At `width=200`:
- `name_width = max(20, 200 - 67) = 133`
- `133 + 68 = 201` — one character overflows
- `safe_addstr` silently drops that single overflow character, so it's invisible
- The bug is present at ALL widths, just masked by the silent error handling

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

At width 88 with `name_width = max(20, 88 - 68) = 20`:
- Name col: positions 2-21
- Buff163: 25-32
- 7d: 36-43
- 30d: 47-54
- 60d: 58-65
- 90d: 69-76
- Trend: 80-84
- Closing ║ at 87

All data fits cleanly within the 88-column terminal. The header (which uses
`sep.join()` with 6 separators) also fits: `20 + 6*3 + 40 + 5 = 83` chars,
starting at x=2, ending at 84, well within 88.

## Acceptable variations

Any fix that achieves the following is valid:

1. `MIN_WIDTH ≥ 88` (or derived dynamically from the corrected overhead)
2. Both formulas account for 7 separators (not 6)
3. The start-offset is 2 (not 4)
4. At MIN_WIDTH, `name_width + overhead ≤ width` and header fits

Examples of acceptable alternative approaches:
- Computing `overhead = 2 + 7 * len(" │ ") + 5 * price_width + trend_width` as a constant
  and using `name_width = max(20, width - overhead)` — more explicit
- Computing MIN_WIDTH dynamically: `min_printable = MIN_NAME + 2 + 7 * 3 + 5 * 8 + 5`
  instead of hardcoding 88
