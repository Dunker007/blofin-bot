"""Blofin Bot - AI-Powered Trading System

Entry point for the trading bot.
"""

import argparse
import sys

from .core.config import Config
from .core.client import BlofinClient
from .core.logger import get_logger
from .data.market import MarketData
from .data.account import AccountData
from .ai.brain import AIBrain
from .dashboard.terminal import TerminalDashboard

logger = get_logger("blofin-bot")


def print_banner():
    """Print startup banner."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ██╗      ██████╗ ███████╗██╗███╗   ██╗            ║
║   ██╔══██╗██║     ██╔═══██╗██╔════╝██║████╗  ██║            ║
║   ██████╔╝██║     ██║   ██║█████╗  ██║██╔██╗ ██║            ║
║   ██╔══██╗██║     ██║   ██║██╔══╝  ██║██║╚██╗██║            ║
║   ██████╔╝███████╗╚██████╔╝██║     ██║██║ ╚████║            ║
║   ╚═════╝ ╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═══╝            ║
║                                                              ║
║               AI-Powered Trading Bot v0.1.0                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def cmd_dashboard(args, config: Config, client: BlofinClient):
    """Run the terminal dashboard."""
    market = MarketData(client)
    account = AccountData(client)
    
    brain = None
    if config.ai.api_key:
        brain = AIBrain(config, market, account)
    
    dashboard = TerminalDashboard(config, client, market, account, brain)
    dashboard.run(refresh_rate=args.refresh)


def cmd_test(args, config: Config, client: BlofinClient):
    """Test API connection."""
    print("\n[Testing Connection]")
    
    # Test public endpoint
    print("├─ Public API... ", end="")
    if client.test_connection():
        print("✓ OK")
    else:
        print("✗ FAILED")
        return
    
    # Test auth
    if config.api.api_key:
        print("├─ Authentication... ", end="")
        if client.test_auth():
            print("✓ OK")
        else:
            print("✗ FAILED (check API keys)")
    else:
        print("├─ Authentication... SKIPPED (no API key)")
    
    # Get ticker
    print("├─ Fetching BTC price... ", end="")
    ticker = client.get_ticker("BTC-USDT")
    if ticker.get("last"):
        print(f"${float(ticker['last']):,.2f}")
    else:
        print("FAILED")
    
    print("└─ Done!\n")


def cmd_price(args, config: Config, client: BlofinClient):
    """Get price for a symbol."""
    market = MarketData(client)
    ticker = market.get_ticker(args.symbol)
    
    print(f"\n{ticker.symbol}")
    print(f"├─ Price:  ${ticker.last:,.2f}")
    print(f"├─ Change: {ticker.change_24h:+.2f}%")
    print(f"├─ High:   ${ticker.high_24h:,.2f}")
    print(f"├─ Low:    ${ticker.low_24h:,.2f}")
    print(f"└─ Spread: ${ticker.spread:.2f} ({ticker.spread_pct:.4f}%)\n")


def cmd_analyze(args, config: Config, client: BlofinClient):
    """Run AI analysis on a symbol."""
    if not config.ai.api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        return
    
    market = MarketData(client)
    account = AccountData(client)
    brain = AIBrain(config, market, account)
    
    print(f"\nAnalyzing {args.symbol}...\n")
    
    analysis = brain.analyze_market(args.symbol)
    
    tech = analysis.get("technical", {})
    ai = analysis.get("ai_analysis", {})
    
    print(f"Price: ${analysis.get('price', 0):,.2f}")
    print(f"\n[Technical Analysis]")
    print(f"├─ Trend: {tech.get('trend', 'N/A')} (strength {tech.get('trend_strength', 'N/A')}/10)")
    print(f"├─ RSI: {tech.get('rsi', 0):.1f} ({tech.get('rsi_signal', 'N/A')})")
    print(f"├─ EMA: {tech.get('ema_signal', 'N/A')}")
    print(f"├─ Support: {tech.get('support', [])}")
    print(f"└─ Resistance: {tech.get('resistance', [])}")
    
    print(f"\n[AI Analysis]")
    print(f"├─ Trend: {ai.get('trend', 'N/A')}")
    print(f"├─ Sentiment: {ai.get('sentiment', 'N/A')}")
    print(f"└─ Summary: {ai.get('summary', 'N/A')}\n")


def cmd_decision(args, config: Config, client: BlofinClient):
    """Get AI trade decision for a symbol."""
    if not config.ai.api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        return
    
    market = MarketData(client)
    account = AccountData(client)
    brain = AIBrain(config, market, account)
    
    print(f"\nGetting decision for {args.symbol}...\n")
    
    decision = brain.get_decision(args.symbol)
    
    action_colors = {
        "long": "🟢",
        "short": "🔴",
        "close": "🟡",
        "wait": "⚪"
    }
    
    print(f"[Decision: {decision.decision_id}]")
    print(f"├─ Action: {action_colors.get(decision.action, '')} {decision.action.upper()}")
    print(f"├─ Confidence: {decision.confidence}%")
    
    if decision.entry:
        print(f"├─ Entry: ${decision.entry:,.2f}")
    if decision.stop_loss:
        print(f"├─ Stop Loss: ${decision.stop_loss:,.2f}")
    if decision.take_profit:
        print(f"├─ Take Profit: ${decision.take_profit:,.2f}")
    if decision.risk_reward:
        print(f"├─ R:R: {decision.risk_reward:.2f}")
    
    print(f"├─ Reasoning: {decision.reasoning}")
    print(f"└─ Invalidation: {decision.invalidation}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Blofin Bot - AI-Powered Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--config", "-c",
        default="config",
        help="Config directory (default: config)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Dashboard command
    dash_parser = subparsers.add_parser("dashboard", aliases=["d"], help="Run terminal dashboard")
    dash_parser.add_argument("--refresh", "-r", type=float, default=5.0, help="Refresh rate in seconds")
    
    # Test command
    subparsers.add_parser("test", aliases=["t"], help="Test API connection")
    
    # Price command
    price_parser = subparsers.add_parser("price", aliases=["p"], help="Get price for symbol")
    price_parser.add_argument("symbol", default="BTC-USDT", nargs="?", help="Trading symbol")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", aliases=["a"], help="AI analysis for symbol")
    analyze_parser.add_argument("symbol", default="BTC-USDT", nargs="?", help="Trading symbol")
    
    # Decision command
    decision_parser = subparsers.add_parser("decision", aliases=["dec"], help="Get AI trade decision")
    decision_parser.add_argument("symbol", default="BTC-USDT", nargs="?", help="Trading symbol")
    
    args = parser.parse_args()
    
    # Print banner
    print_banner()
    
    # Load config
    try:
        config = Config.load(args.config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)
    
    # Create client
    client = BlofinClient(config)
    
    # Route to command
    if args.command in ["dashboard", "d"]:
        cmd_dashboard(args, config, client)
    elif args.command in ["test", "t"]:
        cmd_test(args, config, client)
    elif args.command in ["price", "p"]:
        cmd_price(args, config, client)
    elif args.command in ["analyze", "a"]:
        cmd_analyze(args, config, client)
    elif args.command in ["decision", "dec"]:
        cmd_decision(args, config, client)
    else:
        # Default to dashboard
        args.refresh = 5.0
        cmd_dashboard(args, config, client)


if __name__ == "__main__":
    main()
