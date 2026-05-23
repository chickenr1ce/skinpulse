# Skinpulse

## Entrypoint

- **`python3 tui.py`** — the only executable.
- Dependency: only `requests`. No requirements.txt — install via `pip install requests`.
- No test, lint, typecheck, or formatter config exists.
- Weapon names are defined in `constants/weapons.py` and imported by `items.py`, `manage.py`, and `wizard.py`.

## TUI Keybindings

| Key | Action |
|-----|--------|
| `r` | Force refresh (API fetch) |
| `p` | Toggle between watchlist and portfolio view |
| `q` | Quit |
| `1` - `4` | Sort watchlist by column (name/buff/skins/lowest). Press same key again to toggle asc/desc. ▲/▼ indicator shown in header. |
| `1` - `6` | Sort portfolio by column (name/qty/buy/now/total/P&L/ROI). Same toggle behavior. |
| `Ctrl-D` / `PgDn` | Scroll half/full page down |
| `Ctrl-U` / `PgUp` | Scroll half/full page up |
| `g` / `G` | Jump to top / bottom |
| Auto | Refreshes every 300s |

Price deltas show inline after each price: `320.50(+5.20)` — green for rises, red for drops. First load shows `(  ~  )` placeholder.
In portfolio view, P&L and ROI are green for profit, red for loss.
Scrolling indicator in the help bar shows position (e.g. `↑ 12-17/17 ↓`) when items exceed terminal height.

## API (PriceEmpire Trader Tier)

- Endpoint: `https://api.pricempire.com/v4/trader/items/prices`
- Available sources: only `buff163` and `skins` (skins.com). Do not use `csfloat`, `skinport`, etc.
- Currency: `EUR`. The API returns raw cents values; `price_empire_scraper.py` divides all `price` fields by 100.
- Rate limit: auto-refresh every 300s in TUI; `'r'` for manual refresh; `'q'` to quit.

## Config

- `config.json` is gitignored (secrets). Copy `config.json.example` to create it.
- Format: `{ "api_key": "...", "portfolio_slug": "..." }`

## Item Management

### Primary: `items.txt` (plain-text watchlist)

One item per line, format: `[ST ]Name[, Wear]`

```
Karambit | Black Laminate, Well-Worn
ST AK-47 | Redline, Field-Tested
M4A1-S | Printstream
```

- `ST ` prefix = StatTrak.
- `#` comments are ignored.
- Name is the full "Weapon | Skin" string (the ★ star is auto-added by `format_market_hash_name()`).
- Wear accepts short codes: `fn`, `mw`, `ft`, `ww`, `bs` (e.g. `AK-47 | Redline, ft`).
- Edit in any text editor — the TUI hot-reloads on save via mtime polling (`items.py:get_items_mtime`).

### CLI helper: `python3 manage.py <list|add|remove>`

| Command | What it does |
|---------|-------------|
| `manage.py list` | Prints all tracked items with indices |
| `manage.py add` | Interactive add with weapon search, API validation, and typo detection |
| `manage.py remove 2` | Remove by index |
| `manage.py remove Redline` | Remove by name substring (first match) |

Items are stored exclusively in `items.txt`.

#### `manage.py add` — interactive flow

1. **Weapon selection** — type to fuzzy-search, enter an index, or type `list` to see all weapons.
   - Accepts flexible input: `ak47`, `ak-47`, `AK 47`, `m4a1s`, `deserteagle` all resolve correctly.
   - Full-name shortcut: typing `AK-47 Redline` auto-splits into weapon + skin.
2. **Skin input** — auto-capitalized with correct apostrophe handling (`rameses reach` → `Rameses Reach`).
3. **Wear** — optional. Accepts short codes: `fn`, `mw`, `ft`, `ww`, `bs` (or full names like `Factory New`).
4. **StatTrak** — y/N toggle.
5. **API validation** — the item is checked against the PriceEmpire API before saving:
   - **Found** → shows prices from buff163 and skins, then asks for confirmation.
   - **Not found** → shows similar items ("Did you mean...?") as numbered options:
     - Pick a **number** to auto-correct the skin name and wear from the API, with prices.
     - `p` — proceed anyway (add despite the warning)
     - `r` — retry (re-enter the skin name)
     - `c` — cancel
   - **API error / no key** → warns but lets you proceed.

## Name Formatting

`format_market_hash_name()` prepends `★` for all knife types using an exact `KNIFE_NAMES` lookup (defined in `constants/weapons.py`). All 21 knife types (including `Bayonet`, `Shadow Daggers`, `Kukri Knife`, etc.) are handled correctly.
