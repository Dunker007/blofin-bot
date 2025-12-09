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
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 1rem;
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
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--bg-secondary);
            border-top: 1px solid rgba(255,255,255,0.1);
            max-height: 350px;
            display: flex;
            flex-direction: column;
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
            max-height: 200px;
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
    <header>
        <div class="logo">🤖 Blofin Bot</div>
        <div>
            <span class="status-badge status-demo" id="mode-badge">DEMO</span>
        </div>
    </header>
    
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
        
        <div class="controls">
            <button class="btn btn-danger" onclick="killSwitch()">🛑 Kill Switch</button>
            <button class="btn btn-primary" onclick="togglePause()" id="pause-btn">⏸️ Pause</button>
            <button class="btn btn-success" onclick="refreshData()">🔄 Refresh</button>
        </div>
        
        <!-- Tab Navigation -->
        <div class="tabs" style="margin-top: 1rem;">
            <button class="tab active" onclick="showTab('positions')">📊 Positions</button>
            <button class="tab" onclick="showTab('watchlist')">⭐ Watchlist</button>
            <button class="tab" onclick="showTab('scanner')">🔍 Scanner</button>
            <button class="tab" onclick="showTab('planner')">📝 Planner</button>
            <button class="tab" onclick="showTab('styles')">🎭 Styles</button>
        </div>
        
        <!-- Positions Tab -->
        <div id="tab-positions" class="tab-content active">
            <div class="grid grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Open Positions</span>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Size</th>
                                <th>P&L</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="positions-table">
                            <tr><td colspan="5" style="text-align:center;color:var(--text-secondary)">No positions</td></tr>
                        </tbody>
                    </table>
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Pending Approvals</span>
                    </div>
                    <div id="approvals-list">
                        <p style="color:var(--text-secondary)">No pending approvals</p>
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
                
                // Update positions table
                const positions = status.positions?.positions || [];
                const tbody = document.getElementById('positions-table');
                if (positions.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-secondary)">No positions</td></tr>';
                } else {
                    tbody.innerHTML = positions.map(p => `
                        <tr>
                            <td>${p.symbol}</td>
                            <td class="${p.side === 'long' ? 'positive' : 'negative'}">${p.side.toUpperCase()}</td>
                            <td>${p.size}</td>
                            <td class="${p.pnl >= 0 ? 'positive' : 'negative'}">$${p.pnl?.toFixed(2) || '0.00'}</td>
                            <td><button class="btn btn-danger" onclick="closePosition('${p.symbol}')" style="padding:0.25rem 0.5rem;font-size:0.75rem">Close</button></td>
                        </tr>
                    `).join('');
                }
            } catch (e) {
                console.error('Refresh failed:', e);
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
        });
    </script>
    
    <!-- Chat Window -->
    <div id="chat-container" class="chat-container">
        <div class="chat-header" onclick="toggleChat()">
            <h3>💬 AI Trading Assistant</h3>
            <button class="chat-toggle" id="chat-toggle-btn">▼</button>
        </div>
        <div class="chat-messages" id="chat-messages">
            <div class="chat-message ai">
                👋 Hi! I'm your trading assistant. I can see your portfolio, positions, and market data. Ask me anything about your trades!
            </div>
        </div>
        <div class="chat-input-container">
            <input type="text" class="chat-input" id="chat-input" placeholder="Ask about your portfolio, markets, or trading strategies..." />
            <button class="chat-send" id="chat-send-btn" onclick="sendChatMessage()">Send</button>
        </div>
    </div>
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
    
    # ==================== Dashboard ====================
    
    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        """Serve dashboard HTML."""
        return DASHBOARD_HTML
    
    return app

