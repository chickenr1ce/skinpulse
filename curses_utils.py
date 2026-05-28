"""Low-level curses UI helpers.

Extracted from wizard.py so that curses utilities don't live inside a feature module.
"""

import curses


def safe_addstr(stdscr, y, x, text, attr=0):
    """Add string to screen, silently ignoring curses.error if coords are out of bounds."""
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def draw_centered_box(stdscr, box_y, box_x, box_h, box_w):
    """Draw a box with double-line corners at (box_y, box_x) with given dimensions."""
    if box_h < 3 or box_w < 4:
        return
    safe_addstr(stdscr, box_y, box_x, "╔" + "═" * (box_w - 2) + "╗")
    for row in range(1, box_h - 1):
        safe_addstr(stdscr, box_y + row, box_x, "║")
        safe_addstr(stdscr, box_y + row, box_x + box_w - 1, "║")
    safe_addstr(stdscr, box_y + box_h - 1, box_x, "╚" + "═" * (box_w - 2) + "╝")


def curses_input_blocking(stdscr, y, x, max_width, prompt="", initial=""):
    """Blocking text input widget. Returns the entered string or None on Escape.

    Renders 'prompt' + cursor at (y, x). Handles printable chars, Backspace,
    Enter (submit), Escape (cancel). Assumes nodelay(False) is already set.
    """
    buffer = list(initial)
    while True:
        # Render
        display = prompt + "".join(buffer)
        safe_addstr(stdscr, y, x, " " * (max_width + 2))
        safe_addstr(stdscr, y, x, display[:max_width])
        stdscr.refresh()
        ch = stdscr.getch()
        if ch == 27:  # Escape
            return None
        elif ch in (10, 13, curses.KEY_ENTER):  # Enter
            return "".join(buffer)
        elif ch in (127, curses.KEY_BACKSPACE, 8):  # Backspace
            if buffer:
                buffer.pop()
        elif 32 <= ch <= 126 and len("".join(buffer)) < max_width:  # Printable
            buffer.append(chr(ch))
        # else ignore


def confirm_dialog(stdscr, message, restore_nodelay=True, restore_timeout=100):
    """Show a centered modal confirmation dialog. Returns True for yes, False for no.

    Operates in blocking mode (sets nodelay(False) temporarily).
    Restores nodelay/state on exit using provided restore values (ME-5 fix).
    """
    height, width = stdscr.getmaxyx()
    stdscr.nodelay(False)
    stdscr.timeout(-1)
    curses.curs_set(0)

    # Dialog dimensions
    msg_lines = message.split('\n')
    box_w = max(40, min(60, width - 4))
    box_h = max(5, len(msg_lines) + 4)
    box_y = (height - box_h) // 2
    box_x = (width - box_w) // 2

    # Capture area underneath
    try:
        stdscr.refresh()
    except curses.error:
        pass

    result = False
    while True:
        draw_centered_box(stdscr, box_y, box_x, box_h, box_w)
        # Message
        for i, line in enumerate(msg_lines):
            safe_addstr(stdscr, box_y + 1 + i, box_x + 2, line[:box_w - 4])
        # Prompt
        prompt_y = box_y + box_h - 2
        safe_addstr(stdscr, prompt_y, box_x + 2, "(y)es  (n)o", curses.A_REVERSE)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (ord('y'), ord('Y')):
            result = True
            break
        elif ch in (ord('n'), ord('N'), 27):  # n, Escape
            result = False
            break

    # Restore state using caller-provided values (ME-5 fix)
    if restore_nodelay:
        stdscr.nodelay(True)
    else:
        stdscr.nodelay(False)
    stdscr.timeout(restore_timeout)
    return result
