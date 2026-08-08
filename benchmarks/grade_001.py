#!/usr/bin/env python3
"""Automated grading for Benchmark 001: Curses Column Wrapping.

Run from the repo root against the (hopefully fixed) codebase:

    python3 benchmarks/grade_001.py

All checks must pass. Exit code 0 = all pass, 1 = one or more failures.

Grading is behavioral: it evaluates the width formulas and MIN_WIDTH that are
actually present in the code and verifies the rows fit without wrapping at
MIN_WIDTH. It accepts any correct formulation — an inline formula, a named
`overhead` constant, a dynamically computed MIN_WIDTH, a reordered expression,
etc. — not just the reference spelling.
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Layout facts for the 7-column tables (widths of the columns after the name
# column). Watchlist: buff(8) 7d(8) 30d(8) 60d(8) 90d(8) trend(5).
WL_OTHERS = [8, 8, 8, 8, 8, 5]
# Portfolio: qty(3) buy(8) now(9) total(10) pl(9) roi(6).
PF_OTHERS = [3, 8, 9, 10, 9, 6]

# The render loop advances x by col_width + 3 after EVERY column (7 times), so
# the width formulas must account for 2 (start offset after "║ ") + 7
# separators x 3 + all column widths.
WATCHLIST_OVERHEAD = 2 + 7 * 3 + sum(WL_OTHERS)   # 68
PORTFOLIO_OVERHEAD = 2 + 7 * 3 + sum(PF_OTHERS)   # 68

# The 7th x-advance (after the last column) is a phantom gap — no separator is
# written there — so the real last data character sits at name_w + 64.
# The column header is the tighter constraint: a sort arrow (" ▲") overflows
# narrow headers ("Trend ▲" = 7 chars in the 5-wide trend column; "Qty ▲" =
# 6 chars in the 3-wide qty column), pushing the last header character to
# name_w + 66 (watchlist) and name_w + 67 (portfolio). With the name floor of
# 20, the portfolio header needs width >= 88 — which is why MIN_WIDTH = 88.
WL_HEADER_OVERFLOW = 2   # "Trend ▲" (7 chars) in the 5-wide trend column
PF_HEADER_OVERFLOW = 2   # "Qty ▲" (5 chars) in the 3-wide qty column


# ---------------------------------------------------------------------------
# Safe expression evaluation
# ---------------------------------------------------------------------------

def _eval_expr(node, namespace):
    """Safely evaluate a constant arithmetic expression AST.

    Supports numeric literals, + - * / // %, unary +/-, Name lookups in
    `namespace`, and len("...") calls. Returns None on anything unsupported
    (no arbitrary code execution).
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node.value, str):
            return node.value
        return None
    if isinstance(node, ast.Name):
        return namespace.get(node.id)
    if isinstance(node, ast.UnaryOp):
        v = _eval_expr(node.operand, namespace)
        if v is None:
            return None
        if isinstance(node.op, ast.UAdd):
            return v
        if isinstance(node.op, ast.USub):
            return -v
        return None
    if isinstance(node, ast.BinOp):
        left = _eval_expr(node.left, namespace)
        right = _eval_expr(node.right, namespace)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return None if right == 0 else left / right
        if isinstance(node.op, ast.FloorDiv):
            return None if right == 0 else left // right
        if isinstance(node.op, ast.Mod):
            return None if right == 0 else left % right
        return None
    if isinstance(node, ast.Call):
        if (isinstance(node.func, ast.Name) and node.func.id == "len"
                and len(node.args) == 1):
            arg = _eval_expr(node.args[0], namespace)
            if isinstance(arg, str):
                return len(arg)
        # The views._overhead(fixed_width_sum, n_columns) helper:
        # start offset 2 + all fixed column widths + one 3-char advance per column.
        if (isinstance(node.func, ast.Name) and node.func.id == "_overhead"
                and len(node.args) == 2):
            fixed_sum = _eval_expr(node.args[0], namespace)
            n_columns = _eval_expr(node.args[1], namespace)
            if (isinstance(fixed_sum, (int, float))
                    and isinstance(n_columns, (int, float))):
                return 2 + fixed_sum + 3 * n_columns
        return None
    return None


def _build_namespace(tree):
    """Collect all `name = constant-expr` assignments, evaluated in source
    order, so later expressions can reference earlier ones (e.g. `overhead`)."""
    ns = {"price_width": 8, "trend_width": 5}  # render constants
    assigns = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.lineno is not None:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigns.append((node.lineno, t.id, node.value))
    assigns.sort(key=lambda x: x[0])
    for _, name, value in assigns:
        val = _eval_expr(value, ns)
        if val is not None:
            ns[name] = val
    return ns


