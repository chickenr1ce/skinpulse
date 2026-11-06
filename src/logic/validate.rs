//! Checking a hand-typed item against the price book, and turning API names back into items.

use super::item::Item;
use super::prices::{ItemPrices, PriceBook};

#[derive(Clone, Debug, PartialEq)]
pub enum Validation {
    Found(ItemPrices),
    NotFound { similar: Vec<String> },
}

pub fn validate_item(item: &Item, book: &PriceBook) -> Validation {
    let market_name = item.market_hash_name();
    if let Some(prices) = book.get(&market_name) {
        return Validation::Found(*prices);
    }

    let (weapon_part, skin_part) = match item.name.split_once(" | ") {
        Some((weapon, skin)) => (weapon.to_lowercase(), skin.to_lowercase()),
        None => (String::new(), String::new()),
    };
    let mut similar = Vec::new();
    // Sorted names make the capped suggestion list deterministic across runs.
    for api_name in book.names() {
        if !weapon_part.is_empty() && !api_name.to_lowercase().contains(&weapon_part) {
            continue;
        }
        let (api_stattrak, api_souvenir) = prefixes(api_name);
        if item.stattrak != api_stattrak || item.souvenir != api_souvenir {
            continue;
        }
        if let Some((_, api_skin)) = api_name.split_once(" | ")
            && similar_names(&skin_part, strip_wear(api_skin))
        {
            similar.push(api_name.to_string());
            if similar.len() >= 5 {
                break;
            }
        }
    }
    Validation::NotFound { similar }
}

pub fn apply_suggestion(api_name: &str, stattrak: bool, souvenir: bool) -> Item {
    Item { stattrak, souvenir, ..parse_api_name(api_name) }
}

pub fn parse_api_name(api_name: &str) -> Item {
    let (rest, stattrak, souvenir) = strip_prefixes(api_name);
    let rest = rest.trim_start_matches(['★', ' ']).trim();
    let (name, wear) = split_wear(rest);
    Item { name: name.to_string(), wear: wear.map(str::to_string), stattrak, souvenir }
}

/// The (StatTrak, Souvenir) flags carried by an API market hash name.
fn prefixes(name: &str) -> (bool, bool) {
    let (_, stattrak, souvenir) = strip_prefixes(name);
    (stattrak, souvenir)
}

/// Peels `Souvenir ` and `StatTrak™ ` in whichever order they appear.
fn strip_prefixes(mut rest: &str) -> (&str, bool, bool) {
    let (mut stattrak, mut souvenir) = (false, false);
    loop {
        if !souvenir && let Some(after) = strip_prefix_ignore_case(rest, "Souvenir ") {
            souvenir = true;
            rest = after.trim_start();
        } else if !stattrak && let Some(after) = strip_prefix_ignore_case(rest, "StatTrak™ ") {
            stattrak = true;
            rest = after.trim_start();
        } else {
            break;
        }
    }
    (rest, stattrak, souvenir)
}

fn strip_prefix_ignore_case<'a>(s: &'a str, prefix: &str) -> Option<&'a str> {
    let head = s.get(..prefix.len())?;
    head.eq_ignore_ascii_case(prefix).then(|| &s[prefix.len()..])
}

/// Splits a trailing `(...)` off as the wear, matching the API's market hash names.
fn split_wear(rest: &str) -> (&str, Option<&str>) {
    let trimmed = rest.trim();
    if let Some(open) = trimmed.rfind('(')
        && let Some(inner) = trimmed[open + 1..].strip_suffix(')')
        && !inner.trim().is_empty()
        && !inner.contains(')')
    {
        let name = trimmed[..open].trim();
        if !name.is_empty() {
            return (name, Some(inner.trim()));
        }
    }
    (trimmed, None)
}

/// Removes a wear suffix such as ` (Field-Tested)` from a skin name.
fn strip_wear(skin: &str) -> &str {
    let trimmed = skin.trim_end();
    if trimmed.ends_with(')')
        && let Some(open) = trimmed.find('(')
    {
        return trimmed[..open].trim();
    }
    skin.trim()
}

fn similar_names(a: &str, b: &str) -> bool {
    let (a, b) = (normalize(a), normalize(b));
    if a.is_empty() || b.is_empty() {
        return false;
    }
    if a == b || a.contains(&b) || b.contains(&a) {
        return true;
    }
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    ratio(&a, &b) > 0.8
}

