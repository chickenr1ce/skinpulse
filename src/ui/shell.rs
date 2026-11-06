//! The frame every screen sits in: view switcher and refresh status on top, key hints below.

use rune::{Cursor, Cx, El, col, el, row, text};

use skinpulse::logic::config::ViewKind;

use super::app::App;
use super::theme::{GUTTER, Tokens};
use super::{dialogs, portfolio, watchlist};

pub fn view(s: &App, cx: &mut Cx<App>) -> El {
    let t = Tokens::new(cx.system_dark());
    let body = col()
        .key("page")
        .w_full()
        .h_full()
        .min_h(0.0)
        .fill(t.kit.c.page)
        .child(top_bar(s, &t))
        .child(if s.ui.view == ViewKind::Watchlist { watchlist::view(s, &t) } else { portfolio::view(s, &t) })
        .child(hints(s, &t));
    let mut layer = Vec::new();
    dialogs::layer(s, &t, &mut layer);
    rune_kit::root(body, layer)
}

fn top_bar(s: &App, t: &Tokens) -> El {
    row()
        .key("top-bar")
        .w_full()
        .h(52.0)
        .px(GUTTER)
        .center_y()
        .justify_between()
        .child(
            row()
                .key("views")
                .gap(16.0)
                .center_y()
                .child(tab("Watchlist", ViewKind::Watchlist, s, t))
                .child(tab("Portfolio", ViewKind::Portfolio, s, t)),
        )
        .child(status(s, t))
}

fn tab(label: &'static str, view: ViewKind, s: &App, t: &Tokens) -> El {
    let c = &t.kit.c;
    let selected = s.ui.view == view;
    row()
        .key(label)
        .role("tab")
        .label(label)
        .focusable(true)
        .cursor(Cursor::Pointer)
        .on_press(move |s: &mut App| s.set_view(view))
        .child(text(label).font(if selected { t.kit.ty.ui_medium } else { t.kit.ty.ui }).color(if selected { c.text_base } else { c.text_faint }))
}

fn status(s: &App, t: &Tokens) -> El {
    let c = &t.kit.c;
    let mut bar = row().key("status").gap(12.0).center_y().min_w(0.0).shrink();
    if let Some(error) = s.error_status() {
        bar = bar.child(text(error).font(t.kit.ty.text_small).color(t.down).truncate().shrink().min_w(0.0));
    } else if let Some((notice, _)) = &s.notice {
        bar = bar.child(text(notice.clone()).font(t.kit.ty.text_small).color(c.text_muted).truncate().shrink().min_w(0.0));
    }
    bar.child(text(s.refresh_status()).font(t.number).color(c.text_muted).single_line())
}

fn hints(s: &App, t: &Tokens) -> El {
    let mut keys = row().key("keys").gap(16.0).center_y();
    let hints: &[(&str, &str)] = if s.ui.view == ViewKind::Watchlist {
        &[("a", "add"), ("d", "delete"), ("i", "import"), ("e", "export"), ("r", "refresh"), ("p", "portfolio"), ("1–7", "sort"), ("s", "settings"), ("q", "quit")]
    } else {
        &[("r", "refresh"), ("p", "watchlist"), ("1–7", "sort"), ("s", "settings"), ("q", "quit")]
    };
    for (key, what) in hints {
        keys = keys.child(
            row()
                .key(*what)
                .gap(5.0)
                .center_y()
                .child(text(*key).font(t.number).color(t.kit.c.text_muted))
                .child(text(*what).font(t.kit.ty.text_small).color(t.kit.c.text_faint)),
        );
    }
    let (cursor, total, at) = if s.ui.view == ViewKind::Watchlist {
        let at = s.table.cursor().and_then(|id| s.rows.iter().position(|r| r.id == id));
        (s.table.cursor(), s.rows.len(), at)
    } else {
        let at = s.portfolio_table.cursor().and_then(|id| s.holdings.iter().position(|(_, h)| h == id));
        (s.portfolio_table.cursor(), s.holdings.len(), at)
    };
    let count = match (cursor, at) {
        (Some(_), Some(at)) => format!("{}/{total}", at + 1),
        _ => format!("{total}"),
    };
    col()
        .key("footer")
        .w_full()
        .child(el().key("footer-rule").w_full().h(1.0).fill(t.rule))
        .child(
            row()
                .key("footer-row")
                .w_full()
                .h(38.0)
                .px(GUTTER)
                .center_y()
                .justify_between()
                .child(keys)
                .child(text(count).font(t.number).color(t.kit.c.text_muted)),
        )
}
