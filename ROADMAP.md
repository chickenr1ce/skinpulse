# CS2 SkinPrice Scraper — Roadmap

## Completed

- Legacy cleanup: removed `main.py`, `scraper.py`, `scrapersoup.py`, `msedgedriver.exe`, `sample.html`, leftover screenshot
- [x] Price deltas: per-source inline display with green (drop) / red (rise) color coding
- [x] Sorting: press 1-4 to sort by name/buff/skins/lowest, same key toggles asc/desc
- [x] Dynamic column widths: adapts to terminal size
- [x] items.txt watchlist — plain-text format with hot-reload
- [x] manage.py CLI — add/list/remove commands
- [x] Portfolio view — press `p` to toggle, shows P&L/ROI per item with live prices

## Planned

- [ ] Price alerts — config-based thresholds per item, visual highlight or terminal bell on trigger
- [ ] CSV export — dump current prices to a timestamped CSV
- [ ] Scrolling — arrow keys / jk when items exceed terminal height
- [ ] Favorites/watchlist — mark items, toggle between views
- [ ] Configurable refresh interval — +/- keys to adjust 300s default
- [ ] Profit spread column — calculate buff163 vs skins.com margin
- [ ] Historical tracking — in-memory log per session, show biggest movers
- [ ] Minimize mode — compact view with fewer columns
