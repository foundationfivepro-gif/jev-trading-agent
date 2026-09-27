# jev-trading-agent

A long-only crypto trend-following strategy on spot (no leverage), built from
the parts of popular X trading posts that hold up, with a backtester, a
paper-trading mode and a memecoin rug-risk screen.

See [STRATEGY.md](STRATEGY.md) for where each rule came from, what was
thrown out, and the backtest results.

## Setup

```bash
pip install -r requirements.txt
```

Prices come from Coinbase's public API (no key needed) and are cached in `data_cache/`.

## Usage

```bash
python -m trading_agent backtest            # full history vs BTC buy & hold, by year
python -m trading_agent backtest --trades   # plus every closed trade
python -m trading_agent ablate              # switch off each borrowed rule and compare
python -m trading_agent paper --start 2026-10-01   # start a paper account
python -m trading_agent paper               # run daily after 00:00 UTC
python -m trading_agent screen examples/tokens.json   # rug-risk screen (example input)
```

`paper` prints the current positions, stops, equity and the orders to place
at the next open, and appends to `paper_state/equity_log.csv`. To run it
daily, a cron line such as `5 0 * * * cd /path/to/repo && python -m trading_agent paper`
is enough.

`screen` takes one token snapshot or a list (fields are in
`trading_agent/screening/rug_filters.py`: market cap, 24h volume, fees,
holders with % supply, SOL position, wallet age, cluster id, recent closes,
mint/freeze authority). It flags reasons to avoid a token. Passing is not a buy signal.

## Strategy in one paragraph

Each day at the close, for BTC, ETH, SOL, XRP, LINK and DOGE: buy at the next
open if the 20-day MA is above the 100-day MA, price is at a 20-day high,
it isn't stretched more than 3 ATR above the 20-day MA, the coin is liquid,
and BTC is above its 200-day MA. Size each trade so hitting a 3-ATR stop loses
1% of equity (max 25% per coin, never above 100% invested). Trail the stop at
3 ATR below the highest close, sell a third at +4R, exit fully on the stop or
when the 20-day MA drops below the 100-day. New entries pause for 30 days after a
25% drawdown.

## Settings

All parameters are in `trading_agent/config.py`. The one to consider changing
is `risk_per_trade`: it scales return and drawdown together (see STRATEGY.md).

## Tests

```bash
python -m pytest
```

## Not included yet

Live order placement. Paper trade first; wiring a real exchange should come
only after paper results track the backtest.
