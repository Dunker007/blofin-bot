# Blofin Bot - Development Plan

## Vision
Full-featured trading bot and dashboard for Blofin perpetual futures. Not a toy—a real tool for real trading.

---

## Architecture

```
blofin-bot/
├── src/
│   ├── core/
│   │   ├── client.py          # Blofin API wrapper
│   │   ├── config.py          # Settings + pair configs
│   │   ├── logger.py          # Logging system
│   │   └── exceptions.py      # Custom error handling
│   │
│   ├── data/
│   │   ├── market.py          # Price, orderbook, candles
│   │   ├── account.py         # Balance, positions, orders
│   │   ├── funding.py         # Funding rate tracking
│   │   └── websocket.py       # Real-time data streams
│   │
│   ├── trading/
│   │   ├── orders.py          # Order placement + management
│   │   ├── positions.py       # Position management + TP/SL
│   │   ├── risk.py            # Position sizing, risk calcs
│   │   └── templates.py       # Predefined order templates
│   │
│   ├── strategies/
│   │   ├── base.py            # Strategy interface
│   │   ├── signals.py         # Signal generation + ingestion
│   │   ├── indicators.py      # Technical indicators
│   │   └── backtest.py        # Historical testing
│   │
│   ├── alerts/
│   │   ├── price.py           # Price level alerts
│   │   ├── funding.py         # Funding rate alerts
│   │   ├── position.py        # P&L, liquidation warnings
│   │   └── notify.py          # Notification dispatcher
│   │
│   ├── dashboard/
│   │   ├── terminal.py        # CLI dashboard (rich/textual)
│   │   ├── web.py             # Local web UI (optional)
│   │   └── views/
│   │       ├── positions.py   # Position view
│   │       ├── orders.py      # Order view
│   │       ├── market.py      # Market overview
│   │       └── performance.py # Trade journal + stats
│   │
│   ├── journal/
│   │   ├── trades.py          # Trade logging
│   │   ├── performance.py     # Win rate, R multiples, etc
│   │   └── export.py          # CSV/JSON export
│   │
│   └── main.py                # Entry point
│
├── config/
│   ├── pairs.yaml             # Trading pair configurations
│   ├── alerts.yaml            # Alert thresholds
│   └── strategies.yaml        # Strategy parameters
│
├── data/
│   ├── candles/               # Cached historical data
│   ├── trades/                # Trade journal storage
│   └── logs/                  # Application logs
│
├── tests/
│   ├── test_client.py
│   ├── test_orders.py
│   └── test_strategies.py
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── PLAN.md
```

---

## Feature Breakdown

### 1. Core Infrastructure
| Feature | Description | Priority |
|---------|-------------|----------|
| API Client | Wrapped Blofin SDK with retry logic, rate limiting | P0 |
| Config System | YAML-based config for pairs, alerts, strategies | P0 |
| Logging | Structured logging with rotation | P0 |
| Error Handling | Graceful failures, reconnection logic | P0 |

### 2. Market Data
| Feature | Description | Priority |
|---------|-------------|----------|
| Ticker Feed | Real-time price for watchlist pairs | P0 |
| Order Book | Depth visualization, liquidity analysis | P1 |
| Candles | OHLCV data, multiple timeframes | P0 |
| Funding Rates | Current + historical, prediction | P1 |
| WebSocket | Real-time streams vs polling | P1 |

### 3. Account Data
| Feature | Description | Priority |
|---------|-------------|----------|
| Balance | Total equity, available margin, unrealized P&L | P0 |
| Positions | All open positions with full details | P0 |
| Open Orders | Pending orders, ability to cancel | P0 |
| Order History | Filled orders, historical trades | P1 |
| Transaction Log | Deposits, withdrawals, fees | P2 |

### 4. Trading Engine
| Feature | Description | Priority |
|---------|-------------|----------|
| Market Orders | Instant execution | P0 |
| Limit Orders | Price-specific entries | P0 |
| Stop Orders | Stop loss, stop entry | P0 |
| Take Profit | TP orders, partial TPs | P0 |
| Trailing Stop | Dynamic stop that follows price | P1 |
| OCO Orders | One-cancels-other | P1 |
| Order Templates | Saved order configurations | P1 |
| Batch Orders | Multiple orders at once | P2 |

### 5. Position Management
| Feature | Description | Priority |
|---------|-------------|----------|
| Quick TP/SL | Set/adjust TP/SL on existing positions | P0 |
| Position Sizing | Calculate size from risk % | P0 |
| Partial Close | Close portion of position | P1 |
| Break Even | Move stop to entry | P1 |
| Scale In/Out | Add to or reduce position | P1 |
| Liquidation Warning | Alert when approaching liq price | P0 |

### 6. Risk Management
| Feature | Description | Priority |
|---------|-------------|----------|
| Risk Calculator | Position size from stop distance + risk % | P0 |
| Max Position Size | Hard limits per pair | P1 |
| Daily Loss Limit | Stop trading after X% daily loss | P1 |
| Exposure Limits | Max total exposure across positions | P1 |
| Correlation Check | Warn on correlated positions | P2 |

### 7. Alerts System
| Feature | Description | Priority |
|---------|-------------|----------|
| Price Alerts | Cross above/below level | P0 |
| Funding Alerts | High/low funding rate | P1 |
| P&L Alerts | Position hits target/stop | P0 |
| Liquidation Alerts | Approaching liquidation | P0 |
| Volume Alerts | Unusual volume spike | P2 |
| Custom Alerts | User-defined conditions | P2 |

