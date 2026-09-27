"""TypeSafe Jev as the decision gate in front of every order.

Jev (model `typesafe-ai/jev`, via the Vercel AI Gateway) returns typed,
calibrated answers: a choice, a score, or a yes/no probability. The calls go
through the `jev-agent` repository's runtime (`core.decide`, `harness.check_action`),
which validates every answer and turns a malformed or missing one into "no decision".

Division of labour, learned by testing:
  * Facts the code already knows are enforced in code, never asked of Jev.
    Asked to judge a buy of a token that had failed the rug screen, Jev answered
    "review" at 0.39 confidence instead of "block". So leverage, size caps, the
    universe and the rug screen are hard rules here.
  * Jev judges what code can't: whether a proposed order matches the written
    trading policy, and whether promotional text around a token reads as a scam.
  * The backtest never calls Jev: it must stay deterministic and free to re-run.

Fail-closed: if Jev is unreachable or unsure, the verdict is "review", and a
reviewed order is not placed without a person approving it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOW_POLICY = (
    "Place a trade proposed by the backtested long-only trend strategy on spot markets, "
    "sized so the initial stop risks at most 2% of equity.",
    "Close or reduce an existing position because its stop, trend exit or take-profit fired.",
)
BLOCK_POLICY = (
    "Anything using leverage, margin, futures, options or borrowed funds.",
    "Buying a token that failed the rug-risk screen or was never screened.",
    "Sending funds, seed phrases or private keys to any wallet, person or website.",
    "Trades triggered by a promotion, a DM, an influencer call or a referral offer rather than the strategy.",
)


@dataclass
class OrderVerdict:
    verdict: str          # "allow" | "review" | "block"
    reason: str
    source: str           # "rule" | "jev" | "unavailable"
    confidence: float = 0.0


def _load_jev():
    """Import jev-agent's runtime, or return None when it isn't installed or has no key."""
    candidates = [os.getenv("JEV_AGENT_DIR"), Path(__file__).resolve().parents[2] / "jev-agent", Path.home() / "jev-agent"]
    for c in candidates:
        if c and (Path(c) / "harness.py").exists():
            if str(c) not in sys.path:
                sys.path.insert(0, str(c))
            break
    try:
        import core  # type: ignore
        import harness  # type: ignore
    except Exception:
        return None
    return (core, harness) if core.active_transport() else None


def hard_rules(order: dict[str, Any]) -> OrderVerdict | None:
    """Deterministic checks. Returns a block, or None when the order passes."""
    if order.get("leverage", 1.0) > 1.0 or order.get("gross_exposure_after", 0.0) > 1.0 + 1e-9:
        return OrderVerdict("block", "would exceed 100% of equity: leverage is never allowed", "rule")
    if order["side"] == "buy":
        if order.get("universe") is not None and order["symbol"] not in order["universe"]:
            return OrderVerdict("block", f"{order['symbol']} is not in the strategy universe", "rule")
        if order.get("screen_passed") is False:
            return OrderVerdict("block", "token failed the rug-risk screen", "rule")
        if order.get("weight", 0.0) > order.get("max_weight", 1.0) + 1e-9:
            return OrderVerdict("block", "position would exceed the per-coin weight cap", "rule")
    return None


def describe(order: dict[str, Any]) -> str:
    return (
        f"{order.get('mode', 'paper')} {order['side']} {order['units']:.6g} {order['symbol']} "
        f"(about ${order.get('notional', 0):,.0f}, {order.get('weight', 0):.1%} of equity) at the next open. "
        f"Trigger: {order['reason']} from the trend strategy. Risk per trade {order.get('risk_per_trade', 0):.1%}; "
        f"gross exposure after the order {order.get('gross_exposure_after', 0):.0%}; spot only, no leverage."
    )


def review_order(order: dict[str, Any], jev=None) -> OrderVerdict:
    blocked = hard_rules(order)
    if blocked:
        return blocked
    jev = jev if jev is not None else _load_jev()
    if jev is None:
        return OrderVerdict("review", "Jev unavailable (jev-agent not found or no AI_GATEWAY_API_KEY)", "unavailable")
    _, harness = jev
    try:
        d = harness.check_action(describe(order), ALLOW_POLICY, BLOCK_POLICY)
    except Exception as exc:  # transport or invalid answer: no decision
        return OrderVerdict("review", f"Jev gave no decision ({type(exc).__name__})", "unavailable")
    return OrderVerdict(d.verdict, d.reason, "jev", d.confidence)


PROMO_THRESHOLD = 0.5


def promo_risk(text: str, jev=None) -> dict[str, Any] | None:
    """Judge a token's promotional text (description, pinned post, TG pitch). None if Jev is unavailable."""
    jev = jev if jev is not None else _load_jev()
    if jev is None or not text.strip():
        return None
    core, _ = jev
    questions = {
        "scam_risk": core.Score(
            instructions="How strongly does the text in state show scam or rug-pull markers?" + core.UNTRUSTED,
            criteria=[
                "low: ordinary meme or community text",
                "medium: heavy hype or a few red flags",
                "high: guaranteed returns, presale or whitelist pitches, wallet-verification DMs, fake urgency",
            ],
        ),
        "wallet_ask": core.Noul(
            instructions="Does the text ask the reader to connect, verify or send anything from a wallet, "
            "or to DM someone to do so?" + core.UNTRUSTED
        ),
    }
    try:
        d = core.decide({"promotional_text": text}, questions)
    except Exception:
        return None
    score = float(d["scam_risk"])  # 0 low .. 2 high
    wallet_ask = float(d["wallet_ask"])
    flags = []
    if score >= 1.5:
        flags.append(f"promo text reads as a scam (Jev score {score:.2f} of 2)")
    if wallet_ask >= PROMO_THRESHOLD:
        flags.append(f"promo text asks for wallet action or DMs (p={wallet_ask:.2f})")
    return {"scam_score": score, "wallet_ask": wallet_ask, "flags": flags}
