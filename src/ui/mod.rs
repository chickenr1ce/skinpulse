//! The window: state in `app`, one module per screen, all drawn from the tokens in `theme`.

mod add;
mod app;
mod data;
mod dialogs;
mod fixtures;
mod keys;
mod portfolio;
mod shell;
#[cfg(test)]
mod tests;
mod theme;
mod watchlist;

use std::sync::OnceLock;

use rune::{AppHandle, AppSpec};

use app::App;

const FONTS: &[&[u8]] = &[
    include_bytes!("../../assets/fonts/Geist-Variable.ttf"),
    include_bytes!("../../assets/fonts/GeistMono-Variable.ttf"),
];

/// Lets `poll` ask whether the window is on screen, to pause auto-refresh while it isn't.
static HANDLE: OnceLock<AppHandle<App>> = OnceLock::new();

fn spec() -> AppSpec<App> {
    AppSpec {
        min_size: Some((820.0, 540.0)),
        fonts: FONTS,
        families: ("Geist", "Geist Mono"),
        scenes: fixtures::SCENES,
        setup: Some(data::setup),
        poll: Some(data::poll),
        on_key: Some(keys::on_key),
        ..AppSpec::new("Skinpulse", (1040.0, 640.0), App::load, shell::view)
    }
}

pub fn run() {
    let app = rune::App::new(spec());
    let _ = HANDLE.set(app.handle());
    app.run();
}

/// False while the window is known to be hidden or minimized. Wayland doesn't report either, so
/// there it stays true.
pub fn window_visible() -> bool {
    HANDLE.get().is_none_or(AppHandle::is_visible)
}
