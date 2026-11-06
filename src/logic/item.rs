//! Watchlist items: the `items.txt` line format, Steam market hash names and flexible name input.

/// Every CS2 weapon that can have skins, in the order the add dialog lists them.
pub const WEAPONS: &[&str] = &[
    "Glock-18", "USP-S", "P250", "CZ75-Auto", "Tec-9", "Five-SeveN", "Desert Eagle", "R8 Revolver", "Dual Berettas", "P2000",
    "AK-47", "M4A4", "M4A1-S", "AUG", "SG 553", "FAMAS", "Galil AR", "AWP", "SSG 08", "SCAR-20", "G3SG1",
    "MAC-10", "MP9", "MP7", "MP5-SD", "UMP-45", "P90", "PP-Bizon",
    "Nova", "XM1014", "MAG-7", "Sawed-Off", "M249", "Negev",
    "Karambit", "M9 Bayonet", "Bayonet", "Butterfly Knife", "Flip Knife", "Gut Knife", "Falchion Knife", "Huntsman Knife",
    "Bowie Knife", "Shadow Daggers", "Navaja Knife", "Stiletto Knife", "Talon Knife", "Ursus Knife", "Classic Knife",
    "Paracord Knife", "Survival Knife", "Nomad Knife", "Skeleton Knife", "Kukri Knife", "Clutch Knife",
    "Sport Gloves", "Driver Gloves", "Moto Gloves", "Specialist Gloves", "Bloodhound Gloves", "Hydra Gloves",
];

/// Knives and gloves: the weapons whose market hash names carry a ★.
const STARRED: &[&str] = &[
    "Karambit", "M9 Bayonet", "Bayonet", "Butterfly Knife", "Flip Knife", "Gut Knife", "Falchion Knife", "Huntsman Knife",
    "Bowie Knife", "Shadow Daggers", "Navaja Knife", "Stiletto Knife", "Talon Knife", "Ursus Knife", "Classic Knife",
    "Paracord Knife", "Survival Knife", "Nomad Knife", "Skeleton Knife", "Kukri Knife", "Clutch Knife",
    "Sport Gloves", "Driver Gloves", "Moto Gloves", "Specialist Gloves", "Bloodhound Gloves", "Hydra Gloves",
];

/// The wear names the market uses, with the short code `items.txt` accepts for each.
pub const WEARS: &[(&str, &str)] = &[
    ("fn", "Factory New"),
    ("mw", "Minimal Wear"),
    ("ft", "Field-Tested"),
    ("ww", "Well-Worn"),
    ("bs", "Battle-Scarred"),
];

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Item {
    /// "Weapon | Skin", without a star.
    pub name: String,
    pub wear: Option<String>,
    pub stattrak: bool,
    pub souvenir: bool,
}

impl Item {
    /// The Steam market hash name, the key prices are looked up by.
    pub fn market_hash_name(&self) -> String {
        let weapon = self.name.split(" | ").next().unwrap_or(&self.name);
        let mut full = if STARRED.contains(&weapon) && !self.name.starts_with('★') {
            format!("★ {}", self.name)
        } else {
            self.name.clone()
        };
        if self.souvenir {
            full = format!("Souvenir {full}");
        }
        if self.stattrak {
            full = format!("StatTrak™ {full}");
        }
        if let Some(wear) = &self.wear {
            full = format!("{full} ({wear})");
        }
        full
    }

    /// The item as one `items.txt` line.
    pub fn to_line(&self) -> String {
        let mut line = String::new();
        if self.souvenir {
            line.push_str("SV ");
        }
        if self.stattrak {
            line.push_str("ST ");
        }
        line.push_str(&self.name);
        if let Some(wear) = &self.wear {
            line.push_str(", ");
            line.push_str(wear);
        }
        line
    }

    /// Reads one `items.txt` line: `[SV ][ST ]Name[, Wear]`. Blank lines and `#` comments give
    /// `None`. The prefixes work in either order, since a line this app wrote has `SV ST`.
    pub fn parse_line(line: &str) -> Option<Item> {
        let mut rest = line.trim();
        if rest.is_empty() || rest.starts_with('#') {
            return None;
        }
        let (mut stattrak, mut souvenir) = (false, false);
        loop {
            if !stattrak && let Some(after) = strip_prefix_ignore_case(rest, "ST ") {
                stattrak = true;
                rest = after.trim_start();
            } else if !souvenir && let Some(after) = strip_prefix_ignore_case(rest, "SV ") {
                souvenir = true;
                rest = after.trim_start();
            } else {
                break;
            }
        }
        let (name, wear) = match rest.split_once(',') {
            Some((name, wear)) => (name, Some(wear.trim()).filter(|w| !w.is_empty())),
            None => (rest, None),
        };
        let name = name.trim_start_matches(['★', ' ']).trim();
        if name.is_empty() {
            return None;
        }
        Some(Item { name: name.to_string(), wear: wear.map(normalize_wear), stattrak, souvenir })
    }
}

