//! Skinpulse: a keyboard-first desktop app for tracking CS2 skin prices.

mod ui;

fn main() {
    rune::run(ui::spec());
}
