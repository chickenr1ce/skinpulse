//! Skinpulse: a keyboard-first desktop app for tracking CS2 skin prices.

#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

mod ui;

fn main() {
    ui::run();
}
