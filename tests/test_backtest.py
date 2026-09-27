import numpy as np
import pytest

from trading_agent.backtest import run
from trading_agent.config import Params
from tests.conftest import make_frame

P = Params(
    universe=("AAA-USD",),
    regime_symbol="AAA-USD",
    fast_ma=5,
    slow_ma=20,
    regime_ma=20,
    breakout_lookback=5,
    atr_period=5,
    liquidity_lookback=5,
    use_partial_take_profit=False,
)


def uptrend_then_crash():
    flat = np.full(30, 100.0)
    up = 100 * 1.02 ** np.arange(1, 41)
    crash = up[-1] * 0.9 ** np.arange(1, 11)
    return np.concatenate([flat, up, crash])


def test_buys_on_next_open_not_signal_close():
    df = make_frame(uptrend_then_crash())
    df["open"] = df["open"] * 1.005  # overnight gap so open != prior close
    df["high"] = df[["high", "open"]].max(axis=1)
    result = run({"AAA-USD": df}, P)
    first_buy = next(f for f in result.fills if f["side"] == "buy")
    signal_day = first_buy["date"] - np.timedelta64(1, "D")
    assert first_buy["price"] == pytest.approx(df.loc[first_buy["date"], "open"] * (1 + P.slippage))
    assert first_buy["price"] != pytest.approx(df.loc[signal_day, "close"] * (1 + P.slippage))


def test_stop_or_trend_exit_closes_position_in_crash():
    result = run({"AAA-USD": make_frame(uptrend_then_crash())}, P)
    assert not result.positions
    assert result.trades and result.trades[0].exit_reason in {"stop", "trend"}


def test_fees_reduce_equity():
    closes = uptrend_then_crash()
    cheap = run({"AAA-USD": make_frame(closes)}, P.with_(fee_rate=0.0, slippage=0.0))
    costly = run({"AAA-USD": make_frame(closes)}, P.with_(fee_rate=0.01, slippage=0.002))
    assert costly.equity.iloc[-1] < cheap.equity.iloc[-1]


def test_position_weight_is_capped():
    p = P.with_(risk_per_trade=0.5, max_position_weight=0.2)
    df = make_frame(uptrend_then_crash())
    result = run({"AAA-USD": df}, p)
    buy = next(f for f in result.fills if f["side"] == "buy")
    equity_before = result.equity.loc[buy["date"] - np.timedelta64(1, "D")]
    assert buy["units"] * buy["price"] <= 0.2 * equity_before * 1.05  # 5% for overnight gap


def test_regime_filter_blocks_entries_in_downtrend():
    falling_btc = make_frame(100 * 0.99 ** np.arange(80))
    alt = make_frame(uptrend_then_crash())
    p = P.with_(universe=("AAA-USD", "BTC-USD"), regime_symbol="BTC-USD")
    result = run({"AAA-USD": alt, "BTC-USD": falling_btc}, p)
    assert not [f for f in result.fills if f["side"] == "buy"]
    off = run({"AAA-USD": alt, "BTC-USD": falling_btc}, p.with_(use_regime_filter=False))
    assert [f for f in off.fills if f["side"] == "buy" and f["symbol"] == "AAA-USD"]


def test_partial_take_profit_sells_a_fraction():
    closes = np.concatenate([np.full(30, 100.0), 100 * 1.03 ** np.arange(1, 60)])
    result = run({"AAA-USD": make_frame(closes)}, P.with_(use_partial_take_profit=True, take_profit_r=1.0))
    tp = [f for f in result.fills if f["reason"] == "take_profit"]
    buy = next(f for f in result.fills if f["side"] == "buy")
    assert len(tp) == 1
    assert tp[0]["units"] == pytest.approx(buy["units"] * P.take_profit_fraction)
    assert "AAA-USD" in result.positions  # the rest keeps riding the trend


def test_never_uses_leverage():
    closes = uptrend_then_crash()
    result = run({"AAA-USD": make_frame(closes)}, P.with_(risk_per_trade=1.0, max_position_weight=5.0))
    assert result.exposure.max() <= 1.0 + 1e-9
