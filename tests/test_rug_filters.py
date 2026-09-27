from trading_agent.screening.rug_filters import Holder, TokenSnapshot, screen


def healthy_holders():
    return [Holder("lp", 20.0, is_liquidity_pool=True)] + [
        Holder(f"w{i}", 4.0 - i * 0.15, position_sol=5 + i * 3, wallet_age_days=90) for i in range(20)
    ]


def token(**overrides):
    base = dict(
        symbol="GOOD",
        market_cap_usd=150_000,
        volume_24h_usd=300_000,
        fees_generated_sol=10,
        holders=healthy_holders(),
        closes=[1, 1.1, 1.05, 1.2, 1.1, 1.3, 1.25, 1.4, 1.3, 1.5, 1.45, 1.6],
        mint_authority_revoked=True,
        freeze_authority_revoked=True,
    )
    base.update(overrides)
    return TokenSnapshot(**base)


def test_healthy_token_passes():
    res = screen(token())
    assert res.passed, res.flags


def test_liquidity_pool_is_ignored_for_concentration():
    assert screen(token()).passed  # LP holds 20% but is excluded


def test_whale_flagged():
    holders = healthy_holders() + [Holder("whale", 12.0, position_sol=500, wallet_age_days=90)]
    assert any("single wallet" in f for f in screen(token(holders=holders)).flags)


def test_linked_wallet_cluster_flagged():
    holders = healthy_holders()
    for h in holders[1:5]:
        h.cluster_id = "bundle"
    assert any("linked wallets" in f for f in screen(token(holders=holders)).flags)


def test_fresh_wallets_and_tiny_positions_flagged():
    holders = [Holder(f"f{i}", 2.0, position_sol=2.0, wallet_age_days=0.5) for i in range(20)]
    flags = screen(token(holders=holders)).flags
    assert any("wallets under" in f for f in flags)
    assert any("median position" in f for f in flags)
    assert any("near-identical" in f for f in flags)


def test_low_volume_and_fees_flagged():
    flags = screen(token(volume_24h_usd=10_000, fees_generated_sol=0.1)).flags
    assert any("volume" in f for f in flags)
    assert any("fees generated" in f for f in flags)


def test_stair_step_flagged():
    flags = screen(token(closes=[1 + 0.05 * i for i in range(15)])).flags
    assert any("stair-step" in f for f in flags)


def test_unrevoked_authorities_flagged():
    flags = screen(token(mint_authority_revoked=False, freeze_authority_revoked=False)).flags
    assert len([f for f in flags if "authority" in f]) == 2
