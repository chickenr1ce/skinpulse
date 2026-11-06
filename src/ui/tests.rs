//! Drives the real view and key map headlessly: no window, no network.

use rune::{Env, Key, KeyEvent, Mods, Runtime};
use skinpulse::logic::config::{Config, Paths, ViewKind};
use skinpulse::logic::prices::{ItemPrices, PriceBook, Quote};
use skinpulse::logic::watchlist::Watchlist;

use super::app::{App, Modal, default_ui};
use super::data::Msg;
use super::{keys, shell};

fn prices(price: f64) -> ItemPrices {
    ItemPrices { buff163: Quote { price: Some(price), ..Quote::default() }, skins: Some(price + 1.0) }
}

fn book() -> PriceBook {
    let mut book = PriceBook::default();
    for (name, price) in [
        ("AK-47 | Redline (Field-Tested)", 30.0),
        ("AK-47 | Vulcan (Minimal Wear)", 160.0),
        ("AK-47 | B the Monster (Field-Tested)", 700.0),
        ("AWP | Asiimov (Battle-Scarred)", 70.0),
    ] {
        book.insert(name, prices(price));
    }
    book
}

fn runtime(app: App) -> Runtime<App> {
    let mut rt = Runtime::new(app, shell::view, (1040.0, 640.0), Env::new(true, 1.0));
    rt.on_key = Some(keys::on_key);
    rt.frame(0.0);
    rt
}

fn app(file: &str, slug: &str) -> App {
    let config = Config { api_key: String::new(), portfolio_slug: slug.into() };
    App::new(config, Watchlist::parse(file), book(), default_ui())
}

fn press(rt: &mut Runtime<App>, key: Key) {
    rt.key(KeyEvent { key, mods: Mods::default() });
    rt.frame(1.0 / 60.0);
}

fn typed(rt: &mut Runtime<App>, text: &str) {
    press(rt, Key::Text(text.into()));
}

const TWO: &str = "AWP | Asiimov, bs\nAK-47 | Redline, ft\n";

fn names(rt: &Runtime<App>) -> Vec<&str> {
    rt.state.rows.iter().map(|r| r.name.as_str()).collect()
}

#[test]
fn number_keys_sort_and_flip() {
    let mut rt = runtime(app(TWO, ""));
    assert_eq!(names(&rt)[0], "AK-47 | Redline (Field-Tested)", "buff163 ascending by default");
    typed(&mut rt, "2");
    assert_eq!(names(&rt)[0], "AWP | Asiimov (Battle-Scarred)", "the same column flips");
    typed(&mut rt, "1");
    assert!(rt.state.ui.watchlist_sort.ascending, "a new column starts ascending");
    assert_eq!(rt.state.ui.watchlist_sort.column, 0);
}

#[test]
fn arrows_and_g_move_the_cursor() {
    let mut rt = runtime(app(TWO, ""));
    press(&mut rt, Key::Down);
    assert_eq!(rt.state.selected_row().unwrap().name, "AK-47 | Redline (Field-Tested)");
    press(&mut rt, Key::Down);
    assert_eq!(rt.state.selected_row().unwrap().name, "AWP | Asiimov (Battle-Scarred)");
    press(&mut rt, Key::Down);
    assert_eq!(rt.state.selected_row().unwrap().name, "AWP | Asiimov (Battle-Scarred)", "stops at the end");
    typed(&mut rt, "g");
    assert_eq!(rt.state.selected_row().unwrap().name, "AK-47 | Redline (Field-Tested)");
    typed(&mut rt, "G");
    assert_eq!(rt.state.selected_row().unwrap().name, "AWP | Asiimov (Battle-Scarred)");
}

#[test]
fn the_add_dialog_checks_then_adds() {
    let mut rt = runtime(app(TWO, ""));
    typed(&mut rt, "a");
    assert_eq!(rt.state.modal, Modal::Add);
    typed(&mut rt, "ak47");
    assert_eq!(rt.state.add.weapon.text, "ak47", "the weapon field has focus when the dialog opens");
    press(&mut rt, Key::Enter);
    typed(&mut rt, "vulcan, mw");
    assert_eq!(rt.state.add.skin.text, "vulcan, mw", "Enter moves on to the skin field");
    press(&mut rt, Key::Enter);
    assert!(matches!(rt.state.add.check, super::add::Check::Found(..)), "the first Enter checks");
    assert_eq!(rt.state.watchlist.len(), 2);
    press(&mut rt, Key::Enter);
    assert_eq!(rt.state.modal, Modal::None);
    assert!(names(&rt).contains(&"AK-47 | Vulcan (Minimal Wear)"), "the second Enter adds");
}

