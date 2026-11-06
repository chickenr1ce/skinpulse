//! The frame every screen sits in: view switcher and refresh status on top, key hints below.

use rune::{Cx, El, col, el, row, text};

use skinpulse::logic::config::ViewKind;

use super::app::App;
use super::theme::{GUTTER, Tokens};
use super::watchlist;

pub fn view(s: &App, cx: &mut Cx<App>) -> El {
    let t = Tokens::new(cx.system_dark());
    let body = col()
        .key("page")
        .w_full()
        .h_full()
        .min_h(0.0)
        .fill(t.kit.c.page)
        .child(top_bar(s, &t))
        .child(watchlist::view(s, &t))
        .child(hints(s, &t));
    rune_kit::root(body, [])
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
                .child(tab("Watchlist", s.ui.view == ViewKind::Watchlist, t))
                .child(tab("Portfolio", s.ui.view == ViewKind::Portfolio, t)),
        )
        .child(status(s, t))
}

fn tab(label: &'static str, selected: bool, t: &Tokens) -> El {
    let c = &t.kit.c;
    text(label)
        .key(label)
        .font(if selected { t.kit.ty.ui_medium } else { t.kit.ty.ui })
        .color(if selected { c.text_base } else { c.text_faint })
}

fn status(s: &App, t: &Tokens) -> El {
    let c = &t.kit.c;
    let line = if s.schedule.loading() {
        "Refreshing…".to_string()
    } else {
        match s.schedule.seconds_until_next(s.now) {
            Some(left) => {
                let left = left as u64;
                format!("Next {}:{:02}", left / 60, left % 60)
            }
            None => "No data yet".to_string(),
        }
    };
    let mut bar = row().key("status").gap(12.0).center_y();
    if let Some(error) = &s.error {
        bar = bar.child(text(error.clone()).font(t.kit.ty.text_small).color(t.down).truncate().shrink().min_w(0.0));
    }
    bar.child(text(line).font(t.number).color(c.text_muted))
}

fn hints(s: &App, t: &Tokens) -> El {
    let mut keys = row().key("keys").gap(16.0).center_y();
    for (key, what) in [("a", "add"), ("d", "delete"), ("i", "import"), ("e", "export"), ("r", "refresh"), ("p", "portfolio"), ("1–7", "sort"), ("q", "quit")] {
        keys = keys.child(
            row()
                .key(what)
                .gap(5.0)
                .center_y()
                .child(text(key).font(t.number).color(t.kit.c.text_muted))
                .child(text(what).font(t.kit.ty.text_small).color(t.kit.c.text_faint)),
        );
    }
    let position = s.table.cursor().and_then(|id| s.rows.iter().position(|r| r.id == id)).map_or(0, |i| i + 1);
    let count = format!("{position}/{}", s.rows.len());
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
