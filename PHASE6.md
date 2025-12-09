# Phase 6: Advanced Features

## Overview
With core trading, AI brain, and dashboards complete, Phase 6 adds the features that make this a serious edge.

---

## 6.1 WebSocket Real-Time Data

Replace polling with live streams. Faster reactions, less API calls.

**Files:**
- `src/data/websocket.py` - WebSocket manager

**Features:**
| Feature | Description |
|---------|-------------|
| Price Stream | Real-time ticker updates |
| Orderbook Stream | Live depth changes |
| Trade Stream | Executed trades feed |
| Position Stream | Live position updates (private) |
| Order Stream | Order status changes (private) |
| Auto-reconnect | Handle disconnects gracefully |

**Blofin WebSocket Endpoints:**
```
Public:  wss://openapi.blofin.com/ws/public
Private: wss://openapi.blofin.com/ws/private
```

**Subscribe Messages:**
```json
{"op": "subscribe", "args": [{"channel": "tickers", "instId": "BTC-USDT"}]}
{"op": "subscribe", "args": [{"channel": "books5", "instId": "BTC-USDT"}]}
{"op": "subscribe", "args": [{"channel": "trades", "instId": "BTC-USDT"}]}
{"op": "subscribe", "args": [{"channel": "positions"}]}  // Private
{"op": "subscribe", "args": [{"channel": "orders"}]}     // Private
```

---

## 6.2 Backtesting Engine

Test strategies before risking real money.

**Files:**
- `src/strategies/backtest.py` - Backtesting engine
- `src/strategies/results.py` - Results analysis
- `data/candles/` - Historical data cache

**Features:**
| Feature | Description |
|---------|-------------|
| Historical Data | Fetch and cache candles |
| Strategy Runner | Run any strategy on historical data |
| Metrics | Win rate, profit factor, max drawdown, Sharpe |
| Trade Log | Every simulated trade recorded |
| Equity Curve | Visualize performance over time |
| Compare | Run multiple strategies side by side |

**Usage:**
```python
from strategies.backtest import Backtest
from strategies.my_strategy import MyStrategy

bt = Backtest(
    strategy=MyStrategy(),
    symbol="BTC-USDT",
    start="2024-01-01",
    end="2024-12-01",
    initial_balance=10000
)

results = bt.run()
print(results.summary())
results.plot_equity_curve()
```

---

## 6.3 Signal Webhook Receiver

Receive signals from TradingView, custom scripts, or other services.

**Files:**
- `src/strategies/webhook.py` - Webhook server
- `src/strategies/signal_processor.py` - Signal validation and execution

**Features:**
| Feature | Description |
|---------|-------------|
| HTTP Endpoint | Receive POST signals |
| Auth | API key validation |
| Signal Format | Standardized JSON schema |
| Validation | Check required fields, validate values |
| Routing | Route to appropriate action |
| Logging | All signals logged |

**Signal Schema:**
```json
{
    "secret": "your_webhook_secret",
    "symbol": "BTC-USDT",
    "action": "long",           // long, short, close
    "price": 95000,             // optional, market if omitted
    "stop_loss": 94000,         // optional
    "take_profit": 98000,       // optional
    "size_percent": 5,          // optional, default from config
    "source": "tradingview",    // identifier
    "message": "RSI oversold"   // optional note
}
```

**TradingView Alert Example:**
```
{"secret":"{{strategy.order.alert_message}}","symbol":"BTC-USDT","action":"{{strategy.order.action}}","price":{{close}}}
```

---

## 6.4 Multi-Account Support

Trade across multiple Blofin accounts or subaccounts.

**Files:**
- `src/core/accounts.py` - Account manager
- `config/accounts.yaml` - Account configurations

**Features:**
| Feature | Description |
|---------|-------------|
| Multiple APIs | Store multiple API key sets |
| Account Switching | Switch active account in dashboard |
| Aggregate View | See all accounts at once |
| Copy Trading | Mirror trades across accounts |
| Per-Account Limits | Different risk settings per account |

**Config:**
```yaml
accounts:
  main:
    api_key: ${BLOFIN_API_KEY}
    api_secret: ${BLOFIN_API_SECRET}
    passphrase: ${BLOFIN_PASSPHRASE}
    max_leverage: 10
    
  degen:
    api_key: ${BLOFIN_DEGEN_KEY}
    api_secret: ${BLOFIN_DEGEN_SECRET}
    passphrase: ${BLOFIN_DEGEN_PASS}
    max_leverage: 50
    
default_account: main
```

---

## 6.5 Discord/Telegram Notifications

Push alerts to your phone.

**Files:**
- `src/alerts/discord.py` - Discord webhook
- `src/alerts/telegram.py` - Telegram bot
- `config/notifications.yaml` - Channel config

**Features:**
| Feature | Description |
|---------|-------------|
| Trade Alerts | New position, closed position |
| P&L Updates | Periodic portfolio summary |
| Price Alerts | Level hits |
| AI Decisions | When AI wants to trade (copilot mode) |
| Error Alerts | Connection issues, failures |
| Custom Messages | Send from dashboard |

