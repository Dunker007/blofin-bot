"""FastAPI web dashboard for Blofin Bot."""

from datetime import datetime
from typing import Dict, List, Optional
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from ..core.config import Config
from ..core.client import BlofinClient
from ..trading.engine import TradingEngine
from ..core.logger import get_logger

logger = get_logger(__name__)


# ==================== Request/Response Models ====================

class TradeRequest(BaseModel):
    """Manual trade request."""
    symbol: str
    side: str  # long/short
    size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class ApprovalRequest(BaseModel):
    """Approval request."""
    decision_id: str
    action: str  # approve/reject
    notes: str = ""


class TPSLRequest(BaseModel):
    """TP/SL update request."""
    symbol: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class ChatRequest(BaseModel):
    """Chat message request."""
    message: str
    symbol: Optional[str] = None  # Optional symbol context


class WatchlistAddRequest(BaseModel):
    """Add symbol to watchlist."""
    symbol: str
    notes: str = ""
    tags: List[str] = []


class AlertRequest(BaseModel):
    """Price alert request."""
    symbol: str
    condition: str  # above/below
    price: float


class TradePlanRequest(BaseModel):
    """Create trade plan."""
    symbol: str
    side: str  # long/short
    entry: float
    stop_loss: float
    take_profit: float
    size_percent: float = 1.0
    leverage: int = 3
    notes: str = ""


class RRCalcRequest(BaseModel):
    """R:R calculator request."""
    entry: float
    stop_loss: float
    take_profit: float
    side: str = "long"


# ==================== WebSocket Manager ====================

class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


# ==================== Create API ====================

