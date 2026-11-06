//! The add dialog: pick a weapon, name a skin, check it against the saved market prices.

use rune::{Color, El, Key, KeyEvent, TextEdit, Tx, col, row, text};
use rune_kit::{Button, ButtonVariant, Dialog, SegmentedControl, Switch, TextInput};
use skinpulse::logic::item::{Item, WEAPONS, WEARS, capitalize_skin, find_weapons, normalize_wear, split_name};
use skinpulse::logic::prices::ItemPrices;
use skinpulse::logic::validate::{Validation, apply_suggestion, validate_item};

use super::app::App;
use super::theme::Tokens;
use super::watchlist::money;

const LIST_ROWS: usize = 5;
const LIST_ROW_HEIGHT: f32 = 26.0;

#[derive(Default)]
pub struct AddForm {
    pub weapon: TextEdit,
    pub weapon_cursor: usize,
    pub skin: TextEdit,
    /// 0 means no wear, otherwise an index into `WEARS` plus one.
    pub wear: usize,
    pub stattrak: bool,
    pub souvenir: bool,
    pub check: Check,
}

#[derive(Default, Clone)]
pub enum Check {
    #[default]
    Unchecked,
    Invalid(String),
    Found(Item, ItemPrices),
    NotFound(Item, Vec<String>),
    /// No market data to check against yet.
    NoData(Item),
}

impl AddForm {
    fn chosen_weapon(&self) -> Option<&'static str> {
        find_weapons(&self.weapon.text).get(self.weapon_cursor).copied()
    }

    /// Reads the fields into an item. The skin field also takes a whole name, like
    /// `AK-47 Redline` or `ak47 | redline, ft`, which wins over the weapon list.
    fn item(&self) -> Result<Item, String> {
        let (typed, typed_wear) = match self.skin.text.split_once(',') {
            Some((name, wear)) => (name.trim(), Some(normalize_wear(wear.trim()))),
            None => (self.skin.text.trim(), None),
        };
        let (weapon, skin) = split_name(typed);
        let name = if WEAPONS.contains(&weapon.as_str()) && (skin.is_some() || self.chosen_weapon().is_none()) {
            // Text with a `|` is already spelled out: market names aren't always title case.
            let skin = typed.split_once('|').map(|(_, s)| s.trim().to_string()).or(skin).filter(|s| !s.is_empty());
            skin.map_or(weapon.clone(), |skin| format!("{weapon} | {skin}"))
        } else {
            let Some(chosen) = self.chosen_weapon() else {
                return Err("Choose a weapon, or type its name with the skin.".to_string());
            };
            if typed.is_empty() { chosen.to_string() } else { format!("{chosen} | {}", capitalize_skin(typed)) }
        };
        let wear = typed_wear.filter(|w| !w.is_empty()).or_else(|| self.wear.checked_sub(1).map(|i| WEARS[i].1.to_string()));
        Ok(Item { name, wear, stattrak: self.stattrak, souvenir: self.souvenir })
    }
}

fn edited(s: &mut App) {
    s.add.check = Check::Unchecked;
}

fn check_with(s: &mut App, item: Item) {
    s.add.check = if s.watchlist.contains(&item) {
        Check::Invalid(format!("{} is already on your watchlist.", item.market_hash_name()))
    } else if s.book.is_empty() {
        Check::NoData(item)
    } else {
        match validate_item(&item, &s.book) {
            Validation::Found(prices) => Check::Found(item, prices),
            Validation::NotFound { similar } => Check::NotFound(item, similar),
        }
    };
}

/// Enter or the main button: check first, then add what was checked.
fn submit(s: &mut App) {
    match s.add.check.clone() {
        Check::Found(item, _) | Check::NoData(item) => add(s, item),
        _ => match s.add.item() {
            Ok(item) => check_with(s, item),
            Err(message) => s.add.check = Check::Invalid(message),
        },
    }
}

