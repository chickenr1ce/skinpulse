//! The portfolio: a summary line over the holdings table.

use std::borrow::Cow;

use rune::{Align, Color, El, col, el, row, text};
use rune_kit::{Cell, Table, TableColumn, TableStyle};

use skinpulse::logic::portfolio::{Summary, value_delta};
use skinpulse::logic::prices::Delta;

use super::app::App;
use super::theme::{CELL_PAD, GUTTER, HEADER_HEIGHT, Tokens};
use super::watchlist::{money, number_cell, ruled, track_height};

/// Column ids and titles, in the order the number keys sort them.
pub const COLUMNS: [(&str, &str); 7] = [
    ("name", "Item"),
    ("qty", "Qty"),
    ("buy", "Buy"),
    ("now", "Now"),
    ("total", "Total"),
    ("pl", "P&L"),
    ("roi", "ROI"),
];

pub fn view(s: &App, t: &Tokens) -> El {
    let Some(portfolio) = &s.portfolio else {
        return placeholder(s, t);
    };
    let mut table = Table::new(|s: &App| &s.portfolio_table, |s: &mut App| &mut s.portfolio_table, |s: &App| s.holdings.len(), |s: &App, i| Cow::Borrowed(s.holdings[i].1.as_str()))
        .name("Portfolio")
        .style(TableStyle { rule: Color::TRANSPARENT, ..t.table_style() });
    for (i, (id, title)) in COLUMNS.iter().enumerate() {
        let column = TableColumn::new(*id, *title).sortable().resizable(false);
        table = table.column(match i {
            0 => column.flex(1.0).min(220.0),
            1 => column.width(56.0).align(Align::End),
            _ => column.width(92.0).align(Align::End),
        });
    }
    let (rule, up, down, muted, base, faint, font, number) =
        (t.rule, t.up, t.down, t.kit.c.text_muted, t.kit.c.text_base, t.kit.c.text_faint, t.kit.ty.text_small, t.number);
    let table = table
        .cell(move |s: &App, i, id| {
            let tone = |d: Delta| match d {
                Delta::Up => up,
                Delta::Down => down,
                Delta::Flat => muted,
            };
            let Some(portfolio) = &s.portfolio else { return Cell::text("") };
            let holding = &portfolio.items[s.holdings[i].0];
            let book = &s.book;
            let signed = |v: Option<f64>, suffix: &str| {
                let shown = v.map_or("—".to_string(), |v| format!("{v:+.2}{suffix}"));
                text(shown).font(number).color(if v.is_some() { tone(value_delta(v)) } else { faint }).single_line()
            };
            let body = match id {
                "name" => text(holding.market_hash_name.clone()).font(font).color(base).truncate().shrink().min_w(0.0).help_when_truncated(holding.market_hash_name.clone()),
                "qty" => text(holding.holdings.to_string()).font(number).color(base).single_line(),
                "buy" => number_cell(holding.avg_buy, number, muted, faint),
                "now" => number_cell(holding.live_price(book), number, base, faint),
                "total" => number_cell(holding.total_value(book), number, base, faint),
                "pl" => signed(holding.profit(book), ""),
                _ => signed(holding.roi_pct(book), "%"),
            };
            Cell::el(ruled(body, id != "name", rule))
        })
        .on_sort(|s: &mut App, id, _, _| {
            if let Some(column) = COLUMNS.iter().position(|(c, _)| *c == id) {
                s.sort_by(column);
            }
        })
        .build(s, &t.kit)
        .grow(1.0)
        .min_h(0.0);
    let inset = GUTTER - CELL_PAD;
    let underline = el().key("header-rule").pin(Some(inset), Some(HEADER_HEIGHT - 1.0), Some(inset), None).h(1.0).fill(rule).a11y_hidden();
    col()
        .key("portfolio")
        .w_full()
        .grow(1.0)
        .min_h(0.0)
        .child(summary(&portfolio.summary, t))
        .child(col().key("holdings").w_full().grow(1.0).min_h(0.0).px(inset).on_layout(track_height).child(table).child(underline))
}

fn summary(summary: &Summary, t: &Tokens) -> El {
    let fact = |label: &'static str, value: String, color: Color| {
        col()
            .key(label)
            .gap(2.0)
            .child(text(label).font(t.kit.ty.small).color(t.kit.c.text_faint))
            .child(text(value).font(t.number).color(color).single_line())
    };
    let tone = |v: f64| match value_delta(Some(v)) {
        Delta::Up => t.up,
        Delta::Down => t.down,
        Delta::Flat => t.kit.c.text_muted,
    };
    row()
        .key("summary")
        .w_full()
        .px(GUTTER)
        .pb(14.0)
        .gap(32.0)
        .child(fact("Portfolio", summary.name.clone(), t.kit.c.text_base))
        .child(fact("Value", format!("€{}", money(Some(summary.total_value))), t.kit.c.text_base))
        .child(fact("P&L", signed_euros(summary.total_profit, summary.total_roi), tone(summary.total_profit)))
        .child(fact("24h", signed_euros(summary.change_24h, summary.change_24h_pct), tone(summary.change_24h)))
}

fn signed_euros(value: f64, percent: f64) -> String {
    let sign = if value < 0.0 { '-' } else { '+' };
    format!("{sign}€{:.2} ({percent:+.2}%)", value.abs())
}

fn placeholder(s: &App, t: &Tokens) -> El {
    let line = if s.schedule.portfolio_loading { "Loading your portfolio…" } else { "No portfolio data yet" };
    col()
        .key("portfolio-empty")
        .w_full()
        .grow(1.0)
        .center()
        .gap(4.0)
        .child(text(line).font(t.kit.ty.ui_medium).color(t.kit.c.text_base))
        .child(text("Press r to refresh.").font(t.kit.ty.text_small).color(t.kit.c.text_muted))
}
