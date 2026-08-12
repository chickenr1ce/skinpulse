# Minimum terminal dimensions before the TUI shows a "too small" message.
MIN_HEIGHT = 10
MIN_WIDTH = 88

# Height of the ASCII banner drawn at the top when the terminal is tall enough.
BANNER_HEIGHT = 6

# Seconds between automatic price refreshes in the TUI.
# 900 s (15 min): the PriceEmpire Trader tier budget (100/day, 1,000/month) is
# shared with the skinpulse web app, so the TUI must be a disciplined consumer.
REFRESH_INTERVAL = 900
