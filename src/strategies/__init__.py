"""Strategies module - signals, indicators, and backtesting."""

from .base import Strategy, Signal, SignalType
from .indicators import Indicators
from .signals import SignalGenerator
from .backtest import Backtester, BacktestResult, Backtest, Candle
from .webhook import WebhookReceiver, SignalProcessor, WebhookSignal

__all__ = [
    "Strategy",
    "Signal", 
    "SignalType",
    "Indicators",
    "SignalGenerator",
    "Backtester",
    "BacktestResult",
    "Backtest",
    "Candle",
    "WebhookReceiver",
    "SignalProcessor",
    "WebhookSignal",
]

