//! The watchlist as a document: `items.txt` keeps its comments and blank lines through every edit,
//! and import and export use the same format.

use std::collections::HashSet;
use std::fs;
use std::io::{self, Write};
use std::path::Path;

use super::item::{Item, WEAPONS, split_name};

#[derive(Clone, Debug, PartialEq, Eq)]
enum Line {
    Item { item: Item, raw: String },
    Other(String),
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Watchlist {
    lines: Vec<Line>,
    crlf: bool,
}

impl Watchlist {
    pub fn parse(text: &str) -> Watchlist {
        let lines = text
            .lines()
            .map(|raw| match Item::parse_line(raw) {
                Some(item) => Line::Item { item, raw: raw.to_string() },
                None => Line::Other(raw.to_string()),
            })
            .collect();
        Watchlist { lines, crlf: text.contains("\r\n") }
    }

    pub fn to_text(&self) -> String {
        let eol = if self.crlf { "\r\n" } else { "\n" };
        let mut text = String::new();
        for line in &self.lines {
            text.push_str(match line {
                Line::Item { raw, .. } => raw,
                Line::Other(raw) => raw,
            });
            text.push_str(eol);
        }
        text
    }

    /// Reads the file; a missing file is an empty watchlist.
    pub fn load(path: &Path) -> io::Result<Watchlist> {
        match fs::read_to_string(path) {
            Ok(text) => Ok(Watchlist::parse(&text)),
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(Watchlist::default()),
            Err(e) => Err(e),
        }
    }

    pub fn save(&self, path: &Path) -> io::Result<()> {
        write_atomic(path, self.to_text().as_bytes())
    }

    pub fn items(&self) -> impl Iterator<Item = &Item> {
        self.lines.iter().filter_map(|line| match line {
            Line::Item { item, .. } => Some(item),
            Line::Other(_) => None,
        })
    }

    pub fn len(&self) -> usize {
        self.items().count()
    }

    pub fn is_empty(&self) -> bool {
        self.items().next().is_none()
    }

    pub fn contains(&self, item: &Item) -> bool {
        let name = item.market_hash_name();
        self.items().any(|i| i.market_hash_name() == name)
    }

    pub fn add(&mut self, item: Item) {
        let raw = item.to_line();
        self.lines.push(Line::Item { item, raw });
    }

    /// Removes the item's line, leaving every other line as it was. True when it was there.
    pub fn remove(&mut self, item: &Item) -> bool {
        let found = self.lines.iter().position(|line| matches!(line, Line::Item { item: i, .. } if i == item));
        if let Some(i) = found {
            self.lines.remove(i);
        }
        found.is_some()
    }

    /// Removes the item at this position in file order, leaving every other line as it was.
    pub fn remove_at(&mut self, index: usize) -> Option<Item> {
        let line = self.lines.iter().enumerate().filter(|(_, line)| matches!(line, Line::Item { .. })).nth(index)?.0;
        match self.lines.remove(line) {
            Line::Item { item, .. } => Some(item),
            Line::Other(_) => None,
        }
    }

    /// Reads text to import and sorts its lines into what would change, without changing anything.
    pub fn preview_import(&self, text: &str) -> ImportPreview {
        let mut seen: HashSet<String> = self.items().map(Item::market_hash_name).collect();
        let mut preview = ImportPreview::default();
        for line in text.lines() {
            let Some(item) = Item::parse_line(line) else { continue };
            let Some(item) = canonical(item) else {
                preview.unreadable.push(line.trim().to_string());
                continue;
            };
            if seen.insert(item.market_hash_name()) {
                preview.new.push(item);
            } else {
                preview.duplicates += 1;
            }
        }
        preview
    }

    /// Appends a preview's new items.
    pub fn apply_import(&mut self, preview: ImportPreview) {
        for item in preview.new {
            self.add(item);
        }
    }
}

/// An import reads the loose forms the add dialog does. A line already spelled "Weapon | Skin"
/// keeps its skin's casing, because market names aren't title case ("B the Monster"). A known
/// weapon alone is a real item too: vanilla knives have no skin.
fn canonical(item: Item) -> Option<Item> {
    let (weapon, guessed_skin) = split_name(&item.name);
    let skin = match item.name.split_once('|') {
        Some((_, skin)) => Some(skin.trim()).filter(|s| !s.is_empty()).map(str::to_string),
        None => guessed_skin,
    };
    let name = match skin {
        Some(skin) => format!("{weapon} | {skin}"),
        None if WEAPONS.contains(&weapon.as_str()) => weapon,
        None => return None,
    };
    Some(Item { name, ..item })
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ImportPreview {
    pub new: Vec<Item>,
    pub duplicates: usize,
    pub unreadable: Vec<String>,
}

/// Writes through a temporary file beside the target and renames it over, so a crash leaves
/// either the old file or the new one.
pub fn write_atomic(path: &Path, bytes: &[u8]) -> io::Result<()> {
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir)?;
    }
    let mut tmp = path.as_os_str().to_owned();
    tmp.push(format!(".{}.tmp", std::process::id()));
    let tmp = Path::new(&tmp);
    let _ = fs::remove_file(tmp);
    let written = (|| {
        let mut options = fs::OpenOptions::new();
        options.write(true).create(true).truncate(true);
        #[cfg(unix)]
        if let Ok(meta) = fs::metadata(path) {
            use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
            options.mode(meta.permissions().mode());
        }
        let mut file = options.open(tmp)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        drop(file);
        fs::rename(tmp, path)
    })();
    if written.is_err() {
        let _ = fs::remove_file(tmp);
    }
    written
}