**Discord Webhook:**
```python
import requests

def send_discord(webhook_url: str, message: str, embed: dict = None):
    payload = {"content": message}
    if embed:
        payload["embeds"] = [embed]
    requests.post(webhook_url, json=payload)
```

**Telegram Bot:**
```python
import requests

def send_telegram(bot_token: str, chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"})
```

---

## 6.6 Advanced Order Types

More sophisticated order handling.

**Files:**
- `src/trading/advanced_orders.py` - Advanced order types

**Features:**
| Feature | Description |
|---------|-------------|
| Trailing Stop | Stop follows price at fixed distance |
| Scaled Entry | Multiple limit orders at different prices |
| Scaled Exit | Multiple TPs at different levels |
| Time-Based | Orders that expire after duration |
| Iceberg | Large orders split into smaller chunks |
| TWAP | Time-weighted average price execution |

**Trailing Stop Logic:**
```python
class TrailingStop:
    def __init__(self, symbol: str, side: str, distance: float, activation: float = None):
        self.symbol = symbol
        self.side = side  # long or short
        self.distance = distance  # In price or percent
        self.activation = activation  # Price to activate trailing
        self.highest = None  # Track best price
        self.stop_price = None
    
    def update(self, current_price: float) -> Optional[float]:
        """Update trailing stop, return trigger price if hit."""
        if self.side == "long":
            if self.highest is None or current_price > self.highest:
                self.highest = current_price
                self.stop_price = self.highest - self.distance
            if current_price <= self.stop_price:
                return self.stop_price  # Triggered
        # Similar for short...
        return None
```

---

## 6.7 Performance Analytics Dashboard

Deep dive into trading performance.

**Files:**
- `src/journal/analytics.py` - Analytics engine
- `src/dashboard/views/analytics.py` - Analytics view

**Features:**
| Feature | Description |
|---------|-------------|
| Equity Curve | Account value over time |
| Drawdown Chart | Visualize drawdowns |
| Win/Loss Streaks | Identify patterns |
| By Symbol | Performance per trading pair |
| By Time | Best/worst days, hours |
| By Setup | Performance per strategy/setup type |
| Risk Metrics | Sharpe, Sortino, Calmar ratios |
| Expectancy | Average R per trade |

**Key Metrics:**
```python
@dataclass
class PerformanceMetrics:
    total_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    max_drawdown: float
    max_drawdown_duration: timedelta
    sharpe_ratio: float
    sortino_ratio: float
    expectancy: float  # Avg R per trade
    avg_hold_time: timedelta
```

---

## 6.8 Strategy Builder (AI-Assisted)

Let AI help build and refine strategies.

**Files:**
- `src/strategies/builder.py` - Strategy builder
- `src/ai/strategy_assistant.py` - AI strategy helper

**Features:**
| Feature | Description |
|---------|-------------|
| Natural Language | "Entry when RSI < 30 and price above 20 EMA" |
| Code Generation | AI writes the strategy code |
| Backtest Integration | Immediately test generated strategy |
| Optimization | AI suggests parameter tweaks |
| Explanation | AI explains why strategy works/doesn't |

**Usage:**
```python
builder = StrategyBuilder(brain)

strategy = builder.create("""
    Long when:
    - RSI below 30
    - Price above 200 EMA
    - Funding rate negative
    
    Exit when:
    - RSI above 70
    - Or 2% profit
    - Or 1% loss
""")

# Returns executable Strategy object
results = backtest(strategy, "BTC-USDT", "2024-01-01", "2024-12-01")
```

---

## Development Order

1. **WebSocket** - Foundation for real-time everything
2. **Discord/Telegram** - Get alerts on your phone
3. **Webhook Receiver** - Accept external signals
4. **Advanced Orders** - Trailing stops, scaled entries
5. **Backtesting** - Test before you trade
6. **Analytics** - Understand your performance
7. **Multi-Account** - Scale up
8. **Strategy Builder** - AI creates strategies

---

## File Checklist

```
src/
├── data/
│   └── websocket.py           [ ] NEW
├── strategies/
│   ├── backtest.py            [ ] NEW
│   ├── results.py             [ ] NEW
│   ├── webhook.py             [ ] NEW
│   └── signal_processor.py    [ ] NEW
├── trading/
│   └── advanced_orders.py     [ ] NEW
├── alerts/
│   ├── discord.py             [ ] NEW
│   └── telegram.py            [ ] NEW
├── journal/
│   └── analytics.py           [ ] NEW
├── ai/
│   └── strategy_assistant.py  [ ] NEW
├── core/
│   └── accounts.py            [ ] NEW
└── dashboard/
    └── views/
        └── analytics.py       [ ] NEW

config/
├── accounts.yaml              [ ] NEW
└── notifications.yaml         [ ] NEW
```

---

## Dependencies to Add

```
# requirements.txt additions
websockets>=12.0
discord-webhook>=1.3.0
python-telegram-bot>=20.0
plotly>=5.18.0          # For equity curves
pandas>=2.0.0           # For backtesting data
numpy>=1.24.0           # For calculations
```
