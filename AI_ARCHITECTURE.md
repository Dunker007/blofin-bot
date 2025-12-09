# Blofin Bot - AI Architecture

## Vision
AI-native trading system. The bot doesn't just execute—it thinks, analyzes, and acts. Human sets the guardrails, AI operates within them.

---

## Autonomy Levels (User Configurable)

```yaml
# config/autonomy.yaml
autonomy_level: "copilot"  # none | assistant | copilot | autonomous | agent

levels:
  none:
    description: "Manual mode - bot executes your commands only"
    ai_analysis: false
    ai_suggestions: false
    ai_execution: false
    requires_approval: N/A
    
  assistant:
    description: "AI analyzes and explains, you decide everything"
    ai_analysis: true
    ai_suggestions: false
    ai_execution: false
    requires_approval: N/A
    
  copilot:
    description: "AI suggests trades, you approve before execution"
    ai_analysis: true
    ai_suggestions: true
    ai_execution: true
    requires_approval: always
    
  autonomous:
    description: "AI trades within your rules, notifies you"
    ai_analysis: true
    ai_suggestions: true
    ai_execution: true
    requires_approval: never  # but respects risk limits
    
  agent:
    description: "Full AI control with capital allocation"
    ai_analysis: true
    ai_suggestions: true
    ai_execution: true
    requires_approval: never
    capital_allocation: true  # AI decides position sizes
```

---

## AI Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BLOFIN BOT                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐   │
│  │  MARKET DATA  │───▶│   AI BRAIN    │───▶│   EXECUTOR    │   │
│  │               │    │               │    │               │   │
│  │ • Price       │    │ • Analysis    │    │ • Orders      │   │
│  │ • Volume      │    │ • Signals     │    │ • Positions   │   │
│  │ • Orderbook   │    │ • Decisions   │    │ • Risk Mgmt   │   │
│  │ • Funding     │    │ • Confidence  │    │ • TP/SL       │   │
│  │ • Candles     │    │               │    │               │   │
│  └───────────────┘    └───────┬───────┘    └───────────────┘   │
│                               │                                 │
│                               ▼                                 │
│                      ┌───────────────┐                         │
│                      │  HUMAN LAYER  │                         │
│                      │               │                         │
│                      │ • Approval    │                         │
│                      │ • Override    │                         │
│                      │ • Kill Switch │                         │
│                      │ • Settings    │                         │
│                      └───────────────┘                         │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                        AI PROVIDER                              │
│                    ┌─────────────┐                              │
│                    │   Claude    │                              │
│                    │  Sonnet 4   │                              │
│                    └─────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## AI Brain Components

### 1. Market Analyzer
```python
# What AI sees every tick/interval
context = {
    "price_action": {
        "current": 95420.50,
        "change_1h": -0.8,
        "change_24h": 2.3,
        "high_24h": 96100,
        "low_24h": 93800
    },
    "structure": {
        "trend": "bullish",
        "key_levels": [94000, 95000, 96000, 97500],
        "recent_breaks": ["95000 reclaimed"]
    },
    "volume": {
        "current_vs_avg": 1.4,
        "buy_sell_ratio": 0.55
    },
    "funding": {
        "current": 0.0012,
        "predicted_next": 0.0008,
        "sentiment": "slightly_long_heavy"
    },
    "orderbook": {
        "bid_wall": 94800,
        "ask_wall": 96200,
        "imbalance": "bid_heavy"
    },
    "positions": {
        "current": [...],
        "exposure": 0.15,  # 15% of account
        "unrealized_pnl": 234.50
    }
}
```

### 2. Decision Engine
```python
class AIDecision:
    action: str          # "long", "short", "close", "adjust", "wait"
    instrument: str      # "BTC-USDT"
    confidence: float    # 0.0 - 1.0
    reasoning: str       # Human-readable explanation
    entry: float         # Suggested entry price
    stop_loss: float     # Suggested SL
    take_profit: float   # Suggested TP
    size: float          # Position size (if agent mode)
    risk_reward: float   # R:R ratio
    timeframe: str       # Expected hold time
    invalidation: str    # "Below 94000" - when to abandon thesis
```

### 3. Confidence Thresholds
```yaml
# config/ai.yaml
confidence_thresholds:
  minimum_to_suggest: 0.6    # Below this, AI stays quiet
  minimum_to_execute: 0.75   # Below this, requires human approval even in autonomous
  high_confidence: 0.85      # AI is very sure
  
execution_rules:
  max_positions: 3
  max_exposure_percent: 30
  max_single_position_percent: 10
  require_stop_loss: true
  max_leverage: 10
  
  # Time-based rules
  no_trading_hours: ["00:00-02:00"]  # Optional quiet hours
  funding_window_pause: 5  # Minutes before/after funding to pause
```

### 4. Decision Logging
Every AI decision is logged for review:
```python
{
    "timestamp": "2024-12-09T10:23:45Z",
    "decision_id": "dec_abc123",
    "autonomy_level": "copilot",
    "market_context": {...},  # Full snapshot
    "decision": {
        "action": "long",
        "instrument": "BTC-USDT",
        "confidence": 0.78,
        "reasoning": "Price reclaimed 95k with increasing volume. Funding negative suggesting shorts are paying longs. Orderbook shows bid support at 94.8k. R:R of 2.5:1 to next resistance."
    },
    "human_action": "approved",  # approved | rejected | modified | timeout
    "execution": {
        "executed": true,
        "fill_price": 95150,
        "slippage": 0.02
    },
    "outcome": {  # Filled in later
        "result": "win",
        "pnl": 425.00,
        "r_multiple": 1.8,
        "hold_time": "4h 23m"
    }
}
```

---

## Model Provider

Claude is the brain. Keep it simple.

