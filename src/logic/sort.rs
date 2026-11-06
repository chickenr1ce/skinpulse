//! Table ordering. Rows whose value is missing sink to the bottom in either direction, so a gap
//! never hides the top of an ascending or a descending list.

use std::cmp::Ordering;

use super::item::Item;
use super::portfolio::Holding;
use super::prices::PriceBook;

/// Display order as indexes into `items`. `column`: 0 name, 1 buff163, 2-5 avg 7/30/60/90, 6 trend.
pub fn sort_watchlist(items: &[Item], book: &PriceBook, column: usize, ascending: bool) -> Vec<usize> {
    let mut order: Vec<usize> = (0..items.len()).collect();
    order.sort_by(|&a, &b| {
        if column == 0 {
            return text(&items[a].market_hash_name(), &items[b].market_hash_name(), ascending);
        }
        let (a, b) = (watchlist_value(&items[a], book, column), watchlist_value(&items[b], book, column));
        numbers(a, b, ascending)
    });
    order
}

/// `column`: 0 name, 1 qty, 2 buy, 3 now, 4 total, 5 P&L, 6 ROI.
pub fn sort_portfolio(items: &[Holding], book: &PriceBook, column: usize, ascending: bool) -> Vec<usize> {
    let mut order: Vec<usize> = (0..items.len()).collect();
    order.sort_by(|&a, &b| {
        if column == 0 {
            return text(&items[a].market_hash_name, &items[b].market_hash_name, ascending);
        }
        let (a, b) = (portfolio_value(&items[a], book, column), portfolio_value(&items[b], book, column));
        numbers(a, b, ascending)
    });
    order
}

fn watchlist_value(item: &Item, book: &PriceBook, column: usize) -> Option<f64> {
    let quote = book.quote(&item.market_hash_name());
    match column {
        1 => quote.price,
        2 => quote.avg_7,
        3 => quote.avg_30,
        4 => quote.avg_60,
        5 => quote.avg_90,
        6 => quote.trend(),
        _ => None,
    }
}

fn portfolio_value(item: &Holding, book: &PriceBook, column: usize) -> Option<f64> {
    match column {
        1 => Some(item.holdings as f64),
        2 => item.avg_buy,
        3 => item.live_price(book),
        4 => item.total_value(book),
        5 => item.profit(book),
        6 => item.roi_pct(book),
        _ => None,
    }
}

fn text(a: &str, b: &str, ascending: bool) -> Ordering {
    ordered(a.to_lowercase().cmp(&b.to_lowercase()), ascending)
}

fn numbers(a: Option<f64>, b: Option<f64>, ascending: bool) -> Ordering {
    match (a, b) {
        (Some(a), Some(b)) => ordered(a.partial_cmp(&b).unwrap_or(Ordering::Equal), ascending),
        (Some(_), None) => Ordering::Less,
        (None, Some(_)) => Ordering::Greater,
        (None, None) => Ordering::Equal,
    }
}

