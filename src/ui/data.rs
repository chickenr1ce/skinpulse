//! Everything that happens between frames: background fetches, the disk cache, the refresh
//! schedule and hot-reloading `items.txt`.

use std::sync::mpsc::Sender;
use std::time::Duration;

use rune::{Tx, Waker};
use skinpulse::logic::api::Client;
use skinpulse::logic::cache;
use skinpulse::logic::config::ViewKind;
use skinpulse::logic::portfolio::Portfolio;
use skinpulse::logic::prices::PriceBook;
use skinpulse::logic::refresh::{Context, Fetch};

use super::app::{App, mtime};

pub enum Msg {
    Cached { prices: Option<(PriceBook, f64)>, portfolio: Option<(Portfolio, f64)> },
    Prices { generation: u64, result: Result<PriceBook, String> },
    Portfolio { generation: u64, result: Result<Portfolio, String> },
}

/// Reads the saved responses off the main thread: the prices body covers the whole market.
pub fn setup(s: &mut App, waker: Waker) {
    s.waker = Some(waker.clone());
    let Some(paths) = s.paths.clone() else { return };
    let tx = s.tx.clone();
    let slug = s.config.portfolio_slug.clone();
    std::thread::spawn(move || {
        let prices = cache::read(&paths.prices_cache()).and_then(|(body, at)| PriceBook::parse(&body).ok().map(|b| (b, at)));
        let portfolio = cache::read(&paths.portfolio_cache()).and_then(|(body, at)| Portfolio::parse(&body, &slug).ok().map(|p| (p, at)));
        send(&tx, &waker, Msg::Cached { prices, portfolio });
    });
}

fn send(tx: &Sender<Msg>, waker: &Waker, msg: Msg) {
    let _ = tx.send(msg);
    waker();
}

pub fn poll(s: &mut App, _clock: f64, tx: &mut Tx) -> bool {
    let mut changed = false;
    while let Ok(msg) = s.rx.try_recv() {
        s.receive(msg);
        changed = true;
    }
    if s.paths.is_none() {
        return changed;
    }
    s.now = cache::now_unix();
    tx.wake_after(Duration::from_secs(1));
    let second = s.now as u64;
    if second == s.last_second {
        return changed;
    }
    s.last_second = second;
    s.check_items_file();
    if s.notice.as_ref().is_some_and(|(_, until)| s.now >= *until) {
        s.notice = None;
    }
    if s.cache_loaded {
        let fetch = s.schedule.due(&s.context());
        s.start(fetch);
    }
    true
}

impl App {
    pub fn context(&self) -> Context {
        Context {
            now: self.now,
            has_key: self.has_key(),
            has_slug: self.has_slug(),
            portfolio_visible: self.ui.view == ViewKind::Portfolio,
            paused: !super::window_visible(),
        }
    }

    /// The `r` key.
    pub fn refresh_now(&mut self) {
        if !self.has_key() {
            self.open_setup();
            return;
        }
        let fetch = self.schedule.manual(&self.context());
        self.start(fetch);
    }

    fn start(&mut self, fetch: Fetch) {
        let (Some(paths), Some(waker)) = (self.paths.clone(), self.waker.clone()) else { return };
        if !fetch.any() {
            return;
        }
        self.schedule.start(fetch);
        let key = self.config.api_key.clone();
        let slug = self.config.portfolio_slug.clone();
        let generation = self.generation;
        if fetch.prices {
            let (tx, waker, key, file) = (self.tx.clone(), waker.clone(), key.clone(), paths.prices_cache());
            std::thread::spawn(move || {
                let result = Client::new(&key).prices().and_then(|body| {
                    let book = PriceBook::parse(&body)?;
                    let _ = cache::write(&file, &body);
                    Ok(book)
                });
                send(&tx, &waker, Msg::Prices { generation, result });
            });
        }
        if fetch.portfolio {
            let (tx, file) = (self.tx.clone(), paths.portfolio_cache());
            std::thread::spawn(move || {
                let result = Client::new(&key).portfolio(&slug).and_then(|body| {
                    let portfolio = Portfolio::parse(&body, &slug)?;
                    let _ = cache::write(&file, &body);
                    Ok(portfolio)
                });
                send(&tx, &waker, Msg::Portfolio { generation, result });
            });
        }
    }

    pub fn receive(&mut self, msg: Msg) {
        let now = cache::now_unix();
        match msg {
            Msg::Cached { prices, portfolio } => {
                self.cache_loaded = true;
                if let Some((book, at)) = prices {
                    self.book = book;
                    self.book_at = Some(at);
                    self.schedule.prices_at = Some(at);
                }
                if let Some((portfolio, at)) = portfolio {
                    self.portfolio = Some(portfolio);
                    self.schedule.portfolio_at = Some(at);
                }
            }
            // An answer for a key or slug that has since changed: free the slot so the right
            // request can start, and keep nothing from it.
            Msg::Prices { generation, .. } if generation != self.generation => self.schedule.prices_loading = false,
            Msg::Portfolio { generation, .. } if generation != self.generation => self.schedule.portfolio_loading = false,
            Msg::Prices { result, .. } => {
                self.schedule.finish_prices(now);
                match result {
                    Ok(book) => {
                        self.book = book;
                        self.book_at = Some(now);
                        self.error = None;
                    }
                    Err(e) => self.error = Some(e),
                }
            }
            Msg::Portfolio { result, .. } => {
                self.schedule.finish_portfolio(now);
                match result {
                    Ok(portfolio) => {
                        self.portfolio = Some(portfolio);
                        self.portfolio_error = None;
                    }
                    Err(e) => self.portfolio_error = Some(e),
                }
            }
        }
        self.resort();
        self.resort_portfolio();
    }

    pub fn check_items_file(&mut self) {
        let Some(paths) = &self.paths else { return };
        let current = mtime(&paths.items_file());
        if current != self.items_mtime {
            self.reload_watchlist();
            self.items_mtime = current;
        }
    }

    /// What the status line says about refreshing.
    pub fn refresh_status(&self) -> String {
        if self.schedule.loading() {
            return "Refreshing…".to_string();
        }
        if !self.has_key() {
            return "No API key".to_string();
        }
        match self.schedule.seconds_until_next(self.now) {
            Some(left) => {
                let left = left as u64;
                format!("Next {}:{:02}", left / 60, left % 60)
            }
            None => "No data yet".to_string(),
        }
    }

    /// The error for the current view, saying how old the data on screen is.
    pub fn error_status(&self) -> Option<String> {
        let portfolio = self.ui.view == ViewKind::Portfolio;
        let error = if portfolio { self.portfolio_error.as_ref() } else { self.error.as_ref() }?;
        Some(match self.book_at.filter(|_| !portfolio) {
            Some(at) => {
                let minutes = ((self.now - at).max(0.0) / 60.0) as u64;
                format!("{error}. Showing data from {minutes} min ago.")
            }
            None => error.clone(),
        })
    }
}
