# PriceEmpire Trader API Reference

Base URL: `https://api.pricempire.com/v4/trader`
Auth: `Authorization: Bearer {api_key}` header or `?api_key=` query param
App ID: `730` (CS2)
Allowed sources: `buff163`, `skins`
Currencies: EUR, USD, GBP, JPY, CNY, CAD, AUD, CHF, SEK, NZD, AED, and ~150 more.
Prices are returned in raw cents — divide by 100 for display currency.

---

## Endpoints

### GET /items/prices
Fetch prices for items from buff163 and skins.com.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `app_id` | int | - | Game ID (`730` for CS2) |
| `sources` | csv | `buff163,skins` | `buff163`, `skins` |
| `currency` | string | `USD` | Currency code |
| `avg` | bool | `false` | Include 7d/30d/60d/90d avg prices |
| `median` | bool | `false` | Include 7d/30d/60d/90d median prices |
| `inflation_threshold` | number | `-1` | Inflation threshold % |

Response: array of `{ market_hash_name, prices: [{ price, count, updated_at, provider_key }] }`

### GET /trending
Items with biggest price increases.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `period` | enum | - | `1d`, `7d`, `30d`, `90d` |
| `limit` | number | `100` | 1-100 |

Response: `{ period, items: [{ id, market_hash_name, type, image, current_price, old_price, price_change, price_change_percentage }], generated_at }`

### GET /declining
Items with biggest price drops. Same params/response shape as `/trending`.

### GET /insights
Paginated list of curated item categories (e.g. "All Knives", "AK-47 Skins").

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | number | `1` | Page number |
| `limit` | number | `20` | 1-100 |
| `search` | string | - | Search by name/description |
| `category` | string | - | Filter by category |
| `sort` | enum | - | `views`, `avg_change_1d`, `avg_change_7d`, `avg_change_30d`, `current_price`, `total_items`, `created_at` |
| `order` | enum | - | `ASC`, `DESC` |

Response: `{ data: [{ id, name, slug, description, category, stats: { current_price, avg_change_1d, avg_change_7d, avg_change_30d, total_items }, sample_images }], total, page, limit, totalPages }`

### GET /insights/{slug}
Single insight detail with full stats and change history.

Response: `{ id, name, slug, description, category, provider, filters, views, stats: { current_price, total_value, avg_price, highest_price, lowest_price, median_price, total_volume, total_sold, total_items, unique_items }, changes: { 24h, 7d, 30d, 60d, 90d }, stats_updated_at, created_at }`

### GET /insights/{slug}/chart
Timestamped price history for an insight.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | enum | - | `steam`, `buff163`, `csfloat`, `skinport` |

Response: `{ slug, provider, format: "[timestamp, total_min, total_max, total_price, count, sold]", data: [[ts, min, max, price, count, sold], ...], generated_at }`

### GET /alerts
List all price alerts configured on PriceEmpire.

Response: array of `{ id, asset_item: { id, market_hash_name, asset: { name, type } }, type, target_price, provider_key, notification_method, enabled, last_triggered_at, trigger_count, created_at }`

### PUT /alerts/{id}
Update an existing price alert.

### GET /portfolios
List all user portfolios.

Response: array of `{ id, name, slug, provider_key, currency, value, change24h, change24h_percentage, items_count, total_invested, profit_loss, roi }`

### GET /portfolios/{slug}
Full portfolio detail with stats, items, and performance metrics.

Response includes stats: `{ totalValue, totalInvested, totalRealizedPL, totalUnrealizedPL, totalProfit, totalROI, change24h, change24hPercentage, diversificationScore: { overallScore, typeScore, priceRangeScore, wearScore, rarityScore }, timePeriodPerformance: { 1w, 1m, 3m, 6m, 1y: { value, percentage } }, monthlyPerformance: { averageMonthlyReturn, bestMonth: { month, monthName, changePercentage }, worstMonth }, weeklyPatterns: { bestDay: { day, averageChange }, worstDay, weekendVsWeekday: { weekend, weekday } } }`

Items: array of `{ id, market_hash_name, currentPrice, stats: { holdings, avgBuyPrice, currentValue, totalInvested, realizedPL, unrealizedPL, totalProfit, roi } }`

### GET /portfolios/{slug}/signals
Trading signals for portfolio items.

### PUT /portfolios/{id}
Update portfolio settings.

### POST /portfolios/{slug}/transactions
Add a buy/sell transaction to the portfolio.

### PUT /portfolios/{slug}/transactions/{id}
Update an existing transaction.

### GET /portfolios/{slug}/export
Export portfolio data (CSV/JSON).
