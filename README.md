# Skinpulse

A terminal-based tool to track real-time skin prices across multiple marketplaces using the PriceEmpire API.

## Prerequisites

*   **Python 3.x**: Ensure you have Python 3 installed on your system.
*   **PriceEmpire API Key**: You need a valid API key from [PriceEmpire](https://pricempire.com/api).
*   **Windows**: The TUI needs the `curses` module, which is **not** included with Python on Windows. Install the `windows-curses` package (see [Running on Windows](#running-on-windows)).

## Installation

1.  **Clone the repository** (if you haven't already):
    ```bash
    git clone https://github.com/chickenr1ce/skinpulse.git
    cd skinpulse
    ```

2.  **Verify Dependencies**:
    The project uses the `requests` library. Check if it's installed:
    ```bash
    python3 -c "import requests; print('Requests is installed')"
    ```
    If not installed, install it via:
    ```bash
    pip install requests
    ```

    **Windows only**: the TUI also needs `curses`, which isn't bundled with
    Python on Windows. Install it together with `requests`:
    ```bash
    python -m pip install requests windows-curses
    ```
    (On Windows, use `python` or `py` instead of `python3`.)

## Adding Items

You can add items in two ways:

### Option 1: Interactive CLI (recommended)

```bash
python3 manage.py add
```

This launches an interactive flow:

1. **Weapon selection** — type to fuzzy-search (e.g. `ak47`, `m4a1s`, `glock`), enter an index, or type `list` to see all weapons.
2. **Skin name** — auto-capitalized automatically (`rameses reach` → `Rameses Reach`).
3. **Wear** — optional. Accepts short codes: `fn`, `mw`, `ft`, `ww`, `bs` (or full names like `Factory New`).
4. **StatTrak** — y/N toggle.
5. **API validation** — the item is checked against the PriceEmpire API. If not found, similar items are shown as numbered options — pick one to auto-correct the name and wear, or use `r` to retry, `p` to proceed anyway, `c` to cancel.

**Flexible input:** you can type `AK-47 Redline`, `ak47|redline`, or `ak 47 redline` — the parser handles all variations.

### Option 2: Edit `items.txt` directly

Open `items.txt` in any text editor. One item per line:

```
Karambit | Black Laminate, Well-Worn
ST AK-47 | Redline, Field-Tested
M4A1-S | Printstream
```

- `ST ` prefix = StatTrak.
- `#` comments are ignored.
- The TUI hot-reloads on save via mtime polling.
- Wear accepts short codes: `Karambit | Black Laminate, ww` or `M4A1-S | Printstream, fn`.

### Managing items

```bash
python3 manage.py list              # List all tracked items
python3 manage.py remove 2          # Remove by index
python3 manage.py remove Redline    # Remove by name substring
```

## Configuration

1.  **Open `config.json`** in your preferred text editor.
2.  **Insert your API Key**: Replace `"YOUR_PRICEEMPIRE_API_KEY"` with your actual PriceEmpire API key (Trader plan is free).

Example `config.json`:
```json
{
    "api_key": "your-api-key-here",
    "portfolio_slug": "your-portfolio-slug"
}
```

## How to Run

1.  **Start the TUI**:
    Run the following command in your terminal:
    ```bash
    python3 tui.py
    ```

    **Tip:** add a shell alias to launch from anywhere:
    ```bash
    # For bash/zsh — add to ~/.bashrc or ~/.zshrc
    alias skinpulse='cd /path/to/skinpulse && python3 tui.py'
    alias skinpulse-manage='cd /path/to/skinpulse && python3 manage.py'

    # For fish — add to ~/.config/fish/config.fish
    alias skinpulse 'cd /path/to/skinpulse && python3 tui.py'
    alias skinpulse-manage 'cd /path/to/skinpulse && python3 manage.py'
    ```
    Then just type `skinpulse` or `skinpulse-manage add` from anywhere.

2.  **Interface Controls**:
    *   **'r'**: Manually refresh prices (the app also auto-refreshes every 5 minutes).
    *   **'p'**: Toggle between watchlist and portfolio view.
    *   **'q'**: Quit the application.
    *   **1-7**: Sort watchlist columns (press again to toggle asc/desc).
    *   **1-7**: Sort portfolio columns (press again to toggle asc/desc).
    *   **Ctrl-D / Ctrl-U**: Scroll half-page down/up.
    *   **PgDn / PgUp**: Scroll full-page down/up.
    *   **g / G**: Jump to top / bottom of list.

## Running on Windows

The TUI is built on Python's `curses` library, which is **not** included with
Python on Windows. Without it, `tui.py` fails immediately with:

```
ModuleNotFoundError: No module named 'curses'
```

1.  **Install dependencies** (in the project folder):
    ```powershell
    python -m pip install requests windows-curses
    ```
    `windows-curses` provides the missing `curses` module. Only the TUI
    (`tui.py`) needs it — `manage.py` works fine without it.

2.  **Run the TUI**:
    ```powershell
    python tui.py
    ```
    If `python` isn't recognized, try `py tui.py` (the Python launcher) or use
    a Python 3.x installation with "Add to PATH" enabled.

3.  **Use a modern terminal**: Windows Terminal (available from the Microsoft
    Store) or the Windows 11 terminal work best. Legacy `cmd.exe`/conhost can
    render curses apps poorly (missing colors, flickering, resize bugs).

All other commands work the same way — just replace `python3` with `python`:

```powershell
python manage.py add
python manage.py list
python manage.py remove 2
```

**Tip:** add these to your PowerShell profile to launch from anywhere
(open it with `notepad $PROFILE`):

```powershell
function skinpulse { Set-Location "C:\path\to\skinpulse"; python tui.py }
function skinpulse-manage { Set-Location "C:\path\to\skinpulse"; python manage.py @args }
```

Then type `skinpulse` or `skinpulse-manage add` from any directory. Note that
PowerShell functions run in your current session, so the working directory
stays changed after the call.

## Troubleshooting

*   **`ModuleNotFoundError: No module named 'curses'` (Windows)**: Python on
    Windows doesn't ship the `curses` module. Fix it with
    `python -m pip install windows-curses` (see [Running on Windows](#running-on-windows)).

*   **API status 403**: This means your API key is invalid or you are accessing an endpoint not covered by your plan. Ensure you have the **Trader (Free)** plan or higher.
*   **API status 429**: Rate limit exceeded. The app is configured to auto-refresh every 5 minutes to stay within free tier limits.
*   **Test with Curl**: 
    ```bash
    curl -H "Authorization: Bearer YOUR_KEY" "https://api.pricempire.com/v4/trader/items/prices?app_id=730&currency=USD"
    ```