#[test]
fn the_skin_field_takes_a_whole_name_and_keeps_its_casing() {
    let mut rt = runtime(app(TWO, ""));
    typed(&mut rt, "a");
    press(&mut rt, Key::Tab);
    typed(&mut rt, "AK-47 | B the Monster, ft");
    press(&mut rt, Key::Enter);
    assert!(matches!(rt.state.add.check, super::add::Check::Found(..)), "{}", rt.state.add.skin.text);
}

#[test]
fn a_typo_offers_suggestions_and_picking_one_finds_it() {
    let mut rt = runtime(app(TWO, ""));
    typed(&mut rt, "a");
    press(&mut rt, Key::Tab);
    typed(&mut rt, "AK-47 Vulcann, mw");
    press(&mut rt, Key::Enter);
    let super::add::Check::NotFound(_, similar) = rt.state.add.check.clone() else { panic!("expected not found") };
    assert_eq!(similar, ["AK-47 | Vulcan (Minimal Wear)"]);
    let (x, y) = rt.find("AK-47 | Vulcan (Minimal Wear)").expect("the suggestion is on screen");
    rt.pointer_down(x, y);
    rt.pointer_up(x, y);
    rt.frame(1.0 / 60.0);
    assert!(matches!(rt.state.add.check, super::add::Check::Found(..)));
}

#[test]
fn adding_what_is_already_watched_is_refused() {
    let mut rt = runtime(app(TWO, ""));
    typed(&mut rt, "a");
    press(&mut rt, Key::Tab);
    typed(&mut rt, "AK-47 Redline, ft");
    press(&mut rt, Key::Enter);
    assert!(matches!(rt.state.add.check, super::add::Check::Invalid(_)));
    press(&mut rt, Key::Enter);
    assert_eq!(rt.state.watchlist.len(), 2);
}

#[test]
fn keys_type_into_a_dialog_instead_of_acting() {
    let mut rt = runtime(app(TWO, ""));
    typed(&mut rt, "a");
    typed(&mut rt, "d");
    typed(&mut rt, "1");
    assert_eq!(rt.state.modal, Modal::Add);
    assert_eq!(rt.state.ui.watchlist_sort.column, 1);
    press(&mut rt, Key::Escape);
    assert_eq!(rt.state.modal, Modal::None);
}

#[test]
fn delete_asks_first() {
    let mut rt = runtime(app(TWO, ""));
    typed(&mut rt, "d");
    assert_eq!(rt.state.modal, Modal::None, "nothing is selected yet");
    press(&mut rt, Key::Down);
    typed(&mut rt, "d");
    assert_eq!(rt.state.modal, Modal::Delete);
    press(&mut rt, Key::Escape);
    assert_eq!(rt.state.watchlist.len(), 2, "Escape keeps it");
    typed(&mut rt, "d");
    press(&mut rt, Key::Enter);
    assert_eq!(rt.state.modal, Modal::None);
    assert_eq!(names(&rt), ["AWP | Asiimov (Battle-Scarred)"]);
}

#[test]
fn the_portfolio_needs_a_slug() {
    let mut rt = runtime(app(TWO, ""));
    typed(&mut rt, "p");
    assert_eq!(rt.state.ui.view, ViewKind::Watchlist);
    assert!(rt.state.notice.is_some());

    let mut rt = runtime(app(TWO, "mine"));
    typed(&mut rt, "p");
    assert_eq!(rt.state.ui.view, ViewKind::Portfolio);
    typed(&mut rt, "a");
    assert_eq!(rt.state.modal, Modal::None, "the watchlist's keys stay on the watchlist");
    typed(&mut rt, "p");
    assert_eq!(rt.state.ui.view, ViewKind::Watchlist);
}

