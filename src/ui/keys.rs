//! The key map. Keys reach this only when no text field took them.

use rune::{Key, KeyEvent, Tx};
use rune_kit::TableState;
use skinpulse::logic::config::ViewKind;

use super::app::{App, Modal};
use super::dialogs;
use super::theme::ROW_HEIGHT;

pub fn on_key(s: &mut App, ev: &KeyEvent, tx: &mut Tx) -> bool {
    if s.modal != Modal::None {
        return false;
    }
    let page = ((s.list_height / ROW_HEIGHT).floor() as usize).max(1);
    if ev.is_command('d') {
        move_cursor(s, tx, Move::By((page / 2).max(1) as isize));
        return true;
    }
    if ev.is_command('u') {
        move_cursor(s, tx, Move::By(-((page / 2).max(1) as isize)));
        return true;
    }
    match &ev.key {
        Key::Up => move_cursor(s, tx, Move::By(-1)),
        Key::Down => move_cursor(s, tx, Move::By(1)),
        Key::PageUp => move_cursor(s, tx, Move::By(-(page as isize))),
        Key::PageDown => move_cursor(s, tx, Move::By(page as isize)),
        Key::Home => move_cursor(s, tx, Move::Top),
        Key::End => move_cursor(s, tx, Move::Bottom),
        Key::Text(t) => {
            let mut chars = t.chars();
            let (Some(c), None) = (chars.next(), chars.next()) else { return false };
            return letter(s, c, tx);
        }
        _ => return false,
    }
    true
}

fn letter(s: &mut App, c: char, tx: &mut Tx) -> bool {
    let watchlist = s.ui.view == ViewKind::Watchlist;
    match c {
        'q' => tx.quit(),
        'r' => s.refresh_now(),
        'p' => s.set_view(if watchlist { ViewKind::Portfolio } else { ViewKind::Watchlist }),
        's' => s.open_setup(),
        'g' => move_cursor(s, tx, Move::Top),
        'G' => move_cursor(s, tx, Move::Bottom),
        '1'..='7' => s.sort_by(c as usize - '1' as usize),
        'a' if watchlist => s.open_add(),
        'd' if watchlist => dialogs::ask_delete(s),
        'i' if watchlist => s.modal = Modal::Import,
        'e' if watchlist => s.modal = Modal::Export,
        _ => return false,
    }
    true
}

enum Move {
    By(isize),
    Top,
    Bottom,
}

fn move_cursor(s: &mut App, tx: &mut Tx, to: Move) {
    let (ids, table): (Vec<&str>, &mut TableState) = if s.ui.view == ViewKind::Watchlist {
        (s.rows.iter().map(|r| r.id.as_str()).collect(), &mut s.table)
    } else {
        (s.holdings.iter().map(|(_, id)| id.as_str()).collect(), &mut s.portfolio_table)
    };
    if ids.is_empty() {
        return;
    }
    let last = ids.len() - 1;
    let at = table.cursor().and_then(|id| ids.iter().position(|i| *i == id));
    let target = match to {
        Move::Top => 0,
        Move::Bottom => last,
        Move::By(n) => match at {
            Some(at) => at.saturating_add_signed(n).min(last),
            None if n < 0 => last,
            None => 0,
        },
    };
    table.reveal(ids[target].to_string(), tx);
}