fn strip_prefix_ignore_case<'a>(s: &'a str, prefix: &str) -> Option<&'a str> {
    let head = s.get(..prefix.len())?;
    head.eq_ignore_ascii_case(prefix).then(|| &s[prefix.len()..])
}

/// Expands a short wear code; anything else passes through unchanged.
pub fn normalize_wear(wear: &str) -> String {
    let code = wear.trim().to_lowercase();
    match WEARS.iter().find(|(short, _)| *short == code) {
        Some((_, full)) => (*full).to_string(),
        None => wear.to_string(),
    }
}

/// Lowercases and drops spaces and hyphens, so `ak47`, `AK 47` and `AK-47` compare equal.
fn normalize(s: &str) -> String {
    s.chars().filter(|c| !c.is_whitespace() && *c != '-').flat_map(char::to_lowercase).collect()
}

/// Capitalizes each word's first letter, without touching the letter after an apostrophe.
pub fn capitalize_skin(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut at_start = true;
    for c in s.chars() {
        if at_start {
            out.extend(c.to_uppercase());
        } else {
            out.push(c);
        }
        at_start = c.is_whitespace() || c == '-';
    }
    out
}

/// Splits free input like `AK-47 | Redline`, `ak47 redline` or `M4A1-S Printstream` into a weapon
/// and a skin. Input that names no known weapon comes back whole, with no skin.
pub fn split_name(raw: &str) -> (String, Option<String>) {
    let raw = raw.trim();
    if raw.is_empty() {
        return (String::new(), None);
    }
    if let Some((weapon, skin)) = raw.split_once('|') {
        let weapon = weapon.trim();
        let skin = Some(skin.trim()).filter(|s| !s.is_empty()).map(capitalize_skin);
        let known = WEAPONS.iter().find(|w| normalize(w) == normalize(weapon));
        return (known.map_or(weapon, |w| *w).to_string(), skin);
    }
    let raw_norm = normalize(raw);
    let mut by_length: Vec<&str> = WEAPONS.to_vec();
    by_length.sort_by_key(|w| std::cmp::Reverse(w.len()));
    for weapon in by_length {
        let weapon_norm = normalize(weapon);
        if raw_norm == weapon_norm {
            return (weapon.to_string(), None);
        }
        if let Some(skin) = skin_after_literal(raw, weapon) {
            return (weapon.to_string(), Some(capitalize_skin(skin)));
        }
        if raw_norm.starts_with(&weapon_norm) && raw_norm.len() > weapon_norm.len() {
            let rest = rest_after_normalized(raw, &weapon_norm);
            let rest = rest.trim_start_matches(|c: char| c.is_whitespace() || c == '-' || c == '|').trim();
            if !rest.is_empty() {
                return (weapon.to_string(), Some(capitalize_skin(rest)));
            }
        }
    }
    (raw.to_string(), None)
}

/// The text after `weapon` and one separator (space, `-` or `|`), when `raw` starts with `weapon`.
fn skin_after_literal<'a>(raw: &'a str, weapon: &str) -> Option<&'a str> {
    let after = strip_prefix_ignore_case(raw, weapon)?;
    let trimmed = after.trim_start();
    let skin = match trimmed.strip_prefix(['|', '-']) {
        Some(skin) => skin,
        None if trimmed.len() < after.len() => trimmed,
        None => return None,
    };
    Some(skin.trim_start()).filter(|s| !s.is_empty())
}

/// The part of `raw` after the characters that spell `weapon_norm`, skipping spaces and hyphens.
fn rest_after_normalized<'a>(raw: &'a str, weapon_norm: &str) -> &'a str {
    let mut want = weapon_norm.chars().peekable();
    for (i, c) in raw.char_indices() {
        if want.peek().is_none() {
            return &raw[i..];
        }
        if c.to_lowercase().next() == want.peek().copied() {
            want.next();
        }
    }
    ""
}

