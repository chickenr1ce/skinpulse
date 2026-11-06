//! The smaller dialogs: first-run setup and settings, delete, import and export.

use std::io::Read;
use std::path::Path;

use rune::{El, FileDialogOptions, Tx, col, row, text};
use rune_kit::{Button, ButtonVariant, Dialog, TextInput};
use skinpulse::logic::config::{Config, ViewKind, import_from_folder};
use skinpulse::logic::watchlist::write_atomic;

use super::app::{App, Modal};
use super::theme::Tokens;

/// Larger than any real watchlist. Picking some unrelated huge file shouldn't hang the app.
const MAX_IMPORT_BYTES: u64 = 2 * 1024 * 1024;

pub fn layer(s: &App, t: &Tokens, layer: &mut Vec<El>) {
    match s.modal {
        Modal::None => {}
        Modal::Add => super::add::dialog(s, t, layer),
        Modal::Setup => setup(s, t, layer),
        Modal::Delete => delete(s, t, layer),
        Modal::Import => import(s, t, layer),
        Modal::Export => export(s, t, layer),
    }
}

fn shell(key: &'static str, title: &'static str) -> Dialog {
    Dialog::new(key, title).open(true).fit().width(460.0).on_close(|s: &mut App| s.close_modal())
}

/// A dialog's padded body, led by its explanation. The kit's own description line doesn't wrap.
fn body(key: &'static str, description: impl Into<String>, t: &Tokens) -> El {
    col()
        .key(key)
        .w_full()
        .px(16.0)
        .pb(16.0)
        .gap(14.0)
        .child(text(description.into()).font(t.kit.ty.text_small).color(t.kit.c.text_muted).wrap())
}

fn error_line(s: &App, t: &Tokens) -> Option<El> {
    s.dialog_error.as_ref().map(|e| text(e.clone()).font(t.kit.ty.text_small).color(t.down).wrap())
}

fn save_setup(s: &mut App) {
    // Saving overwrites the file, which may hold the only copy of a key.
    if s.setup_key.text.trim().is_empty() {
        s.dialog_error = Some("Enter your API key. Cancel leaves your settings as they are.".to_string());
        return;
    }
    let config = Config { api_key: s.setup_key.text.trim().to_string(), portfolio_slug: s.setup_slug.text.trim().to_string() };
    if let Some(paths) = &s.paths
        && let Err(e) = config.save(&paths.config_file())
    {
        s.dialog_error = Some(format!("Couldn't save settings: {e}"));
        return;
    }
    let slug_changed = config.portfolio_slug != s.config.portfolio_slug;
    let key_changed = config.api_key != s.config.api_key;
    s.config = config;
    s.setup_error = None;
    if slug_changed || key_changed {
        s.generation += 1;
        s.schedule.portfolio_loading = false;
    }
    if slug_changed {
        s.portfolio = None;
        s.portfolio_error = None;
        s.schedule.portfolio_at = None;
        if let Some(paths) = &s.paths {
            let _ = std::fs::remove_file(paths.portfolio_cache());
        }
        s.resort_portfolio();
        if !s.has_slug() {
            s.ui.view = ViewKind::Watchlist;
        }
    }
    if key_changed {
        s.error = None;
        s.portfolio_error = None;
        s.schedule.prices_loading = false;
        // A new key deserves an answer now, not after the old key's failure ages out.
        s.schedule.prices_at = None;
        s.schedule.portfolio_at = None;
    }
    s.close_modal();
}

fn setup(s: &App, t: &Tokens, layer: &mut Vec<El>) {
    let k = &t.kit;
    let key = TextInput::new(&s.setup_key)
        .secure()
        .width(None)
        .label("API key")
        .placeholder("Your PriceEmpire API key")
        .on_edit(|s: &mut App| &mut s.setup_key)
        .on_submit(|s: &mut App, _: &mut Tx| save_setup(s))
        .build(k)
        .key("setup-key");
    let slug = TextInput::new(&s.setup_slug)
        .width(None)
        .label("Portfolio slug")
        .placeholder("Optional")
        .on_edit(|s: &mut App| &mut s.setup_slug)
        .on_submit(|s: &mut App, _: &mut Tx| save_setup(s))
        .build(k)
        .key("setup-slug");
    let mut content = body("setup-body", "Skinpulse reads prices with your own PriceEmpire key. It stays on this computer.", t)
        .child(labelled("API key", key, t))
        .child(labelled("Portfolio slug", slug, t));
    if let Some(e) = s.setup_error.as_ref().or(s.dialog_error.as_ref()) {
        content = content.child(text(e.clone()).font(k.ty.text_small).color(t.down).wrap());
    }
    let buttons = row()
        .key("setup-buttons")
        .w_full()
        .gap(8.0)
        .justify_between()
        .child(Button::new("Import from a folder…").variant(ButtonVariant::Ghost).on_press_tx(ask_import_folder).build(k))
        .child(
            row()
                .gap(8.0)
                .child(Button::new("Cancel").variant(ButtonVariant::Ghost).on_press(|s: &mut App| s.close_modal()).build(k))
                .child(Button::new("Save").variant(ButtonVariant::Contrast).on_press(save_setup).build(k).default_button()),
        );
    shell("setup", "Settings")
        .click_outside(false)
        .child(content.child(buttons))
        .build(k, layer);
}

