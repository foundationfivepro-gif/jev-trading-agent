"""Strategy parameters.

Every rule borrowed from the posts we reviewed has a switch here, so its
effect can be measured on its own (see `python -m trading_agent ablate`).
Defaults are textbook values, not values tuned to fit the backtest.
"""

from dataclasses import dataclass, field, replace

DEFAULT_UNIVERSE = ("BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "LINK-USD", "DOGE-USD")


@dataclass(frozen=True)
class Params:
    universe: tuple[str, ...] = DEFAULT_UNIVERSE
    regime_symbol: str = "BTC-USD"

    # Trend signal: time-series momentum via a fast/slow moving-average pair.
    fast_ma: int = 20
    slow_ma: int = 100
    # Confirmation: close makes a new N-day high (breakout).
    breakout_lookback: int = 20
    atr_period: int = 20

    # Borrowed rules (each can be switched off for ablation).
    use_regime_filter: bool = True       # only open new longs while BTC > its 200d MA
    regime_ma: int = 200
    use_liquidity_filter: bool = True    # skip thin markets ("volume vs market cap" check)
    min_dollar_volume: float = 5_000_000.0
    liquidity_lookback: int = 30
    use_anti_fomo: bool = True           # don't chase: skip entries stretched far above the fast MA
    max_extension_atr: float = 3.0
    use_partial_take_profit: bool = True # "lock in profits in stages"
    take_profit_r: float = 4.0           # take profit once the gain reaches this many R
    take_profit_fraction: float = 0.33   # fraction of the position sold at that point

    # Risk management.
    risk_per_trade: float = 0.01         # equity lost if the initial stop is hit
    stop_atr: float = 3.0                # initial and trailing stop distance in ATRs
    max_position_weight: float = 0.25    # cap per coin, as a fraction of equity
    max_gross_exposure: float = 1.0      # spot only, no leverage
    drawdown_halt: float = 0.25          # pause new entries after this peak-to-trough loss
    halt_days: int = 30

    # Costs per side, as fractions of notional.
    fee_rate: float = 0.004
    slippage: float = 0.001

    initial_equity: float = 10_000.0

    @property
    def warmup_bars(self) -> int:
        return max(self.slow_ma, self.regime_ma, self.liquidity_lookback, self.breakout_lookback) + 1

    def with_(self, **changes) -> "Params":
        return replace(self, **changes)
