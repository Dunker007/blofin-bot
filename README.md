# Blofin Bot 🤖

AI-powered trading bot for Blofin perpetual futures exchange.

## Features

- **AI-Native Trading**: Claude Sonnet 4 for market analysis and trade decisions
- **5 Autonomy Levels**: From manual to fully autonomous trading
- **Rich Terminal Dashboard**: Real-time positions, P&L, and market data
- **Technical Analysis**: RSI, EMA, support/resistance detection
- **Risk Management**: Position sizing, stop-loss requirements, exposure limits

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and add your keys:

```bash
cp .env.example .env
```

Required keys:
- `BLOFIN_API_KEY` - Your Blofin API key
- `BLOFIN_API_SECRET` - Your Blofin API secret
- `BLOFIN_PASSPHRASE` - Your Blofin API passphrase
- `ANTHROPIC_API_KEY` - Claude API key (for AI features)

### 3. Run the Bot

```bash
# Start the dashboard
python -m src.main dashboard

# Or test connection first
python -m src.main test

# Get BTC price
python -m src.main price BTC-USDT

# AI analysis
python -m src.main analyze BTC-USDT

# Get AI trade decision
python -m src.main decision BTC-USDT
```

## Autonomy Levels

Configure in `config/autonomy.yaml`:

| Level | Description |
|-------|-------------|
| `none` | Manual - bot only executes your commands |
| `assistant` | AI analyzes, you decide everything |
| `copilot` | AI suggests trades, you approve (default) |
| `autonomous` | AI trades within rules, notifies you |
| `agent` | Full AI control with capital allocation |

## Project Structure

```
blofin-bot/
├── src/
│   ├── core/           # API client, config, logging
│   ├── data/           # Market and account data
│   ├── ai/             # AI brain and analysis
│   ├── providers/      # Claude API integration
│   ├── dashboard/      # Terminal UI
│   └── main.py         # Entry point
├── config/
│   ├── pairs.yaml      # Trading pairs
│   ├── autonomy.yaml   # Autonomy settings
│   └── ai.yaml         # AI configuration
├── .env.example
├── requirements.txt
├── PLAN.md             # Full feature spec
└── AI_ARCHITECTURE.md  # AI design
```

## Safety

⚠️ **Demo Mode**: By default, the bot runs in demo mode (`BLOFIN_DEMO=true`).

⚠️ **Kill Switch**: Available in all modes - instantly closes all positions.

⚠️ **Risk Limits**: Configured in `autonomy.yaml`:
- Max 3 positions
- Max 30% exposure
- Max 10x leverage
- Stop-loss required

## Development

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## License

MIT
