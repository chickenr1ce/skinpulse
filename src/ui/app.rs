//! The app's state.

use rune::{Key, KeyEvent, Tx};
use rune_kit::{SortDir, TableState};
use skinpulse::logic::config::{Config, Paths, SortChoice, UiState, ViewKind};
use skinpulse::logic::item::Item;
use skinpulse::logic::prices::PriceBook;
use skinpulse::logic::refresh::Schedule;
use skinpulse::logic::sort::sort_watchlist;
use skinpulse::logic::watchlist::Watchlist;

use super::watchlist::COLUMNS;

pub struct App {
    pub config: Config,
    pub watchlist: Watchlist,
    /// The watchlist in display order; the table's row ids are market hash names.
    pub rows: Vec<Row>,
    pub book: PriceBook,
    pub ui: UiState,
    pub table: TableState,
    pub schedule: Schedule,
    pub now: f64,
    pub error: Option<String>,
}

pub struct Row {
    pub item: Item,
    pub id: String,
}

impl App {
    pub fn load() -> App {
        let paths = Paths::system();
        let config = paths.as_ref().and_then(|p| Config::load(&p.config_file()).ok()).unwrap_or_default();
        let watchlist = paths.as_ref().and_then(|p| Watchlist::load(&p.items_file()).ok()).unwrap_or_default();
        let ui = paths.as_ref().map(|p| UiState::load(&p.state_file())).unwrap_or_else(|| UiState {
            view: ViewKind::Watchlist,
            watchlist_sort: SortChoice { column: 1, ascending: true },
            portfolio_sort: SortChoice { column: 0, ascending: true },
        });
        App::new(config, watchlist, PriceBook::default(), ui)
    }

    pub fn new(config: Config, watchlist: Watchlist, book: PriceBook, ui: UiState) -> App {
        let mut app = App {
            config,
            watchlist,
            rows: Vec::new(),
            book,
            ui,
            table: TableState::new().key("watchlist-table"),
            schedule: Schedule::default(),
            now: 0.0,
            error: None,
        };
        app.resort();
        app
    }

    /// Rebuilds the display order from the watchlist, the prices and the sort choice.
    pub fn resort(&mut self) {
        let items: Vec<Item> = self.watchlist.items().cloned().collect();
        let SortChoice { column, ascending } = self.ui.watchlist_sort;
        let order = sort_watchlist(&items, &self.book, column, ascending);
        self.rows = order
            .into_iter()
            .map(|i| Row { id: items[i].market_hash_name(), item: items[i].clone() })
            .collect();
        let dir = if ascending { SortDir::Ascending } else { SortDir::Descending };
        self.table.set_sort(COLUMNS[column].0, dir);
    }

    /// A number key or header click: the same column flips the direction, a new one starts ascending.
    pub fn sort_by(&mut self, column: usize) {
        let sort = &mut self.ui.watchlist_sort;
        *sort = if sort.column == column {
            SortChoice { column, ascending: !sort.ascending }
        } else {
            SortChoice { column, ascending: true }
        };
        self.resort();
    }
}

pub fn on_key(s: &mut App, ev: &KeyEvent, _tx: &mut Tx) -> bool {
    if let Key::Text(t) = &ev.key
        && let Some(digit @ 1..=7) = t.chars().next().and_then(|c| c.to_digit(10))
    {
        s.sort_by(digit as usize - 1);
        return true;
    }
    false
}