def create_api(engine: TradingEngine) -> FastAPI:
    """
    Create FastAPI app with trading endpoints.
    
    Args:
        engine: Initialized TradingEngine
    
    Returns:
        FastAPI app
    """
    app = FastAPI(
        title="Blofin Bot API",
        description="AI-Powered Trading Bot Dashboard",
        version="0.1.0"
    )
    
    manager = ConnectionManager()
    
    # ==================== Status Endpoints ====================
    
    @app.get("/api/status")
    async def get_status():
        """Get bot status."""
        return engine.get_status()
    
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "demo_mode": engine.config.api.demo_mode,
        }
    
    # ==================== Market Data ====================
    
    @app.get("/api/ticker/{symbol}")
    async def get_ticker(symbol: str):
        """Get ticker for symbol."""
        try:
            ticker = engine.market.get_ticker(symbol)
            return {
                "symbol": ticker.symbol,
                "last": ticker.last,
                "change_24h": ticker.change_24h,
                "high_24h": ticker.high_24h,
                "low_24h": ticker.low_24h,
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/api/tickers")
    async def get_tickers(symbols: Optional[str] = None):
        """Get tickers for symbols (comma-separated)."""
        symbol_list = symbols.split(",") if symbols else None
        tickers = engine.market.get_tickers(symbol_list)
        return [
            {
                "symbol": t.symbol,
                "last": t.last,
                "change_24h": t.change_24h,
            }
            for t in tickers
        ]
    
    # ==================== Account ====================
    
    @app.get("/api/account")
    async def get_account():
        """Get account summary."""
        try:
            return engine.account.get_account_summary()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/api/positions")
    async def get_positions():
        """Get open positions."""
        return engine.positions.get_position_summary()
    
    @app.get("/api/orders")
    async def get_orders():
        """Get open orders."""
        return engine.orders.get_open_orders()
    
    # ==================== AI ====================
    
    @app.get("/api/decision/{symbol}")
    async def get_decision(symbol: str):
        """Get AI decision for symbol."""
        try:
            decision = engine.get_decision(symbol)
            return decision.to_dict()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/api/approvals")
    async def get_pending_approvals():
        """Get pending approvals."""
        return engine.get_pending_approvals()
    
    @app.post("/api/approve")
    async def approve_decision(request: ApprovalRequest):
        """Approve or reject a decision."""
        if request.action == "approve":
            success, execution = engine.approve_and_execute(request.decision_id)
            return {
                "success": success,
                "execution": execution.order_result.to_dict() if execution else None
            }
        else:
            success = engine.reject_decision(request.decision_id, request.notes)
            return {"success": success}
    
    # ==================== Trading ====================
    
    @app.post("/api/trade")
    async def place_trade(request: TradeRequest):
        """Place a manual trade."""
        if engine.is_paused:
            raise HTTPException(status_code=400, detail="Trading is paused")
        
        try:
            result = engine.quick_trade(
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                stop_loss=request.stop_loss,
                take_profit=request.take_profit
            )
            return result.to_dict()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.post("/api/close/{symbol}")
    async def close_position(symbol: str):
        """Close a position."""
        success = engine.close_position(symbol)
        return {"success": success, "symbol": symbol}
    
    @app.post("/api/close-all")
    async def close_all_positions():
        """Close all positions."""
        count = engine.close_all_positions()
        return {"success": True, "closed": count}
    
    @app.post("/api/tpsl")
    async def set_tpsl(request: TPSLRequest):
        """Set TP/SL for a position."""
        success = engine.positions.set_tpsl(
            request.symbol,
            request.stop_loss,
            request.take_profit
        )
        return {"success": success}
    
    # ==================== Controls ====================
    
    @app.post("/api/kill-switch")
    async def kill_switch():
        """Emergency kill switch."""
        result = engine.kill_switch()
        await manager.broadcast({"type": "kill_switch", "data": result})
        return {"success": True, "result": result}
    
    @app.post("/api/pause")
    async def pause_trading(reason: str = ""):
        """Pause AI trading."""
        engine.pause(reason)
        return {"success": True, "paused": True}
    
    @app.post("/api/resume")
    async def resume_trading():
        """Resume AI trading."""
        engine.resume()
        return {"success": True, "paused": False}
    
    # ==================== Journal ====================
    
    @app.get("/api/journal/decisions")
    async def get_decisions(limit: int = 50):
        """Get recent AI decisions."""
        return engine.decision_journal.get_recent(limit)
    
    @app.get("/api/journal/trades")
    async def get_trades(limit: int = 50):
        """Get recent trades."""
        return engine.trade_journal.get_trades(limit=limit)
    
    @app.get("/api/journal/stats")
    async def get_stats():
        """Get trading statistics."""
        return engine.trade_journal.get_performance_stats()
    
    # ==================== Chat ====================
    
    @app.post("/api/chat")
    async def chat_with_ai(request: ChatRequest):
        """
        Chat with the portfolio-aware AI assistant.
        AI has context of positions, market data, and decisions.
        """
        try:
            # Build context from current state
            context_parts = []
            
            # Add account balance context
            try:
                balance = engine.account.get_balance()
                context_parts.append(f"Account: ${balance.total_equity:,.2f} equity, ${balance.available_balance:,.2f} available")
                if balance.unrealized_pnl != 0:
                    context_parts.append(f"Unrealized P&L: ${balance.unrealized_pnl:+,.2f}")
            except:
                context_parts.append("Account: Unable to fetch balance")
            
            # Add position context
            try:
                positions = engine.positions.get_position_summary()
                if positions.get("positions"):
                    pos_text = "Current Positions:\\n"
                    for p in positions["positions"]:
                        pos_text += f"- {p['symbol']}: {p['side'].upper()} {p['size']} (P&L: ${p.get('pnl', 0):+.2f})\\n"
                    context_parts.append(pos_text)
                else:
                    context_parts.append("Current Positions: None")
            except:
                context_parts.append("Current Positions: Unable to fetch")
            
            # Add market context for specific symbol
            if request.symbol:
                try:
                    ticker = engine.market.get_ticker(request.symbol)
                    context_parts.append(f"\\n{request.symbol} Price: ${ticker.last:,.2f} ({ticker.change_24h:+.2f}% 24h)")
                except:
                    pass
            
            # Add pending approvals
            pending = engine.get_pending_approvals()
            if pending:
                context_parts.append(f"\\nPending Approvals: {len(pending)} trades awaiting decision")
            
            # Add session stats
            try:
                stats = engine.limits.get_stats()
                context_parts.append(f"\\nToday: {stats['trades_today']} trades, P&L: ${stats['daily_pnl']:+.2f}")
            except:
                pass
            
            # Combine context
            full_context = "\\n".join(context_parts)
            
            # Get AI response
            if engine.brain and engine.brain.provider.client:
                response = engine.brain.chat(request.message, full_context)
            else:
                response = "AI not configured. Please set ANTHROPIC_API_KEY in your .env file to enable chat."
            
            return {
                "success": True,
                "response": response,
                "context": full_context
            }
            
        except Exception as e:
            return {
                "success": False,
                "response": f"Error: {str(e)}",
                "context": ""
            }
    
    # ==================== WebSocket ====================
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket for real-time updates."""
        await manager.connect(websocket)
        try:
            while True:
                # Wait for messages from client
                data = await websocket.receive_text()
                
                # Handle subscription requests
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "subscribe":
                        # Handle subscription
                        pass
                except:
                    pass
                
        except WebSocketDisconnect:
            manager.disconnect(websocket)
    
    return app


# ==================== Dashboard HTML ====================

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Blofin Bot Dashboard</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a25;
            --text-primary: #e4e4e7;
            --text-secondary: #71717a;
            --accent: #3b82f6;
            --green: #22c55e;
            --red: #ef4444;
            --yellow: #eab308;
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        .main-layout {
            display: flex;
            min-height: calc(100vh - 120px);
        }
        
        .main-content {
            flex: 2;
            padding: 1rem 1.5rem;
            overflow-y: auto;
        }
        
        .sidebar-chat {
            flex: 1;
            max-width: 400px;
            min-width: 300px;
            background: var(--bg-secondary);
            border-left: 1px solid var(--border);
            display: flex;
            flex-direction: column;
        }
        
        .container {
            max-width: 100%;
            padding: 0;
        }
        
        header {
            background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-card) 100%);
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .status-badge {
            padding: 0.5rem 1rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        
        .status-demo { background: rgba(234,179,8,0.2); color: var(--yellow); }
        .status-live { background: rgba(239,68,68,0.2); color: var(--red); }
        .status-active { background: rgba(34,197,94,0.2); color: var(--green); }
        
        .grid {
            display: grid;
            gap: 1rem;
            margin-top: 1rem;
        }
        
        .grid-2 { grid-template-columns: repeat(2, 1fr); }
        .grid-3 { grid-template-columns: repeat(3, 1fr); }
        .grid-4 { grid-template-columns: repeat(4, 1fr); }
        
        .card {
            background: var(--bg-card);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 1.5rem;
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        
        .card-title {
            font-size: 0.875rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .metric {
            font-size: 2rem;
            font-weight: 700;
        }
        
        .metric-sub {
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        .positive { color: var(--green); }
        .negative { color: var(--red); }
        
        .metric-card {
            background: var(--bg-tertiary);
            padding: 1rem;
            border-radius: 12px;
            text-align: center;
        }
        .metric-card .metric-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }
        .metric-card .metric-value {
            font-size: 1.25rem;
            font-weight: bold;
        }
        
        .btn {
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .btn-primary { background: var(--accent); color: white; }
        .btn-danger { background: var(--red); color: white; }
        .btn-success { background: var(--green); color: white; }
        
        .btn:hover { transform: translateY(-1px); opacity: 0.9; }
        
        .controls {
            display: flex;
            gap: 1rem;
            padding: 1rem;
            background: var(--bg-secondary);
            border-radius: 12px;
            margin-top: 1rem;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        
        th { color: var(--text-secondary); font-size: 0.75rem; }
        
        @media (max-width: 768px) {
            .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
        }
        
        /* Chat Window Styles */
        .chat-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--bg-secondary);
        }
        
        .chat-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            cursor: pointer;
        }
        
        .chat-header h3 {
            font-size: 0.875rem;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .chat-toggle {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 1.25rem;
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        
        .chat-message {
            padding: 0.75rem 1rem;
            border-radius: 12px;
            max-width: 80%;
            line-height: 1.5;
        }
        
        .chat-message.user {
            background: var(--accent);
            color: white;
            align-self: flex-end;
            border-bottom-right-radius: 4px;
        }
        
        .chat-message.ai {
            background: var(--bg-card);
            color: var(--text-primary);
            align-self: flex-start;
            border-bottom-left-radius: 4px;
        }
        
        .chat-message.loading {
            opacity: 0.7;
        }
        
        .chat-input-container {
            display: flex;
            gap: 0.5rem;
            padding: 0.75rem 1rem;
            border-top: 1px solid rgba(255,255,255,0.05);
        }
        
        .chat-input {
            flex: 1;
            background: var(--bg-card);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            color: var(--text-primary);
            font-size: 0.875rem;
        }
        
        .chat-input:focus {
            outline: none;
            border-color: var(--accent);
        }
        
        .chat-input::placeholder {
            color: var(--text-secondary);
        }
        
        .chat-send {
            background: var(--accent);
            border: none;
            border-radius: 8px;
            padding: 0 1.25rem;
            color: white;
            cursor: pointer;
            font-weight: 600;
        }
        
        .chat-send:hover {
            opacity: 0.9;
        }
        
        .chat-send:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        /* Add padding to container for chat */
        .container {
            padding-bottom: 380px;
        }
        
        .chat-collapsed .chat-messages,
        .chat-collapsed .chat-input-container {
            display: none;
        }
        
        .chat-collapsed {
            max-height: 50px;
        }
        
        /* Tabs */
        .tabs {
            display: flex;
            gap: 0.5rem;
            background: var(--bg-secondary);
            padding: 0.5rem;
            border-radius: 12px;
        }
        
        .tab {
            padding: 0.75rem 1.25rem;
            background: none;
            border: none;
            color: var(--text-secondary);
            border-radius: 8px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }
        
        .tab:hover {
            color: var(--text-primary);
            background: var(--bg-card);
        }
        
        .tab.active {
            color: var(--text-primary);
            background: var(--bg-card);
        }
        
        .tab-content {
            margin-top: 1rem;
        }
        
        .tab-content:not(.active) {
            display: none;
        }
        
        /* Small inputs */
        .input-sm {
            padding: 0.5rem 0.75rem;
            background: var(--bg-card);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 0.875rem;
        }
        
        .input-sm:focus {
            outline: none;
            border-color: var(--accent);
        }
        
        .btn-sm {
            padding: 0.5rem 1rem;
            font-size: 0.75rem;
        }
        
        /* Watchlist item */
        .watchlist-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        
        .watchlist-item:hover {
            background: var(--bg-secondary);
        }
        
        .watchlist-symbol {
            font-weight: 600;
        }
        
        .watchlist-price {
            font-size: 1.125rem;
        }
        
        /* Scanner item */
        .scanner-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        
        /* Plan item */
        .plan-item {
            padding: 0.75rem;
            background: var(--bg-secondary);
            border-radius: 8px;
            margin-bottom: 0.5rem;
        }
        
        .plan-item .plan-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 0.5rem;
        }
        
        /* Style card */
        .style-card {
            padding: 1rem;
            background: var(--bg-secondary);
            border: 2px solid transparent;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .style-card:hover {
            border-color: var(--accent);
        }
        
        .style-card.active {
            border-color: var(--accent);
            background: rgba(59, 130, 246, 0.1);
        }
        
        .style-emoji {
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }
        
        .style-name {
            font-weight: 600;
            margin-bottom: 0.25rem;
        }
        
        .style-desc {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }
    </style>
</head>
<body>
    <!-- Live Price Ticker -->
    <div id="price-ticker" style="background:var(--bg-tertiary);padding:0.5rem 1rem;display:flex;justify-content:center;gap:2rem;font-size:0.85rem;border-bottom:1px solid var(--border);">
        <div style="display:flex;align-items:center;gap:0.5rem;">
            <span style="color:var(--text-secondary);">BTC</span>
            <span id="ticker-btc" style="font-weight:bold;">--</span>
            <span id="ticker-btc-pct" class="positive">--%</span>
        </div>
        <div style="display:flex;align-items:center;gap:0.5rem;">
            <span style="color:var(--text-secondary);">ETH</span>
            <span id="ticker-eth" style="font-weight:bold;">--</span>
            <span id="ticker-eth-pct" class="positive">--%</span>
        </div>
        <div style="display:flex;align-items:center;gap:0.5rem;">
            <span style="color:var(--text-secondary);">SOL</span>
            <span id="ticker-sol" style="font-weight:bold;">--</span>
            <span id="ticker-sol-pct" class="positive">--%</span>
        </div>
    </div>
    
    <header>
        <div class="logo">🤖 Blofin Helper</div>
        <div style="display:flex;align-items:center;gap:1rem;">
            <button class="btn btn-danger btn-sm" onclick="killSwitch()" style="padding:0.4rem 0.8rem;">🛑 Kill</button>
            <button class="btn btn-primary btn-sm" onclick="togglePause()" id="pause-btn" style="padding:0.4rem 0.8rem;">⏸️ Pause</button>
            <button class="btn btn-sm" onclick="refreshData()" style="padding:0.4rem 0.8rem;">🔄</button>
            <span id="last-update" style="font-size:0.75rem;color:var(--text-secondary);"></span>
            <span class="status-badge" id="mode-badge">LIVE</span>
        </div>
    </header>
    
    <div class="main-layout">
        <div class="main-content">
            <div class="container">
                <div class="grid grid-4">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Equity</span>
                </div>
                <div class="metric" id="equity">$0.00</div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Unrealized P&L</span>
                </div>
                <div class="metric" id="pnl">$0.00</div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Positions</span>
                </div>
                <div class="metric" id="positions">0</div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Pending Approvals</span>
                </div>
                <div class="metric" id="approvals">0</div>
            </div>
        </div>
        
        <!-- Tab Navigation -->
        <div class="tabs" style="margin-top: 1rem;">
            <button class="tab active" onclick="showTab('positions')">📊 Positions</button>
            <button class="tab" onclick="showTab('fills')">💹 Fills</button>
            <button class="tab" onclick="showTab('watchlist')">⭐ Watchlist</button>
            <button class="tab" onclick="showTab('scanner')">🔍 Scanner</button>
            <button class="tab" onclick="showTab('planner')">📝 Planner</button>
            <button class="tab" onclick="showTab('actions')">⚡ Actions</button>
            <button class="tab" onclick="showTab('journal')">📓 Journal</button>
            <button class="tab" onclick="showTab('stats')">📈 Stats</button>
            <button class="tab" onclick="showTab('styles')">🎭 Styles</button>
            <button class="tab" onclick="showTab('settings')">⚙️ Settings</button>
        </div>
        
        <!-- Positions Tab -->
        <div id="tab-positions" class="tab-content active">
            <!-- Account Summary -->
            <div class="grid grid-4" style="margin-bottom:1rem;">
                <div class="metric-card">
                    <div class="metric-label">💰 Account Value</div>
                    <div class="metric-value" id="account-equity">$0.00</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">📊 Unrealized P&L</div>
                    <div class="metric-value" id="account-upnl">$0.00</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">🔓 Available</div>
                    <div class="metric-value" id="account-available">$0.00</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">⚡ Margin Used</div>
                    <div class="metric-value" id="account-margin">0%</div>
                </div>
            </div>
            
            <div class="grid grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">📈 Open Positions</span>
                        <button class="btn btn-sm" onclick="refreshPositions()">🔄 Refresh</button>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Size</th>
                                <th>Entry</th>
                                <th>Mark</th>
                                <th>P&L</th>
                                <th>ROI</th>
                            </tr>
                        </thead>
                        <tbody id="positions-table">
                            <tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">Loading...</td></tr>
                        </tbody>
                    </table>
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">🧮 Position Size Calculator</span>
                    </div>
                    <div style="display:grid;gap:0.75rem;margin-top:1rem;">
                        <div class="grid grid-2" style="gap:0.5rem;">
                            <div>
                                <label style="font-size:0.7rem;color:var(--text-secondary);">Account Risk %</label>
                                <input type="number" id="calc-risk" value="2" step="0.5" class="input-sm" style="width:100%;" />
                            </div>
                            <div>
                                <label style="font-size:0.7rem;color:var(--text-secondary);">Entry Price</label>
                                <input type="number" id="calc-entry" placeholder="95000" class="input-sm" style="width:100%;" />
                            </div>
                        </div>
                        <div class="grid grid-2" style="gap:0.5rem;">
                            <div>
                                <label style="font-size:0.7rem;color:var(--text-secondary);">Stop Loss</label>
                                <input type="number" id="calc-stop" placeholder="94000" class="input-sm" style="width:100%;" />
                            </div>
                            <div>
                                <label style="font-size:0.7rem;color:var(--text-secondary);">Leverage</label>
                                <input type="number" id="calc-leverage" value="3" class="input-sm" style="width:100%;" />
                            </div>
                        </div>
                        <button class="btn btn-primary" onclick="calculateSize()">Calculate Position Size</button>
                        <div id="calc-result" style="background:var(--bg-tertiary);padding:1rem;border-radius:8px;display:none;">
                            <div class="grid grid-3" style="text-align:center;">
                                <div>
                                    <div style="font-size:0.7rem;color:var(--text-secondary);">Position Size</div>
                                    <div id="calc-size" style="font-size:1.2rem;font-weight:bold;color:var(--accent);">-</div>
                                </div>
                                <div>
                                    <div style="font-size:0.7rem;color:var(--text-secondary);">Risk Amount</div>
                                    <div id="calc-amount" style="font-size:1rem;">-</div>
                                </div>
                                <div>
                                    <div style="font-size:0.7rem;color:var(--text-secondary);">Notional</div>
                                    <div id="calc-notional" style="font-size:1rem;">-</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Trade Logger -->
            <div class="card" style="margin-top:1rem;">
                <div class="card-header">
                    <span class="card-title">📝 Log a Trade (from Blofin)</span>
                </div>
                <div class="grid grid-6" style="gap:0.5rem;margin-top:1rem;">
                    <div>
                        <label style="font-size:0.7rem;color:var(--text-secondary);">Symbol</label>
                        <input type="text" id="log-symbol" value="BTC-USDT" class="input-sm" style="width:100%;" />
                    </div>
                    <div>
                        <label style="font-size:0.7rem;color:var(--text-secondary);">Side</label>
                        <select id="log-side" class="input-sm" style="width:100%;">
                            <option value="long">Long</option>
                            <option value="short">Short</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-size:0.7rem;color:var(--text-secondary);">Entry</label>
                        <input type="number" id="log-entry" placeholder="95000" class="input-sm" style="width:100%;" />
                    </div>
                    <div>
                        <label style="font-size:0.7rem;color:var(--text-secondary);">Exit</label>
                        <input type="number" id="log-exit" placeholder="96000" class="input-sm" style="width:100%;" />
                    </div>
                    <div>
                        <label style="font-size:0.7rem;color:var(--text-secondary);">Size</label>
                        <input type="number" id="log-size" placeholder="0.01" step="0.001" class="input-sm" style="width:100%;" />
                    </div>
                    <div style="display:flex;align-items:flex-end;">
                        <button class="btn btn-success btn-sm" onclick="logTrade()" style="width:100%;">Log Trade</button>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Fills Tab (Trade History) -->
        <div id="tab-fills" class="tab-content" style="display:none;">
            <div class="grid grid-3">
                <!-- Trade Fills -->
                <div class="card" style="grid-column: span 2;">
                    <div class="card-header">
                        <span class="card-title">💹 Recent Trade Fills</span>
                        <button class="btn btn-sm" onclick="loadFills()">🔄 Refresh</button>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Price</th>
                                <th>Size</th>
                                <th>P&L</th>
                                <th>Fee</th>
                            </tr>
                        </thead>
                        <tbody id="fills-table">
                            <tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">Loading...</td></tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Leverage & Funding -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">⚙️ Leverage Control</span>
                    </div>
                    <div style="display:grid;gap:0.75rem;margin-top:1rem;">
                        <div>
                            <label style="font-size:0.7rem;color:var(--text-secondary);">Symbol</label>
                            <select id="leverage-symbol" class="input-sm" style="width:100%;">
                                <option value="BTC-USDT">BTC-USDT</option>
                                <option value="ETH-USDT">ETH-USDT</option>
                                <option value="SOL-USDT">SOL-USDT</option>
                            </select>
                        </div>
                        <div>
                            <label style="font-size:0.7rem;color:var(--text-secondary);">Leverage</label>
                            <input type="range" id="leverage-slider" min="1" max="50" value="3" style="width:100%;" oninput="document.getElementById('leverage-value').textContent = this.value + 'x'" />
                            <div style="text-align:center;font-size:1.5rem;font-weight:bold;" id="leverage-value">3x</div>
                        </div>
                        <button class="btn btn-primary" onclick="setLeverage()">Set Leverage</button>
                    </div>
                    
                    <div style="margin-top:1.5rem;">
                        <div class="card-header" style="padding:0;">
                            <span class="card-title">📊 BTC Funding Rate</span>
                        </div>
                        <div style="margin-top:0.75rem;">
                            <div style="display:flex;justify-content:space-between;">
                                <span style="color:var(--text-secondary);">Current Rate:</span>
                                <span id="funding-current" style="font-weight:bold;">--</span>
                            </div>
                            <div id="funding-history" style="margin-top:0.5rem;font-size:0.75rem;color:var(--text-secondary);">Loading...</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Watchlist Tab -->
        <div id="tab-watchlist" class="tab-content" style="display:none;">
            <div class="grid grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">⭐ My Watchlist</span>
                        <div style="display:flex;gap:0.5rem;">
                            <input type="text" id="watchlist-add" placeholder="BTC-USDT" class="input-sm" />
                            <button class="btn btn-primary btn-sm" onclick="addToWatchlist()">Add</button>
                        </div>
                    </div>
                    <div id="watchlist-items" style="max-height:300px;overflow-y:auto;">
                        <p style="color:var(--text-secondary)">Loading...</p>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">🔔 Price Alerts</span>
                    </div>
                    <div style="padding:0.5rem 0;">
                        <div style="display:flex;gap:0.5rem;margin-bottom:1rem;">
                            <input type="text" id="alert-symbol" placeholder="Symbol" class="input-sm" style="width:100px;"/>
                            <select id="alert-condition" class="input-sm">
                                <option value="above">Above</option>
                                <option value="below">Below</option>
                            </select>
                            <input type="number" id="alert-price" placeholder="Price" class="input-sm" style="width:100px;"/>
                            <button class="btn btn-success btn-sm" onclick="setAlert()">Set</button>
                        </div>
                    </div>
                    <div id="alerts-triggered"></div>
                </div>
            </div>
        </div>
        
        <!-- Scanner Tab -->
        <div id="tab-scanner" class="tab-content" style="display:none;">
            <div class="grid grid-3">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">🔥 Top Movers</span>
                        <button class="btn btn-sm" onclick="loadMovers()">🔄</button>
                    </div>
                    <div id="movers-list"></div>
                </div>
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">🟢 Top Gainers</span>
                    </div>
                    <div id="gainers-list"></div>
                </div>
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">🔴 Top Losers</span>
                    </div>
                    <div id="losers-list"></div>
                </div>
            </div>
        </div>
        
        <!-- Planner Tab -->
        <div id="tab-planner" class="tab-content" style="display:none;">
            <div class="grid grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">📝 New Trade Plan</span>
                    </div>
                    <div style="display:grid;gap:0.75rem;">
                        <div style="display:flex;gap:0.5rem;">
                            <input type="text" id="plan-symbol" placeholder="BTC-USDT" class="input-sm" style="flex:1;"/>
                            <select id="plan-side" class="input-sm" style="width:100px;">
                                <option value="long">🟢 Long</option>
                                <option value="short">🔴 Short</option>
                            </select>
                        </div>
                        <div style="display:flex;gap:0.5rem;">
                            <input type="number" id="plan-entry" placeholder="Entry" class="input-sm" style="flex:1;"/>
                            <input type="number" id="plan-sl" placeholder="Stop Loss" class="input-sm" style="flex:1;"/>
                            <input type="number" id="plan-tp" placeholder="Take Profit" class="input-sm" style="flex:1;"/>
                        </div>
                        <div style="display:flex;gap:0.5rem;">
                            <button class="btn btn-primary" onclick="calculateRR()">Calculate R:R</button>
                            <button class="btn btn-success" onclick="createPlan()">Create Plan</button>
                        </div>
                        <div id="rr-result" style="padding:0.5rem;background:var(--bg-secondary);border-radius:8px;display:none;"></div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">📋 My Plans</span>
                    </div>
                    <div id="plans-list" style="max-height:300px;overflow-y:auto;"></div>
                </div>
            </div>
        </div>
        
        <!-- Styles Tab -->
        <div id="tab-styles" class="tab-content" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">🎭 Trading Style</span>
                    <span id="current-style" class="status-badge status-demo">Loading...</span>
                </div>
                <div id="styles-grid" class="grid grid-3" style="margin-top:1rem;"></div>
            </div>
        </div>
        
        <!-- Quick Actions Tab -->
        <div id="tab-actions" class="tab-content" style="display:none;">
            <div class="grid grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">⚡ Quick Trade - BTC</span>
                        <span id="quick-btc-price" style="font-weight:bold;">$--</span>
                    </div>
                    <div class="grid grid-2" style="gap:0.5rem;margin-top:1rem;">
                        <button class="btn btn-success" onclick="quickTrade('BTC-USDT', 'long', 0.001)" style="padding:1rem;">
                            🟢 LONG 0.001 BTC
                        </button>
                        <button class="btn btn-danger" onclick="quickTrade('BTC-USDT', 'short', 0.001)" style="padding:1rem;">
                            🔴 SHORT 0.001 BTC
                        </button>
                        <button class="btn btn-success" onclick="quickTrade('BTC-USDT', 'long', 0.01)" style="padding:1rem;">
                            🟢 LONG 0.01 BTC
                        </button>
                        <button class="btn btn-danger" onclick="quickTrade('BTC-USDT', 'short', 0.01)" style="padding:1rem;">
                            🔴 SHORT 0.01 BTC
                        </button>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">⚡ Quick Trade - ETH</span>
                        <span id="quick-eth-price" style="font-weight:bold;">$--</span>
                    </div>
                    <div class="grid grid-2" style="gap:0.5rem;margin-top:1rem;">
                        <button class="btn btn-success" onclick="quickTrade('ETH-USDT', 'long', 0.01)" style="padding:1rem;">
                            🟢 LONG 0.01 ETH
                        </button>
                        <button class="btn btn-danger" onclick="quickTrade('ETH-USDT', 'short', 0.01)" style="padding:1rem;">
                            🔴 SHORT 0.01 ETH
                        </button>
                        <button class="btn btn-success" onclick="quickTrade('ETH-USDT', 'long', 0.1)" style="padding:1rem;">
                            🟢 LONG 0.1 ETH
                        </button>
                        <button class="btn btn-danger" onclick="quickTrade('ETH-USDT', 'short', 0.1)" style="padding:1rem;">
                            🔴 SHORT 0.1 ETH
                        </button>
                    </div>
                </div>
            </div>
            
            <!-- Custom Quick Trade -->
            <div class="card" style="margin-top:1rem;">
                <div class="card-header">
                    <span class="card-title">🎯 Custom Quick Trade</span>
                </div>
                <div class="grid grid-5" style="gap:0.5rem;margin-top:1rem;">
                    <div>
                        <label style="font-size:0.7rem;color:var(--text-secondary);">Symbol</label>
                        <input type="text" id="quick-symbol" value="BTC-USDT" class="input-sm" style="width:100%;" />
                    </div>
                    <div>
                        <label style="font-size:0.7rem;color:var(--text-secondary);">Side</label>
                        <select id="quick-side" class="input-sm" style="width:100%;">
                            <option value="long">Long</option>
                            <option value="short">Short</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-size:0.7rem;color:var(--text-secondary);">Size</label>
                        <input type="number" id="quick-size" value="0.01" step="0.001" class="input-sm" style="width:100%;" />
                    </div>
                    <div>
                        <label style="font-size:0.7rem;color:var(--text-secondary);">Leverage</label>
                        <input type="number" id="quick-leverage" value="3" class="input-sm" style="width:100%;" />
                    </div>
                    <div style="display:flex;align-items:flex-end;">
                        <button class="btn btn-primary" onclick="executeCustomTrade()" style="width:100%;">⚡ Execute</button>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Session Journal Tab -->
        <div id="tab-journal" class="tab-content" style="display:none;">
            <div class="grid grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">📓 Today's Journal</span>
                        <select id="journal-mood" class="input-sm" onchange="updateJournalMood()">
                            <option value="bullish">🟢 Bullish</option>
                            <option value="bearish">🔴 Bearish</option>
                            <option value="neutral" selected>⚪ Neutral</option>
                            <option value="uncertain">🟡 Uncertain</option>
                        </select>
                    </div>
                    <div style="display:grid;gap:0.75rem;margin-top:1rem;">
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);">Trading Plan</label>
                            <textarea id="journal-plan" class="input-sm" style="width:100%;min-height:80px;" placeholder="What's your plan for today?"></textarea>
                        </div>
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);">Notes</label>
                            <textarea id="journal-notes" class="input-sm" style="width:100%;min-height:80px;" placeholder="Thoughts, observations..."></textarea>
                        </div>
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);">End of Day Review</label>
                            <textarea id="journal-review" class="input-sm" style="width:100%;min-height:80px;" placeholder="How did it go?"></textarea>
                        </div>
                        <button class="btn btn-primary" onclick="saveJournal()">💾 Save Journal</button>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">📜 Recent Entries</span>
                    </div>
                    <div id="journal-history" style="max-height:400px;overflow-y:auto;"></div>
                </div>
            </div>
        </div>
        
        <!-- Performance Stats Tab -->
        <div id="tab-stats" class="tab-content" style="display:none;">
            <div class="grid grid-4">
                <div class="card">
                    <div class="card-header"><span class="card-title">Win Rate</span></div>
                    <div class="metric" id="stat-winrate">—%</div>
                </div>
                <div class="card">
                    <div class="card-header"><span class="card-title">Total P&L</span></div>
                    <div class="metric" id="stat-pnl">$0.00</div>
                </div>
                <div class="card">
                    <div class="card-header"><span class="card-title">Trades</span></div>
                    <div class="metric" id="stat-trades">0</div>
                </div>
                <div class="card">
                    <div class="card-header"><span class="card-title">Current Streak</span></div>
                    <div class="metric" id="stat-streak">0</div>
                </div>
            </div>
            <div class="grid grid-2" style="margin-top:1rem;">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">📊 Performance Details</span>
                    </div>
                    <table>
                        <tbody id="stats-table">
                            <tr><td colspan="2" style="text-align:center;color:var(--text-secondary)">Loading...</td></tr>
                        </tbody>
                    </table>
                </div>
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">📈 Daily P&L</span>
                    </div>
                    <div id="pnl-chart" style="min-height:200px;"></div>
                </div>
            </div>
        </div>
        
        <!-- Settings Tab -->
        <div id="tab-settings" class="tab-content" style="display:none;">
            <div class="grid grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">🔑 Blofin API Keys</span>
                        <span id="blofin-status" class="status-badge status-demo">Not Configured</span>
                    </div>
                    <div style="display:grid;gap:1rem;margin-top:1rem;">
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);display:block;margin-bottom:0.25rem;">API Key</label>
                            <input type="password" id="settings-blofin-key" class="input-sm" style="width:100%;" placeholder="Your Blofin API key" />
                        </div>
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);display:block;margin-bottom:0.25rem;">API Secret</label>
                            <input type="password" id="settings-blofin-secret" class="input-sm" style="width:100%;" placeholder="Your Blofin API secret" />
                        </div>
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);display:block;margin-bottom:0.25rem;">Passphrase</label>
                            <input type="password" id="settings-blofin-pass" class="input-sm" style="width:100%;" placeholder="Your Blofin passphrase" />
                        </div>
                        <div style="display:flex;gap:0.5rem;align-items:center;">
                            <input type="checkbox" id="settings-blofin-demo" checked />
                            <label for="settings-blofin-demo" style="font-size:0.875rem;">Demo Mode (paper trading)</label>
                        </div>
                        <button class="btn btn-primary" onclick="saveBlofinSettings()">💾 Save Blofin Settings</button>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">🤖 Claude AI Key</span>
                        <span id="claude-status" class="status-badge status-demo">Not Configured</span>
                    </div>
                    <div style="display:grid;gap:1rem;margin-top:1rem;">
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);display:block;margin-bottom:0.25rem;">Anthropic API Key</label>
                            <input type="password" id="settings-claude-key" class="input-sm" style="width:100%;" placeholder="sk-ant-api..." />
                        </div>
                        <p style="font-size:0.75rem;color:var(--text-secondary);">
                            Get your API key from <a href="https://console.anthropic.com/" target="_blank" style="color:var(--accent);">console.anthropic.com</a>
                        </p>
                        <button class="btn btn-primary" onclick="saveClaudeSettings()">💾 Save Claude Key</button>
                    </div>
                </div>
            </div>
            
            <div class="grid grid-2" style="margin-top:1rem;">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">📱 Notifications</span>
                    </div>
                    <div style="display:grid;gap:1rem;margin-top:1rem;">
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);display:block;margin-bottom:0.25rem;">Discord Webhook URL</label>
                            <input type="text" id="settings-discord" class="input-sm" style="width:100%;" placeholder="https://discord.com/api/webhooks/..." />
                        </div>
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);display:block;margin-bottom:0.25rem;">Telegram Bot Token</label>
                            <input type="text" id="settings-telegram-token" class="input-sm" style="width:100%;" placeholder="123456789:ABC..." />
                        </div>
                        <div>
                            <label style="font-size:0.75rem;color:var(--text-secondary);display:block;margin-bottom:0.25rem;">Telegram Chat ID</label>
                            <input type="text" id="settings-telegram-chat" class="input-sm" style="width:100%;" placeholder="Your chat ID" />
                        </div>
                        <button class="btn btn-primary" onclick="saveNotificationSettings()">💾 Save Notification Settings</button>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">ℹ️ System Info</span>
                    </div>
                    <table style="margin-top:1rem;">
                        <tbody id="system-info">
                            <tr><td colspan="2" style="text-align:center;color:var(--text-secondary)">Loading...</td></tr>
                        </tbody>
                    </table>
                    <div style="margin-top:1rem;">
                        <button class="btn btn-success btn-sm" onclick="testConnection()">🔌 Test Connection</button>
                        <button class="btn btn-sm" onclick="loadSettings()" style="margin-left:0.5rem;">🔄 Reload</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let isPaused = false;
        
        async function fetchApi(endpoint) {
            const res = await fetch('/api' + endpoint);
            return res.json();
        }
        
        async function postApi(endpoint, data = {}) {
            const res = await fetch('/api' + endpoint, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            return res.json();
        }
        
        async function refreshData() {
            try {
                const status = await fetchApi('/status');
                document.getElementById('positions').textContent = status.positions?.count || 0;
                document.getElementById('approvals').textContent = status.pending_approvals || 0;
                
                isPaused = status.is_paused;
                document.getElementById('pause-btn').textContent = isPaused ? '▶️ Resume' : '⏸️ Pause';
                
                // Update account metrics
                const balance = status.account || {};
                document.getElementById('account-equity').textContent = '$' + (balance.equity || 0).toFixed(2);
                
                const upnl = balance.upnl || 0;
                const upnlEl = document.getElementById('account-upnl');
                upnlEl.textContent = '$' + upnl.toFixed(2);
                upnlEl.className = 'metric-value ' + (upnl >= 0 ? 'positive' : 'negative');
                
                document.getElementById('account-available').textContent = '$' + (balance.available || 0).toFixed(2);
                
                const marginPct = balance.equity > 0 ? ((balance.margin || 0) / balance.equity * 100) : 0;
                document.getElementById('account-margin').textContent = marginPct.toFixed(1) + '%';
                
                // Update positions table
                const positions = status.positions?.positions || [];
                const tbody = document.getElementById('positions-table');
                if (positions.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">No open positions</td></tr>';
                } else {
                    tbody.innerHTML = positions.map(p => `
                        <tr>
                            <td><strong>${p.symbol}</strong></td>
                            <td class="${p.side === 'long' ? 'positive' : 'negative'}">${p.side.toUpperCase()}</td>
                            <td>${p.size}</td>
                            <td>$${(p.entry || 0).toFixed(2)}</td>
                            <td>$${(p.mark || p.entry || 0).toFixed(2)}</td>
                            <td class="${(p.pnl || 0) >= 0 ? 'positive' : 'negative'}">$${(p.pnl || 0).toFixed(2)}</td>
                            <td class="${(p.roi || 0) >= 0 ? 'positive' : 'negative'}">${(p.roi || 0).toFixed(2)}%</td>
                        </tr>
                    `).join('');
                }
                
                // Update mode badge
                const modeBadge = document.getElementById('mode-badge');
                if (status.autonomy_level === 'copilot') {
                    modeBadge.textContent = 'LIVE - Copilot';
                    modeBadge.className = 'status-badge status-active';
                } else {
                    modeBadge.textContent = status.autonomy_level.toUpperCase();
                }
                
                // Update timestamp
                document.getElementById('last-update').textContent = 'Updated: ' + new Date().toLocaleTimeString();
                
            } catch (e) {
                console.error('Refresh failed:', e);
            }
        }
        
        // Live ticker
        async function updateTicker() {
            try {
                const tickers = await fetchApi('/tickers?symbols=BTC-USDT,ETH-USDT,SOL-USDT');
                for (const t of tickers) {
                    const sym = t.symbol.split('-')[0].toLowerCase();
                    const priceEl = document.getElementById('ticker-' + sym);
                    const pctEl = document.getElementById('ticker-' + sym + '-pct');
                    if (priceEl) {
                        priceEl.textContent = '$' + parseFloat(t.last).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                        pctEl.textContent = (t.change_24h >= 0 ? '+' : '') + t.change_24h.toFixed(2) + '%';
                        pctEl.className = t.change_24h >= 0 ? 'positive' : 'negative';
                    }
                }
            } catch (e) {
                console.log('Ticker update failed');
            }
        }
        
        async function refreshPositions() {
            await refreshData();
        }
        
        // Quick Trade Execution
        async function quickTrade(symbol, side, size) {
            if (!confirm(`Execute ${side.toUpperCase()} ${size} ${symbol}?`)) {
                return;
            }
            
            try {
                const result = await postApi('/trade', {
                    symbol: symbol,
                    side: side,
                    size: size
                });
                
                if (result.success) {
                    alert('✅ Order placed!\\nOrder ID: ' + result.order_id);
                    refreshData();
                } else {
                    alert('❌ Trade failed: ' + (result.error || 'Unknown error'));
                }
            } catch (e) {
                alert('❌ Error executing trade');
            }
        }
        
        async function executeCustomTrade() {
            const symbol = document.getElementById('quick-symbol').value;
            const side = document.getElementById('quick-side').value;
            const size = parseFloat(document.getElementById('quick-size').value);
            const leverage = parseInt(document.getElementById('quick-leverage').value);
            
            if (!symbol || !size) {
                alert('Please enter symbol and size');
                return;
            }
            
            if (!confirm(`Execute ${side.toUpperCase()} ${size} ${symbol} @ ${leverage}x?`)) {
                return;
            }
            
            try {
                const result = await postApi('/trade', {
                    symbol: symbol,
                    side: side,
                    size: size
                });
                
                if (result.success) {
                    alert('✅ Order placed!\\nOrder ID: ' + result.order_id);
                    refreshData();
                } else {
                    alert('❌ Trade failed: ' + (result.error || 'Unknown error'));
                }
            } catch (e) {
                alert('❌ Error executing trade');
            }
        }
        
        // Trade Fills
        async function loadFills() {
            try {
                const fills = await fetchApi('/fills?limit=20');
                const tbody = document.getElementById('fills-table');
                
                if (fills.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">No recent fills</td></tr>';
                    return;
                }
                
                tbody.innerHTML = fills.map(f => {
                    const time = new Date(f.time).toLocaleString();
                    const pnlClass = f.pnl >= 0 ? 'positive' : 'negative';
                    return `
                        <tr>
                            <td style="font-size:0.75rem;">${time}</td>
                            <td><strong>${f.symbol}</strong></td>
                            <td class="${f.side === 'buy' ? 'positive' : 'negative'}">${f.side.toUpperCase()}</td>
                            <td>$${f.price.toLocaleString()}</td>
                            <td>${f.size}</td>
                            <td class="${pnlClass}">$${f.pnl.toFixed(2)}</td>
                            <td style="color:var(--text-secondary);">$${f.fee.toFixed(4)}</td>
                        </tr>
                    `;
                }).join('');
            } catch (e) {
                console.log('Failed to load fills');
            }
        }
        
        // Set Leverage
        async function setLeverage() {
            const symbol = document.getElementById('leverage-symbol').value;
            const leverage = document.getElementById('leverage-slider').value;
            
            if (!confirm(`Set ${symbol} leverage to ${leverage}x?`)) {
                return;
            }
            
            try {
                const result = await postApi('/leverage', { symbol, leverage: parseInt(leverage) });
                if (result.success) {
                    alert(`✅ Leverage set to ${leverage}x for ${symbol}`);
                } else {
                    alert('❌ Failed: ' + (result.error || 'Unknown error'));
                }
            } catch (e) {
                alert('❌ Error setting leverage');
            }
        }
        
        // Funding Rate
        async function loadFunding() {
            try {
                const data = await fetchApi('/funding/BTC-USDT');
                const rateEl = document.getElementById('funding-current');
                const historyEl = document.getElementById('funding-history');
                
                const rate = data.current;
                rateEl.textContent = (rate >= 0 ? '+' : '') + rate.toFixed(4) + '%';
                rateEl.className = rate >= 0 ? 'positive' : 'negative';
                
                if (data.history && data.history.length > 0) {
                    const last3 = data.history.slice(0, 3).map(h => (h.rate >= 0 ? '+' : '') + h.rate.toFixed(4) + '%');
                    historyEl.textContent = 'Last 3: ' + last3.join(', ');
                }
            } catch (e) {
                console.log('Failed to load funding');
            }
        }
        
        // Position Size Calculator
        function calculateSize() {
            const risk = parseFloat(document.getElementById('calc-risk').value) || 2;
            const entry = parseFloat(document.getElementById('calc-entry').value);
            const stop = parseFloat(document.getElementById('calc-stop').value);
            const leverage = parseFloat(document.getElementById('calc-leverage').value) || 1;
            
            if (!entry || !stop) {
                alert('Please enter entry and stop loss prices');
                return;
            }
            
            // Get account equity
            const equityText = document.getElementById('account-equity').textContent;
            const equity = parseFloat(equityText.replace('$', '').replace(',', '')) || 1000;
            
            // Calculate
            const riskAmount = equity * (risk / 100);
            const stopDistance = Math.abs(entry - stop);
            const stopPct = stopDistance / entry * 100;
            
            // Position size = risk amount / (stop distance * leverage effect)
            const positionSize = riskAmount / stopDistance;
            const notional = positionSize * entry;
            
            // Show result
            document.getElementById('calc-result').style.display = 'block';
            document.getElementById('calc-size').textContent = positionSize.toFixed(6);
            document.getElementById('calc-amount').textContent = '$' + riskAmount.toFixed(2);
            document.getElementById('calc-notional').textContent = '$' + notional.toFixed(2);
        }
        
        // Trade Logger
        async function logTrade() {
            const symbol = document.getElementById('log-symbol').value;
            const side = document.getElementById('log-side').value;
            const entry = parseFloat(document.getElementById('log-entry').value);
            const exit = parseFloat(document.getElementById('log-exit').value);
            const size = parseFloat(document.getElementById('log-size').value);
            
            if (!entry || !exit || !size) {
                alert('Please fill all trade fields');
                return;
            }
            
            try {
                const result = await postApi('/trades/log', {
                    symbol, side, entry_price: entry, exit_price: exit, size
                });
                
                if (result.success) {
                    alert('✅ Trade logged! P&L: $' + result.pnl.toFixed(2));
                    // Clear form
                    document.getElementById('log-entry').value = '';
                    document.getElementById('log-exit').value = '';
                    document.getElementById('log-size').value = '';
                } else {
                    alert('❌ Error: ' + (result.error || 'Unknown'));
                }
            } catch (e) {
                alert('❌ Failed to log trade');
            }
        }
        
        async function killSwitch() {
            if (confirm('⚠️ KILL SWITCH: This will close ALL positions. Continue?')) {
                await postApi('/kill-switch');
                refreshData();
            }
        }
        
        async function togglePause() {
            if (isPaused) {
                await postApi('/resume');
            } else {
                await postApi('/pause');
            }
            refreshData();
        }
        
        async function closePosition(symbol) {
            if (confirm(`Close position: ${symbol}?`)) {
                await postApi('/close/' + symbol);
                refreshData();
            }
        }
        
        // Initial load
        refreshData();
        
        // Auto-refresh every 5 seconds
        setInterval(refreshData, 5000);
        
        // ==================== Tab Navigation ====================
        
        function showTab(tabName) {
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            
            // Update content
            document.querySelectorAll('.tab-content').forEach(t => {
                t.style.display = 'none';
                t.classList.remove('active');
            });
            const tab = document.getElementById('tab-' + tabName);
            tab.style.display = 'block';
            tab.classList.add('active');
            
            // Load tab-specific data
            if (tabName === 'watchlist') loadWatchlist();
            if (tabName === 'scanner') loadMovers();
            if (tabName === 'styles') loadStyles();
            if (tabName === 'planner') loadPlans();
            if (tabName === 'actions') loadActions();
            if (tabName === 'journal') loadJournal();
            if (tabName === 'stats') loadStats();
            if (tabName === 'settings') loadSettings();
        }
        
        // ==================== Watchlist ====================
        
        async function loadWatchlist() {
            try {
                const items = await fetchApi('/watchlist');
                const container = document.getElementById('watchlist-items');
                
                if (items.length === 0) {
                    container.innerHTML = '<p style="color:var(--text-secondary);padding:1rem;">No symbols in watchlist. Add one above!</p>';
                    return;
                }
                
                container.innerHTML = items.map(item => `
                    <div class="watchlist-item">
                        <div>
                            <span class="watchlist-symbol">${item.symbol}</span>
                            ${item.notes ? `<br><small style="color:var(--text-secondary)">${item.notes}</small>` : ''}
                        </div>
                        <div style="text-align:right;">
                            <span class="watchlist-price ${item.change_24h >= 0 ? 'positive' : 'negative'}">
                                $${item.price?.toLocaleString() || '—'}
                            </span>
                            <br>
                            <small class="${item.change_24h >= 0 ? 'positive' : 'negative'}">
                                ${item.change_24h >= 0 ? '+' : ''}${item.change_24h?.toFixed(2) || 0}%
                            </small>
                        </div>
                        <button class="btn btn-danger btn-sm" onclick="removeFromWatchlist('${item.symbol}')" style="margin-left:0.5rem;">×</button>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load watchlist:', e);
            }
        }
        
        async function addToWatchlist() {
            const input = document.getElementById('watchlist-add');
            const symbol = input.value.trim().toUpperCase();
            if (!symbol) return;
            
            await postApi('/watchlist', { symbol, notes: '' });
            input.value = '';
            loadWatchlist();
        }
        
        async function removeFromWatchlist(symbol) {
            await fetch('/api/watchlist/' + symbol, { method: 'DELETE' });
            loadWatchlist();
        }
        
        async function setAlert() {
            const symbol = document.getElementById('alert-symbol').value.trim().toUpperCase();
            const condition = document.getElementById('alert-condition').value;
            const price = parseFloat(document.getElementById('alert-price').value);
            
            if (!symbol || !price) return;
            
            await postApi('/watchlist/alert', { symbol, condition, price });
            document.getElementById('alert-symbol').value = '';
            document.getElementById('alert-price').value = '';
        }
        
        // ==================== Scanner ====================
        
        async function loadMovers() {
            try {
                const [movers, gainers, losers] = await Promise.all([
                    fetchApi('/scanner/movers?limit=8'),
                    fetchApi('/scanner/gainers?limit=5'),
                    fetchApi('/scanner/losers?limit=5'),
                ]);
                
                document.getElementById('movers-list').innerHTML = movers.map(m => `
                    <div class="scanner-item">
                        <span>${m.symbol}</span>
                        <span class="${m.change_24h >= 0 ? 'positive' : 'negative'}">
                            ${m.change_24h >= 0 ? '+' : ''}${m.change_24h?.toFixed(2) || 0}%
                        </span>
                    </div>
                `).join('');
                
                document.getElementById('gainers-list').innerHTML = gainers.map(g => `
                    <div class="scanner-item">
                        <span>${g.symbol}</span>
                        <span class="positive">+${g.change_24h?.toFixed(2) || 0}%</span>
                    </div>
                `).join('');
                
                document.getElementById('losers-list').innerHTML = losers.map(l => `
                    <div class="scanner-item">
                        <span>${l.symbol}</span>
                        <span class="negative">${l.change_24h?.toFixed(2) || 0}%</span>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load scanner:', e);
            }
        }
        
        // ==================== Planner ====================
        
        async function calculateRR() {
            const entry = parseFloat(document.getElementById('plan-entry').value);
            const sl = parseFloat(document.getElementById('plan-sl').value);
            const tp = parseFloat(document.getElementById('plan-tp').value);
            const side = document.getElementById('plan-side').value;
            
            if (!entry || !sl || !tp) {
                alert('Please fill in entry, SL, and TP');
                return;
            }
            
            const result = await postApi('/planner/calculate-rr', {
                entry, stop_loss: sl, take_profit: tp, side
            });
            
            const box = document.getElementById('rr-result');
            box.style.display = 'block';
            box.innerHTML = `
                <strong>R:R = ${result.risk_reward?.toFixed(2) || '—'}</strong><br>
                Risk: ${result.risk_percent?.toFixed(2)}% (${result.risk?.toFixed(2)})<br>
                Reward: ${result.reward_percent?.toFixed(2)}% (${result.reward?.toFixed(2)})<br>
                ${result.valid ? '✅ Valid' : '❌ Invalid setup'}
            `;
        }
        
        async function createPlan() {
            const symbol = document.getElementById('plan-symbol').value.trim().toUpperCase();
            const side = document.getElementById('plan-side').value;
            const entry = parseFloat(document.getElementById('plan-entry').value);
            const sl = parseFloat(document.getElementById('plan-sl').value);
            const tp = parseFloat(document.getElementById('plan-tp').value);
            
            if (!symbol || !entry || !sl || !tp) {
                alert('Please fill all fields');
                return;
            }
            
            const result = await postApi('/planner', {
                symbol, side, entry, stop_loss: sl, take_profit: tp
            });
            
            if (result.success) {
                // Clear form
                document.getElementById('plan-symbol').value = '';
                document.getElementById('plan-entry').value = '';
                document.getElementById('plan-sl').value = '';
                document.getElementById('plan-tp').value = '';
                document.getElementById('rr-result').style.display = 'none';
                loadPlans();
            }
        }
        
        async function loadPlans() {
            try {
                const plans = await fetchApi('/planner');
                const container = document.getElementById('plans-list');
                
                if (plans.length === 0) {
                    container.innerHTML = '<p style="color:var(--text-secondary)">No trade plans yet</p>';
                    return;
                }
                
                container.innerHTML = plans.slice(0, 10).map(p => `
                    <div class="plan-item">
                        <div class="plan-header">
                            <span>
                                <strong>${p.symbol}</strong>
                                <span class="${p.side === 'long' ? 'positive' : 'negative'}">${p.side.toUpperCase()}</span>
                            </span>
                            <span>R:R ${p.risk_reward?.toFixed(2)}</span>
                        </div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">
                            Entry: $${p.entry?.toLocaleString()} | SL: $${p.stop_loss?.toLocaleString()} | TP: $${p.take_profit?.toLocaleString()}
                        </div>
                        <div style="font-size:0.75rem;margin-top:0.25rem;">
                            Status: <span class="${p.status === 'executed' ? 'positive' : ''}">${p.status}</span>
                            <button class="btn btn-danger btn-sm" onclick="deletePlan('${p.plan_id}')" style="float:right;padding:0.25rem 0.5rem;">Delete</button>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load plans:', e);
            }
        }
        
        async function deletePlan(planId) {
            await fetch('/api/planner/' + planId, { method: 'DELETE' });
            loadPlans();
        }
        
        // ==================== Styles ====================
        
        async function loadStyles() {
            try {
                const data = await fetchApi('/styles');
                document.getElementById('current-style').textContent = data.current.toUpperCase();
                
                const container = document.getElementById('styles-grid');
                container.innerHTML = Object.entries(data.styles).map(([key, style]) => `
                    <div class="style-card ${key === data.current ? 'active' : ''}" onclick="setStyle('${key}')">
                        <div class="style-emoji">${style.emoji}</div>
                        <div class="style-name">${style.name}</div>
                        <div class="style-desc">${style.description}</div>
                        <div style="margin-top:0.5rem;font-size:0.75rem;color:var(--text-secondary);">
                            Risk: ${style.risk_per_trade}% | Leverage: ${style.max_leverage}x | R:R: ${style.min_rr_ratio}
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load styles:', e);
            }
        }
        
        async function setStyle(styleName) {
            await postApi('/styles/' + styleName);
            loadStyles();
        }
        
        // ==================== Quick Actions ====================
        
        async function loadActions() {
            try {
                const actions = await fetchApi('/actions');
                const container = document.getElementById('actions-grid');
                
                container.innerHTML = actions.map(a => `
                    <div class="style-card" onclick="executeAction('${a.action_id}')">
                        <div style="font-size:1.5rem;margin-bottom:0.5rem;">${a.side === 'long' ? '🟢' : '🔴'}</div>
                        <div class="style-name">${a.name}</div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.5rem;">
                            ${a.symbol}<br>
                            Size: ${a.size_percent}% | Lev: ${a.leverage}x<br>
                            SL: ${a.stop_loss_percent}% | TP: ${a.take_profit_percent}%
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load actions:', e);
            }
        }
        
        async function executeAction(actionId) {
            if (!confirm('Execute this quick action?')) return;
            
            const result = await postApi('/actions/' + actionId + '/execute');
            if (result.success) {
                alert('Action executed!');
            } else {
                alert('Failed: ' + (result.error || 'Unknown error'));
            }
        }
        
        // ==================== Session Journal ====================
        
        async function loadJournal() {
            try {
                // Load today's journal
                const today = await fetchApi('/journal/session');
                document.getElementById('journal-mood').value = today.mood || 'neutral';
                document.getElementById('journal-plan').value = today.plan || '';
                document.getElementById('journal-notes').value = today.notes || '';
                document.getElementById('journal-review').value = today.review || '';
                
                // Load history
                const history = await fetchApi('/journal/session/history?days=7');
                const container = document.getElementById('journal-history');
                
                if (history.length === 0) {
                    container.innerHTML = '<p style="color:var(--text-secondary)">No entries yet</p>';
                    return;
                }
                
                container.innerHTML = history.map(e => `
                    <div class="plan-item">
                        <div class="plan-header">
                            <strong>${e.date}</strong>
                            <span>${e.mood === 'bullish' ? '🟢' : e.mood === 'bearish' ? '🔴' : '⚪'}</span>
                        </div>
                        ${e.plan ? `<div style="font-size:0.75rem;"><strong>Plan:</strong> ${e.plan.substring(0, 100)}...</div>` : ''}
                        ${e.notes ? `<div style="font-size:0.75rem;margin-top:0.25rem;">${e.notes.substring(0, 100)}...</div>` : ''}
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load journal:', e);
            }
        }
        
        async function saveJournal() {
            const mood = document.getElementById('journal-mood').value;
            const plan = document.getElementById('journal-plan').value;
            const notes = document.getElementById('journal-notes').value;
            const review = document.getElementById('journal-review').value;
            
            await postApi('/journal/session?mood=' + mood + '&plan=' + encodeURIComponent(plan) + '&notes=' + encodeURIComponent(notes) + '&review=' + encodeURIComponent(review));
            alert('Journal saved!');
        }
        
        async function updateJournalMood() {
            const mood = document.getElementById('journal-mood').value;
            await postApi('/journal/session?mood=' + mood);
        }
        
        // ==================== Performance Stats ====================
        
        async function loadStats() {
            try {
                const stats = await fetchApi('/performance');
                
                // Update metrics
                document.getElementById('stat-winrate').textContent = stats.win_rate + '%';
                document.getElementById('stat-pnl').textContent = '$' + stats.total_pnl.toFixed(2);
                document.getElementById('stat-pnl').className = 'metric ' + (stats.total_pnl >= 0 ? 'positive' : 'negative');
                document.getElementById('stat-trades').textContent = stats.total_trades;
                
                const streakEmoji = stats.streak_type === 'win' ? '🔥' : stats.streak_type === 'loss' ? '❄️' : '';
                document.getElementById('stat-streak').textContent = streakEmoji + stats.current_streak;
                
                // Update details table
                document.getElementById('stats-table').innerHTML = `
                    <tr><td>Winning Trades</td><td class="positive">${stats.winning_trades}</td></tr>
                    <tr><td>Losing Trades</td><td class="negative">${stats.losing_trades}</td></tr>
                    <tr><td>Average Win</td><td class="positive">$${stats.average_win.toFixed(2)}</td></tr>
                    <tr><td>Average Loss</td><td class="negative">$${stats.average_loss.toFixed(2)}</td></tr>
                    <tr><td>Largest Win</td><td class="positive">$${stats.largest_win.toFixed(2)}</td></tr>
                    <tr><td>Largest Loss</td><td class="negative">$${stats.largest_loss.toFixed(2)}</td></tr>
                    <tr><td>Profit Factor</td><td>${stats.profit_factor.toFixed(2)}</td></tr>
                    <tr><td>Expectancy</td><td>$${stats.expectancy.toFixed(2)}</td></tr>
                    <tr><td>Max Win Streak</td><td>🔥${stats.max_win_streak}</td></tr>
                    <tr><td>Max Loss Streak</td><td>❄️${stats.max_loss_streak}</td></tr>
                `;
                
                // Load daily P&L
                const daily = await fetchApi('/performance/daily?days=14');
                const chartContainer = document.getElementById('pnl-chart');
                
                if (daily.length === 0) {
                    chartContainer.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:2rem;">No trade history yet</p>';
                    return;
                }
                
                // Simple bar chart
                const maxPnl = Math.max(...daily.map(d => Math.abs(d.pnl)), 1);
                chartContainer.innerHTML = `
                    <div style="display:flex;align-items:flex-end;gap:4px;height:150px;padding:1rem 0;">
                        ${daily.map(d => `
                            <div style="flex:1;display:flex;flex-direction:column;align-items:center;">
                                <div style="width:100%;background:${d.pnl >= 0 ? 'var(--green)' : 'var(--red)'};height:${Math.max(Math.abs(d.pnl) / maxPnl * 100, 5)}px;border-radius:4px 4px 0 0;"></div>
                                <div style="font-size:0.6rem;color:var(--text-secondary);margin-top:4px;">${d.date.substring(5)}</div>
                            </div>
                        `).join('')}
                    </div>
                `;
            } catch (e) {
                console.error('Failed to load stats:', e);
            }
        }
        
        // ==================== Settings ====================
        
        async function loadSettings() {
            try {
                const settings = await fetchApi('/settings');
                
                // Update status badges
                if (settings.blofin_configured) {
                    document.getElementById('blofin-status').textContent = settings.blofin_demo ? 'Demo Mode' : 'Live';
                    document.getElementById('blofin-status').className = 'status-badge ' + (settings.blofin_demo ? 'status-demo' : 'status-active');
                } else {
                    document.getElementById('blofin-status').textContent = 'Not Configured';
                    document.getElementById('blofin-status').className = 'status-badge status-demo';
                }
                
                if (settings.claude_configured) {
                    document.getElementById('claude-status').textContent = 'Configured';
                    document.getElementById('claude-status').className = 'status-badge status-active';
                } else {
                    document.getElementById('claude-status').textContent = 'Not Configured';
                    document.getElementById('claude-status').className = 'status-badge status-demo';
                }
                
                // Update demo checkbox
                document.getElementById('settings-blofin-demo').checked = settings.blofin_demo;
                
                // Update system info
                document.getElementById('system-info').innerHTML = `
                    <tr><td>Version</td><td>${settings.version || '0.1.0'}</td></tr>
                    <tr><td>Blofin API</td><td>${settings.blofin_configured ? '✅ Connected' : '❌ Not Set'}</td></tr>
                    <tr><td>Claude AI</td><td>${settings.claude_configured ? '✅ Connected' : '❌ Not Set'}</td></tr>
                    <tr><td>Mode</td><td>${settings.blofin_demo ? '📝 Demo' : '🔴 Live'}</td></tr>
                    <tr><td>Autonomy</td><td>${settings.autonomy || 'copilot'}</td></tr>
                `;
            } catch (e) {
                console.error('Failed to load settings:', e);
            }
        }
        
        async function saveBlofinSettings() {
            const apiKey = document.getElementById('settings-blofin-key').value;
            const apiSecret = document.getElementById('settings-blofin-secret').value;
            const passphrase = document.getElementById('settings-blofin-pass').value;
            const demo = document.getElementById('settings-blofin-demo').checked;
            
            if (!apiKey || !apiSecret || !passphrase) {
                alert('Please fill in all Blofin fields');
                return;
            }
            
            try {
                const result = await postApi('/settings/blofin', {
                    api_key: apiKey,
                    api_secret: apiSecret,
                    passphrase: passphrase,
                    demo: demo
                });
                
                if (result.success) {
                    alert('✅ Blofin settings saved! Restart the server to apply.');
                    document.getElementById('settings-blofin-key').value = '';
                    document.getElementById('settings-blofin-secret').value = '';
                    document.getElementById('settings-blofin-pass').value = '';
                    loadSettings();
                } else {
                    alert('❌ Error: ' + (result.error || 'Unknown error'));
                }
            } catch (e) {
                alert('❌ Error saving settings');
            }
        }
        
        async function saveClaudeSettings() {
            const apiKey = document.getElementById('settings-claude-key').value;
            
            if (!apiKey) {
                alert('Please enter your Claude API key');
                return;
            }
            
            try {
                const result = await postApi('/settings/claude', {
                    api_key: apiKey
                });
                
                if (result.success) {
                    alert('✅ Claude API key saved! Restart the server to apply.');
                    document.getElementById('settings-claude-key').value = '';
                    loadSettings();
                } else {
                    alert('❌ Error: ' + (result.error || 'Unknown error'));
                }
            } catch (e) {
                alert('❌ Error saving settings');
            }
        }
        
        async function saveNotificationSettings() {
            const discord = document.getElementById('settings-discord').value;
            const telegramToken = document.getElementById('settings-telegram-token').value;
            const telegramChat = document.getElementById('settings-telegram-chat').value;
            
            try {
                const result = await postApi('/settings/notifications', {
                    discord_webhook: discord,
                    telegram_token: telegramToken,
                    telegram_chat_id: telegramChat
                });
                
                if (result.success) {
                    alert('✅ Notification settings saved!');
                } else {
                    alert('❌ Error: ' + (result.error || 'Unknown error'));
                }
            } catch (e) {
                alert('❌ Error saving settings');
            }
        }
        
        async function testConnection() {
            try {
                const result = await postApi('/settings/test');
                
                if (result.blofin_ok) {
                    alert('✅ Blofin connection successful!\\nBalance: $' + (result.balance || 0).toFixed(2));
                } else {
                    alert('❌ Blofin connection failed: ' + (result.blofin_error || 'Check your API keys'));
                }
            } catch (e) {
                alert('❌ Connection test failed');
            }
        }
        
        // ==================== Chat Functions ====================
        
        let chatCollapsed = false;
        
        function toggleChat() {
            const container = document.getElementById('chat-container');
            chatCollapsed = !chatCollapsed;
            container.classList.toggle('chat-collapsed', chatCollapsed);
            document.getElementById('chat-toggle-btn').textContent = chatCollapsed ? '▲' : '▼';
        }
        
        function addMessage(text, isUser) {
            const messages = document.getElementById('chat-messages');
            const div = document.createElement('div');
            div.className = `chat-message ${isUser ? 'user' : 'ai'}`;
            div.textContent = text;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
            return div;
        }
        
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Add user message
            addMessage(message, true);
            input.value = '';
            
            // Show loading
            const loadingDiv = addMessage('Thinking...', false);
            loadingDiv.classList.add('loading');
            
            // Disable send button
            const sendBtn = document.getElementById('chat-send-btn');
            sendBtn.disabled = true;
            
            try {
                const response = await postApi('/chat', { message });
                
                // Remove loading
                loadingDiv.remove();
                
                // Add AI response
                if (response.success) {
                    addMessage(response.response, false);
                } else {
                    addMessage(response.response || 'Error getting response', false);
                }
            } catch (e) {
                loadingDiv.remove();
                addMessage('Error: ' + e.message, false);
            }
            
            sendBtn.disabled = false;
        }
        
        // Handle Enter key in chat input
        document.addEventListener('DOMContentLoaded', function() {
            const input = document.getElementById('chat-input');
            input.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    sendChatMessage();
                }
            });
            
            // Start auto-refresh
            refreshData();
            updateTicker();
            loadFills();
            loadFunding();
            setInterval(refreshData, 5000);  // Every 5 seconds
            setInterval(updateTicker, 10000); // Every 10 seconds
            setInterval(loadFunding, 60000);  // Every minute
        });
            </script>
        </div>
        <!-- /main-content -->
        
        <!-- Sidebar Chat -->
        <div class="sidebar-chat">
            <div id="chat-container" class="chat-container">
                <div class="chat-header">
                    <h3>💬 AI Trading Assistant</h3>
                </div>
                <div class="chat-messages" id="chat-messages">
                    <div class="chat-message ai">
                        👋 Hi! I'm your trading assistant. I can see your portfolio, positions, and market data. Ask me anything about your trades!
                    </div>
                </div>
                <div class="chat-input-container">
                    <input type="text" class="chat-input" id="chat-input" placeholder="Ask about markets or trading..." />
                    <button class="chat-send" id="chat-send-btn" onclick="sendChatMessage()">Send</button>
                </div>
            </div>
        </div>
        <!-- /sidebar-chat -->
    </div>
    <!-- /main-layout -->
</body>
</html>
"""


def create_full_app(config: Config, client: BlofinClient) -> FastAPI:
    """
    Create full app with dashboard.
    
    Args:
        config: Bot configuration
        client: Blofin API client
    
    Returns:
        FastAPI app with dashboard
    """
    from ..ai.brain import AIBrain
    from ..data.market import MarketData
    from ..data.account import AccountData
    from ..features.watchlist import Watchlist, MarketScanner
    from ..features.styles import TradingStyleManager, TradingStyle
    from ..features.planner import TradePlanner
    
    # Initialize components
    market = MarketData(client)
    account = AccountData(client)
    brain = AIBrain(config, market, account)
    engine = TradingEngine(config, client, brain)
    
    # Initialize features
    watchlist = Watchlist(market)
    scanner = MarketScanner(market)
    styles = TradingStyleManager()
    planner = TradePlanner()
    
    app = create_api(engine)
    
    # ==================== Watchlist Endpoints ====================
    
    @app.get("/api/watchlist")
    async def get_watchlist():
        """Get watchlist with prices."""
        return watchlist.get_with_prices()
    
    @app.post("/api/watchlist")
    async def add_to_watchlist(request: WatchlistAddRequest):
        """Add symbol to watchlist."""
        item = watchlist.add(request.symbol, request.notes, request.tags)
        return {"success": True, "item": item.to_dict()}
    
    @app.delete("/api/watchlist/{symbol}")
    async def remove_from_watchlist(symbol: str):
        """Remove symbol from watchlist."""
        success = watchlist.remove(symbol)
        return {"success": success}
    
    @app.post("/api/watchlist/alert")
    async def set_price_alert(request: AlertRequest):
        """Set a price alert."""
        success = watchlist.set_alert(request.symbol, request.condition, request.price)
        return {"success": success}
    
    @app.get("/api/watchlist/alerts")
    async def check_alerts():
        """Check for triggered alerts."""
        return watchlist.check_alerts()
    
    # ==================== Scanner Endpoints ====================
    
    @app.get("/api/scanner/movers")
    async def get_top_movers(limit: int = 10):
        """Get top market movers."""
        return scanner.get_top_movers(limit)
    
    @app.get("/api/scanner/gainers")
    async def get_gainers(limit: int = 5):
        """Get top gainers."""
        return scanner.get_gainers(limit)
    
    @app.get("/api/scanner/losers")
    async def get_losers(limit: int = 5):
        """Get top losers."""
        return scanner.get_losers(limit)
    
    # ==================== Trading Style Endpoints ====================
    
    @app.get("/api/styles")
    async def get_styles():
        """Get all trading styles."""
        return {
            "styles": styles.get_all_styles(),
            "current": styles.current.value,
            "config": styles.current_config.to_dict(),
        }
    
    @app.post("/api/styles/{style_name}")
    async def set_style(style_name: str):
        """Set active trading style."""
        config = styles.set_style_by_name(style_name)
        if config:
            return {"success": True, "style": config.to_dict()}
        raise HTTPException(status_code=400, detail=f"Unknown style: {style_name}")
    
    @app.get("/api/styles/risk")
    async def get_risk_params():
        """Get risk parameters for current style."""
        return styles.get_risk_params()
    
    # ==================== Trade Planner Endpoints ====================
    
    @app.get("/api/planner")
    async def get_plans(status: Optional[str] = None):
        """Get trade plans."""
        from ..features.planner import PlanStatus
        plan_status = PlanStatus(status) if status else None
        plans = planner.get_all_plans(plan_status)
        return [p.to_dict() for p in plans]
    
    @app.post("/api/planner")
    async def create_plan(request: TradePlanRequest):
        """Create a trade plan."""
        plan = planner.create_plan(
            symbol=request.symbol,
            side=request.side,
            entry=request.entry,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            size_percent=request.size_percent,
            leverage=request.leverage,
            notes=request.notes,
        )
        valid, errors = plan.validate()
        return {
            "success": True,
            "plan": plan.to_dict(),
            "valid": valid,
            "errors": errors,
        }
    
    @app.post("/api/planner/{plan_id}/ready")
    async def mark_plan_ready(plan_id: str):
        """Mark plan as ready for execution."""
        success = planner.set_ready(plan_id)
        return {"success": success}
    
    @app.post("/api/planner/{plan_id}/execute")
    async def execute_plan(plan_id: str):
        """Execute a trade plan."""
        plan = planner.get_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Execute via trading engine
        result = engine.quick_trade(
            symbol=plan.symbol,
            side=plan.side,
            size=plan.size_percent,  # TODO: Calculate actual size
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
        )
        
        if result.success:
            planner.mark_executed(plan_id)
        
        return {
            "success": result.success,
            "order": result.to_dict() if result.success else None,
            "error": result.error,
        }
    
    @app.delete("/api/planner/{plan_id}")
    async def delete_plan(plan_id: str):
        """Delete a trade plan."""
        success = planner.delete_plan(plan_id)
        return {"success": success}
    
    @app.post("/api/planner/calculate-rr")
    async def calculate_rr(request: RRCalcRequest):
        """Calculate R:R ratio."""
        return planner.calculate_rr(
            entry=request.entry,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            side=request.side,
        )
    
    # ==================== Trade History & Leverage ====================
    
    @app.get("/api/fills")
    async def get_trade_fills(symbol: Optional[str] = None, limit: int = 20):
        """Get filled trade history from Blofin."""
        try:
            fills = engine.client.get_trade_history(inst_id=symbol, limit=limit)
            return [
                {
                    "symbol": f.get("instId"),
                    "side": f.get("side"),
                    "price": float(f.get("fillPrice", 0)),
                    "size": float(f.get("fillSize", 0)),
                    "pnl": float(f.get("fillPnl", 0)),
                    "fee": float(f.get("fee", 0)),
                    "time": int(f.get("ts", 0)),
                }
                for f in fills
            ]
        except Exception as e:
            return []
    
    @app.post("/api/leverage")
    async def set_leverage(request: dict):
        """Set leverage for a symbol."""
        try:
            symbol = request.get("symbol", "BTC-USDT")
            leverage = int(request.get("leverage", 3))
            result = engine.client.set_leverage(symbol, leverage)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @app.get("/api/funding/{symbol}")
    async def get_funding_rate(symbol: str):
        """Get current and historical funding rate."""
        try:
            current = engine.client.get_funding_rate(symbol)
            history = engine.client.get_funding_rate_history(symbol, limit=24)
            return {
                "current": float(current.get("fundingRate", 0)) * 100,
                "next_time": current.get("fundingTime"),
                "history": [
                    {
                        "rate": float(h.get("fundingRate", 0)) * 100,
                        "time": int(h.get("fundingTime", 0)),
                    }
                    for h in history[:24]
                ]
            }
        except Exception as e:
            return {"current": 0, "history": [], "error": str(e)}
    
    # ==================== Session Journal Endpoints ====================
    
    from ..features.journal import SessionJournal
    session_journal = SessionJournal()
    
    @app.get("/api/journal/session")
    async def get_session():
        """Get today's session journal."""
        return session_journal.get_today().to_dict()
    
    @app.post("/api/journal/session")
    async def update_session(
        mood: Optional[str] = None,
        notes: Optional[str] = None,
        plan: Optional[str] = None,
        review: Optional[str] = None,
    ):
        """Update today's session journal."""
        entry = session_journal.update_today(
            mood=mood,
            notes=notes,
            plan=plan,
            review=review,
        )
        return {"success": True, "entry": entry.to_dict()}
    
    @app.get("/api/journal/session/history")
    async def get_session_history(days: int = 7):
        """Get recent session journal entries."""
        entries = session_journal.get_recent(days)
        return [e.to_dict() for e in entries]
    
    # ==================== Quick Actions Endpoints ====================
    
    from ..features.actions import QuickActions
    quick_actions = QuickActions()
    
    @app.get("/api/actions")
    async def get_quick_actions():
        """Get all quick actions."""
        return [a.to_dict() for a in quick_actions.get_all()]
    
    @app.post("/api/actions/{action_id}/execute")
    async def execute_quick_action(action_id: str):
        """Execute a quick action."""
        action = quick_actions.get(action_id)
        if not action:
            raise HTTPException(status_code=404, detail="Action not found")
        
        # Calculate actual SL/TP from percentages
        try:
            ticker = engine.market.get_ticker(action.symbol)
            price = ticker.last
            
            stop_loss = None
            take_profit = None
            
            if action.stop_loss_percent:
                if action.side == "long":
                    stop_loss = price * (1 - action.stop_loss_percent / 100)
                else:
                    stop_loss = price * (1 + action.stop_loss_percent / 100)
            
            if action.take_profit_percent:
                if action.side == "long":
                    take_profit = price * (1 + action.take_profit_percent / 100)
                else:
                    take_profit = price * (1 - action.take_profit_percent / 100)
            
            # Execute
            result = engine.quick_trade(
                symbol=action.symbol,
                side=action.side,
                size=action.size_percent,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            
            return {
                "success": result.success,
                "action": action.to_dict(),
                "error": result.error,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==================== Performance Endpoints ====================
    
    from ..features.performance import PerformanceTracker
    perf_tracker = PerformanceTracker(engine.trade_journal)
    
    @app.get("/api/performance")
    async def get_performance(days: Optional[int] = None):
        """Get performance statistics."""
        stats = perf_tracker.get_stats(days=days)
        return stats.to_dict()
    
    @app.get("/api/performance/summary")
    async def get_performance_summary():
        """Get full performance summary."""
        return perf_tracker.get_summary()
    
    @app.get("/api/performance/daily")
    async def get_daily_pnl(days: int = 30):
        """Get daily P&L for charting."""
        return perf_tracker.get_daily_pnl(days)
    
    # ==================== Trade Logging ====================
    
    @app.post("/api/trades/log")
    async def log_trade(request: dict):
        """Log a manual trade for tracking."""
        try:
            symbol = request.get("symbol", "BTC-USDT")
            side = request.get("side", "long")
            entry_price = float(request.get("entry_price", 0))
            exit_price = float(request.get("exit_price", 0))
            size = float(request.get("size", 0))
            
            # Calculate P&L
            if side == "long":
                pnl = (exit_price - entry_price) * size
            else:
                pnl = (entry_price - exit_price) * size
            
            pnl_percent = ((exit_price / entry_price) - 1) * 100
            if side == "short":
                pnl_percent = -pnl_percent
            
            # Log to journal
            trade = engine.trade_journal.add_trade(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
                size=size,
                pnl=pnl,
                pnl_percent=pnl_percent,
                notes="Manually logged from dashboard"
            )
            
            return {
                "success": True,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "trade_id": trade.trade_id
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @app.get("/api/trades/recent")
    async def get_recent_trades(limit: int = 20):
        """Get recent logged trades."""
        trades = engine.trade_journal.get_recent(limit=limit)
        return trades
    
    # ==================== Settings Endpoints ====================
    
    import os
    from pathlib import Path
    
    @app.get("/api/settings")
    async def get_settings():
        """Get current settings status."""
        return {
            "version": "0.1.0",
            "blofin_configured": bool(os.getenv("BLOFIN_API_KEY")),
            "blofin_demo": os.getenv("BLOFIN_DEMO", "true").lower() == "true",
            "claude_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
            "discord_configured": bool(os.getenv("DISCORD_WEBHOOK_URL")),
            "telegram_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "autonomy": config.autonomy,
        }
    
    @app.post("/api/settings/blofin")
    async def save_blofin_settings(request: dict):
        """Save Blofin API settings to .env file."""
        try:
            env_path = Path(".env")
            env_content = {}
            
            # Read existing .env
            if env_path.exists():
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            env_content[key] = value
            
            # Update with new values
            env_content["BLOFIN_API_KEY"] = request.get("api_key", "")
            env_content["BLOFIN_API_SECRET"] = request.get("api_secret", "")
            env_content["BLOFIN_PASSPHRASE"] = request.get("passphrase", "")
            env_content["BLOFIN_DEMO"] = "true" if request.get("demo", True) else "false"
            
            # Write back
            with open(env_path, "w") as f:
                for key, value in env_content.items():
                    f.write(f"{key}={value}\n")
            
            return {"success": True, "message": "Settings saved. Restart server to apply."}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @app.post("/api/settings/claude")
    async def save_claude_settings(request: dict):
        """Save Claude API key to .env file."""
        try:
            env_path = Path(".env")
            env_content = {}
            
            if env_path.exists():
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            env_content[key] = value
            
            env_content["ANTHROPIC_API_KEY"] = request.get("api_key", "")
            
            with open(env_path, "w") as f:
                for key, value in env_content.items():
                    f.write(f"{key}={value}\n")
            
            return {"success": True, "message": "Claude API key saved. Restart server to apply."}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @app.post("/api/settings/notifications")
    async def save_notification_settings(request: dict):
        """Save notification settings to .env file."""
        try:
            env_path = Path(".env")
            env_content = {}
            
            if env_path.exists():
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            env_content[key] = value
            
            if request.get("discord_webhook"):
                env_content["DISCORD_WEBHOOK_URL"] = request.get("discord_webhook")
            if request.get("telegram_token"):
                env_content["TELEGRAM_BOT_TOKEN"] = request.get("telegram_token")
            if request.get("telegram_chat_id"):
                env_content["TELEGRAM_CHAT_ID"] = request.get("telegram_chat_id")
            
            with open(env_path, "w") as f:
                for key, value in env_content.items():
                    f.write(f"{key}={value}\n")
            
            return {"success": True, "message": "Notification settings saved."}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @app.post("/api/settings/test")
    async def test_blofin_connection():
        """Test Blofin API connection."""
        try:
            balance = client.get_balance()
            return {
                "blofin_ok": True,
                "balance": float(balance.get("totalEquity", 0)),
            }
        except Exception as e:
            return {
                "blofin_ok": False,
                "blofin_error": str(e),
            }
    
    # ==================== Dashboard ====================
    
    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        """Serve dashboard HTML."""
        return DASHBOARD_HTML
    
    return app