fn add(s: &mut App, item: Item) {
    s.check_items_file();
    let name = item.market_hash_name();
    if s.watchlist.contains(&item) {
        s.add.check = Check::Invalid(format!("{name} is already on your watchlist."));
        return;
    }
    s.watchlist.add(item);
    s.save_watchlist();
    s.table.select(name.clone());
    s.say(format!("Added {name}"));
    s.close_modal();
}

fn pick_suggestion(s: &mut App, name: &str) {
    let item = apply_suggestion(name, s.add.stattrak, s.add.souvenir);
    check_with(s, item);
}

fn weapon_key(s: &mut App, ev: &KeyEvent, _tx: &mut Tx) -> bool {
    let last = find_weapons(&s.add.weapon.text).len().saturating_sub(1);
    match ev.key {
        Key::Up => s.add.weapon_cursor = s.add.weapon_cursor.saturating_sub(1),
        Key::Down => s.add.weapon_cursor = (s.add.weapon_cursor + 1).min(last),
        _ => return false,
    }
    edited(s);
    true
}

pub fn dialog(s: &App, t: &Tokens, layer: &mut Vec<El>) {
    let k = &t.kit;
    let form = &s.add;
    let weapon = TextInput::new(&form.weapon)
        .width(None)
        .label("Weapon")
        .placeholder("Search weapons")
        .on_edit(|s: &mut App| &mut s.add.weapon)
        .on_change(|s: &mut App, _: &mut Tx| {
            s.add.weapon_cursor = 0;
            edited(s);
        })
        .on_key(weapon_key)
        .on_submit(|s: &mut App, _: &mut Tx| {
            s.add.weapon.focused = false;
            s.add.skin.focused = true;
        })
        .build(k)
        .key("add-weapon");
    let skin = TextInput::new(&form.skin)
        .width(None)
        .label("Skin")
        .placeholder("Redline, or a full name like AK-47 Redline")
        .on_edit(|s: &mut App| &mut s.add.skin)
        .on_change(|s: &mut App, _: &mut Tx| edited(s))
        .on_submit(|s: &mut App, _: &mut Tx| submit(s))
        .build(k)
        .key("add-skin");
    let wear = SegmentedControl::new(&["Any wear", "FN", "MW", "FT", "WW", "BS"], Some(form.wear))
        .label("Wear")
        .width(None)
        .on_pick(|s: &mut App, i, _: &mut Tx| {
            s.add.wear = i;
            edited(s);
        })
        .build(k)
        .key("add-wear");
    let toggles = row()
        .key("add-toggles")
        .gap(20.0)
        .child(Switch::new(form.stattrak).label("StatTrak").on_toggle(|s: &mut App| {
            s.add.stattrak = !s.add.stattrak;
            edited(s);
        }).build(k))
        .child(Switch::new(form.souvenir).label("Souvenir").on_toggle(|s: &mut App| {
            s.add.souvenir = !s.add.souvenir;
            edited(s);
        }).build(k));

    let middle = match &form.check {
        Check::NotFound(_, similar) if !similar.is_empty() => suggestions(similar, t),
        _ => weapon_list(form, t),
    };
    let (primary, anyway) = match &form.check {
        Check::Found(..) => ("Add to watchlist", false),
        Check::NoData(_) => ("Add anyway", false),
        Check::NotFound(..) => ("Check again", true),
        _ => ("Check", false),
    };
    let mut buttons = row().key("add-buttons").w_full().gap(8.0).justify_end();
    if anyway {
        buttons = buttons.child(
            Button::new("Add anyway")
                .variant(ButtonVariant::Ghost)
                .on_press(|s: &mut App| {
                    if let Check::NotFound(item, _) = s.add.check.clone() {
                        add(s, item);
                    }
                })
                .build(k),
        );
    }
    buttons = buttons
        .child(Button::new("Cancel").variant(ButtonVariant::Ghost).on_press(|s: &mut App| s.close_modal()).build(k))
        .child(Button::new(primary).variant(ButtonVariant::Contrast).on_press(submit).build(k).default_button());

    Dialog::new("add", "Add a skin")
        .open(true)
        .fit()
        .width(560.0)
        .click_outside(false)
        .on_close(|s: &mut App| s.close_modal())
        .child(
            col()
                .key("add-body")
                .w_full()
                .px(16.0)
                .pb(16.0)
                .gap(12.0)
                .child(weapon)
                .child(middle)
                .child(skin)
                .child(wear)
                .child(toggles)
                .child(result_line(&form.check, t))
                .child(buttons),
        )
        .build(k, layer);
}

