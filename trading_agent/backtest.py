"""Daily portfolio simulator.

Signals are read on day t's close and filled at day t+1's open, with fees and
slippage charged on every fill, so no trade uses information it couldn't have
had. Paper trading runs this same engine (see `paper.py`).
"""

from dataclasses import dataclass, field

import pandas as pd

from .config import Params
from .strategy import compute_features, regime_on


@dataclass
class Position:
    units: float
    entry_price: float
    entry_date: pd.Timestamp
    stop: float
    risk_per_unit: float  # 1R: distance from entry to the initial stop
    highest_close: float
    initial_units: float
    partial_taken: bool = False
    cost_basis: float = 0.0  # cash paid including fees, for P&L
    proceeds: float = 0.0    # cash received from partial sells


@dataclass
class Order:
    symbol: str
    side: str        # "buy" or "sell"
    units: float
    reason: str
    atr: float = 0.0  # ATR at signal time, used to place the stop on a buy


@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    pnl: float
    r_multiple: float
    exit_reason: str


@dataclass
class Result:
    equity: pd.Series
    trades: list[Trade]
    positions: dict[str, Position]
    pending: list[Order]
    exposure: pd.Series
    cash: float
    fills: list[dict] = field(default_factory=list)


def run(data: dict[str, pd.DataFrame], p: Params, start=None, end=None) -> Result:
    feats = {s: compute_features(df, p) for s, df in data.items() if s in p.universe}
    regime = regime_on(data[p.regime_symbol], p)

    dates = sorted(set().union(*(f.index for f in feats.values())))
    first_trade_date = pd.Timestamp(start) if start else None
    if end:
        dates = [d for d in dates if d <= pd.Timestamp(end)]

    cash = p.initial_equity
    positions: dict[str, Position] = {}
    pending: list[Order] = []
    trades: list[Trade] = []
    fills: list[dict] = []
    equity_curve: dict[pd.Timestamp, float] = {}
    exposure_curve: dict[pd.Timestamp, float] = {}
    peak = p.initial_equity
    halted_until: pd.Timestamp | None = None
    last_close: dict[str, float] = {}

    for date in dates:
        if first_trade_date is not None and date < first_trade_date:
            continue
        bars = {s: f.loc[date] for s, f in feats.items() if date in f.index}

        # 1. Fill yesterday's orders at today's open.
        still_pending = []
        for order in pending:
            bar = bars.get(order.symbol)
            if bar is None or pd.isna(bar["open"]):
                still_pending.append(order)
                continue
            if order.side == "sell":
                cash += _sell(order, bar["open"], date, positions, trades, fills, p)
            else:
                cash -= _buy(order, bar["open"], date, cash, positions, fills, p)
        pending = still_pending

        # 2. Mark to market.
        for s, bar in bars.items():
            last_close[s] = bar["close"]
        held_value = sum(pos.units * last_close[s] for s, pos in positions.items())
        equity = cash + held_value
        equity_curve[date] = equity
        exposure_curve[date] = held_value / equity if equity > 0 else 0.0

        # 3. Circuit breaker on portfolio drawdown.
        peak = max(peak, equity)
        if halted_until is None and equity < peak * (1 - p.drawdown_halt):
            halted_until = date + pd.Timedelta(days=p.halt_days)
            peak = equity  # measure the next drawdown from here
        if halted_until is not None and date >= halted_until:
            halted_until = None

        # 4. Manage open positions.
        for s, pos in positions.items():
            bar = bars.get(s)
            if bar is None or pd.isna(bar["atr"]):
                continue
            pos.highest_close = max(pos.highest_close, bar["close"])
            pos.stop = max(pos.stop, pos.highest_close - p.stop_atr * bar["atr"])
            if bar["close"] <= pos.stop:
                pending.append(Order(s, "sell", pos.units, "stop"))
            elif bar["trend_exit"]:
                pending.append(Order(s, "sell", pos.units, "trend"))
            elif (
                p.use_partial_take_profit
                and not pos.partial_taken
                and bar["close"] >= pos.entry_price + p.take_profit_r * pos.risk_per_unit
            ):
                pending.append(Order(s, "sell", pos.initial_units * p.take_profit_fraction, "take_profit"))
                pos.partial_taken = True

        # 5. New entries.
        risk_on = bool(regime.get(date, False))
        if halted_until is None and risk_on:
            exiting = {o.symbol for o in pending if o.side == "sell" and o.reason != "take_profit"}
            committed = sum(
                pos.units * last_close[s] for s, pos in positions.items() if s not in exiting
            )
            candidates = sorted(
                (
                    (s, bar)
                    for s, bar in bars.items()
                    if s not in positions and bool(bar["entry"])
                ),
                key=lambda sb: sb[1]["strength"],
                reverse=True,
            )
            for s, bar in candidates:
                units = p.risk_per_trade * equity / (p.stop_atr * bar["atr"])
                notional = min(units * bar["close"], p.max_position_weight * equity)
                room = p.max_gross_exposure * equity - committed
                notional = min(notional, room)
                if notional <= 0.01 * equity:
                    break
                pending.append(Order(s, "buy", notional / bar["close"], "entry", atr=bar["atr"]))
                committed += notional

    return Result(
        equity=pd.Series(equity_curve, dtype=float),
        trades=trades,
        positions=positions,
        pending=pending,
        exposure=pd.Series(exposure_curve, dtype=float),
        cash=cash,
        fills=fills,
    )


def _buy(order, open_price, date, cash, positions, fills, p: Params) -> float:
    price = open_price * (1 + p.slippage)
    units = min(order.units, cash / (price * (1 + p.fee_rate)))
    if units <= 0 or order.symbol in positions:
        return 0.0
    cost = units * price * (1 + p.fee_rate)
    risk = p.stop_atr * order.atr
    positions[order.symbol] = Position(
        units=units,
        entry_price=price,
        entry_date=date,
        stop=price - risk,
        risk_per_unit=risk,
        highest_close=price,
        initial_units=units,
        cost_basis=cost,
    )
    fills.append({"date": date, "symbol": order.symbol, "side": "buy", "units": units, "price": price, "reason": order.reason})
    return cost


def _sell(order, open_price, date, positions, trades, fills, p: Params) -> float:
    pos = positions.get(order.symbol)
    if pos is None:
        return 0.0
    price = open_price * (1 - p.slippage)
    units = min(order.units, pos.units)
    proceeds = units * price * (1 - p.fee_rate)
    pos.units -= units
    pos.proceeds += proceeds
    fills.append({"date": date, "symbol": order.symbol, "side": "sell", "units": units, "price": price, "reason": order.reason})
    if pos.units <= 1e-12:
        pnl = pos.proceeds - pos.cost_basis
        initial_risk = pos.risk_per_unit * pos.initial_units
        trades.append(
            Trade(
                symbol=order.symbol,
                entry_date=pos.entry_date,
                exit_date=date,
                entry_price=pos.entry_price,
                exit_price=price,
                pnl=pnl,
                r_multiple=pnl / initial_risk if initial_risk > 0 else 0.0,
                exit_reason=order.reason,
            )
        )
        del positions[order.symbol]
    return proceeds