fn normalize(s: &str) -> String {
    s.chars().filter(|c| !c.is_whitespace() && *c != '\'' && *c != '-').flat_map(char::to_lowercase).collect()
}

/// difflib.SequenceMatcher(None, a, b).ratio(), i.e. 2 * matched chars / total chars.
fn ratio(a: &[char], b: &[char]) -> f64 {
    let mut total = 0;
    let mut queue = vec![(0, a.len(), 0, b.len())];
    while let Some((alo, ahi, blo, bhi)) = queue.pop() {
        let (i, j, size) = longest_match(a, b, alo, ahi, blo, bhi);
        if size == 0 {
            continue;
        }
        total += size;
        if alo < i && blo < j {
            queue.push((alo, i, blo, j));
        }
        if i + size < ahi && j + size < bhi {
            queue.push((i + size, ahi, j + size, bhi));
        }
    }
    if a.is_empty() && b.is_empty() {
        return 1.0;
    }
    2.0 * total as f64 / (a.len() + b.len()) as f64
}

/// Longest common block; ties go to the earliest position in `a`, then in `b`, as difflib does.
fn longest_match(a: &[char], b: &[char], alo: usize, ahi: usize, blo: usize, bhi: usize) -> (usize, usize, usize) {
    let (mut best_i, mut best_j, mut best_size) = (alo, blo, 0);
    let mut previous = vec![0usize; b.len() + 1];
    for (i, &a_char) in a.iter().enumerate().take(ahi).skip(alo) {
        let mut current = vec![0usize; b.len() + 1];
        for j in blo..bhi {
            if a_char == b[j] {
                let size = previous[j] + 1;
                current[j + 1] = size;
                if size > best_size {
                    best_i = i + 1 - size;
                    best_j = j + 1 - size;
                    best_size = size;
                }
            }
        }
        previous = current;
    }
    (best_i, best_j, best_size)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::logic::prices::{ItemPrices, Quote};

    fn item(name: &str, wear: Option<&str>, stattrak: bool, souvenir: bool) -> Item {
        Item { name: name.into(), wear: wear.map(Into::into), stattrak, souvenir }
    }

    fn book(names: &[&str]) -> PriceBook {
        let mut book = PriceBook::default();
        for name in names {
            book.insert(*name, ItemPrices { buff163: Quote { price: Some(1.0), ..Quote::default() }, skins: None });
        }
        book
    }

    #[test]
    fn a_known_item_is_found_with_its_prices() {
        let mut book = PriceBook::default();
        let prices = ItemPrices { buff163: Quote { price: Some(166.79), ..Quote::default() }, skins: Some(170.0) };
        book.insert("AK-47 | Redline (Field-Tested)", prices);
        let found = validate_item(&item("AK-47 | Redline", Some("Field-Tested"), false, false), &book);
        assert_eq!(found, Validation::Found(prices));
    }

    #[test]
    fn suggestions_are_sorted_and_skip_stattrak_and_souvenir_mismatches() {
        let book = book(&[
            "AK-47 | Redline (Minimal Wear)",
            "AK-47 | Redline (Field-Tested)",
            "AK-47 | Case Hardened (Field-Tested)",
            "StatTrak™ AK-47 | Redline (Field-Tested)",
            "Souvenir AK-47 | Redline (Field-Tested)",
            "M4A1-S | Printstream (Field-Tested)",
        ]);
        let found = validate_item(&item("AK-47 | Redline", None, false, false), &book);
        assert_eq!(
            found,
            Validation::NotFound {
                similar: vec!["AK-47 | Redline (Field-Tested)".into(), "AK-47 | Redline (Minimal Wear)".into()]
            }
        );
    }

    #[test]
    fn stattrak_items_only_get_stattrak_suggestions() {
        let book = book(&[
            "AK-47 | Redline (Field-Tested)",
            "StatTrak™ AK-47 | Redline (Minimal Wear)",
            "StatTrak™ AK-47 | Redline (Field-Tested)",
        ]);
        let found = validate_item(&item("AK-47 | Redline", None, true, false), &book);
        assert_eq!(
            found,
            Validation::NotFound {
                similar: vec![
                    "StatTrak™ AK-47 | Redline (Field-Tested)".into(),
                    "StatTrak™ AK-47 | Redline (Minimal Wear)".into()
                ]
            }
        );
    }

    #[test]
    fn souvenir_items_only_get_souvenir_suggestions() {
        let book = book(&[
            "AK-47 | B the Monster (Field-Tested)",
            "Souvenir AK-47 | B the Monster (Field-Tested)",
            "Souvenir AK-47 | B the Monster (Minimal Wear)",
        ]);
        let found = validate_item(&item("AK-47 | B the Monster", None, false, true), &book);
        assert_eq!(
            found,
            Validation::NotFound {
                similar: vec![
                    "Souvenir AK-47 | B the Monster (Field-Tested)".into(),
                    "Souvenir AK-47 | B the Monster (Minimal Wear)".into()
                ]
            }
        );
    }

    #[test]
    fn suggestions_are_capped_at_five() {
        let names: Vec<String> = (1..=7).map(|i| format!("AK-47 | Redline (Wear {i})")).collect();
        let book = book(&names.iter().map(String::as_str).collect::<Vec<_>>());
        let Validation::NotFound { similar } = validate_item(&item("AK-47 | Redline", None, false, false), &book) else {
            panic!("expected not found");
        };
        assert_eq!(similar, names[..5].to_vec());
    }

    #[test]
    fn an_item_without_a_weapon_or_skin_gets_no_suggestions() {
        let book = book(&["AK-47 | Redline (Field-Tested)"]);
        assert_eq!(validate_item(&item("Mystery", None, false, false), &book), Validation::NotFound { similar: vec![] });
    }

    #[test]
    fn similarity_normalizes_case_spaces_apostrophes_and_hyphens() {
        assert!(similar_names("Neo-Noir", "neo noir"));
        assert!(similar_names("Rameses's Reach", "rameses reach"));
        assert!(similar_names("Redline", "Redline"));
        assert!(similar_names("Redline", "Red"));
        assert!(similar_names("Red", "Redline"));
        assert!(!similar_names("Redline", "Gamma Doppler"));
        assert!(!similar_names("", "Redline"));
        assert!(!similar_names("Redline", ""));
    }

    #[test]
    fn similarity_uses_a_positional_ratio() {
        // "doppler" vs "dopplar" match six of seven characters: 12/14 > 0.8.
        assert!(similar_names("Doppler", "Dopplar"));
        // A character-set match that reads nothing alike stays unrelated.
        assert!(!similar_names("abcd", "dcba"));
    }

    #[test]
    fn parses_api_names_with_wear() {
        assert_eq!(
            parse_api_name("AK-47 | Redline (Field-Tested)"),
            item("AK-47 | Redline", Some("Field-Tested"), false, false)
        );
        assert_eq!(parse_api_name("AK-47 | Redline"), item("AK-47 | Redline", None, false, false));
    }

    #[test]
    fn parses_stattrak_and_souvenir_prefixes_in_either_order() {
        assert_eq!(
            parse_api_name("StatTrak™ AK-47 | Redline (Field-Tested)"),
            item("AK-47 | Redline", Some("Field-Tested"), true, false)
        );
        assert_eq!(
            parse_api_name("Souvenir AK-47 | B the Monster (Field-Tested)"),
            item("AK-47 | B the Monster", Some("Field-Tested"), false, true)
        );
        let both = item("AK-47 | X", Some("Field-Tested"), true, true);
        assert_eq!(parse_api_name("Souvenir StatTrak™ AK-47 | X (Field-Tested)"), both);
        assert_eq!(parse_api_name("StatTrak™ Souvenir AK-47 | X (Field-Tested)"), both);
    }

    #[test]
    fn parses_starred_knife_names() {
        assert_eq!(
            parse_api_name("★ Karambit | Fade (Factory New)"),
            item("Karambit | Fade", Some("Factory New"), false, false)
        );
        assert_eq!(
            parse_api_name("StatTrak™ ★ Karambit | Fade (Factory New)"),
            item("Karambit | Fade", Some("Factory New"), true, false)
        );
    }

    #[test]
    fn a_suggestion_keeps_the_chosen_flags() {
        let chosen = apply_suggestion("AK-47 | Redline (Field-Tested)", true, false);
        assert_eq!(chosen, item("AK-47 | Redline", Some("Field-Tested"), true, false));
        assert!(apply_suggestion("★ Karambit | Fade", false, true).souvenir);
    }
}