fn labelled(label: &'static str, input: El, t: &Tokens) -> El {
    col().key(label).w_full().gap(6.0).child(text(label).font(t.kit.ty.text_small).color(t.kit.c.text_muted)).child(input)
}

fn ask_import_folder(_: &mut App, tx: &mut Tx) {
    let options = FileDialogOptions { title: "Choose a folder holding config.json and items.txt".into(), ..Default::default() };
    tx.open_folder(options, |s: &mut App, result, _: &mut Tx| match result {
        Ok(Some(folder)) => import_folder(s, &folder),
        Ok(None) => {}
        Err(e) => s.dialog_error = Some(format!("Couldn't open the folder picker: {e}")),
    });
}

fn import_folder(s: &mut App, folder: &Path) {
    let Some(paths) = s.paths.clone() else { return };
    match import_from_folder(folder, &paths) {
        Ok(summary) => {
            if summary.items {
                s.reload_watchlist();
            }
            if summary.config
                && let Ok(config) = Config::load(&paths.config_file())
            {
                s.config = config;
                s.open_setup();
            }
            s.dialog_error = match (summary.config, summary.items) {
                (false, false) => Some("Nothing imported: no new files in that folder, and existing files are kept.".to_string()),
                _ => None,
            };
            if summary.config || summary.items {
                s.say("Imported your existing setup.");
            }
        }
        Err(e) => s.dialog_error = Some(e),
    }
}

pub fn ask_delete(s: &mut App) {
    if let Some(row) = s.selected_row() {
        s.delete = Some(row.id.clone());
        s.modal = Modal::Delete;
    }
}

fn confirm_delete(s: &mut App) {
    s.check_items_file();
    let before = s.cursor_position();
    let target = s.delete.take().and_then(|id| s.rows.iter().find(|r| r.id == id).map(|r| r.index));
    match target.and_then(|index| s.watchlist.remove_at(index)) {
        Some(item) => {
            s.save_watchlist();
            s.reselect(before);
            s.say(format!("Removed {}", item.market_hash_name()));
        }
        None => s.say("That item is no longer on your watchlist."),
    }
    s.close_modal();
}

fn delete(s: &App, t: &Tokens, layer: &mut Vec<El>) {
    let k = &t.kit;
    let name = s.delete.as_ref().and_then(|id| s.rows.iter().find(|r| &r.id == id)).map_or_else(String::new, |r| r.name.clone());
    let buttons = row()
        .key("delete-buttons")
        .w_full()
        .gap(8.0)
        .justify_end()
        .child(Button::new("Cancel").variant(ButtonVariant::Ghost).on_press(|s: &mut App| s.close_modal()).build(k))
        .child(Button::new("Remove").variant(ButtonVariant::Danger).on_press(confirm_delete).build(k).default_button());
    shell("delete", "Remove from watchlist?").child(body("delete-body", name, t).child(buttons)).build(k, layer);
}

fn preview(s: &mut App, text: &str) {
    s.dialog_error = None;
    s.import = Some(s.watchlist.preview_import(text));
}

fn ask_import_file(_: &mut App, tx: &mut Tx) {
    let options = FileDialogOptions { title: "Import a watchlist".into(), ..Default::default() }.filter("Text", &["txt"]);
    tx.open_file(options, |s: &mut App, result, _: &mut Tx| match result {
        Ok(Some(path)) => match read_import(&path) {
            Ok(text) => preview(s, &text),
            Err(e) => s.dialog_error = Some(e),
        },
        Ok(None) => {}
        Err(e) => s.dialog_error = Some(format!("Couldn't open the file picker: {e}. You can paste from the clipboard instead.")),
    });
}

fn read_import(path: &Path) -> Result<String, String> {
    let file = std::fs::File::open(path).map_err(|e| format!("Couldn't read that file: {e}"))?;
    if !file.metadata().is_ok_and(|m| m.is_file()) {
        return Err("That isn't a regular file.".to_string());
    }
    let mut text = String::new();
    file.take(MAX_IMPORT_BYTES + 1).read_to_string(&mut text).map_err(|e| format!("Couldn't read that file: {e}"))?;
    if text.len() as u64 > MAX_IMPORT_BYTES {
        return Err("That file is too large to be a watchlist.".to_string());
    }
    Ok(text)
}

