//! The app's state and the changes everything else asks of it.

use std::sync::mpsc::{Receiver, Sender, channel};

use rune::{TextEdit, Waker};
use rune_kit::{SortDir, TableState};
use skinpulse::logic::cache::now_unix;
use skinpulse::logic::config::{Config, Paths, SortChoice, UiState, ViewKind};
use skinpulse::logic::item::Item;
use skinpulse::logic::portfolio::Portfolio;
use skinpulse::logic::prices::PriceBook;
use skinpulse::logic::refresh::Schedule;
use skinpulse::logic::sort::{sort_portfolio, sort_watchlist};
use skinpulse::logic::watchlist::{ImportPreview, Watchlist};

use super::add::AddForm;
use super::data::Msg;
use super::portfolio::COLUMNS as PORTFOLIO_COLUMNS;
use super::watchlist::COLUMNS;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Modal {
    None,
    Setup,
    Add,
    Delete,
    Import,
    Export,
}

pub struct App {
    /// Where files live. `None` in headless tooling runs and scenes, which never read or write
    /// the user's files or spend API requests.
    pub paths: Option<Paths>,
    pub config: Config,
    pub watchlist: Watchlist,
    pub items_mtime: Option<std::time::SystemTime>,
    /// The watchlist in display order.
    pub rows: Vec<Row>,
    pub book: PriceBook,
    pub book_at: Option<f64>,
    pub portfolio: Option<Portfolio>,
    /// Indexes into `portfolio.items`, in display order, with their table row ids.
    pub holdings: Vec<(usize, String)>,
    pub ui: UiState,
    pub table: TableState,
    pub portfolio_table: TableState,
    /// Height of the visible table, for paging keys.
    pub list_height: f32,
    pub schedule: Schedule,
    /// Refresh waits until the disk cache has been read, or a launch would always fetch.
    pub cache_loaded: bool,
    pub now: f64,
    pub last_second: u64,
    pub error: Option<String>,
    pub portfolio_error: Option<String>,
    pub notice: Option<(String, f64)>,
    pub modal: Modal,
    pub add: AddForm,
    pub setup_key: TextEdit,
    pub setup_slug: TextEdit,
    pub setup_error: Option<String>,
    /// The row a delete is asking about, by id.
    pub delete: Option<String>,
    pub import: Option<ImportPreview>,
    pub dialog_error: Option<String>,
    pub tx: Sender<Msg>,
    pub rx: Receiver<Msg>,
    pub waker: Option<Waker>,
    /// Bumped when the key or slug changes, so answers to older requests are dropped.
    pub generation: u64,
}

pub struct Row {
    pub item: Item,
    /// The market hash name, the key prices are looked up by.
    pub name: String,
    /// Unique, unlike the name: a file can list the same item twice.
    pub id: String,
    /// The item's position in file order.
    pub index: usize,
}

impl App {
    pub fn load() -> App {
        // Rune's tooling flags (--snap, --tree, --script) start headless runs.
        let tooling = std::env::args().skip(1).any(|a| a.starts_with("--"));
        let paths = if tooling { None } else { Paths::system() };
        let mut setup_error = None;
        let config = match paths.as_ref().map(|p| Config::load(&p.config_file())) {
            Some(Ok(config)) => config,
            Some(Err(e)) => {
                setup_error = Some(e);
                Config::default()
            }
            None => Config::default(),
        };
        let watchlist = paths.as_ref().and_then(|p| Watchlist::load(&p.items_file()).ok()).unwrap_or_default();
        let ui = paths.as_ref().map_or_else(default_ui, |p| UiState::load(&p.state_file()));
        let mut app = App::new(config, watchlist, PriceBook::default(), ui);
        app.items_mtime = paths.as_ref().and_then(|p| mtime(&p.items_file()));
        app.paths = paths;
        app.setup_error = setup_error;
        if app.paths.is_some() {
            app.now = now_unix();
            if app.config.api_key.trim().is_empty() {
                app.open_setup();
            }
        }
        app
    }

    pub fn new(config: Config, watchlist: Watchlist, book: PriceBook, ui: UiState) -> App {
        let (tx, rx) = channel();
        let mut app = App {
            paths: None,
            setup_key: TextEdit::new(config.api_key.clone()),
            setup_slug: TextEdit::new(config.portfolio_slug.clone()),
            config,
            watchlist,
            items_mtime: None,
            rows: Vec::new(),
            book,
            book_at: None,
            portfolio: None,
            holdings: Vec::new(),
            ui,
            table: TableState::new().key("watchlist-table"),
            portfolio_table: TableState::new().key("portfolio-table"),
            list_height: 0.0,
            schedule: Schedule::default(),
            cache_loaded: false,
            now: 0.0,
            last_second: 0,
            error: None,
            portfolio_error: None,
            notice: None,
            modal: Modal::None,
            add: AddForm::default(),
            setup_error: None,
            delete: None,
            import: None,
            dialog_error: None,
            tx,
            rx,
            waker: None,
            generation: 0,
        };
        if !app.has_slug() {
            app.ui.view = ViewKind::Watchlist;
        }
        app.resort();
        app.resort_portfolio();
        app
    }

    pub fn has_key(&self) -> bool {
        !self.config.api_key.trim().is_empty()
    }

    pub fn has_slug(&self) -> bool {
        !self.config.portfolio_slug.trim().is_empty()
    }

