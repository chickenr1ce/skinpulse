#!/usr/bin/env python3
"""Automated grading for Benchmark 001: Curses Column Wrapping.

Run from the repo root against the (hopefully fixed) codebase:

    python3 benchmarks/grade_001.py

All checks must pass. Exit code 0 = all pass, 1 = one or more failures.
"""

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Check 1: MIN_WIDTH >= 88
# ---------------------------------------------------------------------------

def check_min_width():
    """Parse constants/display.py and verify MIN_WIDTH >= 88."""
    path = REPO_ROOT / "constants" / "display.py"
    if not path.exists():
        return False, f"File not found: {path}"

    content = path.read_text()
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MIN_WIDTH":
                    value = _safe_eval(node.value)
                    if value is None:
                        return False, "MIN_WIDTH value is not a constant literal"
                    if value >= 88:
                        return True, f"MIN_WIDTH = {value} >= 88"
                    return False, f"MIN_WIDTH = {value}, but needs >= 88"
    return False, "MIN_WIDTH not found in constants/display.py"


# ---------------------------------------------------------------------------
# Check 2: Watchlist formula (line ~168)
# ---------------------------------------------------------------------------

def check_watchlist_formula():
    """Verify the watchlist name_width formula uses 7 separators + 2."""
    path = REPO_ROOT / "views.py"
    if not path.exists():
        return False, f"File not found: {path}"

    content = path.read_text()

    # Pattern we want: 7 * len(" │ ") + 2  or  len(" │ ") * 7 + 2
    good = re.search(
        r"""7\s*\*\s*len\(\s*["']\s*│\s*["']\s*\)\s*\+\s*2|"""
        r"""len\(\s*["']\s*│\s*["']\s*\)\s*\*\s*7\s*\+\s*2""",
        content,
    )
    if good:
        return True, "Watchlist formula uses 7 separators + 2"

    # Pattern we don't want: len(" │ ") * 6 + 4
    bad = re.search(r"""len\(\s*["']\s*│\s*["']\s*\)\s*\*\s*6\s*\+\s*4""", content)
    if bad:
        return False, "Watchlist formula still uses old pattern (6 separators + 4)"

    return False, "Watchlist formula: unrecognized pattern (neither 7+2 nor 6+4 found)"


# ---------------------------------------------------------------------------
# Check 3: Portfolio formula (line ~306)
# ---------------------------------------------------------------------------

def check_portfolio_formula():
    """Verify the portfolio name_w formula uses 7 separators + 2."""
    path = REPO_ROOT / "views.py"
    if not path.exists():
        return False, f"File not found: {path}"

    content = path.read_text()

    # Same patterns, but look near "name_w = max(15"
    # Find the portfolio formula block
    m = re.search(r"name_w\s*=\s*max\(15,\s*width\s*-\s*\((.+)\)", content)
    if not m:
        return False, "Portfolio formula (name_w = max(...)) not found"

    formula_body = m.group(1)

    good = re.search(
        r"""7\s*\*\s*len\(\s*["']\s*│\s*["']\s*\)\s*\+\s*2|"""
        r"""len\(\s*["']\s*│\s*["']\s*\)\s*\*\s*7\s*\+\s*2""",
        formula_body,
    )
    if good:
        return True, "Portfolio formula uses 7 separators + 2"

    bad = re.search(r"""len\(\s*["']\s*│\s*["']\s*\)\s*\*\s*6\s*\+\s*4""", formula_body)
    if bad:
        return False, "Portfolio formula still uses old pattern (6 separators + 4)"

    return False, "Portfolio formula: unrecognized pattern (neither 7+2 nor 6+4 found)"


# ---------------------------------------------------------------------------
# Check 4: Math verification
# ---------------------------------------------------------------------------

def check_math_verification():
    """At MIN_WIDTH, verify name_width + overhead <= width for both views.

    This is a soft check — validates that whichever formula is present,
    it produces a name_width that fits at the declared MIN_WIDTH.
    """
    display_content = (REPO_ROOT / "constants" / "display.py").read_text()
    tree = ast.parse(display_content)
    min_width = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MIN_WIDTH":
                    min_width = _safe_eval(node.value)

    if min_width is None:
        return False, "Cannot verify math: MIN_WIDTH not found"

    # Compute overhead from the formulas using regex extraction
    views_content = (REPO_ROOT / "views.py").read_text()

    # Extract watchlist formula
    wl_match = re.search(
        r"name_width\s*=\s*max\(\s*20\s*,\s*width\s*-\s*\((.+)\)",
        views_content,
    )
    pf_match = re.search(
        r"name_w\s*=\s*max\(\s*15\s*,\s*width\s*-\s*\((.+)\)",
        views_content,
    )

    overheads = {}

    if wl_match:
        expr = wl_match.group(1).strip()
        val = _eval_overhead(expr)
        if val is not None:
            overheads["watchlist"] = val

    if pf_match:
        expr = pf_match.group(1).strip()
        val = _eval_overhead(expr)
        if val is not None:
            overheads["portfolio"] = val

    if not overheads:
        return False, "Cannot verify math: could not parse either formula"

    results = []
    for view_name, overhead in overheads.items():
        name_floor = 20 if view_name == "watchlist" else 15
        name_w = max(name_floor, min_width - overhead)
        total = name_w + overhead
        fits = total <= min_width
        results.append(
            f"{view_name}: overhead={overhead}, name_w={name_w}, "
            f"total={total}, fits={fits} (MIN_WIDTH={min_width})"
        )
        if not fits:
            return False, "; ".join(results)

    return True, "; ".join(results)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_eval(node):
    """Safely evaluate a constant AST node. Returns the value or None."""
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def _eval_overhead(expr_str):
    """Naively evaluate an arithmetic expression like '5*8 + 5 + 7*3 + 2'.

    Only handles +, *, literal integers. Falls back to None on complexity.
    This is safe: no exec/eval of arbitrary code.
    """
    try:
        # Strip trailing ) — the regex capture may include the formula's
        # closing paren because of the adjoining max() paren.
        expr_str = expr_str.strip().rstrip(")")
        # Normalize: replace len(" │ ") with its known value = 3
        expr = re.sub(r'len\(\s*["\']\s*│\s*["\']\s*\)', "3", expr_str)
        # Also handle price_width and trend_width:
        expr = re.sub(r'\bprice_width\b', "8", expr)
        expr = re.sub(r'\btrend_width\b', "5", expr)
        # Only allow digits, whitespace, +, *, (, )
        if not re.match(r'^[\d\s\+\*\(\)]+$', expr):
            return None
        # Use Python's evaluator on this sanitized arithmetic
        code = compile(expr, "<overhead>", "eval")
        return eval(code, {"__builtins__": {}})
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    checks = [
        ("MIN_WIDTH >= 88",      check_min_width),
        ("Watchlist formula",     check_watchlist_formula),
        ("Portfolio formula",     check_portfolio_formula),
        ("Math verification",     check_math_verification),
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
