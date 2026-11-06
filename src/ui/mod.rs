//! The window: state in `app`, one module per screen, all drawn from the tokens in `theme`.

mod app;
mod fixtures;
mod shell;
mod theme;
mod watchlist;

use rune::AppSpec;

use app::App;

const FONTS: &[&[u8]] = &[
    include_bytes!("../../assets/fonts/Geist-Variable.ttf"),
    include_bytes!("../../assets/fonts/GeistMono-Variable.ttf"),
];

pub fn spec() -> AppSpec<App> {
    AppSpec {
        min_size: Some((820.0, 420.0)),
        fonts: FONTS,
        families: ("Geist", "Geist Mono"),
        scenes: fixtures::SCENES,
        on_key: Some(app::on_key),
        ..AppSpec::new("Skinpulse", (1040.0, 640.0), App::load, shell::view)
    }
}