#[cfg(test)]
mod tests {
    use super::*;

    const FILE: &str = "# rifles\nAK-47 | Redline, ft\n\n# knives\n★ Karambit | Fade, Factory New\nM4A1-S | Printstream\n";

    fn parsed(line: &str) -> Item {
        Item::parse_line(line).unwrap()
    }

    #[test]
    fn untouched_text_round_trips_exactly() {
        assert_eq!(Watchlist::parse(FILE).to_text(), FILE);
    }

    #[test]
    fn keeps_crlf_line_endings() {
        let text = "# a\r\nAK-47 | Redline\r\n";
        assert_eq!(Watchlist::parse(text).to_text(), text);
    }

    #[test]
    fn reads_items_and_skips_comments() {
        let w = Watchlist::parse(FILE);
        assert_eq!(w.len(), 3);
        assert_eq!(w.items().next().unwrap().wear.as_deref(), Some("Field-Tested"));
    }

    #[test]
    fn removing_an_item_keeps_comments_and_other_lines_verbatim() {
        let mut w = Watchlist::parse(FILE);
        assert!(w.remove(&parsed("AK-47 | Redline, Field-Tested")));
        assert_eq!(w.to_text(), "# rifles\n\n# knives\n★ Karambit | Fade, Factory New\nM4A1-S | Printstream\n");
        assert!(!w.remove(&parsed("AK-47 | Redline, Field-Tested")));
    }

    #[test]
    fn removing_by_position_takes_that_line_when_two_read_the_same() {
        let mut w = Watchlist::parse("AK-47 | Redline, ft\n# note\nAK-47 | Redline, Field-Tested\n");
        assert_eq!(w.remove_at(1), Some(parsed("AK-47 | Redline, ft")));
        assert_eq!(w.to_text(), "AK-47 | Redline, ft\n# note\n");
        assert_eq!(w.remove_at(5), None);
    }

    #[test]
    fn adding_appends_a_line_and_keeps_the_rest() {
        let mut w = Watchlist::parse(FILE);
        w.add(parsed("ST AWP | Asiimov, bs"));
        assert_eq!(w.to_text(), format!("{FILE}ST AWP | Asiimov, Battle-Scarred\n"));
    }

    #[test]
    fn saves_and_loads_through_a_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("nested/items.txt");
        assert!(Watchlist::load(&path).unwrap().is_empty());
        Watchlist::parse(FILE).save(&path).unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), FILE);
        assert_eq!(Watchlist::load(&path).unwrap(), Watchlist::parse(FILE));
        assert_eq!(fs::read_dir(path.parent().unwrap()).unwrap().count(), 1, "no temporary file left behind");
    }

    #[test]
    fn import_preview_sorts_lines_and_changes_nothing() {
        let w = Watchlist::parse(FILE);
        let text = "# note\nAK-47 | Redline, Field-Tested\nak47 vulcan, mw\nAK-47 Vulcan, Minimal Wear\nmystery line\n";
        let preview = w.preview_import(text);
        assert_eq!(preview.new, [parsed("AK-47 | Vulcan, Minimal Wear")]);
        assert_eq!(preview.duplicates, 2, "one already watched, one repeated within the import");
        assert_eq!(preview.unreadable, ["mystery line"]);
        assert_eq!(w.len(), 3);
    }

    #[test]
    fn importing_keeps_a_skins_market_casing() {
        let w = Watchlist::parse("AK-47 | B the Monster, Field-Tested\n");
        let preview = w.preview_import("AK-47 | B the Monster, Field-Tested\nak47|B the Monster, ft\n");
        assert!(preview.new.is_empty(), "{:?}", preview.new);
        assert_eq!(preview.duplicates, 2);
    }

    #[test]
    fn importing_accepts_a_vanilla_knife_but_not_an_unknown_name() {
        let preview = Watchlist::default().preview_import("★ Karambit\nmystery\n");
        assert_eq!(preview.new, [parsed("Karambit")]);
        assert_eq!(preview.new[0].market_hash_name(), "★ Karambit");
        assert_eq!(preview.unreadable, ["mystery"]);
    }

    #[test]
    fn applying_an_import_only_adds() {
        let mut w = Watchlist::parse(FILE);
        let preview = w.preview_import("AK-47 | Vulcan\n");
        w.apply_import(preview);
        assert_eq!(w.len(), 4);
        assert!(w.to_text().starts_with(FILE));
    }

    #[test]
    fn an_exported_watchlist_imports_as_all_duplicates() {
        let w = Watchlist::parse(FILE);
        let preview = w.preview_import(&w.to_text());
        assert!(preview.new.is_empty());
        assert_eq!(preview.duplicates, 3);
    }

    #[cfg(unix)]
    #[test]
    fn saving_keeps_the_files_permissions() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("items.txt");
        fs::write(&path, "").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        Watchlist::parse(FILE).save(&path).unwrap();
        assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
    }
}
