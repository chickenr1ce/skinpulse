# Skinpulse

Skinpulse is a tui to manage and view CS2 skin prices in a saved watchlist. Users can also view their priceempire portfolio if they have one.
Skins to be stored and watched are in items.txt.
Prices are fetched using the priceempire api.

## Entrypoint

- **`python3 tui.py`** — the only executable.
- Dependency: only `requests`. No requirements.txt — install via `pip install requests`.
- Tests: `python3 -m pytest tests/` from the repo root. Benchmark: `python3 benchmarks/grade_001.py` (all 4 checks must pass). No lint/typecheck/formatter config exists.
- Weapon names are defined in `constants/weapons.py` and imported by `items.py`, `manage.py`, and `wizard.py`.

## TUI Behavior Contract

The key map is rendered in the in-app help bar (bottom line) and handled in `tui.py` — that is the authoritative source for keys. When adding a key, don't collide with the existing set: `q`, `r`, `p`, `a`, `d`, `1`-`7`, `g`, `G`, `Ctrl-D`/`Ctrl-U`, `PgUp`/`PgDn`.

Behavioral invariants that must not break:

- **Refresh cadence** — auto-refresh every 15 min (900s, `REFRESH_INTERVAL` in `constants/display.py`); `r` forces a manual refresh. This cadence is a deliberate budget constraint: the PriceEmpire Trader tier allows ~100 requests/day, shared with the skinpulse web app. Don't shorten it or add fetch paths without accounting for that.
- **Hot-reload** — `items.txt` is re-read automatically when it changes, via mtime polling (`items.py:get_items_mtime`). There is deliberately no manual reload key.
- **In-app editing** — the watchlist view supports `a` (interactive add wizard) and `d` (delete selected item, with confirmation). Items are saved back to `items.txt` immediately.
- **Views** — `p` toggles watchlist/portfolio, but only when `portfolio_slug` is configured. The watchlist shows buff163 prices and historical averages only.
- **Sorting** — `1`-`7` sort by column (watchlist: name/buff163/7d/30d/60d/90d/trend; portfolio: name/qty/buy/now/total/P&L/ROI); pressing the same key again toggles asc/desc, with ▲/▼ in the header. Trend is defined as `7d − 90d` so its direction matches the sparkline's green/red.
- **Colors** — watchlist avg columns (7d/30d/60d/90d) and sparkline are green when current buff163 price exceeds the average, red when below. Portfolio P&L and ROI are green for profit, red for loss.
- **Scrolling** — `Ctrl-D`/`PgDn` scroll down half/full page, `Ctrl-U`/`PgUp` up; `g`/`G` jump to top/bottom. When items exceed terminal height, the help bar shows a position indicator (e.g. `↑ 12-17/17 ↓`).

## API (PriceEmpire Trader Tier)

- Endpoint: `https://api.pricempire.com/v4/trader/items/prices`
- Params: `sources=buff163,skins`, `avg=true`, `currency=EUR`.
- Available sources: `buff163` and `skins` (skins.com). Do not use `csfloat`, `skinport`, etc. Note: the TUI watchlist only displays buff163 prices and historical averages.
- Currency: `EUR`. The API returns raw cents values; `price_empire_scraper.py` divides all `price` and `avg_*` fields by 100.
- Rate limit: Trader tier allows ~100 requests/day (shared with the web app) — the 15-min TUI refresh cadence is a deliberate budget constraint (see TUI Behavior Contract).

## Config

- `config.json` is gitignored (secrets). Copy `config.json.example` to create it.
- Format: `{ "api_key": "...", "portfolio_slug": "..." }`

## Item Management

### Primary: `items.txt` (plain-text watchlist)

One item per line, format: `[ST ][SV ]Name[, Wear]`

```
Karambit | Black Laminate, Well-Worn
ST AK-47 | Redline, Field-Tested
SV AK-47 | B the Monster, Field-Tested
M4A1-S | Printstream
```

- `ST ` prefix = StatTrak.
- `SV ` prefix = Souvenir.
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

Prompts ask for weapon (flexible input: `ak47`, `AK 47`, `m4a1s` all resolve; typing `AK-47 Redline` auto-splits into weapon + skin), skin (auto-capitalized, apostrophe-safe: `rameses reach` → `Rameses Reach`), optional wear (short codes or full names), StatTrak, and Souvenir.

The item is validated against the PriceEmpire API before saving — same contract as the TUI `a` wizard (both use `utils.validate_item`):

- **Found** → shows prices from buff163 and skins, then asks for confirmation.
- **Not found** → shows similar items ("Did you mean...?") as numbered options:
  - Pick a **number** to auto-correct the skin name and wear from the API, with prices.
  - `p` — proceed anyway (add despite the warning)
  - `r` — retry (re-enter the skin name)
  - `c` — cancel
- **API error / no key** → warns but lets you proceed.

## Name Formatting

`format_market_hash_name()` turns an item dict into a Steam Market Hash Name: `Souvenir `/`StatTrak™ ` prefixes, `★` for knives and gloves, and wear in parentheses (e.g. `StatTrak™ ★ Karambit | Black Laminate (Well-Worn)`, `★ Sport Gloves | Nocts (Field-Tested)`). The `★` uses an exact `STARRED_ITEMS` lookup (defined in `constants/weapons.py` as `KNIFE_NAMES | GLOVE_NAMES`) — all 21 knife types (including `Bayonet`, `Shadow Daggers`, `Kukri Knife`, etc.) and all 6 glove types (e.g. `Sport Gloves`, `Driver Gloves`, `Moto Gloves`) are handled correctly.
