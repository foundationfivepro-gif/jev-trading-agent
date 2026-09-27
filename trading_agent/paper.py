"""Paper trading: run the strategy forward from a start date on real prices.

Each run replays the backtest engine from the paper start date through the
latest completed day, so paper results are exactly what the strategy would
have done live (fills at next open, with fees and slippage). It prints the
orders to place at the next open and appends a snapshot to a log, so you can
compare paper performance against the backtest before risking money.
"""

import csv
import json
from datetime import date
from pathlib import Path

from . import data as data_mod
from .backtest import run
from .config import Params
from .jev_gate import OrderVerdict, hard_rules, review_order
from .metrics import equity_stats

DEFAULT_DIR = Path("paper_state")


def paper_step(p: Params, state_dir: Path = DEFAULT_DIR, start: str | None = None, data=None, use_jev: bool = True) -> dict:
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
    else:
        state = {"start": start or date.today().isoformat(), "initial_equity": p.initial_equity}
        state_path.write_text(json.dumps(state, indent=2))

    p = p.with_(initial_equity=state["initial_equity"])
    data = data or data_mod.load_universe(p.universe)
    result = run(data, p, start=state["start"])
    if result.equity.empty:
        return {"start": state["start"], "message": "No completed trading days since the paper start date yet."}

    as_of = result.equity.index[-1]
    last_close = {s: df["close"].loc[:as_of].iloc[-1] for s, df in data.items() if s in p.universe}
    snapshot = {
        "as_of": as_of.date().isoformat(),
        "start": state["start"],
        "equity": round(float(result.equity.iloc[-1]), 2),
        "cash": round(result.cash, 2),
        "positions": {
            s: {
                "units": pos.units,
                "entry_price": round(pos.entry_price, 6),
                "stop": round(pos.stop, 6),
                "value": round(pos.units * last_close[s], 2),
            }
            for s, pos in result.positions.items()
        },
        "orders_for_next_open": _reviewed_orders(result, last_close, p, use_jev),
        "stats": {k: round(float(v), 4) for k, v in equity_stats(result.equity).items()},
    }

    log_path = state_dir / "equity_log.csv"
    new_log = not log_path.exists()
    with log_path.open("a", newline="") as fh:
        writer = csv.writer(fh)
        if new_log:
            writer.writerow(["as_of", "equity", "cash", "positions", "orders"])
        writer.writerow(
            [
                snapshot["as_of"],
                snapshot["equity"],
                snapshot["cash"],
                ";".join(snapshot["positions"]),
                ";".join(f"{o['side']}:{o['symbol']}:{o['verdict']}" for o in snapshot["orders_for_next_open"]),
            ]
        )
    (state_dir / "latest.json").write_text(json.dumps(snapshot, indent=2))
    return snapshot


def _reviewed_orders(result, last_close, p: Params, use_jev: bool) -> list[dict]:
    """Attach a verdict to each order. Only "allow" orders should be placed; "review" needs a person."""
    equity = float(result.equity.iloc[-1])
    gross = sum(pos.units * last_close[s] for s, pos in result.positions.items())
    out = []
    for o in result.pending:
        notional = o.units * last_close[o.symbol]
        gross += notional if o.side == "buy" else -notional
        order = {
            "mode": "paper", "symbol": o.symbol, "side": o.side, "units": o.units, "reason": o.reason,
            "notional": notional, "weight": notional / equity, "max_weight": p.max_position_weight,
            "risk_per_trade": p.risk_per_trade, "gross_exposure_after": gross / equity, "universe": p.universe,
        }
        if use_jev:
            v = review_order(order)
        else:
            v = hard_rules(order) or OrderVerdict("allow", "hard rules passed; Jev review skipped", "rule")
        out.append({
            "symbol": o.symbol, "side": o.side, "units": o.units, "reason": o.reason,
            "verdict": v.verdict, "verdict_reason": v.reason, "verdict_source": v.source,
        })
    return out
