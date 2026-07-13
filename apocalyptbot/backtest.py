"""Backtester: replay a strategy over historical candles and score it.

Walks the candles forward one bar at a time, feeding the strategy only the
history it would have had at that moment (no lookahead), executes decisions
through the paper broker at each bar's close, and tracks the resulting equity
curve. Reports return, drawdown, a rough Sharpe, trade count and win rate,
and — crucially — compares against buy-and-hold so you can see whether the
strategy actually earned its complexity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

from .broker import Fill, PaperBroker
from .data import Candle
from .portfolio import Portfolio
from .strategies.base import Signal, Strategy


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    starting_cash: float
    final_equity: float
    equity_curve: List[float] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        m = self.metrics
        lines = [
            f"Backtest: {self.strategy} on {self.symbol}",
            f"  Bars tested:      {int(m.get('bars', 0))}",
            f"  Starting cash:    {self.starting_cash:,.2f}",
            f"  Final equity:     {self.final_equity:,.2f}",
            f"  Strategy return:  {m.get('total_return', 0) * 100:+.2f}%",
            f"  Buy & hold:       {m.get('buy_hold_return', 0) * 100:+.2f}%",
            f"  Max drawdown:     {m.get('max_drawdown', 0) * 100:.2f}%",
            f"  Sharpe (rough):   {m.get('sharpe', 0):.2f}",
            f"  Trades:           {int(m.get('num_trades', 0))}",
            f"  Win rate:         {m.get('win_rate', 0) * 100:.1f}%",
            f"  Fees paid:        {m.get('fees_paid', 0):,.2f}",
        ]
        return "\n".join(lines)


def run_backtest(
    candles: List[Candle],
    strategy: Strategy,
    symbol: str = "BTC-USD",
    starting_cash: float = 10_000.0,
    fee_rate: float = 0.005,
    slippage: float = 0.0005,
    periods_per_year: float = 24 * 365,
) -> BacktestResult:
    """Run ``strategy`` over ``candles`` and return a scored result."""
    if len(candles) < 2:
        raise ValueError("need at least 2 candles to backtest")

    portfolio = Portfolio(cash=starting_cash)
    broker = PaperBroker(portfolio, fee_rate=fee_rate, slippage=slippage)
    fills: List[Fill] = []
    equity_curve: List[float] = []

    # Bar i carries i+1 candles of history, so the first bar with `warmup`
    # candles available is index warmup-1.
    warmup = max(1, strategy.warmup())
    start = min(max(0, warmup - 1), len(candles) - 1)

    for i in range(start, len(candles)):
        window = candles[: i + 1]
        bar = candles[i]
        price = bar.close

        decision = strategy.decide(symbol, window, portfolio)
        if decision.signal is Signal.BUY:
            fill = broker.buy(symbol, price, portfolio.cash * decision.size, bar.timestamp)
            if fill:
                fills.append(fill)
        elif decision.signal is Signal.SELL:
            qty = portfolio.quantity(symbol) * decision.size
            fill = broker.sell(symbol, price, qty, bar.timestamp)
            if fill:
                fills.append(fill)

        equity_curve.append(portfolio.equity({symbol: price}))

    final_equity = equity_curve[-1] if equity_curve else starting_cash
    metrics = _compute_metrics(
        equity_curve=equity_curve,
        fills=fills,
        starting_cash=starting_cash,
        first_price=candles[start].close,
        last_price=candles[-1].close,
        periods_per_year=periods_per_year,
    )

    return BacktestResult(
        symbol=symbol,
        strategy=strategy.name,
        starting_cash=starting_cash,
        final_equity=final_equity,
        equity_curve=equity_curve,
        fills=fills,
        metrics=metrics,
    )


def _compute_metrics(
    equity_curve: List[float],
    fills: List[Fill],
    starting_cash: float,
    first_price: float,
    last_price: float,
    periods_per_year: float,
) -> Dict[str, float]:
    total_return = (equity_curve[-1] / starting_cash - 1.0) if equity_curve and starting_cash else 0.0
    buy_hold_return = (last_price / first_price - 1.0) if first_price else 0.0

    # Max drawdown over the equity curve.
    peak = -math.inf
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)

    # Per-bar returns -> rough annualized Sharpe (risk-free assumed 0).
    rets: List[float] = []
    for a, b in zip(equity_curve, equity_curve[1:]):
        if a > 0:
            rets.append(b / a - 1.0)
    sharpe = 0.0
    if len(rets) > 1:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        std = math.sqrt(var)
        if std > 0:
            sharpe = (mean / std) * math.sqrt(periods_per_year)

    sells = [f for f in fills if f.side == "SELL"]
    wins = [f for f in sells if f.realized_pnl > 0]
    win_rate = (len(wins) / len(sells)) if sells else 0.0
    fees_paid = sum(f.fee for f in fills)

    return {
        "bars": float(len(equity_curve)),
        "total_return": total_return,
        "buy_hold_return": buy_hold_return,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "num_trades": float(len(fills)),
        "win_rate": win_rate,
        "fees_paid": fees_paid,
    }
