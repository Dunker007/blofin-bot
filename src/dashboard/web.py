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
        
        <div class="grid grid-2" style="margin-top: 1rem;">
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
    </script>
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
    
    # Initialize components
    market = MarketData(client)
    account = AccountData(client)
    brain = AIBrain(config, market, account)
    engine = TradingEngine(config, client, brain)
    
    app = create_api(engine)
    
    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        """Serve dashboard HTML."""
        return DASHBOARD_HTML
    
    return app