    /// Rebuilds the display order from the watchlist, the prices and the sort choice.
    pub fn resort(&mut self) {
        let items: Vec<Item> = self.watchlist.items().cloned().collect();
        let SortChoice { column, ascending } = self.ui.watchlist_sort;
        // Ids come from file order, so sorting can't swap them between repeated lines.
        let ids = unique_ids(items.iter().map(Item::market_hash_name));
        self.rows = sort_watchlist(&items, &self.book, column, ascending)
            .into_iter()
            .map(|i| Row { item: items[i].clone(), name: ids[i].0.clone(), id: ids[i].1.clone(), index: i })
            .collect();
        self.table.set_sort(COLUMNS[column].0, direction(ascending));
    }

    pub fn resort_portfolio(&mut self) {
        let SortChoice { column, ascending } = self.ui.portfolio_sort;
        self.holdings = match &self.portfolio {
            Some(p) => {
                let order = sort_portfolio(&p.items, &self.book, column, ascending);
                let ids = unique_ids(order.iter().map(|i| p.items[*i].market_hash_name.clone()));
                order.into_iter().zip(ids).map(|(i, (_, id))| (i, id)).collect()
            }
            None => Vec::new(),
        };
        self.portfolio_table.set_sort(PORTFOLIO_COLUMNS[column].0, direction(ascending));
    }

    /// A number key or header click: the same column flips the direction, a new one starts ascending.
    pub fn sort_by(&mut self, column: usize) {
        let watchlist = self.ui.view == ViewKind::Watchlist;
        let sort = if watchlist { &mut self.ui.watchlist_sort } else { &mut self.ui.portfolio_sort };
        *sort = if sort.column == column {
            SortChoice { column, ascending: !sort.ascending }
        } else {
            SortChoice { column, ascending: true }
        };
        if watchlist {
            self.resort();
        } else {
            self.resort_portfolio();
        }
        self.save_ui();
    }

    /// Switches between the views. The portfolio needs a slug.
    pub fn set_view(&mut self, view: ViewKind) {
        if view == ViewKind::Portfolio && !self.has_slug() {
            self.say("Add a portfolio slug in settings (s) to see your portfolio.");
            return;
        }
        self.ui.view = view;
        self.save_ui();
    }

    pub fn save_ui(&self) {
        if let Some(paths) = &self.paths {
            let _ = self.ui.save(&paths.state_file());
        }
    }

    /// Writes the watchlist and notes the file's new time, so hot-reload doesn't read it back.
    pub fn save_watchlist(&mut self) {
        self.resort();
        let Some(paths) = self.paths.clone() else { return };
        let file = paths.items_file();
        match self.watchlist.save(&file) {
            Ok(()) => self.items_mtime = mtime(&file),
            Err(e) => self.error = Some(format!("Couldn't save the watchlist: {e}")),
        }
    }

    pub fn reload_watchlist(&mut self) {
        let Some(paths) = self.paths.clone() else { return };
        let file = paths.items_file();
        if let Ok(watchlist) = Watchlist::load(&file) {
            let before = self.cursor_position();
            self.watchlist = watchlist;
            self.items_mtime = mtime(&file);
            self.resort();
            self.reselect(before);
        }
    }

    pub fn say(&mut self, message: impl Into<String>) {
        self.notice = Some((message.into(), self.now + 5.0));
    }

    pub fn close_modal(&mut self) {
        self.modal = Modal::None;
        self.dialog_error = None;
        self.delete = None;
        self.import = None;
    }

    pub fn open_setup(&mut self) {
        self.setup_key = TextEdit::new(self.config.api_key.clone());
        self.setup_slug = TextEdit::new(self.config.portfolio_slug.clone());
        self.setup_key.focused = true;
        self.modal = Modal::Setup;
    }

    pub fn open_add(&mut self) {
        self.add = AddForm::default();
        self.add.weapon.focused = true;
        self.modal = Modal::Add;
    }

    pub fn cursor_position(&self) -> Option<usize> {
        let id = self.table.cursor()?;
        self.rows.iter().position(|r| r.id == id)
    }

    /// After rows changed: a cursor whose row is gone moves to the row now at its old position.
    pub fn reselect(&mut self, before: Option<usize>) {
        if self.table.cursor().is_some_and(|id| self.rows.iter().any(|r| r.id == id)) {
            return;
        }
        match before.and_then(|at| self.rows.get(at.min(self.rows.len().saturating_sub(1)))) {
            Some(row) => {
                let id = row.id.clone();
                self.table.select(id);
            }
            None => self.table.clear_selection(),
        }
    }

    /// The row the cursor is on in the watchlist.
    pub fn selected_row(&self) -> Option<&Row> {
        let id = self.table.cursor()?;
        self.rows.iter().find(|r| r.id == id)
    }
}

pub fn default_ui() -> UiState {
    UiState {
        view: ViewKind::Watchlist,
        watchlist_sort: SortChoice { column: 1, ascending: true },
        portfolio_sort: SortChoice { column: 0, ascending: true },
    }
}

pub fn mtime(path: &std::path::Path) -> Option<std::time::SystemTime> {
    std::fs::metadata(path).and_then(|m| m.modified()).ok()
}

fn direction(ascending: bool) -> SortDir {
    if ascending { SortDir::Ascending } else { SortDir::Descending }
}

/// Pairs each name with a row id that's unique even when a name repeats.
fn unique_ids(names: impl Iterator<Item = String>) -> Vec<(String, String)> {
    let mut seen = std::collections::HashMap::new();
    names
        .map(|name| {
            let count = seen.entry(name.clone()).or_insert(0);
            *count += 1;
            let id = if *count == 1 { name.clone() } else { format!("{name}#{count}") };
            (name, id)
        })
        .collect()
}
