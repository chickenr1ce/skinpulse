# Skinpulse

Skinpulse is a keyboard-first native desktop app for Windows and Linux that tracks CS2 skin prices with the PriceEmpire API. It is built with [Rune](https://github.com/anomalyco/rune). The Python terminal version is [skinpulse-tui](https://github.com/chickenr1ce/skinpulse-tui).

## Requirements

You need a PriceEmpire API key. The Trader plan is free; create a key at <https://pricempire.com/api>.

## Download

Releases provide a portable `skinpulse-<tag>-windows-x64.exe` for Windows and a `skinpulse-<tag>-linux-x64.tar.gz` for Linux. The tarball contains the `skinpulse` binary, a desktop entry, the licence and the font licence.

## First run

Skinpulse shows a setup screen on first launch. Enter your API key and, if you use one, your portfolio slug. The screen can also import `config.json` and `items.txt` from a folder holding a Python TUI install, so an existing setup carries over.

## Where files live

On Linux, settings and the watchlist are in `~/.config/skinpulse/` and price caches are in `~/.cache/skinpulse/`.

On Windows, settings and the watchlist are in `%APPDATA%\skinpulse\` and price caches are in `%LOCALAPPDATA%\skinpulse\`.

The config folder holds:

- `config.json`: the API key and portfolio slug. It is plain text and owner-only on Linux.
- `items.txt`: the watchlist.
- `state.json`: the small pieces of state the app remembers between launches.

## items.txt

One item per line:

```
[SV ][ST ]Weapon | Skin[, Wear]
```

`SV` and `ST` are optional Souvenir and StatTrak prefixes. The wear is optional and accepts the short codes `fn`, `mw`, `ft`, `ww` and `bs`.

```
AK-47 | Redline, ft
ST AWP | Asiimov, bs
★ Karambit | Doppler, fn
```

`#` comments and blank lines are kept when the app saves the file. The app reloads `items.txt` when it changes on disk, so you can edit it in another program while Skinpulse runs.

## Keys

| Key | Action |
| --- | --- |
| `q` | Quit |
| `r` | Refresh |
| `p` | Switch between watchlist and portfolio |
| `a` | Add an item |
| `d` | Delete the selected item |
| `i` | Import |
| `e` | Export |
| `s` | Settings |
| `1`-`7` | Sort by a column; press again to flip the direction |
| Up / Down | Move the selection |
| `Ctrl-D` / `Ctrl-U` | Half page down / up |
| `PgDn` / `PgUp` | Full page down / up |
| `g` / `G` | Jump to the top / bottom |

With a mouse, click a column header to sort, click a row to select it, and use the wheel to scroll.

## Import and export

Import adds items to the existing list and skips duplicates. It shows a preview before changing anything. The clipboard works as an import source and an export destination, and import and export can also use a file picker.

## API budget

The PriceEmpire plan allows about 100 requests a day. Prices refresh every 15 minutes while the app is open. The last response is saved and reused on launch if it is under 15 minutes old. The portfolio is fetched only while its view is open, or when you press `r`.

## Windows

The executable is unsigned, so SmartScreen warns on first run. Choose More info, then Run anyway.

## Build from source

```
cargo build --release
```

For a headless render:

```
target/release/skinpulse --snap out.png --scene watchlist --theme dark --size 1040x640 --scale 2
```

## Licence

MIT. The Geist fonts are under the SIL Open Font License; see `assets/fonts/OFL.txt`. Skinpulse is not affiliated with PriceEmpire or Valve.
