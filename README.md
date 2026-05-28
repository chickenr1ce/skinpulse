# Skinpulse

A terminal-based tool to track real-time skin prices across multiple marketplaces using the PriceEmpire API.

## Prerequisites

*   **Python 3.x**: Ensure you have Python 3 installed on your system.
*   **PriceEmpire API Key**: You need a valid API key from [PriceEmpire](https://pricempire.com/api).

## Installation

1.  **Clone the repository** (if you haven't already):
    ```bash
    git clone https://github.com/chickenr1ce/CS2_SkinPrice_Scraper.git
    cd CS2_SkinPrice_Scraper
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
    alias skinpulse='cd /path/to/CS2_SkinPrice_Scraper && python3 tui.py'
    alias skinpulse-manage='cd /path/to/CS2_SkinPrice_Scraper && python3 manage.py'

    # For fish — add to ~/.config/fish/config.fish
    alias skinpulse 'cd /path/to/CS2_SkinPrice_Scraper && python3 tui.py'
    alias skinpulse-manage 'cd /path/to/CS2_SkinPrice_Scraper && python3 manage.py'
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

## Troubleshooting

*   **API status 403**: This means your API key is invalid or you are accessing an endpoint not covered by your plan. Ensure you have the **Trader (Free)** plan or higher.
*   **API status 429**: Rate limit exceeded. The app is configured to auto-refresh every 5 minutes to stay within free tier limits.
*   **Test with Curl**: 
    ```bash
    curl -H "Authorization: Bearer YOUR_KEY" "https://api.pricempire.com/v4/trader/items/prices?app_id=730&currency=USD"
    ```
