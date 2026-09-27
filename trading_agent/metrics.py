import math

import pandas as pd

from .backtest import Result

DAYS_PER_YEAR = 365  # crypto trades every day


def equity_stats(equity: pd.Series) -> dict:
    if len(equity) < 2:
        return {"total_return": 0.0, "cagr": 0.0, "vol": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
    returns = equity.pct_change().dropna()
    years = (equity.index[-1] - equity.index[0]).days / DAYS_PER_YEAR
    total = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else -1.0
    vol = returns.std() * math.sqrt(DAYS_PER_YEAR)
    sharpe = returns.mean() / returns.std() * math.sqrt(DAYS_PER_YEAR) if returns.std() > 0 else 0.0
    drawdown = (equity / equity.cummax() - 1).min()
    return {"total_return": total, "cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": drawdown}


def summarize(result: Result) -> dict:
    stats = equity_stats(result.equity)
    trades = result.trades
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    stats.update(
        {
            "trades": len(trades),
            "win_rate": len(wins) / len(trades) if trades else 0.0,
            "avg_r": sum(t.r_multiple for t in trades) / len(trades) if trades else 0.0,
            "profit_factor": gross_win / gross_loss if gross_loss > 0 else float("inf"),
            "avg_exposure": result.exposure.mean() if len(result.exposure) else 0.0,
            "final_equity": result.equity.iloc[-1] if len(result.equity) else 0.0,
        }
    )
    return stats


def yearly_returns(equity: pd.Series) -> pd.Series:
    year_end = equity.groupby(equity.index.year).last()
    year_start = pd.concat([pd.Series([equity.iloc[0]], index=[year_end.index[0]]), year_end.shift(1).dropna()])
    return year_end / year_start.values - 1


def format_stats(name: str, s: dict) -> str:
    return (
        f"{name:<28} CAGR {s['cagr']:>7.1%}  Sharpe {s['sharpe']:>5.2f}  MaxDD {s['max_drawdown']:>7.1%}"
        + (
            f"  Trades {s['trades']:>4}  Win {s['win_rate']:>5.1%}  AvgR {s['avg_r']:>5.2f}"
            f"  PF {s['profit_factor']:>5.2f}  Exposure {s['avg_exposure']:>5.1%}"
            if "trades" in s
            else ""
        )
    )