def _find_formula(tree, target, ns):
    """Return (floor, overhead) for `target = max(floor, width - X)`.

    X may be an inline arithmetic expression or a Name resolved through the
    file's assignments (e.g. an `overhead` constant). Returns (None, None)
    if not found or not evaluable.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == target:
                    value = node.value
                    if (isinstance(value, ast.Call) and len(value.args) >= 2
                            and isinstance(value.args[1], ast.BinOp)
                            and isinstance(value.args[1].op, ast.Sub)):
                        floor = _eval_expr(value.args[0], ns)
                        overhead = _eval_expr(value.args[1].right, ns)
                        return floor, overhead
    return None, None


def _load_state():
    """Parse constants/display.py and views.py once and extract what the
    checks need. Never raises; missing/unparseable inputs yield None values."""
    state = {
        "min_width": None,
        "watchlist": (None, None),
        "portfolio": (None, None),
    }
    display_path = REPO_ROOT / "constants" / "display.py"
    if display_path.exists():
        try:
            tree = ast.parse(display_path.read_text())
            ns = _build_namespace(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id == "MIN_WIDTH":
                            state["min_width"] = _eval_expr(node.value, ns)
        except SyntaxError:
            pass
    views_path = REPO_ROOT / "views.py"
    if views_path.exists():
        try:
            tree = ast.parse(views_path.read_text())
            ns = _build_namespace(tree)
            state["watchlist"] = _find_formula(tree, "name_width", ns)
            state["portfolio"] = _find_formula(tree, "name_w", ns)
        except SyntaxError:
            pass
    return state


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_min_width(state):
    """MIN_WIDTH must be a numeric constant (or constant arithmetic) >= 88.

    88 is the exact minimum: with the name floor of 20 and the corrected
    overhead of 68, the portfolio header with a sort arrow ("Qty ▲" overflows
    its 3-wide column by 3) reaches name_w + 67 = 87, which needs width >= 88.
    """
    min_width = state["min_width"]
    if min_width is None:
        return False, ("MIN_WIDTH not found in constants/display.py or is not "
                       "a constant/arithmetic literal")
    if min_width < 88:
        return False, (f"MIN_WIDTH = {min_width}, but needs >= 88 (the header "
                       "with sort arrows needs name_w + 68 <= width)")
    return True, f"MIN_WIDTH = {min_width} >= 88"


def _check_formula(state, view_name, target, expected, label):
    floor, overhead = state[view_name]
    if overhead is None:
        return False, (f"{label} formula ({target} = max(floor, width - ...)) "
                       "not found or not evaluable")
    if overhead == expected:
        return True, (f"{label} formula overhead evaluates to {overhead} "
                      "(7 separators + 2, start offset 2)")
    if overhead == 67:
        return False, (f"{label} formula overhead = {overhead} — still the old "
                       f"pattern (6 separators + 4); needs {expected}")
    return False, (f"{label} formula overhead = {overhead}, needs {expected} "
                   "(7 separators + 2, start offset 2)")


def check_watchlist_formula(state):
    return _check_formula(state, "watchlist", "name_width", WATCHLIST_OVERHEAD,
                          "Watchlist")


def check_portfolio_formula(state):
    return _check_formula(state, "portfolio", "name_w", PORTFOLIO_OVERHEAD,
                          "Portfolio")


def check_math_verification(state):
    """At MIN_WIDTH, verify the data rows AND the column header (with sort
    arrow) fit without wrapping for both views."""
    min_width = state["min_width"]
    if min_width is None:
        return False, "Cannot verify math: MIN_WIDTH not found or not numeric"

    views = [
        ("watchlist", state["watchlist"], WL_OTHERS, WL_HEADER_OVERFLOW, 20),
        ("portfolio", state["portfolio"], PF_OTHERS, PF_HEADER_OVERFLOW, 15),
    ]
    results = []
    for view_name, (floor, overhead), others, header_overflow, default_floor in views:
        if overhead is None:
            results.append(f"{view_name}: formula not evaluable — skipped")
            continue
        floor_used = floor if isinstance(floor, (int, float)) else default_floor
        name_w = max(floor_used, min_width - overhead)
        data_last = _data_last(name_w, others)
        header_last = _header_last(name_w, others, header_overflow)
        border = min_width - 1
        data_fits = data_last <= border
        # Strict: the arrow-overflowing header must not reach the right border
        # (the border ║ would overwrite the last arrow character).
        header_fits = header_last < border
        fits = data_fits and header_fits
        results.append(
            f"{view_name}: overhead={overhead}, name_w={name_w}, "
            f"data_last={data_last}, header_last={header_last}, "
            f"border={border}, fits={fits} (MIN_WIDTH={min_width})"
        )
        if not fits:
            return False, "; ".join(results)
    return True, "; ".join(results)


def _data_last(name_w, others):
    """Last written data character (0-indexed) for a 7-column table."""
    return 2 + name_w + 6 * 3 + sum(others) - 1


def _header_last(name_w, others, overflow):
    """Last header character including the sort-arrow overflow."""
    return _data_last(name_w, others) + overflow


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    state = _load_state()
    checks = [
        ("MIN_WIDTH >= 88",   lambda: check_min_width(state)),
        ("Watchlist formula", lambda: check_watchlist_formula(state)),
        ("Portfolio formula", lambda: check_portfolio_formula(state)),
        ("Math verification", lambda: check_math_verification(state)),
    ]

    print(f"Benchmark 001 — Grading against {REPO_ROOT}")
    print("-" * 50)

    passed = 0
    failed = 0

    for name, fn in checks:
        ok, msg = fn()
        if ok:
            print(f"  PASS  {name}")
            print(f"        {msg}")
            passed += 1
        else:
            print(f"  FAIL  {name}")
            print(f"        {msg}")
            failed += 1
        print()

    print("-" * 50)
    if failed == 0:
        print(f"RESULT: All {passed} checks passed ✓")
        return 0
    else:
        print(f"RESULT: {passed} passed, {failed} failed ✗")
        return 1


if __name__ == "__main__":
    sys.exit(main())
