# Skinpulse — Roadmap

## Completed

- Legacy cleanup: removed `main.py`, `scraper.py`, `scrapersoup.py`, `msedgedriver.exe`, `sample.html`, leftover screenshot
- [x] Price deltas: per-source inline display with green (rise) / red (drop) color coding
- [x] Sorting: press 1-4 (watchlist) / 1-7 (portfolio) to sort, same key toggles asc/desc
- [x] Dynamic column widths: adapts to terminal size
- [x] items.txt watchlist — plain-text format with hot-reload
- [x] manage.py CLI — add/list/remove commands
- [x] Portfolio view — press `p` to toggle, shows Qty/Buy/Now/Total/P&L/ROI with live prices
- [x] API reference doc — `API_REFERENCE.md` with all trader tier endpoints

## Planned

### Views (new API data sources)
- [ ] Trending/Declining feed — new view (`t` key) showing top movers from `/trending` and `/declining`, switchable period (1d/7d/30d/90d)
- [ ] Insights browser — browse curated item categories (knives, rifles, pistols, etc.) from `/insights`, show 24h/7d/30d/60d/90d changes
- [ ] Multi-portfolio switcher — list all portfolios from `/portfolios`, press key to switch, shows snapshot (value/change/ROI)

### Charts
- [ ] Per-item price sparklines — inline Unicode sparkline next to each item's price (6 cols: `▃▅▆▇█▇`), configurable period (1d/7d/30d)
  - `history.py` — on each refresh, append per-item snapshot to `price_history.json`; prune older than configurable window
  - `ascii_chart.py` — render Unicode sparklines + optional full-screen overlay graph on `Enter`/`g` key
  - Data shape: `{ "item_name": [[ts, buff_price, skins_price, min_price], ...] }`
  - Local JSON storage for now; swap to SQLite later if needed

### Analytics
- [ ] Insights chart sparklines — ASCII sparklines from `/insights/{slug}/chart` for curated categories
- [ ] Diversification dashboard — show portfolio diversification scores (type, wear, rarity, price range) on portfolio header
- [ ] Time period returns — display 1w/1m/3m/6m/1y performance bars in portfolio view
- [ ] Best/worst day insight — show weekly patterns (best day, weekend vs weekday delta) from portfolio stats

### Quality of Life
- [ ] Item selection — arrow keys / jk to highlight items (future: quick-remove, per-item settings via selected item). Selection is separate from scrolling — use modifier keys for scrolling to avoid conflicts.
- [ ] Scrolling — Ctrl-D/Ctrl-U (half-page), PgDn/PgUp (full-page), g/G (top/bottom) when items exceed terminal height. Arrow keys / jk are reserved for item selection.
- [ ] Profitable items filter — filter portfolio view to show only items in profit/loss
- [ ] Configurable refresh interval — +/- keys to adjust 300s default
- [ ] Profit spread column — show buff163 vs skins.com margin per item
- [ ] Historical tracking — price history log per session, show biggest movers
- [ ] Minimize mode — compact view with fewer columns
- [ ] Currency selector — cycle through EUR/USD/GBP/CNY via config key