```python
class ModelProvider:
    provider = {
        "name": "claude",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-20250514",
        "capabilities": ["analysis", "signals", "complex_reasoning"]
    }
```

---

## Human Override System

### Kill Switch
```python
# Always available, any mode
EMERGENCY_STOP = {
    "close_all_positions": true,
    "cancel_all_orders": true,
    "pause_ai": true,
    "notify": ["console", "sound", "desktop"]
}

# Keyboard shortcut in dashboard: Ctrl+K
# API endpoint: POST /emergency-stop
# Voice command (future): "Stop everything"
```

### Approval Queue (Copilot Mode)
```
┌────────────────────────────────────────────────────────┐
│ PENDING APPROVAL                                [1/3]  │
├────────────────────────────────────────────────────────┤
│ 🟢 LONG BTC-USDT                                       │
│                                                        │
│ Entry:  $95,150    Size: 0.05 BTC ($4,757)            │
│ Stop:   $94,200    Risk: $47.50 (1%)                  │
│ TP:     $97,500    Reward: $117.50 (2.47R)            │
│                                                        │
│ Confidence: 78%                                        │
│                                                        │
│ Reasoning:                                             │
│ "Price reclaimed 95k with volume. Funding negative.   │
│  Bid wall at 94.8k. Clean R:R to 97.5k resistance."   │
│                                                        │
│ [A]pprove   [R]eject   [M]odify   [S]kip              │
└────────────────────────────────────────────────────────┘
```

### Session Limits
```yaml
# Even in agent mode, hard limits apply
session_limits:
  max_trades_per_day: 10
  max_loss_percent_daily: 5
  max_loss_streak: 3  # Pause after 3 consecutive losses
  mandatory_review_after: 5  # Human must review after 5 trades
```

---

## Updated Folder Structure

```
blofin-bot/
├── src/
│   ├── ai/                    # NEW - AI Brain
│   │   ├── brain.py           # Main AI coordinator
│   │   ├── analyzer.py        # Market analysis
│   │   ├── decision.py        # Decision engine
│   │   ├── confidence.py      # Confidence scoring
│   │   ├── prompts/           # System prompts for each task
│   │   │   ├── analysis.txt
│   │   │   ├── entry.txt
│   │   │   ├── exit.txt
│   │   │   └── risk.txt
│   │   └── router.py          # Model routing
│   │
│   ├── providers/             # NEW - AI Provider
│   │   └── claude.py          # Anthropic API
│   │
│   ├── human/                 # NEW - Human Layer
│   │   ├── approval.py        # Approval queue
│   │   ├── override.py        # Kill switch, manual control
│   │   └── limits.py          # Session limits
│   │
│   ├── journal/               # UPDATED
│   │   ├── trades.py
│   │   ├── decisions.py       # NEW - AI decision log
│   │   ├── performance.py
│   │   └── review.py          # NEW - Review AI performance
│   │
│   └── ... (rest same as before)
│
├── config/
│   ├── autonomy.yaml          # NEW - Autonomy settings
│   ├── ai.yaml                # NEW - AI configuration
│   ├── providers.yaml         # NEW - Model provider settings
│   └── ... (rest same)
│
└── prompts/                   # NEW - Editable AI prompts
    ├── system.md              # Base personality/rules
    ├── market_analysis.md
    ├── trade_decision.md
    └── risk_assessment.md
```

---

## AI Prompt Strategy

Prompts live in files so you can tune them without code changes:

**prompts/system.md**
```markdown
You are a crypto futures trading analyst for Blofin exchange.

Your job:
- Analyze market data objectively
- Identify high-probability setups
- Quantify confidence in your analysis
- Explain reasoning clearly

Your rules:
- Never chase moves
- Always define invalidation
- Risk:Reward minimum 1.5:1
- Funding rates matter
- Liquidity matters
- You can say "no trade" - that's often the best trade

You will receive market data in structured format.
Respond with structured decisions.
```

**prompts/trade_decision.md**
```markdown
Given the market context, decide:

1. ACTION: long | short | close | wait
2. CONFIDENCE: 0-100%
3. ENTRY: price
4. STOP: price (required)
5. TARGET: price
6. REASONING: 2-3 sentences max
7. INVALIDATION: what kills this idea

If confidence < 60%, ACTION must be "wait".
If no clear edge, say so.
```

---

## Development Priority Update

### Phase 1: Core + AI Foundation
- [x] Repo setup
- [ ] Core infrastructure (client, config, logging)
- [ ] Market data layer
- [ ] AI provider abstraction (Claude/Gemini/OpenAI)
- [ ] Basic brain with analysis capability
- [ ] Autonomy level: "assistant" working

### Phase 2: Copilot Mode
- [ ] Decision engine
- [ ] Confidence scoring
- [ ] Approval queue UI
- [ ] Decision logging
- [ ] Autonomy level: "copilot" working

### Phase 3: Trading + Risk
- [ ] Order execution
- [ ] Position management
- [ ] Risk limits
- [ ] Kill switch
- [ ] Human override system

### Phase 4: Autonomous Mode
- [ ] Auto-execution pipeline
- [ ] Session limits
- [ ] Performance tracking
- [ ] Autonomy level: "autonomous" working

### Phase 5: Agent Mode + Polish
- [ ] Capital allocation logic
- [ ] Advanced strategy support
- [ ] Dashboard polish
- [ ] Autonomy level: "agent" working (with heavy guardrails)

---

## Safety Notes

⚠️ **Agent mode is dangerous.** Even with limits:
- Start with tiny capital
- Run in demo mode first
- Always have kill switch accessible
- Review AI decisions daily
- Tune confidence thresholds conservatively
- Log everything

The goal isn't to remove the human—it's to give the human superpowers.
