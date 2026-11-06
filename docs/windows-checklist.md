# Windows release checklist

Run this on a Windows machine before tagging a release. Download the Windows artifact from the CI run for the commit you are about to tag and use it as-is.

## Launch

- [ ] `skinpulse-<tag>-windows-x64.exe` starts when double-clicked.
- [ ] No console window opens or flashes.
- [ ] SmartScreen warns on the unsigned exe; More info, then Run anyway starts it.

## Display

- [ ] A GPU window opens and the fonts look crisp at 100% scaling.
- [ ] Fonts still look crisp at 150% scaling.
- [ ] Live resize: drag each window edge and corner. Content reflows and the window does not stretch. Note how bad the lag and stretching are (known Rune issue #47 on Windows) and whether it blocks the release.

## Input

- [ ] Typing works in the setup screen without an IME: API key and portfolio slug. "Import from a folder…" opens a folder picker.
- [ ] Typing works in the add dialog without an IME, including backspace and paste of a plain item name.
- [ ] Shortcuts work: `q`, `r`, `p`, `a`, `d`, `i`, `e`, `1`-`7` and pressing the same number again, Up/Down, `Ctrl-D`, `Ctrl-U`, `PgDn`, `PgUp`, `g`, `G`.
- [ ] Import opens a file picker and can pick `items.txt`; export opens a save picker and writes the file.
- [ ] Clipboard import pastes a list and shows the preview; clipboard export puts the list on the clipboard.

## Files

- [ ] `%APPDATA%\skinpulse\` is created and holds `config.json`, `items.txt` and `state.json`.
- [ ] Edit `items.txt` in Notepad, add a comment and an item, then save. The app reloads the file, shows the new item, and keeps the comment after its own next save. Notepad may write CRLF line endings; the app must accept them.
- [ ] Price cache files appear in `%LOCALAPPDATA%\skinpulse\`.

## Theme and quit

- [ ] With Windows set to dark, the app opens dark; switch Windows to light and reopen, and it opens light.
- [ ] `q` quits the app.
- [ ] The window's X quits the app.
- [ ] After either quit, Task Manager shows no `skinpulse.exe` process.