fn ordered(order: Ordering, ascending: bool) -> Ordering {
    if ascending { order } else { order.reverse() }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::logic::prices::{ItemPrices, Quote};

    fn item(name: &str) -> Item {
        Item { name: name.into(), wear: None, stattrak: false, souvenir: false }
    }

    fn holding(name: &str, holdings: u32, avg_buy: Option<f64>, current: Option<f64>) -> Holding {
        Holding { market_hash_name: name.into(), holdings, avg_buy, current_price: current }
    }

    /// A, B and C in input order, with B the most valuable and C unknown to the book.
    fn watchlist_fixture() -> (Vec<Item>, PriceBook) {
        let items = [item("A | Skin"), item("B | Skin"), item("C | Skin")].to_vec();
        let mut book = PriceBook::default();
        book.insert(
            "A | Skin",
            ItemPrices {
                buff163: Quote {
                    price: Some(10.0),
                    avg_7: Some(11.0),
                    avg_30: Some(12.0),
                    avg_60: Some(13.0),
                    avg_90: Some(14.0),
                },
                skins: None,
            },
        );
        book.insert(
            "B | Skin",
            ItemPrices {
                buff163: Quote {
                    price: Some(30.0),
                    avg_7: Some(31.0),
                    avg_30: Some(32.0),
                    avg_60: Some(33.0),
                    avg_90: Some(34.0),
                },
                skins: None,
            },
        );
        (items, book)
    }

    #[test]
    fn sorts_watchlist_by_name_case_insensitively() {
        let items = [item("b | Skin"), item("A | Skin")];
        let book = PriceBook::default();
        assert_eq!(sort_watchlist(&items, &book, 0, true), [1, 0]);
        assert_eq!(sort_watchlist(&items, &book, 0, false), [0, 1]);
    }

    #[test]
    fn sorts_watchlist_by_each_price_column() {
        let (items, book) = watchlist_fixture();
        for column in 1..=5 {
            assert_eq!(sort_watchlist(&items, &book, column, true), [0, 1, 2], "column {column}");
            assert_eq!(sort_watchlist(&items, &book, column, false), [1, 0, 2], "column {column}");
        }
    }

    #[test]
    fn sorts_watchlist_by_trend() {
        let items = [item("A | Skin"), item("B | Skin")];
        let mut book = PriceBook::default();
        book.insert("A | Skin", ItemPrices { buff163: Quote { avg_7: Some(1.0), avg_90: Some(5.0), ..Quote::default() }, skins: None });
        book.insert("B | Skin", ItemPrices { buff163: Quote { avg_7: Some(9.0), avg_90: Some(5.0), ..Quote::default() }, skins: None });
        assert_eq!(sort_watchlist(&items, &book, 6, true), [0, 1]);
        assert_eq!(sort_watchlist(&items, &book, 6, false), [1, 0]);
        // A trend needs both averages; only one is not a value.
        book.insert("A | Skin", ItemPrices { buff163: Quote { avg_7: Some(1.0), ..Quote::default() }, skins: None });
        assert_eq!(sort_watchlist(&items, &book, 6, false), [1, 0]);
        assert_eq!(sort_watchlist(&items, &book, 6, true), [1, 0]);
    }

    #[test]
    fn missing_watchlist_values_sort_last_in_both_directions() {
        let (items, book) = watchlist_fixture();
        let ascending = sort_watchlist(&items, &book, 1, true);
        let descending = sort_watchlist(&items, &book, 1, false);
        assert_eq!(ascending.last(), Some(&2));
        assert_eq!(descending.last(), Some(&2));
    }

    #[test]
    fn equal_watchlist_keys_keep_input_order_in_both_directions() {
        let items = [item("A | Skin"), item("B | Skin"), item("C | Skin")];
        let mut book = PriceBook::default();
        for name in ["A | Skin", "B | Skin", "C | Skin"] {
            book.insert(name, ItemPrices { buff163: Quote { price: Some(7.0), ..Quote::default() }, skins: None });
        }
        assert_eq!(sort_watchlist(&items, &book, 1, true), [0, 1, 2]);
        assert_eq!(sort_watchlist(&items, &book, 1, false), [0, 1, 2]);
    }

    fn portfolio_fixture() -> (Vec<Holding>, PriceBook) {
        let items = [
            holding("A | Skin", 2, Some(100.0), Some(1.0)),
            holding("B | Skin", 5, Some(10.0), Some(1.0)),
            holding("C | Skin", 1, None, Some(1.0)),
        ]
        .to_vec();
        let mut book = PriceBook::default();
        book.insert("A | Skin", ItemPrices { buff163: Quote { price: Some(200.0), ..Quote::default() }, skins: None });
        book.insert("B | Skin", ItemPrices { buff163: Quote { price: Some(20.0), ..Quote::default() }, skins: None });
        (items, book)
    }

    #[test]
    fn sorts_portfolio_by_name_qty_and_buy() {
        let (items, book) = portfolio_fixture();
        assert_eq!(sort_portfolio(&items, &book, 0, false), [2, 1, 0]);
        assert_eq!(sort_portfolio(&items, &book, 1, true), [2, 0, 1]);
        assert_eq!(sort_portfolio(&items, &book, 1, false), [1, 0, 2]);
        assert_eq!(sort_portfolio(&items, &book, 2, true), [1, 0, 2]);
        assert_eq!(sort_portfolio(&items, &book, 2, false), [0, 1, 2]);
    }

    #[test]
    fn sorts_portfolio_by_now_total_profit_and_roi() {
        let (items, book) = portfolio_fixture();
        // Now: B 20, A 200, C has only its fallback price of 1.
        assert_eq!(sort_portfolio(&items, &book, 3, true), [2, 1, 0]);
        // Total: C 1, B 100, A 400.
        assert_eq!(sort_portfolio(&items, &book, 4, true), [2, 1, 0]);
        assert_eq!(sort_portfolio(&items, &book, 4, false), [0, 1, 2]);
        // P&L: C missing, B 50, A 200.
        assert_eq!(sort_portfolio(&items, &book, 5, true), [1, 0, 2]);
        assert_eq!(sort_portfolio(&items, &book, 5, false), [0, 1, 2]);
        // ROI: C missing, B 100%, A 100%.
        assert_eq!(sort_portfolio(&items, &book, 6, true), [0, 1, 2]);
        assert_eq!(sort_portfolio(&items, &book, 6, false), [0, 1, 2]);
    }

    #[test]
    fn missing_portfolio_values_sort_last_in_both_directions() {
        let (items, book) = portfolio_fixture();
        for column in [2, 5, 6] {
            assert_eq!(sort_portfolio(&items, &book, column, true).last(), Some(&2), "column {column}");
            assert_eq!(sort_portfolio(&items, &book, column, false).last(), Some(&2), "column {column}");
        }
    }

    #[test]
    fn unknown_columns_keep_input_order() {
        let (items, book) = watchlist_fixture();
        assert_eq!(sort_watchlist(&items, &book, 99, true), [0, 1, 2]);
        let (items, book) = portfolio_fixture();
        assert_eq!(sort_portfolio(&items, &book, 99, false), [0, 1, 2]);
    }
}