**Notification Channels:**
- Console/Terminal
- Desktop notifications (Windows toast)
- Sound alerts
- Discord webhook (future)
- Telegram (future)

### 8. Strategies & Signals
| Feature | Description | Priority |
|---------|-------------|----------|
| Signal Interface | Standard format for buy/sell signals | P1 |
| External Signals | Ingest from webhook, file, or API | P1 |
| Built-in Indicators | RSI, EMA, MACD, BB, etc. | P2 |
| Strategy Engine | Execute trades based on signals | P1 |
| Auto-Execute | Hands-off signal execution | P2 |
| Backtesting | Test strategies on historical data | P2 |

### 9. Dashboard & UI
| Feature | Description | Priority |
|---------|-------------|----------|
| Terminal Dashboard | Rich CLI with live updates | P0 |
| Position Panel | Current positions, P&L, liq price | P0 |
| Order Panel | Open orders, quick cancel | P0 |
| Market Panel | Watchlist prices, funding | P0 |
| Trade Panel | Quick order entry | P1 |
| Performance Panel | Daily/weekly/monthly stats | P1 |
| Web Dashboard | Browser-based UI (localhost) | P2 |

### 10. Trade Journal
| Feature | Description | Priority |
|---------|-------------|----------|
| Auto-Logging | Every trade recorded automatically | P1 |
| Trade Notes | Add notes to trades | P2 |
| Performance Stats | Win rate, avg R, expectancy | P1 |
| Equity Curve | Visualize account growth | P2 |
| Export | CSV, JSON for external analysis | P1 |

---

## Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | Python 3.11+ | SDK available, fast iteration |
| API SDK | `blofin` | Official, maintained |
| Config | PyYAML | Human-readable configs |
| CLI UI | `rich` / `textual` | Beautiful terminal dashboards |
| Web UI | FastAPI + HTMX | Lightweight, no JS framework needed |
| Database | SQLite | Simple, portable, no server |
| Testing | pytest | Standard, reliable |

---

## Development Phases

### Phase 1: Core + Visibility (Week 1-2)
- [ ] Project structure setup
- [ ] Core client with error handling
- [ ] Config system
- [ ] Logging
- [ ] Market data (tickers, candles)
- [ ] Account data (balance, positions)
- [ ] Basic terminal dashboard

**Milestone:** Can view positions and prices in terminal

### Phase 2: Trading Engine (Week 3-4)
- [ ] Order placement (market, limit, stop)
- [ ] TP/SL management
- [ ] Position sizing calculator
- [ ] Order templates
- [ ] Enhanced dashboard with order panel

**Milestone:** Can execute trades through bot

### Phase 3: Alerts + Risk (Week 5-6)
- [ ] Price alerts
- [ ] P&L alerts
- [ ] Liquidation warnings
- [ ] Risk calculator
- [ ] Position limits

**Milestone:** Never miss a level, never over-leverage

### Phase 4: Strategy Layer (Week 7-8)
- [ ] Signal interface
- [ ] External signal ingestion
- [ ] Basic indicators
- [ ] Auto-execution
- [ ] Backtesting framework

**Milestone:** Can auto-trade signals

### Phase 5: Polish + Scale (Week 9+)
- [ ] Trade journal
- [ ] Performance analytics
- [ ] Web dashboard
- [ ] Multi-pair monitoring
- [ ] WebSocket optimization

**Milestone:** Production-ready trading system

---

## API Reference

### Blofin Endpoints Used

**Public (no auth)**
- `GET /api/v1/market/tickers` - All tickers
- `GET /api/v1/market/ticker` - Single ticker
- `GET /api/v1/market/books` - Order book
- `GET /api/v1/market/candles` - OHLCV data
- `GET /api/v1/market/funding-rate` - Funding rates

**Account (auth required)**
- `GET /api/v1/account/balance` - Account balance
- `GET /api/v1/account/positions` - Open positions
- `GET /api/v1/account/bills` - Transaction history

**Trading (auth required)**
- `POST /api/v1/trade/order` - Place order
- `POST /api/v1/trade/cancel-order` - Cancel order
- `POST /api/v1/trade/close-position` - Close position
- `GET /api/v1/trade/orders-pending` - Open orders
- `GET /api/v1/trade/orders-history` - Order history

**WebSocket**
- `wss://openapi.blofin.com/ws/public` - Public streams
- `wss://openapi.blofin.com/ws/private` - Private streams

---

## Notes

- Start with public endpoints to verify structure before adding auth
- Use demo trading endpoint for testing: `https://demo-trading-openapi.blofin.com`
- Rate limits: 500 req/min (IP), 30 req/10s (trading, user-based)
- All timestamps in milliseconds
- Leverage up to 150x available (use responsibly)

---

## Getting Started (For Antigravity/Gemini)

1. Work in `C:/Repos GIT/blofin-bot`
2. Follow structure above
3. Start with `src/core/` - client, config, logger
4. Then `src/data/` - market and account data
5. Build dashboard early so progress is visible
6. Auth can be added later - public endpoints work without it

**Key files to create first:**
1. `src/core/client.py` - API wrapper
2. `src/core/config.py` - Settings loader
3. `src/data/market.py` - Ticker/candle fetching
4. `src/data/account.py` - Balance/position fetching
5. `src/dashboard/terminal.py` - CLI view

Let's build something real.
