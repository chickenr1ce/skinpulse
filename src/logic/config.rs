//! Where the app keeps its files, and the small amount of state it remembers between launches.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use super::watchlist::write_atomic;

#[derive(Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Config {
    #[serde(default)]
    pub api_key: String,
    #[serde(default)]
    pub portfolio_slug: String,
}

/// Written by hand so a stray `{:?}` can't print the key.
impl std::fmt::Debug for Config {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Config").field("api_key", &"[redacted]").field("portfolio_slug", &self.portfolio_slug).finish()
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Paths {
    pub config_dir: PathBuf,
    pub cache_dir: PathBuf,
}

impl Paths {
    /// dirs::config_dir()/skinpulse and dirs::cache_dir()/skinpulse; None if the OS gives no home.
    pub fn system() -> Option<Paths> {
        Some(Paths { config_dir: dirs::config_dir()?.join("skinpulse"), cache_dir: dirs::cache_dir()?.join("skinpulse") })
    }

    pub fn config_file(&self) -> PathBuf {
        self.config_dir.join("config.json")
    }

    pub fn items_file(&self) -> PathBuf {
        self.config_dir.join("items.txt")
    }

    pub fn state_file(&self) -> PathBuf {
        self.config_dir.join("state.json")
    }

    pub fn prices_cache(&self) -> PathBuf {
        self.cache_dir.join("prices.json")
    }

    pub fn portfolio_cache(&self) -> PathBuf {
        self.cache_dir.join("portfolio.json")
    }
}

impl Config {
    pub fn load(path: &Path) -> Result<Config, String> {
        match fs::read_to_string(path) {
            Ok(text) => serde_json::from_str(&text).map_err(|e| format!("Invalid config file: {e}")),
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(Config::default()),
            Err(e) => Err(e.to_string()),
        }
    }

    /// Writes the file owner-only on unix. `write_atomic` gives its temporary file the target's
    /// mode, so the target is locked down first: the key is never in a file others can read.
    pub fn save(&self, path: &Path) -> io::Result<()> {
        let json = serde_json::to_vec_pretty(self).map_err(io::Error::other)?;
        create_private_file(path)?;
        lock_down(path)?;
        write_atomic(path, &json)
    }
}

/// Creates the target empty and owner-only when it does not exist yet.
#[cfg(unix)]
fn create_private_file(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::OpenOptionsExt;
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir)?;
    }
    match fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(path) {
        Ok(_) => Ok(()),
        Err(e) if e.kind() == io::ErrorKind::AlreadyExists => Ok(()),
        Err(e) => Err(e),
    }
}

#[cfg(not(unix))]
fn create_private_file(_path: &Path) -> io::Result<()> {
    Ok(())
}

/// Tightens a pre-existing file that was created with a wider mode.
#[cfg(unix)]
fn lock_down(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
}