#[test]
fn import_previews_then_adds() {
    let mut rt = runtime(app(TWO, ""));
    typed(&mut rt, "i");
    assert_eq!(rt.state.modal, Modal::Import);
    rt.state.import = Some(rt.state.watchlist.preview_import("AK-47 | Redline, ft\nAK-47 | Vulcan, mw\n"));
    rt.invalidate();
    rt.frame(1.0 / 60.0);
    assert_eq!(rt.state.watchlist.len(), 2, "the preview changes nothing");
    press(&mut rt, Key::Enter);
    assert_eq!(rt.state.watchlist.len(), 3);
    assert_eq!(rt.state.modal, Modal::None);
}

#[test]
fn a_failed_refresh_keeps_the_last_prices_and_says_how_old_they_are() {
    let mut rt = runtime(app(TWO, ""));
    rt.state.book_at = Some(0.0);
    rt.state.now = 720.0;
    rt.state.receive(Msg::Prices { generation: 0, result: Err("API status 429".into()) });
    rt.state.now = 720.0;
    assert_eq!(rt.state.book.quote("AK-47 | Redline (Field-Tested)").price, Some(30.0));
    assert_eq!(rt.state.error_status().as_deref(), Some("API status 429. Showing data from 12 min ago."));
}

#[test]
fn a_repeated_line_still_gets_unique_rows() {
    let rt = runtime(app("AK-47 | Redline, ft\nAK-47 | Redline, ft\n", ""));
    assert_ne!(rt.state.rows[0].id, rt.state.rows[1].id);
    assert_eq!(rt.state.rows[0].name, rt.state.rows[1].name);
}

#[test]
fn an_answer_for_an_old_slug_is_dropped_and_frees_the_slot() {
    use skinpulse::logic::portfolio::Portfolio;
    let mut rt = runtime(app(TWO, "old"));
    rt.state.schedule.portfolio_loading = true;
    rt.state.generation = 1;
    rt.state.receive(Msg::Portfolio { generation: 0, result: Ok(Portfolio::default()) });
    assert!(rt.state.portfolio.is_none());
    assert!(!rt.state.schedule.portfolio_loading);
    assert_eq!(rt.state.schedule.portfolio_at, None, "the right request can still start");
}

#[test]
fn settings_refuse_to_save_an_empty_key() {
    let mut app = app(TWO, "");
    app.config.api_key = "real-key".into();
    let mut rt = runtime(app);
    typed(&mut rt, "s");
    assert_eq!(rt.state.modal, Modal::Setup);
    rt.state.setup_key = rune::TextEdit::new("");
    rt.invalidate();
    rt.frame(1.0 / 60.0);
    press(&mut rt, Key::Enter);
    assert_eq!(rt.state.modal, Modal::Setup, "still open");
    assert!(rt.state.dialog_error.is_some());
    assert_eq!(rt.state.config.api_key, "real-key");
}

#[test]
fn changing_the_slug_clears_the_old_portfolio() {
    use skinpulse::logic::portfolio::Portfolio;
    let mut app = app(TWO, "old");
    app.config.api_key = "key".into();
    app.portfolio = Some(Portfolio::default());
    let mut rt = runtime(app);
    typed(&mut rt, "s");
    rt.state.setup_slug = rune::TextEdit::new("new");
    rt.invalidate();
    rt.frame(1.0 / 60.0);
    press(&mut rt, Key::Enter);
    assert_eq!(rt.state.modal, Modal::None);
    assert_eq!(rt.state.config.portfolio_slug, "new");
    assert!(rt.state.portfolio.is_none());
    assert_eq!(rt.state.generation, 1);
}

#[test]
fn delete_takes_the_selected_line_when_two_read_the_same() {
    let (dir, app) = on_disk("AK-47 | Redline, ft\n# note\nAK-47 | Redline, Field-Tested\n");
    let mut rt = runtime(app);
    let second = rt.state.rows.iter().find(|r| r.index == 1).unwrap().id.clone();
    rt.state.table.select(second);
    typed(&mut rt, "d");
    press(&mut rt, Key::Enter);
    let saved = std::fs::read_to_string(dir.path().join("config/items.txt")).unwrap();
    assert_eq!(saved, "AK-47 | Redline, ft\n# note\n");
}