/// Weapons matching a query: exact first, then prefixes, then substrings, each ignoring case,
/// spaces and hyphens. An empty query lists them all.
pub fn find_weapons(query: &str) -> Vec<&'static str> {
    let query = normalize(query);
    if query.is_empty() {
        return WEAPONS.to_vec();
    }
    let matching = |pred: &dyn Fn(&str) -> bool| WEAPONS.iter().copied().filter(|w| pred(&normalize(w))).collect::<Vec<_>>();
    let mut out = matching(&|w| w == query);
    out.extend(matching(&|w| w != query && w.starts_with(&query)));
    out.extend(matching(&|w| !w.starts_with(&query) && w.contains(&query)));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn item(name: &str, wear: Option<&str>, stattrak: bool, souvenir: bool) -> Item {
        Item { name: name.into(), wear: wear.map(Into::into), stattrak, souvenir }
    }

    #[test]
    fn parses_a_plain_name() {
        assert_eq!(Item::parse_line("AK-47 | Redline"), Some(item("AK-47 | Redline", None, false, false)));
    }

    #[test]
    fn parses_wear_and_expands_short_codes() {
        assert_eq!(Item::parse_line("M4A1-S | Printstream, Field-Tested").unwrap().wear.as_deref(), Some("Field-Tested"));
        assert_eq!(Item::parse_line("AK-47 | Redline, ft").unwrap().wear.as_deref(), Some("Field-Tested"));
    }

    #[test]
    fn parses_prefixes() {
        assert!(Item::parse_line("ST AK-47 | Redline").unwrap().stattrak);
        assert!(Item::parse_line("SV AK-47 | B the Monster").unwrap().souvenir);
    }

    #[test]
    fn strips_stars() {
        assert_eq!(Item::parse_line("★ Karambit | Black Laminate").unwrap().name, "Karambit | Black Laminate");
        let gloves = Item::parse_line("★ Sport Gloves | Nocts, Field-Tested").unwrap();
        assert_eq!(gloves.name, "Sport Gloves | Nocts");
        assert_eq!(gloves.wear.as_deref(), Some("Field-Tested"));
    }

    #[test]
    fn ignores_comments_and_blanks() {
        assert_eq!(Item::parse_line("# comment"), None);
        assert_eq!(Item::parse_line(""), None);
        assert_eq!(Item::parse_line("   "), None);
    }

    #[test]
    fn a_line_round_trips_with_both_prefixes() {
        let both = item("AK-47 | Redline", Some("Field-Tested"), true, true);
        assert_eq!(both.to_line(), "SV ST AK-47 | Redline, Field-Tested");
        assert_eq!(Item::parse_line(&both.to_line()), Some(both));
    }

    #[test]
    fn splits_names() {
        let split = |raw| split_name(raw);
        let both = |w: &str, s: &str| (w.to_string(), Some(s.to_string()));
        assert_eq!(split("AK-47 | Redline"), both("AK-47", "Redline"));
        assert_eq!(split("AK-47|Redline"), both("AK-47", "Redline"));
        assert_eq!(split("AK-47 Redline"), both("AK-47", "Redline"));
        assert_eq!(split("ak47 redline"), both("AK-47", "Redline"));
        assert_eq!(split("m4a1s printstream"), both("M4A1-S", "Printstream"));
        assert_eq!(split("M9 Bayonet doppler"), both("M9 Bayonet", "Doppler"));
        assert_eq!(split("AK-47"), ("AK-47".to_string(), None));
        assert_eq!(split("Not a Weapon"), ("Not a Weapon".to_string(), None));
    }

    #[test]
    fn capitalizes_without_touching_apostrophes() {
        assert_eq!(capitalize_skin("rameses reach"), "Rameses Reach");
        assert_eq!(capitalize_skin("rameses's reach"), "Rameses's Reach");
        assert_eq!(capitalize_skin("neo-noir"), "Neo-Noir");
    }

    #[test]
    fn formats_market_hash_names() {
        let name = |i: Item| i.market_hash_name();
        assert_eq!(name(item("AK-47 | Redline", Some("Field-Tested"), false, false)), "AK-47 | Redline (Field-Tested)");
        assert_eq!(name(item("AK-47 | Redline", None, true, false)), "StatTrak™ AK-47 | Redline");
        assert_eq!(name(item("AK-47 | B the Monster", None, false, true)), "Souvenir AK-47 | B the Monster");
        assert_eq!(name(item("Karambit | Black Laminate", Some("Well-Worn"), false, false)), "★ Karambit | Black Laminate (Well-Worn)");
        assert_eq!(name(item("Sport Gloves | Nocts", Some("Field-Tested"), false, false)), "★ Sport Gloves | Nocts (Field-Tested)");
        assert_eq!(name(item("★ Sport Gloves | Nocts", None, false, false)), "★ Sport Gloves | Nocts");
        assert_eq!(name(item("Karambit | Fade", Some("Factory New"), true, false)), "StatTrak™ ★ Karambit | Fade (Factory New)");
    }

    #[test]
    fn finds_weapons_by_relevance() {
        assert_eq!(find_weapons("ak47"), ["AK-47"]);
        assert_eq!(find_weapons("m4a1s"), ["M4A1-S"]);
        assert_eq!(find_weapons("").len(), WEAPONS.len());
        let bayonet = find_weapons("bayonet");
        assert_eq!(bayonet, ["Bayonet", "M9 Bayonet"]);
        assert!(find_weapons("zzz").is_empty());
    }
}
