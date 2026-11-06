//! The PriceEmpire portfolio: its summary totals in euros, and the holdings the table lists.

use serde_json::{Map, Value};

use super::prices::{Delta, PriceBook};

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Summary {
    pub name: String,
    pub total_value: f64,
    pub total_profit: f64,
    pub total_roi: f64,
    pub change_24h: f64,
    pub change_24h_pct: f64,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Holding {
    pub market_hash_name: String,
    pub holdings: u32,
    pub avg_buy: Option<f64>,
    pub current_price: Option<f64>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Portfolio {
    pub summary: Summary,
    pub items: Vec<Holding>,
}

impl Portfolio {
    pub fn parse(body: &str, slug: &str) -> Result<Portfolio, String> {
        let data: Value = serde_json::from_str(body).map_err(|e| format!("Invalid API response: {e}"))?;
        let Value::Object(map) = data else { return Err("Unexpected API response".to_string()) };
        if let Some(error) = api_error(&map) {
            return Err(error);
        }

        let stats = map.get("stats").and_then(Value::as_object);
        let name = map
            .get("portfolio")
            .and_then(Value::as_object)
            .and_then(|portfolio| portfolio.get("name"))
            .and_then(Value::as_str)
            .unwrap_or(slug);
        let summary = Summary {
            name: name.to_string(),
            total_value: euros(stats, "totalValue"),
            total_profit: euros(stats, "totalProfit"),
            total_roi: plain(stats, "totalROI"),
            change_24h: euros(stats, "change24h"),
            change_24h_pct: plain(stats, "change24hPercentage"),
        };

        let items = map
            .get("items")
            .and_then(Value::as_array)
            .map(|items| items.iter().filter_map(holding).collect())
            .unwrap_or_default();
        Ok(Portfolio { summary, items })
    }
}

impl Holding {
    /// buff163 price from the book, else current_price.
    pub fn live_price(&self, book: &PriceBook) -> Option<f64> {
        book.quote(&self.market_hash_name).price.or(self.current_price)
    }

    /// live * holdings.
    pub fn total_value(&self, book: &PriceBook) -> Option<f64> {
        self.live_price(book).map(|live| live * self.holdings as f64)
    }

    /// (live - avg_buy) * holdings.
    pub fn profit(&self, book: &PriceBook) -> Option<f64> {
        match (self.live_price(book), self.avg_buy) {
            (Some(live), Some(avg_buy)) => Some((live - avg_buy) * self.holdings as f64),
            _ => None,
        }
    }

    /// (live - avg_buy)/avg_buy*100, None when avg_buy missing or 0.
    pub fn roi_pct(&self, book: &PriceBook) -> Option<f64> {
        match (self.live_price(book), self.avg_buy) {
            (Some(live), Some(avg_buy)) if avg_buy != 0.0 => Some((live - avg_buy) / avg_buy * 100.0),
            _ => None,
        }
    }
}

/// Above +0.01 is Up, below -0.01 is Down, otherwise Flat. Missing is Flat.
pub fn value_delta(v: Option<f64>) -> Delta {
    match v {
        Some(v) if v > 0.01 => Delta::Up,
        Some(v) if v < -0.01 => Delta::Down,
        _ => Delta::Flat,
    }
}

fn api_error(map: &Map<String, Value>) -> Option<String> {
    if map.get("status").and_then(Value::as_bool) != Some(false) {
        return None;
    }
    let message = map.get("message").and_then(Value::as_str);
    Some(message.map(str::to_string).unwrap_or_else(|| "Unexpected API response".to_string()))
}

fn euros(stats: Option<&Map<String, Value>>, key: &str) -> f64 {
    stats.and_then(|stats| stats.get(key)).and_then(Value::as_f64).map_or(0.0, |v| v / 100.0)
}

fn plain(stats: Option<&Map<String, Value>>, key: &str) -> f64 {
    stats.and_then(|stats| stats.get(key)).and_then(Value::as_f64).unwrap_or(0.0)
}

fn holding(item: &Value) -> Option<Holding> {
    let item = item.as_object()?;
    let stats = item.get("stats").and_then(Value::as_object);
    let holdings = stats
        .and_then(|stats| stats.get("holdings"))
        .and_then(Value::as_f64)
        .filter(|n| *n > 0.0)
        .map_or(0, |n| n.min(u32::MAX as f64) as u32);
    let avg_buy = stats.and_then(|stats| stats.get("avgBuyPrice")).and_then(numeric_cents);
    Some(Holding {
        market_hash_name: item.get("market_hash_name").and_then(Value::as_str).unwrap_or_default().to_string(),
        holdings,
        avg_buy,
        current_price: item.get("currentPrice").and_then(numeric_cents),
    })
}

fn numeric_cents(value: &Value) -> Option<f64> {
    value.as_f64().map(|n| n / 100.0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::logic::prices::{ItemPrices, Quote};

    const NAME: &str = "AK-47 | Redline (Field-Tested)";

    fn body() -> &'static str {
        r#"{
            "portfolio": {"name": "Main"},
            "stats": {"totalValue": 123456, "totalProfit": 2345, "totalROI": 12.5, "change24h": -678, "change24hPercentage": -0.55},
            "items": [
                {"market_hash_name": "AK-47 | Redline (Field-Tested)", "currentPrice": 16679, "stats": {"holdings": 3, "avgBuyPrice": 15000}},
                {"market_hash_name": "No Stats"}
            ]
        }"#
    }

    #[test]
    fn parses_summary_and_holdings() {
        let portfolio = Portfolio::parse(body(), "slug").unwrap();
        assert_eq!(portfolio.summary.name, "Main");
        assert_eq!(portfolio.summary.total_value, 1234.56);
        assert_eq!(portfolio.summary.total_profit, 23.45);
        assert_eq!(portfolio.summary.total_roi, 12.5);
        assert_eq!(portfolio.summary.change_24h, -6.78);
        assert_eq!(portfolio.summary.change_24h_pct, -0.55);
        assert_eq!(portfolio.items.len(), 2);
        assert_eq!(
            portfolio.items[0],
            Holding { market_hash_name: NAME.into(), holdings: 3, avg_buy: Some(150.0), current_price: Some(166.79) }
        );
        assert_eq!(
            portfolio.items[1],
            Holding { market_hash_name: "No Stats".into(), holdings: 0, avg_buy: None, current_price: None }
        );
    }

    #[test]
    fn falls_back_to_the_slug_and_zeroes_missing_stats() {
        let portfolio = Portfolio::parse(r#"{"items":[]}"#, "my-slug").unwrap();
        assert_eq!(portfolio.summary, Summary { name: "my-slug".into(), ..Summary::default() });
        assert!(portfolio.items.is_empty());
    }

    #[test]
    fn a_status_false_body_is_an_error() {
        let err = Portfolio::parse(r#"{"status": false, "message": "no portfolio"}"#, "slug").unwrap_err();
        assert_eq!(err, "no portfolio");
        assert!(Portfolio::parse(r#"{"status": false}"#, "slug").is_err());
    }

    #[test]
    fn a_non_object_body_is_an_error() {
        assert!(Portfolio::parse("[]", "slug").is_err());
        assert!(Portfolio::parse("not json", "slug").is_err());
    }

    #[test]
    fn a_book_price_beats_the_holdings_own_current_price() {
        let holding = Holding { market_hash_name: NAME.into(), holdings: 3, avg_buy: Some(150.0), current_price: Some(1.0) };
        let mut book = PriceBook::default();
        book.insert(NAME, ItemPrices { buff163: Quote { price: Some(200.0), ..Quote::default() }, ..ItemPrices::default() });
        assert_eq!(holding.live_price(&book), Some(200.0));
        assert_eq!(holding.total_value(&book), Some(600.0));
        assert_eq!(holding.profit(&book), Some(150.0));
        assert_eq!(holding.roi_pct(&book), Some((200.0 - 150.0) / 150.0 * 100.0));
    }

    #[test]
    fn falls_back_to_the_holding_current_price() {
        let holding = Holding { market_hash_name: NAME.into(), holdings: 2, avg_buy: Some(100.0), current_price: Some(166.79) };
        assert_eq!(holding.live_price(&PriceBook::default()), Some(166.79));
        assert_eq!(holding.total_value(&PriceBook::default()), Some(333.58));
        let profit = holding.profit(&PriceBook::default()).unwrap();
        assert!((profit - 133.58).abs() < 1e-9, "{profit}");
    }

    #[test]
    fn a_present_zero_stays_a_number() {
        let body = r#"{"items":[{"market_hash_name":"X","currentPrice":0,"stats":{"holdings":1,"avgBuyPrice":0}}]}"#;
        let portfolio = Portfolio::parse(body, "slug").unwrap();
        let holding = &portfolio.items[0];
        assert_eq!(holding.current_price, Some(0.0));
        assert_eq!(holding.avg_buy, Some(0.0));
        assert_eq!(holding.roi_pct(&PriceBook::default()), None);
    }

    #[test]
    fn missing_inputs_make_the_optional_totals_none() {
        let no_avg = Holding { market_hash_name: NAME.into(), holdings: 1, avg_buy: None, current_price: Some(10.0) };
        assert_eq!(no_avg.profit(&PriceBook::default()), None);
        assert_eq!(no_avg.roi_pct(&PriceBook::default()), None);
        let no_live = Holding { market_hash_name: NAME.into(), holdings: 1, avg_buy: Some(10.0), current_price: None };
        assert_eq!(no_live.total_value(&PriceBook::default()), None);
        assert_eq!(no_live.profit(&PriceBook::default()), None);
        assert_eq!(no_live.roi_pct(&PriceBook::default()), None);
    }

    #[test]
    fn zero_average_buy_has_no_roi() {
        let holding = Holding { market_hash_name: NAME.into(), holdings: 1, avg_buy: Some(0.0), current_price: Some(10.0) };
        assert_eq!(holding.roi_pct(&PriceBook::default()), None);
    }

    #[test]
    fn value_delta_has_a_one_cent_dead_zone() {
        assert_eq!(value_delta(Some(0.02)), Delta::Up);
        assert_eq!(value_delta(Some(0.01)), Delta::Flat);
        assert_eq!(value_delta(Some(-0.02)), Delta::Down);
        assert_eq!(value_delta(Some(-0.01)), Delta::Flat);
        assert_eq!(value_delta(None), Delta::Flat);
    }
}