#[test]
fn sorting_keeps_each_repeated_line_its_own_id() {
    let mut rt = runtime(app("AK-47 | Redline, ft\nAK-47 | Redline, Field-Tested\n", ""));
    let by_index = |rt: &Runtime<App>, i| rt.state.rows.iter().find(|r| r.index == i).unwrap().id.clone();
    let first = by_index(&rt, 0);
    typed(&mut rt, "2");
    typed(&mut rt, "1");
    assert_eq!(by_index(&rt, 0), first);
}

#[test]
fn when_the_selected_row_goes_away_on_disk_the_cursor_moves_to_a_neighbour() {
    let (dir, app) = on_disk("AWP | Asiimov, bs\nAK-47 | Redline, ft\nAK-47 | Vulcan, mw\n");
    let mut rt = runtime(app);
    rt.state.table.select("AWP | Asiimov (Battle-Scarred)");
    std::fs::write(dir.path().join("config/items.txt"), "AK-47 | Redline, ft\nAK-47 | Vulcan, mw\n").unwrap();
    rt.state.items_mtime = None;
    rt.state.check_items_file();
    assert_eq!(rt.state.selected_row().unwrap().name, "AK-47 | Vulcan (Minimal Wear)");
}

#[test]
fn an_import_rechecks_against_a_file_changed_after_its_preview() {
    let (dir, app) = on_disk("AWP | Asiimov, bs\n");
    let mut rt = runtime(app);
    typed(&mut rt, "i");
    rt.state.import = Some(rt.state.watchlist.preview_import("AK-47 | Redline, ft\n"));
    rt.invalidate();
    rt.frame(1.0 / 60.0);
    let file = dir.path().join("config/items.txt");
    std::fs::write(&file, "AWP | Asiimov, bs\nAK-47 | Redline, ft\n").unwrap();
    rt.state.items_mtime = None;
    press(&mut rt, Key::Enter);
    assert_eq!(rt.state.watchlist.len(), 2, "no duplicate");
    assert_eq!(std::fs::read_to_string(&file).unwrap(), "AWP | Asiimov, bs\nAK-47 | Redline, ft\n");
}

fn on_disk(file: &str) -> (tempfile::TempDir, App) {
    let dir = tempfile::tempdir().unwrap();
    let paths = Paths { config_dir: dir.path().join("config"), cache_dir: dir.path().join("cache") };
    std::fs::create_dir_all(&paths.config_dir).unwrap();
    std::fs::write(paths.items_file(), file).unwrap();
    let mut app = App::new(Config::default(), Watchlist::load(&paths.items_file()).unwrap(), book(), default_ui());
    app.items_mtime = super::app::mtime(&paths.items_file());
    app.paths = Some(paths);
    (dir, app)
}

#[test]
fn editing_saves_at_once_and_keeps_comments() {
    let (dir, app) = on_disk("# my notes\nAWP | Asiimov, bs\n\n# keep\nAK-47 | Redline, ft\n");
    let mut rt = runtime(app);
    rt.state.table.select("AK-47 | Redline (Field-Tested)");
    typed(&mut rt, "d");
    press(&mut rt, Key::Enter);
    let saved = std::fs::read_to_string(dir.path().join("config/items.txt")).unwrap();
    assert_eq!(saved, "# my notes\nAWP | Asiimov, bs\n\n# keep\n");
}

#[test]
fn an_edit_on_disk_reloads() {
    let (dir, app) = on_disk("AWP | Asiimov, bs\n");
    let mut rt = runtime(app);
    assert_eq!(rt.state.rows.len(), 1);
    std::fs::write(dir.path().join("config/items.txt"), "AWP | Asiimov, bs\nAK-47 | Redline, ft\n").unwrap();
    rt.state.items_mtime = None;
    rt.state.check_items_file();
    assert_eq!(rt.state.rows.len(), 2);
}

#[test]
fn headless_runs_never_touch_the_network_or_files() {
    let mut app = app(TWO, "mine");
    app.config.api_key = "key".into();
    assert!(app.paths.is_none());
    let mut rt = runtime(app);
    typed(&mut rt, "r");
    assert!(!rt.state.schedule.loading(), "without paths, nothing starts");
}
