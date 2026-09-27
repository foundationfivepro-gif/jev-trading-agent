"""Command line entry point: python -m trading_agent <command>."""

import argparse
import json
import sys
from pathlib import Path

from . import data as data_mod
from .backtest import run
from .config import Params
from .metrics import equity_stats, format_stats, summarize, yearly_returns
from .jev_gate import promo_risk
from .paper import paper_step
from .screening.rug_filters import Holder, TokenSnapshot, screen

ABLATIONS = {
    "all rules on (baseline)": {},
    "no BTC regime filter": {"use_regime_filter": False},
    "no liquidity filter": {"use_liquidity_filter": False},
    "no anti-FOMO filter": {"use_anti_fomo": False},
    "no partial take-profit": {"use_partial_take_profit": False},
    "no drawdown halt": {"drawdown_halt": 1.0},
    "Coinbase retail fees (1.2%)": {"fee_rate": 0.012},
}


def _buy_and_hold(df, start, end):
    closes = df["close"].loc[start:end]
    return closes / closes.iloc[0] * Params().initial_equity


def cmd_backtest(args):
    p = Params()
    data = data_mod.load_universe(p.universe, refresh=args.refresh)
    result = run(data, p, start=args.start, end=args.end)
    eq = result.equity
    print(f"Period: {eq.index[0].date()} to {eq.index[-1].date()}  (the first {p.warmup_bars} days of each coin are indicator warm-up)")
    print(format_stats("strategy", summarize(result)))
    btc = _buy_and_hold(data["BTC-USD"], result.equity.index[0], result.equity.index[-1])
    print(format_stats("BTC buy & hold", equity_stats(btc)))
    print("\nReturn by year:")
    strat_y, btc_y = yearly_returns(result.equity), yearly_returns(btc)
    for year in strat_y.index:
        print(f"  {year}: strategy {strat_y[year]:>7.1%}   BTC {btc_y.get(year, float('nan')):>7.1%}")
    if args.trades:
        for t in result.trades:
            print(f"  {t.entry_date.date()} -> {t.exit_date.date()} {t.symbol:<9} {t.r_multiple:>6.2f}R {t.pnl:>10.2f} ({t.exit_reason})")


def cmd_ablate(args):
    base = Params()
    data = data_mod.load_universe(base.universe, refresh=args.refresh)
    for name, change in ABLATIONS.items():
        print(format_stats(name, summarize(run(data, base.with_(**change), start=args.start, end=args.end))))


def cmd_paper(args):
    snapshot = paper_step(Params(), state_dir=Path(args.state_dir), start=args.start, use_jev=not args.no_jev)
    print(json.dumps(snapshot, indent=2, default=str))


def cmd_screen(args):
    raw = json.loads(Path(args.token_file).read_text())
    tokens = raw if isinstance(raw, list) else [raw]
    for t in tokens:
        t["holders"] = [Holder(**h) for h in t.get("holders", [])]
        res = screen(TokenSnapshot(**t))
        flags = list(res.flags)
        if not args.no_jev and t.get("description"):
            judged = promo_risk(t["description"])
            flags += judged["flags"] if judged else ["(Jev unavailable: promo text not judged)"]
        failed = [f for f in flags if not f.startswith("(")]
        print(f"{res.symbol}: {'AVOID' if failed else 'PASSED screen (not a buy signal)'}")
        for flag in flags:
            print(f"  - {flag}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="trading_agent")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="run the strategy on historical data")
    bt.add_argument("--start")
    bt.add_argument("--end")
    bt.add_argument("--refresh", action="store_true", help="re-download all candles")
    bt.add_argument("--trades", action="store_true", help="list every closed trade")
    bt.set_defaults(func=cmd_backtest)

    ab = sub.add_parser("ablate", help="measure each borrowed rule by switching it off")
    ab.add_argument("--start")
    ab.add_argument("--end")
    ab.add_argument("--refresh", action="store_true")
    ab.set_defaults(func=cmd_ablate)

    pp = sub.add_parser("paper", help="forward-test on live prices; run once a day")
    pp.add_argument("--start", help="paper start date (first run only), default today")
    pp.add_argument("--state-dir", default="paper_state")
    pp.add_argument("--no-jev", action="store_true", help="skip the Jev order review")
    pp.set_defaults(func=cmd_paper)

    sc = sub.add_parser("screen", help="rug-risk screen for memecoin snapshots (JSON)")
    sc.add_argument("token_file")
    sc.add_argument("--no-jev", action="store_true", help="skip Jev's judgement of promo text")
    sc.set_defaults(func=cmd_screen)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