#[cfg(not(unix))]
fn lock_down(_path: &Path) -> io::Result<()> {
    Ok(())
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum ViewKind {
    #[default]
    Watchlist,
    Portfolio,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct SortChoice {
    pub column: usize,
    pub ascending: bool,
}

/// Remembered between launches. Unknown or corrupt state falls back to Default, never an error.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct UiState {
    pub view: ViewKind,
    pub watchlist_sort: SortChoice,
    pub portfolio_sort: SortChoice,
}

impl Default for UiState {
    fn default() -> Self {
        UiState {
            view: ViewKind::Watchlist,
            watchlist_sort: SortChoice { column: 1, ascending: true },
            portfolio_sort: SortChoice { column: 0, ascending: true },
        }
    }
}

impl UiState {
    pub fn load(path: &Path) -> UiState {
        fs::read_to_string(path).ok().and_then(|text| serde_json::from_str(&text).ok()).unwrap_or_default()
    }

    pub fn save(&self, path: &Path) -> io::Result<()> {
        let json = serde_json::to_vec_pretty(self).map_err(io::Error::other)?;
        write_atomic(path, &json)
    }
}

/// The files an existing Python install holds, to import on first run.
pub fn import_from_folder(folder: &Path, paths: &Paths) -> Result<ImportSummary, String> {
    let mut summary = ImportSummary::default();

    let source_config = folder.join("config.json");
    if source_config.is_file() {
        let imported = Config::load(&source_config)?;
        let destination = paths.config_file();
        // Never clobber a config that already holds a key; a corrupt one is treated the same way.
        let has_key = match Config::load(&destination) {
            Ok(existing) => !existing.api_key.trim().is_empty(),
            Err(_) => true,
        };
        if !has_key {
            let config = Config { api_key: imported.api_key, portfolio_slug: imported.portfolio_slug };
            config.save(&destination).map_err(|e| e.to_string())?;
            summary.config = true;
        }
    }

    let source_items = folder.join("items.txt");
    if source_items.is_file() {
        let destination = paths.items_file();
        // Comments count: a file holding only notes is still the user's file.
        let populated = match fs::read_to_string(&destination) {
            Ok(text) => !text.trim().is_empty(),
            Err(e) if e.kind() == io::ErrorKind::NotFound => false,
            Err(e) => return Err(e.to_string()),
        };
        if !populated {
            let text = fs::read_to_string(&source_items).map_err(|e| e.to_string())?;
            write_atomic(&destination, text.as_bytes()).map_err(|e| e.to_string())?;
            summary.items = true;
        }
    }

    Ok(summary)
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ImportSummary {
    pub config: bool,
    pub items: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn paths(root: &Path) -> Paths {
        Paths { config_dir: root.join("config/skinpulse"), cache_dir: root.join("cache/skinpulse") }
    }

    #[test]
    fn debug_output_hides_the_key() {
        let config = Config { api_key: "secret-key".into(), portfolio_slug: "mine".into() };
        let printed = format!("{config:?}");
        assert!(!printed.contains("secret-key"), "{printed}");
        assert!(printed.contains("mine"));
    }

    #[cfg(unix)]
    #[test]
    fn saving_over_a_world_readable_config_ends_owner_only() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        fs::write(&path, "{}").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        Config { api_key: "k".into(), portfolio_slug: String::new() }.save(&path).unwrap();
        assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
    }

    #[test]
    fn file_names_follow_the_documented_layout() {
        let paths = Paths { config_dir: "/c".into(), cache_dir: "/k".into() };
        assert_eq!(paths.config_file(), Path::new("/c/config.json"));
        assert_eq!(paths.items_file(), Path::new("/c/items.txt"));
        assert_eq!(paths.state_file(), Path::new("/c/state.json"));
        assert_eq!(paths.prices_cache(), Path::new("/k/prices.json"));
        assert_eq!(paths.portfolio_cache(), Path::new("/k/portfolio.json"));
    }

    #[test]
    fn a_missing_config_loads_as_default() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(Config::load(&dir.path().join("nope.json")), Ok(Config::default()));
    }

    #[test]
    fn a_corrupt_config_is_an_error_without_the_key_in_it() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        fs::write(&path, r#"{"api_key": "SUPER-SECRET","#).unwrap();
        let err = Config::load(&path).unwrap_err();
        assert!(!err.contains("SUPER-SECRET"), "{err}");
    }

    #[test]
    fn config_round_trips_and_ignores_unknown_fields() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        fs::write(&path, r#"{"api_key": "key", "portfolio_slug": "slug", "legacy": true}"#).unwrap();
        let config = Config::load(&path).unwrap();
        assert_eq!(config, Config { api_key: "key".into(), portfolio_slug: "slug".into() });
        let other = dir.path().join("nested/config.json");
        config.save(&other).unwrap();
        assert_eq!(Config::load(&other).unwrap(), config);
    }

    #[cfg(unix)]
    #[test]
    fn saving_a_new_config_creates_it_owner_only() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("nested/config.json");
        Config { api_key: "key".into(), portfolio_slug: String::new() }.save(&path).unwrap();
        assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
    }

    #[cfg(unix)]
    #[test]
    fn saving_over_a_world_readable_config_tightens_it() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        fs::write(&path, "{}").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        Config { api_key: "key".into(), portfolio_slug: String::new() }.save(&path).unwrap();
        assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
        assert_eq!(Config::load(&path).unwrap().api_key, "key");
    }

    #[test]
    fn ui_state_defaults_to_the_watchlist_sorted_by_price() {
        let state = UiState::default();
        assert_eq!(state.view, ViewKind::Watchlist);
        assert_eq!(state.watchlist_sort, SortChoice { column: 1, ascending: true });
        assert_eq!(state.portfolio_sort, SortChoice { column: 0, ascending: true });
    }

    #[test]
    fn ui_state_round_trips() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("state.json");
        let state = UiState {
            view: ViewKind::Portfolio,
            watchlist_sort: SortChoice { column: 6, ascending: false },
            portfolio_sort: SortChoice { column: 5, ascending: false },
        };
        state.save(&path).unwrap();
        assert_eq!(UiState::load(&path), state);
    }

    #[test]
    fn corrupt_or_partial_state_falls_back_to_the_defaults() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("state.json");
        assert_eq!(UiState::load(&path), UiState::default());
        fs::write(&path, "{ not json").unwrap();
        assert_eq!(UiState::load(&path), UiState::default());
        fs::write(&path, r#"{"view": "Settings"}"#).unwrap();
        assert_eq!(UiState::load(&path), UiState::default());
        fs::write(&path, r#"{"view": "Portfolio"}"#).unwrap();
        let state = UiState::load(&path);
        assert_eq!(state.view, ViewKind::Portfolio);
        assert_eq!(state.watchlist_sort, UiState::default().watchlist_sort);
    }

    #[test]
    fn importing_an_existing_install_copies_its_files() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("python");
        fs::create_dir_all(&source).unwrap();
        fs::write(source.join("config.json"), r#"{"api_key": "key", "portfolio_slug": "slug", "legacy": 1}"#).unwrap();
        fs::write(source.join("items.txt"), "# mine\nAK-47 | Redline, ft\n").unwrap();
        let paths = paths(dir.path());

        let summary = import_from_folder(&source, &paths).unwrap();
        assert_eq!(summary, ImportSummary { config: true, items: true });
        assert_eq!(Config::load(&paths.config_file()).unwrap(), Config { api_key: "key".into(), portfolio_slug: "slug".into() });
        assert_eq!(fs::read_to_string(paths.items_file()).unwrap(), "# mine\nAK-47 | Redline, ft\n");
    }

    #[test]
    fn importing_never_overwrites_a_key_or_a_non_empty_watchlist() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("python");
        fs::create_dir_all(&source).unwrap();
        let paths = paths(dir.path());
        fs::create_dir_all(&paths.config_dir).unwrap();
        fs::write(paths.config_file(), r#"{"api_key": "keep-me"}"#).unwrap();
        fs::write(paths.items_file(), "AK-47 | Redline\n").unwrap();
        fs::write(source.join("config.json"), r#"{"api_key": "other"}"#).unwrap();
        fs::write(source.join("items.txt"), "M4A1-S | Printstream\n").unwrap();

        let summary = import_from_folder(&source, &paths).unwrap();
        assert_eq!(summary, ImportSummary { config: false, items: false });
        assert_eq!(Config::load(&paths.config_file()).unwrap().api_key, "keep-me");
        assert_eq!(fs::read_to_string(paths.items_file()).unwrap(), "AK-47 | Redline\n");
    }

    #[test]
    fn importing_fills_an_empty_destination() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("python");
        fs::create_dir_all(&source).unwrap();
        fs::write(source.join("config.json"), r#"{"portfolio_slug": "slug"}"#).unwrap();
        fs::write(source.join("items.txt"), "AK-47 | Redline\n").unwrap();
        let paths = paths(dir.path());
        fs::create_dir_all(&paths.config_dir).unwrap();
        fs::write(paths.config_file(), "{}").unwrap();
        fs::write(paths.items_file(), "\n").unwrap();

        let summary = import_from_folder(&source, &paths).unwrap();
        assert_eq!(summary, ImportSummary { config: true, items: true });
        assert_eq!(Config::load(&paths.config_file()).unwrap().portfolio_slug, "slug");
    }

    #[test]
    fn importing_keeps_a_destination_holding_only_comments() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("python");
        fs::create_dir_all(&source).unwrap();
        fs::write(source.join("items.txt"), "AK-47 | Redline\n").unwrap();
        let paths = paths(dir.path());
        fs::create_dir_all(&paths.config_dir).unwrap();
        fs::write(paths.items_file(), "# only a comment\n").unwrap();

        let summary = import_from_folder(&source, &paths).unwrap();
        assert!(!summary.items);
        assert_eq!(fs::read_to_string(paths.items_file()).unwrap(), "# only a comment\n");
    }

    #[test]
    fn a_corrupt_source_config_fails_the_import() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("python");
        fs::create_dir_all(&source).unwrap();
        fs::write(source.join("config.json"), "not json").unwrap();
        assert!(import_from_folder(&source, &paths(dir.path())).is_err());
    }

    #[test]
    fn an_empty_source_folder_copies_nothing() {
        let dir = tempfile::tempdir().unwrap();
        let summary = import_from_folder(&dir.path().join("missing"), &paths(dir.path())).unwrap();
        assert_eq!(summary, ImportSummary::default());
    }
}
