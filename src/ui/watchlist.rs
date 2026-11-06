//! The watchlist table.

use std::borrow::Cow;

use rune::{Align, Color, El, TextStyle, col, el, row, text};
use rune_kit::{Cell, Table, TableColumn, TableStyle};

use skinpulse::logic::prices::{Delta, Quote, delta};

use super::app::App;
use super::theme::{CELL_PAD, GUTTER, HEADER_HEIGHT, Tokens};

/// Column ids and titles, in the order the number keys sort them.
pub const COLUMNS: [(&str, &str); 7] = [
    ("name", "Item"),
    ("buff", "Buff163"),
    ("d7", "7d"),
    ("d30", "30d"),
    ("d60", "60d"),
    ("d90", "90d"),
    ("trend", "Trend"),
];

const NUMBER_WIDTH: f32 = 92.0;
const SPARK_BAR: f32 = 3.0;
const SPARK_UNIT: f32 = 1.75;

pub fn view(s: &App, t: &Tokens) -> El {
    let mut table = Table::new(|s: &App| &s.table, |s: &mut App| &mut s.table, |s: &App| s.rows.len(), |s: &App, i| Cow::Borrowed(s.rows[i].id.as_str()))
        .name("Watchlist")
        // The kit draws header dividers in the rule colour, so the header's underline is ours.
        .style(TableStyle { rule: Color::TRANSPARENT, ..t.table_style() });
    for (i, (id, title)) in COLUMNS.iter().enumerate() {
        let column = TableColumn::new(*id, *title).sortable().resizable(false);
        table = table.column(match i {
            0 => column.flex(1.0).min(240.0),
            6 => column.width(72.0).align(Align::End),
            _ => column.width(NUMBER_WIDTH).align(Align::End),
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
            let row_data = &s.rows[i];
            let quote = s.book.quote(&row_data.id);
            let body = match id {
                "name" => name_cell(&row_data.id, row_data.item.wear.as_deref(), font, base, muted),
                "buff" => number_cell(quote.price, number, base, faint),
                "d7" => avg_cell(&quote, quote.avg_7, number, &tone, faint),
                "d30" => avg_cell(&quote, quote.avg_30, number, &tone, faint),
                "d60" => avg_cell(&quote, quote.avg_60, number, &tone, faint),
                "d90" => avg_cell(&quote, quote.avg_90, number, &tone, faint),
                _ => spark_cell(&quote, number, &tone, faint),
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
    let underline = el().key("header-rule").pin(Some(GUTTER - CELL_PAD), Some(HEADER_HEIGHT - 1.0), Some(GUTTER - CELL_PAD), None).h(1.0).fill(rule).a11y_hidden();
    let mut page = col().key("watchlist").w_full().grow(1.0).min_h(0.0).px(GUTTER - CELL_PAD).child(table).child(underline);
    if s.rows.is_empty() {
        page = page.child(empty_state(t));
    }
    page
}

fn empty_state(t: &Tokens) -> El {
    col()
        .key("empty")
        .pin(Some(0.0), Some(HEADER_HEIGHT), Some(0.0), Some(0.0))
        .center()
        .gap(4.0)
        .child(text("Nothing on your watchlist yet").font(t.kit.ty.ui_medium).color(t.kit.c.text_base))
        .child(text("Press a to add a skin, or i to import a list.").font(t.kit.ty.text_small).color(t.kit.c.text_muted))
}

/// A cell's content over the hairline that divides rows. The line reaches past the cell's padding,
/// so the cells of a row join into one rule.
fn ruled(body: El, end: bool, rule: Color) -> El {
    let cell = row().w_full().h_full().center_y().min_w(0.0);
    let cell = if end { cell.justify_end() } else { cell };
    cell.child(body).child(el().pin(Some(-CELL_PAD), None, Some(-CELL_PAD), Some(0.0)).h(1.0).fill(rule).a11y_hidden())
}

/// The item's name with its wear quieter beside it.
fn name_cell(hash_name: &str, wear: Option<&str>, font: TextStyle, base: Color, muted: Color) -> El {
    let suffix = wear.map(|w| format!(" ({w})"));
    let name = suffix.as_deref().and_then(|s| hash_name.strip_suffix(s)).unwrap_or(hash_name);
    let mut line = row().gap(6.0).center_y().min_w(0.0).shrink().child(text(name.to_string()).font(font).color(base).truncate().shrink().min_w(0.0).help_when_truncated(hash_name.to_string()));
    if let Some(wear) = wear {
        line = line.child(text(wear.to_string()).font(font).color(muted).single_line());
    }
    line
}

fn money(v: Option<f64>) -> String {
    v.map_or("—".to_string(), |v| format!("{v:.2}"))
}

fn number_cell(v: Option<f64>, font: TextStyle, color: Color, missing: Color) -> El {
    text(money(v)).font(font).color(if v.is_some() { color } else { missing }).single_line()
}

fn avg_cell(quote: &Quote, avg: Option<f64>, font: TextStyle, tone: &dyn Fn(Delta) -> Color, missing: Color) -> El {
    number_cell(avg, font, tone(delta(quote.price, avg)), missing)
}

/// Four bars, 90 days ago on the left to the last 7 days on the right.
fn spark_cell(quote: &Quote, font: TextStyle, tone: &dyn Fn(Delta) -> Color, missing: Color) -> El {
    let Some(spark) = quote.sparkline() else {
        return text("—").font(font).color(missing);
    };
    let color = tone(spark.direction);
    let mut bars = row().gap(2.0).h(8.0 * SPARK_UNIT).items_end();
    for height in spark.heights {
        bars = bars.child(match height {
            Some(h) => el().w(SPARK_BAR).h(f32::from(h) * SPARK_UNIT).radius(1.0).fill(color),
            None => el().w(SPARK_BAR).h(1.0).fill(missing),
        });
    }
    bars
}
