//! Market prices as the API returns them: whole cents scaled to euros, with missing values kept
//! missing so the UI can show `—` instead of inventing `0.00`.

use std::collections::BTreeMap;

use serde_json::{Map, Value};

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Quote {
    pub price: Option<f64>,
    pub avg_7: Option<f64>,
    pub avg_30: Option<f64>,
    pub avg_60: Option<f64>,
    pub avg_90: Option<f64>,
}

impl Quote {
    /// avg_7 minus avg_90 when both exist; matches the sparkline's direction.
    pub fn trend(&self) -> Option<f64> {
        match (self.avg_7, self.avg_90) {
            (Some(recent), Some(old)) => Some(recent - old),
            _ => None,
        }
    }

    pub fn sparkline(&self) -> Option<Sparkline> {
        let values = [self.avg_90, self.avg_60, self.avg_30, self.avg_7];
        let valid: Vec<f64> = values.iter().filter_map(|v| *v).filter(|v| *v > 0.0).collect();
        if valid.len() < 2 {
            return None;
        }
        let min = valid.iter().copied().fold(f64::INFINITY, f64::min);
        let max = valid.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        let mut heights = [None; 4];
        for (i, value) in values.iter().enumerate() {
            if let Some(v) = *value
                && v > 0.0
            {
                let height = if max == min { 4 } else { ((v - min) / (max - min) * 7.0) as u8 + 1 };
                heights[i] = Some(height.clamp(1, 8));
            }
        }
        let first = valid.first().copied().unwrap_or_default();
        let last = valid.last().copied().unwrap_or_default();
        let direction = if last > first {
            Delta::Up
        } else if last < first {
            Delta::Down
        } else {
            Delta::Flat
        };
        Some(Sparkline { heights, direction })
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct ItemPrices {
    pub buff163: Quote,
    pub skins: Option<f64>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct PriceBook(BTreeMap<String, ItemPrices>);

impl PriceBook {
    pub fn parse(body: &str) -> Result<PriceBook, String> {
        let data: Value = serde_json::from_str(body).map_err(|e| format!("Invalid API response: {e}"))?;
        let mut book = PriceBook::default();
        match data {
            Value::Array(entries) => {
                for entry in entries {
                    let Value::Object(entry) = entry else { continue };
                    let name = entry.get("market_hash_name").or_else(|| entry.get("name")).and_then(Value::as_str);
                    let Some(name) = name else { continue };
                    book.insert(name, item_prices(&entry));
                }
            }
            Value::Object(map) => {
                if let Some(error) = api_error(&map) {
                    return Err(error);
                }
                for (name, entry) in map {
                    let Value::Object(entry) = entry else { continue };
                    book.insert(name, item_prices(&entry));
                }
            }
            _ => return Err("Unexpected API response".to_string()),
        }
        Ok(book)
    }

    pub fn insert(&mut self, name: impl Into<String>, prices: ItemPrices) {
        self.0.insert(name.into(), prices);
    }

    pub fn get(&self, name: &str) -> Option<&ItemPrices> {
        self.0.get(name)
    }

    pub fn quote(&self, name: &str) -> Quote {
        self.get(name).map(|p| p.buff163).unwrap_or_default()
    }

    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.0.keys().map(String::as_str)
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

/// The API answers some auth errors with HTTP 200 and `{"status": false, "message": "..."}`, which
/// must surface as an error: an empty book used to mean every row silently rendered 0.00.
fn api_error(map: &Map<String, Value>) -> Option<String> {
    if map.get("status").and_then(Value::as_bool) != Some(false) {
        return None;
    }
    let message = map.get("message").and_then(Value::as_str);
    Some(message.map(str::to_string).unwrap_or_else(|| "Unexpected API response".to_string()))
}

fn item_prices(entry: &Map<String, Value>) -> ItemPrices {
    let mut prices = ItemPrices::default();
    let Some(Value::Array(providers)) = entry.get("prices") else { return prices };
    for provider in providers {
        let Value::Object(provider) = provider else { continue };
        let Some(key) = provider.get("provider_key").and_then(Value::as_str) else { continue };
        match key {
            "buff163" => {
                prices.buff163 = Quote {
                    price: cents(provider.get("price")),
                    avg_7: cents(provider.get("avg_7")),
                    avg_30: cents(provider.get("avg_30")),
                    avg_60: cents(provider.get("avg_60")),
                    avg_90: cents(provider.get("avg_90")),
                };
            }
            "skins" => prices.skins = cents(provider.get("price")),
            _ => {}
        }
    }
    prices
}

/// Whole cents to euros. Missing, null, zero, negative and non-numeric values stay missing.
fn cents(value: Option<&Value>) -> Option<f64> {
    let n = value?.as_f64()?;
    (n > 0.0).then(|| n / 100.0)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Delta {
    Up,
    Down,
    Flat,
}

/// Up when current > reference, Down when below, Flat when equal or either is missing.
pub fn delta(current: Option<f64>, reference: Option<f64>) -> Delta {
    match (current, reference) {
        (Some(current), Some(reference)) if current > reference => Delta::Up,
        (Some(current), Some(reference)) if current < reference => Delta::Down,
        _ => Delta::Flat,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Sparkline {
    pub heights: [Option<u8>; 4],
    pub direction: Delta,
}

#[cfg(test)]
mod tests {
    use super::*;

    const NAME: &str = "M4A1-S | Printstream (Field-Tested)";

    fn raw() -> String {
        format!(
            r#"[{{"market_hash_name":"{NAME}","prices":[
                {{"provider_key":"buff163","price":16679,"avg_7":16658,"avg_30":16992,"avg_60":16985,"avg_90":16724}},
                {{"provider_key":"skins","price":17000,"avg_7":16922}}
            ]}}]"#
        )
    }

    #[test]
    fn parses_the_real_fixture_into_euros() {
        let book = PriceBook::parse(&raw()).unwrap();
        assert_eq!(book.len(), 1);
        let prices = book.get(NAME).unwrap();
        assert_eq!(prices.buff163.price, Some(166.79));
        assert_eq!(prices.buff163.avg_7, Some(166.58));
        assert_eq!(prices.buff163.avg_30, Some(169.92));
        assert_eq!(prices.buff163.avg_60, Some(169.85));
        assert_eq!(prices.buff163.avg_90, Some(167.24));
        assert_eq!(prices.skins, Some(170.0));
    }

    #[test]
    fn missing_average_stays_missing_without_losing_the_price() {
        let body = r#"[{"name":"A","prices":[{"provider_key":"buff163","price":16679}]}]"#;
        let book = PriceBook::parse(body).unwrap();
        assert_eq!(book.quote("A").price, Some(166.79));
        assert_eq!(book.quote("A").avg_90, None);
    }

    #[test]
    fn missing_provider_leaves_every_field_missing() {
        let body = r#"[{"name":"A","prices":[{"provider_key":"skins","price":17000}]}]"#;
        let book = PriceBook::parse(body).unwrap();
        assert_eq!(book.quote("A"), Quote::default());
        assert_eq!(book.get("A").unwrap().skins, Some(170.0));
    }

    #[test]
    fn null_zero_negative_and_text_prices_are_none() {
        let body = r#"[{"name":"A","prices":[{"provider_key":"buff163","price":null,"avg_7":0,"avg_30":-5,"avg_60":"12.5","avg_90":true}]}]"#;
        let book = PriceBook::parse(body).unwrap();
        assert_eq!(book.quote("A"), Quote::default());
    }

    #[test]
    fn a_status_false_body_is_an_error_not_an_empty_book() {
        let body = r#"{"status":false,"message":"error.api_key_invalid_format"}"#;
        let err = PriceBook::parse(body).unwrap_err();
        assert!(err.contains("api_key_invalid_format"), "{err}");
        assert!(err != "Unexpected API response");
    }

    #[test]
    fn a_status_false_body_without_a_message_still_errors() {
        assert_eq!(PriceBook::parse(r#"{"status":false}"#), Err("Unexpected API response".to_string()));
    }

    #[test]
    fn parses_the_object_keyed_form() {
        let body = r#"{"AK-47 | Redline (Field-Tested)":{"prices":[{"provider_key":"buff163","price":1234}]}}"#;
        let book = PriceBook::parse(body).unwrap();
        assert_eq!(book.quote("AK-47 | Redline (Field-Tested)").price, Some(12.34));
    }

    #[test]
    fn skips_non_object_entries_and_nameless_array_entries() {
        let body = r#"[1,"nope",{"prices":[]},{"name":"A","prices":[]}]"#;
        let book = PriceBook::parse(body).unwrap();
        assert_eq!(book.len(), 1);
        assert_eq!(book.names().collect::<Vec<_>>(), ["A"]);
    }

    #[test]
    fn a_body_that_is_neither_array_nor_object_is_an_error() {
        assert!(PriceBook::parse("42").is_err());
        assert!(PriceBook::parse(r#""text""#).is_err());
        assert!(PriceBook::parse("not json").is_err());
    }

    #[test]
    fn names_are_sorted_and_lookup_of_an_absent_item_is_default() {
        let body = r#"[{"name":"B","prices":[]},{"name":"A","prices":[]}]"#;
        let book = PriceBook::parse(body).unwrap();
        assert_eq!(book.names().collect::<Vec<_>>(), ["A", "B"]);
        assert_eq!(book.quote("C"), Quote::default());
        assert!(!book.is_empty());
        assert!(PriceBook::default().is_empty());
    }

    #[test]
    fn trend_is_seven_day_minus_ninety_day() {
        let quote = Quote { avg_7: Some(166.58), avg_90: Some(167.24), ..Quote::default() };
        assert_eq!(quote.trend(), Some(166.58 - 167.24));
        assert_eq!(Quote::default().trend(), None);
        assert_eq!(Quote { avg_7: Some(1.0), ..Quote::default() }.trend(), None);
    }

    #[test]
    fn sparkline_orders_ninety_sixty_thirty_seven() {
        let quote = Quote {
            avg_7: Some(166.58),
            avg_30: Some(169.92),
            avg_60: Some(169.85),
            avg_90: Some(167.24),
            ..Quote::default()
        };
        let spark = quote.sparkline().unwrap();
        assert_eq!(spark.heights, [Some(2), Some(7), Some(8), Some(1)]);
        assert_eq!(spark.direction, Delta::Down);
    }

    #[test]
    fn sparkline_needs_two_valid_averages() {
        assert_eq!(Quote { avg_7: Some(1.0), ..Quote::default() }.sparkline(), None);
        assert_eq!(Quote::default().sparkline(), None);
    }

    #[test]
    fn sparkline_keeps_missing_slots_missing_and_flattens_equal_values() {
        let spark = Quote { avg_7: Some(5.0), avg_90: Some(5.0), ..Quote::default() }.sparkline().unwrap();
        assert_eq!(spark.heights, [Some(4), None, None, Some(4)]);
        assert_eq!(spark.direction, Delta::Flat);
    }

    #[test]
    fn sparkline_direction_uses_first_and_last_valid() {
        let rising = Quote { avg_7: Some(10.0), avg_30: Some(4.0), avg_60: Some(1.0), ..Quote::default() };
        assert_eq!(rising.sparkline().unwrap().direction, Delta::Up);
        let flat = Quote { avg_7: Some(3.0), avg_30: Some(1.0), avg_60: Some(3.0), ..Quote::default() };
        assert_eq!(flat.sparkline().unwrap().direction, Delta::Flat);
    }

    #[test]
    fn delta_compares_optionals() {
        assert_eq!(delta(Some(2.0), Some(1.0)), Delta::Up);
        assert_eq!(delta(Some(1.0), Some(2.0)), Delta::Down);
        assert_eq!(delta(Some(1.0), Some(1.0)), Delta::Flat);
        assert_eq!(delta(None, Some(1.0)), Delta::Flat);
        assert_eq!(delta(Some(1.0), None), Delta::Flat);
    }
}
