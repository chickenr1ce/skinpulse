//! Sample data for headless snapshots. None of it reaches a normal launch.

use skinpulse::logic::config::{Config, SortChoice, UiState, ViewKind};
use skinpulse::logic::portfolio::{Holding, Portfolio, Summary};
use skinpulse::logic::prices::{ItemPrices, PriceBook, Quote};
use skinpulse::logic::refresh::{REFRESH_INTERVAL, Schedule};
use skinpulse::logic::watchlist::Watchlist;

use super::app::{App, Modal};

type Scene = (&'static str, fn(&mut App));

pub const SCENES: &[Scene] = &[
    ("watchlist", |s| *s = sample(None)),
    ("stale", |s| *s = sample(Some("API status 429. Showing data from 14:02."))),
    ("empty", |s| *s = App::new(Config::default(), Watchlist::default(), PriceBook::default(), ui())),
    ("portfolio", |s| {
        *s = sample(None);
        s.ui.view = ViewKind::Portfolio;
    }),
    ("setup", |s| {
        *s = sample(None);
        s.config = Config::default();
        s.open_setup();
    }),
    ("add", |s| {
        *s = sample(None);
        s.open_add();
    }),
    ("delete", |s| {
        *s = sample(None);
        super::dialogs::ask_delete(s);
    }),
    ("import", |s| {
        *s = sample(None);
        s.import = Some(s.watchlist.preview_import("AK-47 | Redline, ft\nAWP | Dragon Lore, Factory New\nP250 | See Ya Later\nnot a skin\n"));
        s.modal = Modal::Import;
    }),
    ("export", |s| {
        *s = sample(None);
        s.modal = Modal::Export;
    }),
];

const WATCHLIST: &str = "\
★ Karambit | Black Laminate, Well-Worn
★ M9 Bayonet | Doppler, Factory New
★ Sport Gloves | Nocts, Field-Tested
ST AK-47 | Redline, Field-Tested
AK-47 | Vulcan, Minimal Wear
SV AK-47 | B the Monster, Field-Tested
M4A1-S | Printstream, Field-Tested
AWP | Asiimov, Battle-Scarred
USP-S | Kill Confirmed, Minimal Wear
Glock-18 | Fade, Factory New
Desert Eagle | Blaze, Factory New
MP9 | Starlight Protector, Field-Tested
";

fn ui() -> UiState {
    UiState {
        view: ViewKind::Watchlist,
        watchlist_sort: SortChoice { column: 1, ascending: false },
        portfolio_sort: SortChoice { column: 0, ascending: true },
    }
}

fn quote(price: f64, a7: f64, a30: f64, a60: f64, a90: f64) -> ItemPrices {
    let v = |x: f64| (x > 0.0).then_some(x);
    ItemPrices { buff163: Quote { price: v(price), avg_7: v(a7), avg_30: v(a30), avg_60: v(a60), avg_90: v(a90) }, skins: v(price * 1.04) }
}

fn sample(error: Option<&str>) -> App {
    let mut book = PriceBook::default();
    for (name, prices) in [
        ("★ Karambit | Black Laminate (Well-Worn)", quote(412.50, 408.10, 401.75, 396.20, 389.90)),
        ("★ M9 Bayonet | Doppler (Factory New)", quote(1184.00, 1192.40, 1210.15, 1228.60, 1241.30)),
        ("★ Sport Gloves | Nocts (Field-Tested)", quote(263.80, 261.40, 268.90, 259.15, 255.00)),
        ("StatTrak™ AK-47 | Redline (Field-Tested)", quote(38.20, 39.05, 40.12, 41.33, 42.80)),
        ("AK-47 | Vulcan (Minimal Wear)", quote(166.79, 166.58, 169.92, 169.85, 167.24)),
        ("Souvenir AK-47 | B the Monster (Field-Tested)", quote(742.00, 735.50, 0.0, 0.0, 0.0)),
        ("M4A1-S | Printstream (Field-Tested)", quote(96.45, 94.20, 92.75, 90.10, 88.35)),
        ("AWP | Asiimov (Battle-Scarred)", quote(71.30, 72.15, 71.30, 73.40, 74.05)),
        ("USP-S | Kill Confirmed (Minimal Wear)", quote(58.90, 57.65, 56.20, 55.45, 54.10)),
        ("Glock-18 | Fade (Factory New)", quote(1020.00, 1005.40, 1012.75, 998.30, 987.60)),
        ("Desert Eagle | Blaze (Factory New)", quote(445.15, 452.30, 449.80, 455.25, 460.10)),
    ] {
        book.insert(name, prices);
    }
    let config = Config { api_key: "sample".into(), portfolio_slug: "sample".into() };
    let mut app = App::new(config, Watchlist::parse(WATCHLIST), book, ui());
    app.portfolio = Some(Portfolio {
        summary: Summary { name: "Long holds".into(), total_value: 2_986.45, total_profit: 412.30, total_roi: 16.02, change_24h: -18.75, change_24h_pct: -0.62 },
        items: vec![
            Holding { market_hash_name: "★ Karambit | Black Laminate (Well-Worn)".into(), holdings: 1, avg_buy: Some(355.00), current_price: Some(410.00) },
            Holding { market_hash_name: "AK-47 | Vulcan (Minimal Wear)".into(), holdings: 4, avg_buy: Some(181.20), current_price: Some(165.00) },
            Holding { market_hash_name: "M4A1-S | Printstream (Field-Tested)".into(), holdings: 8, avg_buy: Some(62.50), current_price: Some(95.00) },
            Holding { market_hash_name: "AWP | Asiimov (Battle-Scarred)".into(), holdings: 2, avg_buy: Some(71.30), current_price: Some(71.30) },
            Holding { market_hash_name: "Sticker | Crown (Foil)".into(), holdings: 3, avg_buy: None, current_price: None },
        ],
    });
    app.resort_portfolio();
    app.schedule = Schedule { prices_at: Some(0.0), ..Schedule::default() };
    app.now = REFRESH_INTERVAL - 724.0;
    app.error = error.map(str::to_string);
    if let Some(row) = app.rows.get(2) {
        app.table.select(row.id.clone());
    }
    app
}