fn weapon_list(form: &AddForm, t: &Tokens) -> El {
    let k = &t.kit;
    let matches = find_weapons(&form.weapon.text);
    let cursor = form.weapon_cursor.min(matches.len().saturating_sub(1));
    let start = cursor.saturating_sub(LIST_ROWS - 1);
    let mut list = col().key("weapon-list").w_full().h(LIST_ROW_HEIGHT * LIST_ROWS as f32);
    if matches.is_empty() {
        return list.child(text("No weapon matches. A full name in the skin field still works.").font(k.ty.text_small).color(k.c.text_muted));
    }
    for (i, weapon) in matches.iter().enumerate().skip(start).take(LIST_ROWS) {
        let selected = i == cursor;
        let mut line = row()
            .key(*weapon)
            .role("button")
            .label(*weapon)
            .w_full()
            .h(LIST_ROW_HEIGHT)
            .px(8.0)
            .radius(k.radius.sm)
            .center_y()
            .hover(k.c.hover)
            .on_press(move |s: &mut App| {
                s.add.weapon_cursor = i;
                s.add.weapon.focused = false;
                s.add.skin.focused = true;
                edited(s);
            })
            .child(text(*weapon).font(k.ty.text_small).color(if selected { k.c.text_base } else { k.c.text_muted }));
        if selected {
            line = line.fill(k.alpha(k.c.text_base, if k.dark { 0.09 } else { 0.06 }));
        }
        list = list.child(line);
    }
    list
}

fn suggestions(similar: &[String], t: &Tokens) -> El {
    let k = &t.kit;
    let mut list = col()
        .key("suggestions")
        .w_full()
        .h(LIST_ROW_HEIGHT * LIST_ROWS as f32)
        .child(text("Did you mean").font(k.ty.small).color(k.c.text_faint));
    for name in similar.iter().take(LIST_ROWS - 1) {
        let pick = name.clone();
        list = list.child(
            row()
                .key(name.clone())
                .role("button")
                .label(name.clone())
                .focusable(true)
                .w_full()
                .h(LIST_ROW_HEIGHT)
                .px(8.0)
                .radius(k.radius.sm)
                .center_y()
                .hover(k.c.hover)
                .on_press(move |s: &mut App| pick_suggestion(s, &pick))
                .child(text(name.clone()).font(k.ty.text_small).color(k.c.text_base).truncate().shrink().min_w(0.0)),
        );
    }
    list
}

fn result_line(check: &Check, t: &Tokens) -> El {
    let k = &t.kit;
    let line = |message: String, color: Color| text(message).font(k.ty.text_small).color(color).truncate().shrink().min_w(0.0);
    let body = match check {
        Check::Unchecked => line(String::new(), k.c.text_muted),
        Check::Invalid(message) => line(message.clone(), t.down),
        Check::Found(item, prices) => line(
            format!("{}: Buff163 €{}, Skins €{}", item.market_hash_name(), money(prices.buff163.price), money(prices.skins)),
            k.c.text_base,
        ),
        Check::NotFound(item, _) => line(format!("{} isn't in the market data.", item.market_hash_name()), t.down),
        Check::NoData(item) => line(format!("Prices haven't loaded, so {} can't be checked.", item.market_hash_name()), k.c.text_muted),
    };
    row().key("add-result").w_full().h(20.0).center_y().min_w(0.0).child(body)
}
