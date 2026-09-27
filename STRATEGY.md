# Strategy notes: what we took from the posts, and what the data says

We reviewed trading "alpha" posts on X (memecoin guides, bot threads, Polymarket
arb claims) plus the research they point at. Most are referral funnels, but
several contain rules that are real risk management. We kept those, made each
one a switch in `trading_agent/config.py`, and measured it.

## Kept

| Idea | Where it came from | How it's implemented |
|---|---|---|
| Trend following: ride momentum, cut when it ends | [Decade of trend following in crypto (arXiv)](https://arxiv.org/pdf/2009.12155), bot threads | Fast/slow MA (20/100) plus a 20-day-high breakout for confirmation |
| One trend indicator, a confirmation, a filter, ATR stops | [Davidd Tech](https://x.com/DaviddDotTech/status/2082142492003020811) | Same structure: MA trend, breakout, liquidity/extension filters, 3-ATR stop |
| Volatility-based position sizing | [Richard Brennan on sizing](https://x.com/RichB118/status/1865165684164169938) | Each trade risks 1% of equity at a 3-ATR stop, capped at 25% per coin |
| Trade many coins, not one | [Max's 21-ticker bot](https://x.com/MaxBecauseBTC/status/2102124214396289191) | Basket of 6 liquid Coinbase coins |
| "Don't FOMO", "be patient" | memecoin guide under review | Skip entries more than 3 ATR above the fast MA |
| "Volume vs market cap" as a quick filter | memecoin guide | Minimum $5M average daily dollar volume |
| "Lock in profits in stages" | memecoin guide | Sell 1/3 at +4R, trail the rest |
| "Don't average down" | memecoin guide | No adding to positions, ever |
| Only trade when the market is healthy | common CT advice | New longs only while BTC is above its 200-day MA |
| Fees kill small edges | [PolyBackTest](https://x.com/polybacktest/status/2030892841552216529): Polymarket's "risk-free" arb has negative EV after fees | 0.4% fee + 0.1% slippage on every fill, stress test at 1.2% |
| Rug-pull checks | memecoin guide, [copy-trading threads](https://x.com/gem_dolphin/status/1856240582647062850) | `trading_agent/screening/rug_filters.py`, screen only |

## Rejected

- **Guaranteed income claims** ($500/day, "$100k in a couple of months"). No verifiable track record anywhere.
- **Sniping launches at $7–10k market cap.** Bots and insiders own that zone; a manual buyer is their exit liquidity.
- **Copy-trading "smart wallets".** Wallets that are known to be copied can dump on their copiers, and the lists are gated behind referral signups.
- **Polymarket both-sides arb.** Taker fees made it negative-EV, and the rest is a latency race.
- **Leverage, "top up your account", "sell at a $1B market cap".** Gambling cues, not rules.

## Results (Coinbase daily data, 2017-07 to 2026-09, $10k start)

Baseline (1% risk per trade):

| | CAGR | Sharpe | Max drawdown |
|---|---|---|---|
| Strategy | 10.5% | 1.05 | -13.7% |
| BTC buy & hold | 57.8% | 1.01 | -83.8% |

102 trades, 44% winners, average winner much bigger than average loser
(profit factor 2.7). Invested only ~7% of the time on average, which is why
the headline return is modest.

**Position size is the dial.** The edge stays the same, and size scales return and drawdown together:

| Risk per trade | CAGR | Max drawdown |
|---|---|---|
| 0.5% | 5.4% | -7.5% |
| 1% (default) | 10.5% | -13.7% |
| 2% | 20.0% | -23.8% |
| 3% | 27.9% | -33.6% |

**Robustness.** Ten MA/breakout combinations around the defaults were all
profitable (Sharpe 0.84–1.18). The result doesn't depend on one lucky setting.

**What each borrowed rule did** (`python -m trading_agent ablate`):

| Variant | CAGR | Sharpe | Max drawdown |
|---|---|---|---|
| All rules on | 10.5% | 1.05 | -13.7% |
| No BTC regime filter | 12.6% | 1.16 | -18.0% |
| No anti-FOMO filter | 12.5% | 1.10 | -16.1% |
| No partial take-profit | 11.8% | 1.00 | -16.3% |
| No liquidity filter | 10.7% | 1.07 | -13.7% |
| Coinbase retail fees (1.2%) | 9.2% | 0.93 | -15.5% |

The regime and anti-FOMO filters **cost** some return and mainly cut drawdown.
The liquidity filter does nothing for large coins; it's there for anything smaller
you add. Defaults were not flipped based on this table, because tuning to the
same backtest you report is how overfitting happens.

**The edge has weakened.** 2017–2021: Sharpe 1.53. 2022–2026: Sharpe 0.59.
Crypto trends have been choppier since 2022. Expect live results closer to
the second half.

## What this is not

Not a money printer, and not financial advice. Backtests overstate live
results. Paper trade it for at least 1–3 months, compare against these
numbers, and only then consider small real money.
