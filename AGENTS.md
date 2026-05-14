# CS2 SkinPrice Scraper

## Entrypoint

- **`python3 tui.py`** — the only executable.
- Dependency: only `requests`. No requirements.txt — install via `pip install requests`.
- No test, lint, typecheck, or formatter config exists.

## API (PriceEmpire Trader Tier)

- Endpoint: `https://api.pricempire.com/v4/trader/items/prices`
- Available sources: only `buff163` and `skins` (skins.com). Do not use `csfloat`, `skinport`, etc.
- Currency: `EUR`. The API returns raw cents values; `price_empire_scraper.py` divides all `price` fields by 100.
- Rate limit: auto-refresh every 300s in TUI; `'r'` for manual refresh; `'q'` to quit.

## Config

- `config.json` is gitignored (secrets). Copy `config.json.example` to create it.
- Format: `{ "api_key": "...", "items": [ { "name": "...", "wear": "...", "stattrak": false } ] }`

## Name Formatting Quirk

`format_market_hash_name()` prepends `★` for knives whose name contains `"Karambit"`, `"M9 Bayonet"`, or `"Knife"`. Plain `"Bayonet"` and `"Shadow Daggers"` are missed — manually prefix with `★` in config if needed.
