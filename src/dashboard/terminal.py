"""Rich terminal dashboard for Blofin Bot."""

import time
from datetime import datetime
from typing import List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from ..core.config import Config
from ..core.client import BlofinClient
from ..data.market import MarketData, Ticker
from ..data.account import AccountData, Position, Balance
from ..ai.brain import AIBrain
from ..core.logger import get_logger

logger = get_logger(__name__)


class TerminalDashboard:
    """
    Rich CLI dashboard with live updates.
    
    Features:
    - Account balance and margin
    - Open positions with P&L
    - Watchlist prices
    - AI analysis panel
    """
    
    def __init__(
        self,
        config: Config,
        client: BlofinClient,
        market: MarketData,
        account: AccountData,
        brain: Optional[AIBrain] = None
    ):
        self.config = config
        self.client = client
        self.market = market
        self.account = account
        self.brain = brain
        
        self.console = Console()
        self.watchlist = [p.symbol for p in config.pairs if p.enabled]
        
        # State
        self._running = False
        self._last_update = None
        self._tickers: List[Ticker] = []
        self._positions: List[Position] = []
        self._balance: Optional[Balance] = None
        self._ai_summary: str = ""
    
    def _make_header(self) -> Panel:
        """Create header panel."""
        mode = "DEMO" if self.config.api.demo_mode else "LIVE"
        mode_color = "yellow" if self.config.api.demo_mode else "red bold"
        
        header = Text()
        header.append("BLOFIN BOT", style="bold cyan")
        header.append(" │ ", style="dim")
        header.append(f"Mode: ", style="dim")
        header.append(mode, style=mode_color)
        header.append(" │ ", style="dim")
        header.append(f"Autonomy: ", style="dim")
        header.append(self.config.autonomy.level.upper(), style="green")
        header.append(" │ ", style="dim")
        header.append(datetime.now().strftime("%H:%M:%S"), style="blue")
        
        return Panel(header, box=box.MINIMAL)
    
    def _make_balance_panel(self) -> Panel:
        """Create account balance panel."""
        if not self._balance:
            return Panel("Loading...", title="[bold]Account[/]", border_style="blue")
        
        b = self._balance
        pnl_color = "green" if b.unrealized_pnl >= 0 else "red"
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="dim")
        table.add_column("Value", justify="right")
        
        table.add_row("Equity", f"[bold]${b.total_equity:,.2f}[/]")
        table.add_row("Available", f"${b.available_balance:,.2f}")
        table.add_row("Used Margin", f"${b.used_margin:,.2f}")
        table.add_row("Unrealized P&L", f"[{pnl_color}]${b.unrealized_pnl:+,.2f}[/]")
        table.add_row("Margin Ratio", f"{b.margin_ratio:.1f}%")
        
        return Panel(table, title="[bold]Account[/]", border_style="blue")
    
    def _make_positions_panel(self) -> Panel:
        """Create positions panel."""
        if not self._positions:
            return Panel(
                Text("No open positions", style="dim italic"),
                title="[bold]Positions[/]",
                border_style="green"
            )
        
        table = Table(box=box.SIMPLE, padding=(0, 1))
        table.add_column("Symbol", style="cyan")
        table.add_column("Side", justify="center")
        table.add_column("Size", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Mark", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("P&L%", justify="right")
        table.add_column("Liq%", justify="right")
        
        for pos in self._positions:
            side_color = "green" if pos.side.value == "long" else "red"
            pnl_color = "green" if pos.unrealized_pnl >= 0 else "red"
            liq_color = "red" if pos.distance_to_liquidation < 10 else "yellow" if pos.distance_to_liquidation < 25 else "green"
            
            table.add_row(
                pos.symbol,
                f"[{side_color}]{pos.side.value.upper()}[/]",
                f"{pos.size:.4f}",
                f"${pos.avg_price:,.2f}",
                f"${pos.mark_price:,.2f}",
                f"[{pnl_color}]${pos.unrealized_pnl:+,.2f}[/]",
                f"[{pnl_color}]{pos.pnl_percent:+.2f}%[/]",
                f"[{liq_color}]{pos.distance_to_liquidation:.1f}%[/]"
            )
        
        return Panel(table, title=f"[bold]Positions ({len(self._positions)})[/]", border_style="green")
    
    def _make_market_panel(self) -> Panel:
        """Create market watchlist panel."""
        if not self._tickers:
            return Panel("Loading...", title="[bold]Markets[/]", border_style="yellow")
        
        table = Table(box=box.SIMPLE, padding=(0, 1))
        table.add_column("Symbol", style="cyan")
        table.add_column("Price", justify="right")
        table.add_column("24h", justify="right")
        table.add_column("High", justify="right", style="dim")
        table.add_column("Low", justify="right", style="dim")
        
        for ticker in self._tickers:
            change_color = "green" if ticker.change_24h >= 0 else "red"
            
            table.add_row(
                ticker.symbol,
                f"[bold]${ticker.last:,.2f}[/]",
                f"[{change_color}]{ticker.change_24h:+.2f}%[/]",
                f"${ticker.high_24h:,.2f}",
                f"${ticker.low_24h:,.2f}"
            )
        
        return Panel(table, title="[bold]Markets[/]", border_style="yellow")
    
    def _make_ai_panel(self) -> Panel:
        """Create AI analysis panel."""
        if not self._ai_summary:
            summary = "Press [bold cyan]A[/] for AI analysis"
        else:
            summary = self._ai_summary
        
        return Panel(
            summary,
            title=f"[bold]AI Analysis[/] [dim](Claude {self.config.ai.model.split('-')[1]})[/]",
            border_style="magenta"
        )
    
    def _make_controls_panel(self) -> Panel:
        """Create controls help panel."""
        controls = Text()
        controls.append("Q", style="bold cyan")
        controls.append(" Quit  ", style="dim")
        controls.append("R", style="bold cyan")
        controls.append(" Refresh  ", style="dim")
        controls.append("A", style="bold cyan")
        controls.append(" AI Analysis  ", style="dim")
        controls.append("T", style="bold cyan")
        controls.append(" Trade  ", style="dim")
        controls.append("K", style="bold red")
        controls.append(" Kill Switch", style="dim")
        
        return Panel(controls, box=box.MINIMAL)
    
    def _make_layout(self) -> Layout:
        """Create the dashboard layout."""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        layout["left"].split_column(
            Layout(name="balance", size=9),
            Layout(name="positions")
        )
        
        layout["right"].split_column(
            Layout(name="market"),
            Layout(name="ai")
        )
        
        return layout
    
    def _update_data(self) -> None:
        """Fetch latest data from API."""
        try:
            # Get tickers for watchlist
            self._tickers = self.market.get_tickers(self.watchlist)
            
            # Get balance and positions (if authenticated)
            if self.config.api.api_key:
                try:
                    self._balance = self.account.get_balance()
                    self._positions = self.account.get_positions()
                except Exception as e:
                    logger.warning(f"Account data fetch failed: {e}")
            
            self._last_update = datetime.now()
            
        except Exception as e:
            logger.error(f"Data update failed: {e}")
    
    def _render(self) -> Layout:
        """Render the full dashboard."""
        layout = self._make_layout()
        
        layout["header"].update(self._make_header())
        layout["balance"].update(self._make_balance_panel())
        layout["positions"].update(self._make_positions_panel())
        layout["market"].update(self._make_market_panel())
        layout["ai"].update(self._make_ai_panel())
        layout["footer"].update(self._make_controls_panel())
        
        return layout
    
    def run_ai_analysis(self) -> None:
        """Run AI analysis on watchlist."""
        if not self.brain:
            self._ai_summary = "[red]AI not configured[/]"
            return
        
        self._ai_summary = "[yellow]Analyzing...[/]"
        
        try:
            self._ai_summary = self.brain.get_summary(self.watchlist[:3])
        except Exception as e:
            self._ai_summary = f"[red]Analysis failed: {e}[/]"
    
    def run_once(self) -> None:
        """Run dashboard once (for testing)."""
        self._update_data()
        self.console.print(self._render())
    
    def run(self, refresh_rate: float = 5.0) -> None:
        """
        Run the live dashboard.
        
        Args:
            refresh_rate: Seconds between data refreshes
        """
        self._running = True
        self._update_data()
        
        self.console.print("[bold cyan]Starting Blofin Bot Dashboard...[/]")
        self.console.print("[dim]Press Ctrl+C to exit[/]\n")
        
        try:
            with Live(self._render(), console=self.console, refresh_per_second=2) as live:
                last_refresh = time.time()
                
                while self._running:
                    # Update data periodically
                    if time.time() - last_refresh >= refresh_rate:
                        self._update_data()
                        last_refresh = time.time()
                    
                    # Update display
                    live.update(self._render())
                    time.sleep(0.5)
                    
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Dashboard stopped[/]")
        finally:
            self._running = False
    
    def stop(self) -> None:
        """Stop the dashboard."""
        self._running = False
