//! When to spend API requests. Every decision is a pure function of the schedule and the clock
//! the caller passes in, so the budget can be tested without waiting.

pub const REFRESH_INTERVAL: f64 = 900.0;

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Schedule {
    pub prices_at: Option<f64>,
    pub portfolio_at: Option<f64>,
    pub prices_loading: bool,
    pub portfolio_loading: bool,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Context {
    pub now: f64,
    pub has_key: bool,
    pub has_slug: bool,
    pub portfolio_visible: bool,
    pub paused: bool,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Fetch {
    pub prices: bool,
    pub portfolio: bool,
}

impl Schedule {
    /// Automatic refreshes, for the idle path.
    pub fn due(&self, ctx: &Context) -> Fetch {
        if !ctx.has_key || ctx.paused {
            return Fetch::default();
        }
        Fetch {
            prices: !self.prices_loading && stale(self.prices_at, ctx.now),
            portfolio: ctx.has_slug
                && ctx.portfolio_visible
                && !self.portfolio_loading
                && stale(self.portfolio_at, ctx.now),
        }
    }

    /// The `r` key: prices, plus the portfolio when a slug is configured, even if it is hidden.
    pub fn manual(&self, ctx: &Context) -> Fetch {
        if !ctx.has_key {
            return Fetch::default();
        }
        Fetch { prices: !self.prices_loading, portfolio: ctx.has_slug && !self.portfolio_loading }
    }

    pub fn start(&mut self, fetch: Fetch) {
        self.prices_loading |= fetch.prices;
        self.portfolio_loading |= fetch.portfolio;
    }

    /// Called on success AND failure: a failure waits for the next interval rather than retrying
    /// in a tight loop.
    pub fn finish_prices(&mut self, now: f64) {
        self.prices_at = Some(now);
        self.prices_loading = false;
    }

    pub fn finish_portfolio(&mut self, now: f64) {
        self.portfolio_at = Some(now);
        self.portfolio_loading = false;
    }

    /// Seconds until the prices refresh is due, clamped at 0; None before any fetch.
    pub fn seconds_until_next(&self, now: f64) -> Option<f64> {
        self.prices_at.map(|at| (at + REFRESH_INTERVAL - now).max(0.0))
    }

    pub fn loading(&self) -> bool {
        self.prices_loading || self.portfolio_loading
    }
}

impl Fetch {
    pub fn any(&self) -> bool {
        self.prices || self.portfolio
    }
}

fn stale(last: Option<f64>, now: f64) -> bool {
    last.is_none_or(|at| now - at > REFRESH_INTERVAL)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn context(now: f64) -> Context {
        Context { now, has_key: true, has_slug: true, portfolio_visible: false, paused: false }
    }

    /// Runs `ticks` one-second frames, finishing every fetch in the frame that started it.
    fn simulate(schedule: &mut Schedule, ticks: u64, ctx: &mut Context) -> Vec<(f64, Fetch)> {
        let mut calls = Vec::new();
        for tick in 0..ticks {
            ctx.now = tick as f64;
            let due = schedule.due(ctx);
            if due.any() {
                calls.push((ctx.now, due));
            }
            schedule.start(due);
            if due.prices {
                schedule.finish_prices(ctx.now);
            }
            if due.portfolio {
                schedule.finish_portfolio(ctx.now);
            }
        }
        calls
    }

    #[test]
    fn an_hour_of_watchlist_idle_makes_four_price_calls() {
        let mut schedule = Schedule::default();
        let mut ctx = context(0.0);
        let calls = simulate(&mut schedule, 3601, &mut ctx);
        // Due at 0, then whenever more than 900 seconds have passed: 901, 1802, 2703.
        assert_eq!(calls.len(), 4);
        assert_eq!(calls.iter().filter(|(_, call)| call.prices).count(), 4);
        assert_eq!(calls.iter().filter(|(_, call)| call.portfolio).count(), 0);
    }

    #[test]
    fn a_visible_portfolio_refreshes_on_the_same_clock() {
        let mut schedule = Schedule::default();
        let mut ctx = Context { portfolio_visible: true, ..context(0.0) };
        let calls = simulate(&mut schedule, 3601, &mut ctx);
        assert_eq!(calls.len(), 4);
        assert!(calls.iter().all(|(_, call)| call.prices && call.portfolio));
    }

    #[test]
    fn a_fresh_disk_cache_waits_out_the_interval() {
        // Launched with a cache five minutes old: the first call comes ten minutes from now,
        // once the cache is older than the 900-second interval.
        let mut schedule = Schedule { prices_at: Some(-300.0), ..Schedule::default() };
        let mut ctx = context(0.0);
        let calls = simulate(&mut schedule, 1200, &mut ctx);
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].0, 601.0);
    }

    #[test]
    fn paused_never_fetches() {
        let mut schedule = Schedule::default();
        let mut ctx = Context { paused: true, portfolio_visible: true, ..context(0.0) };
        assert!(simulate(&mut schedule, 100, &mut ctx).is_empty());
        assert_eq!(schedule.due(&ctx), Fetch::default());
    }

    #[test]
    fn no_key_never_fetches_even_manually() {
        let schedule = Schedule::default();
        let ctx = Context { has_key: false, portfolio_visible: true, ..context(0.0) };
        assert_eq!(schedule.due(&ctx), Fetch::default());
        assert_eq!(schedule.manual(&ctx), Fetch::default());
    }

    #[test]
    fn manual_ignores_the_interval_visibility_and_pauses() {
        let schedule = Schedule { prices_at: Some(0.0), portfolio_at: Some(0.0), ..Schedule::default() };
        let ctx = Context { paused: true, portfolio_visible: false, ..context(0.0) };
        assert_eq!(schedule.manual(&ctx), Fetch { prices: true, portfolio: true });
        assert_eq!(schedule.manual(&Context { has_slug: false, ..ctx }), Fetch { prices: true, portfolio: false });
    }

    #[test]
    fn a_loading_kind_is_not_started_twice() {
        let mut schedule = Schedule::default();
        schedule.start(Fetch { prices: true, portfolio: false });
        let ctx = Context { portfolio_visible: true, ..context(0.0) };
        assert_eq!(schedule.due(&ctx), Fetch { prices: false, portfolio: true });
        let manual = schedule.manual(&ctx);
        assert_eq!(manual, Fetch { prices: false, portfolio: true });
        schedule.start(manual);
        assert!(schedule.loading());
        schedule.finish_prices(10.0);
        assert!(schedule.loading());
        schedule.finish_portfolio(10.0);
        assert!(!schedule.loading());
    }

    #[test]
    fn finishing_records_the_time_for_success_and_failure_alike() {
        let mut schedule = Schedule::default();
        schedule.start(Fetch { prices: true, portfolio: true });
        schedule.finish_prices(123.0);
        schedule.finish_portfolio(456.0);
        assert_eq!(schedule.prices_at, Some(123.0));
        assert_eq!(schedule.portfolio_at, Some(456.0));
        assert_eq!(schedule.seconds_until_next(123.0), Some(REFRESH_INTERVAL));
        assert_eq!(schedule.seconds_until_next(2000.0), Some(0.0));
        assert_eq!(Schedule::default().seconds_until_next(0.0), None);
    }

    #[test]
    fn automated_due_needs_the_interval_to_have_passed() {
        let schedule = Schedule { prices_at: Some(100.0), ..Schedule::default() };
        let ctx = Context { has_key: true, has_slug: false, portfolio_visible: true, paused: false, now: 1000.0 };
        assert!(!schedule.due(&ctx).prices);
        let ctx = Context { now: 1001.0, ..ctx };
        assert!(schedule.due(&ctx).prices);
    }
}
