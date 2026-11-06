//! Skinpulse's look: near-black or white, hairlines instead of boxes, tabular mono for numbers,
//! and colour reserved for what a value is doing.

use rune::{Color, TextStyle, oklch};
use rune_kit::{Kit, PaletteFocus, PaletteSeed, TableStyle};

pub const GUTTER: f32 = 20.0;
pub const ROW_HEIGHT: f32 = 36.0;
pub const HEADER_HEIGHT: f32 = 34.0;
pub const CELL_PAD: f32 = 12.0;

pub struct Tokens {
    pub kit: Kit,
    pub up: Color,
    pub down: Color,
    pub rule: Color,
    pub number: TextStyle,
}

impl Tokens {
    pub fn new(dark: bool) -> Tokens {
        let seed = if dark {
            PaletteSeed { bg: oklch(0.145, 0.0, 0.0), fg: oklch(0.945, 0.0, 0.0), accent: oklch(0.65, 0.19, 255.0) }
        } else {
            PaletteSeed { bg: oklch(1.0, 0.0, 0.0), fg: oklch(0.205, 0.0, 0.0), accent: oklch(0.56, 0.21, 257.0) }
        };
        let kit = Kit::from_palette_focus(seed, PaletteFocus::Accent);
        let (up, down) = if dark {
            (oklch(0.77, 0.16, 152.0), oklch(0.7, 0.18, 24.0))
        } else {
            (oklch(0.52, 0.15, 152.0), oklch(0.55, 0.2, 27.0))
        };
        let rule = kit.c.border_weak;
        let number = kit.ty.mono.features("'tnum' 1");
        Tokens { kit, up, down, rule, number }
    }

    pub fn table_style(&self) -> TableStyle {
        let k = &self.kit;
        TableStyle {
            row_height: ROW_HEIGHT,
            header_height: HEADER_HEIGHT,
            cell_pad: CELL_PAD,
            font: k.ty.text_small,
            mono: self.number,
            header_font: k.ty.text_small,
            selected: k.alpha(k.c.text_base, if k.dark { 0.09 } else { 0.06 }),
            stripe: k.alpha(k.c.text_base, if k.dark { 0.04 } else { 0.03 }),
            ..TableStyle::from_kit(k)
        }
    }
}
