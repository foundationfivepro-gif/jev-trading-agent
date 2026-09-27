"""Per-coin signals, computed on each day's close.

Entry (long only), all must hold:
  1. Trend: fast MA above slow MA (time-series momentum).
  2. Confirmation: close at a new `breakout_lookback`-day high.
  3. Liquidity filter (optional): average daily dollar volume above a floor.
  4. Anti-FOMO filter (optional): close not more than `max_extension_atr`
     ATRs above the fast MA, so we don't buy a vertical candle.
The BTC regime filter is applied at portfolio level (see `regime_on`).

Exit: trailing ATR stop, or the trend flips (fast MA below slow MA).
"""

import pandas as pd

from . import indicators as ind
from .config import Params


def compute_features(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["open"] = df["open"]
    out["close"] = df["close"]
    out["fast"] = ind.sma(df["close"], p.fast_ma)
    out["slow"] = ind.sma(df["close"], p.slow_ma)
    out["atr"] = ind.atr(df, p.atr_period)
    out["dollar_volume"] = ind.dollar_volume(df, p.liquidity_lookback)

    trend_up = out["fast"] > out["slow"]
    breakout = df["close"] >= ind.rolling_high(df["close"], p.breakout_lookback)
    entry = trend_up & breakout & out["atr"].notna()
    if p.use_liquidity_filter:
        entry &= out["dollar_volume"] >= p.min_dollar_volume
    if p.use_anti_fomo:
        entry &= df["close"] <= out["fast"] + p.max_extension_atr * out["atr"]

    out["entry"] = entry
    out["trend_exit"] = out["fast"] < out["slow"]
    # Ranking score when several coins signal on the same day.
    out["strength"] = df["close"] / out["slow"] - 1.0
    return out


def regime_on(regime_df: pd.DataFrame, p: Params) -> pd.Series:
    """True on days the market is risk-on (BTC closes above its long MA)."""
    if not p.use_regime_filter:
        return pd.Series(True, index=regime_df.index)
    ma = ind.sma(regime_df["close"], p.regime_ma)
    return (regime_df["close"] > ma).fillna(False)