fn confirm_import(s: &mut App) {
    s.check_items_file();
    if let Some(mut preview) = s.import.take() {
        // The file may have changed since the preview was made.
        let watchlist = &s.watchlist;
        preview.new.retain(|item| !watchlist.contains(item));
        let count = preview.new.len();
        s.watchlist.apply_import(preview);
        s.save_watchlist();
        s.say(format!("Imported {count} item{}", if count == 1 { "" } else { "s" }));
    }
    s.close_modal();
}

fn import(s: &App, t: &Tokens, layer: &mut Vec<El>) {
    let k = &t.kit;
    let mut content = body("import-body", "Lines use the items.txt format. Items are added to your list, and duplicates are skipped.", t);
    let mut buttons = row().key("import-buttons").w_full().gap(8.0).justify_end();
    if let Some(p) = &s.import {
        let unknown = if s.book.is_empty() { 0 } else { p.new.iter().filter(|i| s.book.get(&i.market_hash_name()).is_none()).count() };
        let mut facts = vec![format!("{} new", p.new.len()), format!("{} already on your watchlist", p.duplicates)];
        if !p.unreadable.is_empty() {
            facts.push(format!("{} unreadable", p.unreadable.len()));
        }
        content = content.child(text(facts.join(", ")).font(k.ty.ui_medium).color(k.c.text_base));
        if unknown > 0 {
            content = content.child(text(format!("{unknown} of the new items aren't in the market data. They'll be added anyway and show no price.")).font(k.ty.text_small).color(k.c.text_muted).wrap());
        }
        if let Some(line) = p.unreadable.first() {
            content = content.child(text(format!("Skipped: {line}")).font(k.ty.text_small).color(k.c.text_muted).truncate());
        }
        buttons = buttons.child(Button::new("Cancel").variant(ButtonVariant::Ghost).on_press(|s: &mut App| s.close_modal()).build(k));
        let label = format!("Add {} item{}", p.new.len(), if p.new.len() == 1 { "" } else { "s" });
        buttons = buttons.child(Button::new(label).variant(ButtonVariant::Contrast).disabled(p.new.is_empty()).on_press(confirm_import).build(k).default_button());
    } else {
        buttons = buttons
            .child(
                Button::new("Paste from clipboard")
                    .variant(ButtonVariant::Ghost)
                    .on_press_tx(|_: &mut App, tx: &mut Tx| tx.read_clipboard(|s: &mut App, content, _: &mut Tx| preview(s, content.text())))
                    .build(k),
            )
            .child(Button::new("Choose a file…").variant(ButtonVariant::Contrast).on_press_tx(ask_import_file).build(k).default_button());
    }
    if let Some(e) = error_line(s, t) {
        content = content.child(e);
    }
    shell("import", "Import a watchlist")
        .child(content.child(buttons))
        .build(k, layer);
}

fn ask_export_file(_: &mut App, tx: &mut Tx) {
    let options = FileDialogOptions { title: "Export your watchlist".into(), file_name: Some("items.txt".into()), ..Default::default() }.filter("Text", &["txt"]);
    tx.save_file(options, |s: &mut App, result, _: &mut Tx| match result {
        Ok(Some(path)) => match write_atomic(&path, s.watchlist.to_text().as_bytes()) {
            Ok(()) => {
                s.say(format!("Exported to {}", path.display()));
                s.close_modal();
            }
            Err(e) => s.dialog_error = Some(format!("Couldn't write that file: {e}")),
        },
        Ok(None) => {}
        Err(e) => s.dialog_error = Some(format!("Couldn't open the file picker: {e}. You can copy to the clipboard instead.")),
    });
}

fn export(s: &App, t: &Tokens, layer: &mut Vec<El>) {
    let k = &t.kit;
    let buttons = row()
        .key("export-buttons")
        .w_full()
        .gap(8.0)
        .justify_end()
        .child(
            Button::new("Copy to clipboard")
                .variant(ButtonVariant::Ghost)
                .on_press_tx(|s: &mut App, tx: &mut Tx| {
                    tx.copy(s.watchlist.to_text());
                    s.say("Copied your watchlist.");
                    s.close_modal();
                })
                .build(k),
        )
        .child(Button::new("Save to a file…").variant(ButtonVariant::Contrast).on_press_tx(ask_export_file).build(k).default_button());
    let count = s.watchlist.len();
    let mut content = body("export-body", format!("{count} item{} in the items.txt format, comments included.", if count == 1 { "" } else { "s" }), t);
    if let Some(e) = error_line(s, t) {
        content = content.child(e);
    }
    shell("export", "Export your watchlist")
        .child(content.child(buttons))
        .build(k, layer);
}
