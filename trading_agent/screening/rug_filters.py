"""Memecoin rug-risk screen.

The useful checks from the memecoin threads we reviewed, as pure functions.
Feed it a token snapshot from whatever source you use (GMGN, Birdeye,
DexScreener, RugCheck, Bubblemaps exports). It only says "avoid" or "passed
the screen". Passing is not a buy signal.
"""

from dataclasses import dataclass, field


@dataclass
class Holder:
    address: str
    pct_supply: float          # 0-100
    position_sol: float = 0.0
    wallet_age_days: float | None = None
    is_liquidity_pool: bool = False
    cluster_id: str | None = None  # wallets funded from the same source share a cluster


@dataclass
class TokenSnapshot:
    symbol: str
    market_cap_usd: float
    volume_24h_usd: float
    fees_generated_sol: float
    holders: list[Holder]
    # Recent closes (oldest first), used for the stair-step check.
    closes: list[float] = field(default_factory=list)
    mint_authority_revoked: bool | None = None
    freeze_authority_revoked: bool | None = None


@dataclass
class ScreenResult:
    symbol: str
    passed: bool
    flags: list[str]


@dataclass(frozen=True)
class ScreenRules:
    max_single_holder_pct: float = 5.0
    max_cluster_pct: float = 10.0
    min_median_position_sol: float = 3.0
    max_fresh_wallet_share: float = 0.4
    fresh_wallet_days: float = 3.0
    min_volume_to_mcap: float = 0.5
    min_fee_sol_per_15k_mcap: float = 0.5
    top_holders_considered: int = 20
    stair_step_min_bars: int = 12
    stair_step_max_pullback: float = 0.01


def screen(token: TokenSnapshot, rules: ScreenRules = ScreenRules()) -> ScreenResult:
    flags: list[str] = []
    holders = [h for h in token.holders if not h.is_liquidity_pool]
    top = sorted(holders, key=lambda h: h.pct_supply, reverse=True)[: rules.top_holders_considered]

    if token.mint_authority_revoked is False:
        flags.append("mint authority not revoked: supply can be inflated")
    if token.freeze_authority_revoked is False:
        flags.append("freeze authority not revoked: your tokens can be frozen")

    if top and top[0].pct_supply > rules.max_single_holder_pct:
        flags.append(f"single wallet holds {top[0].pct_supply:.1f}% (> {rules.max_single_holder_pct}%)")

    clusters: dict[str, float] = {}
    for h in holders:
        if h.cluster_id:
            clusters[h.cluster_id] = clusters.get(h.cluster_id, 0.0) + h.pct_supply
    worst_cluster = max(clusters.values(), default=0.0)
    if worst_cluster > rules.max_cluster_pct:
        flags.append(f"linked wallets control {worst_cluster:.1f}% (> {rules.max_cluster_pct}%)")

    sized = sorted(h.position_sol for h in top if h.position_sol > 0)
    if sized:
        median = sized[len(sized) // 2]
        if median < rules.min_median_position_sol:
            flags.append(f"top holders' median position is {median:.2f} SOL: likely fake distribution")
        if len(sized) >= 5 and max(sized) - min(sized) <= 0.1 * max(sized):
            flags.append("top holder positions are near-identical in size: likely bundled")

    aged = [h for h in top if h.wallet_age_days is not None]
    if aged:
        fresh_share = sum(h.wallet_age_days < rules.fresh_wallet_days for h in aged) / len(aged)
        if fresh_share > rules.max_fresh_wallet_share:
            flags.append(f"{fresh_share:.0%} of top holders are wallets under {rules.fresh_wallet_days:g} days old")

    if token.market_cap_usd > 0:
        ratio = token.volume_24h_usd / token.market_cap_usd
        if ratio < rules.min_volume_to_mcap:
            flags.append(f"24h volume is {ratio:.2f}x market cap: too little real activity")
        min_fees = rules.min_fee_sol_per_15k_mcap * token.market_cap_usd / 15_000
        if token.fees_generated_sol < min_fees:
            flags.append(f"fees generated {token.fees_generated_sol:.2f} SOL (< {min_fees:.2f} expected)")

    if _is_stair_step(token.closes, rules):
        flags.append("stair-step price action with no pullbacks: likely manufactured volume")

    return ScreenResult(symbol=token.symbol, passed=not flags, flags=flags)


def _is_stair_step(closes: list[float], rules: ScreenRules) -> bool:
    if len(closes) < rules.stair_step_min_bars:
        return False
    recent = closes[-rules.stair_step_min_bars :]
    for prev, cur in zip(recent, recent[1:]):
        if prev > 0 and (cur - prev) / prev < -rules.stair_step_max_pullback:
            return False
    return recent[-1] > recent[0]
