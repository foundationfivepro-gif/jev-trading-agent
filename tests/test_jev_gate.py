from types import SimpleNamespace

from trading_agent.jev_gate import OrderVerdict, describe, hard_rules, promo_risk, review_order


def order(**kw):
    base = dict(symbol="BTC-USD", side="buy", units=0.01, reason="entry", notional=800, weight=0.08,
                max_weight=0.25, risk_per_trade=0.01, gross_exposure_after=0.4, universe=("BTC-USD",))
    base.update(kw)
    return base


class FakeHarness:
    def __init__(self, verdict="allow", raises=False):
        self.verdict, self.raises, self.calls = verdict, raises, []

    def check_action(self, action, allow, block):
        self.calls.append(action)
        if self.raises:
            raise RuntimeError("gateway down")
        return SimpleNamespace(verdict=self.verdict, reason="fake", confidence=0.95)


def test_hard_rules_block_before_jev_is_asked():
    h = FakeHarness("allow")
    for bad in (order(gross_exposure_after=1.5), order(symbol="PEPE-USD"), order(screen_passed=False), order(weight=0.4)):
        v = review_order(bad, jev=(None, h))
        assert v.verdict == "block" and v.source == "rule"
    assert h.calls == []


def test_sells_are_not_blocked_by_buy_rules():
    assert hard_rules(order(side="sell", symbol="PEPE-USD", weight=0.9)) is None


def test_jev_verdict_is_used_when_rules_pass():
    h = FakeHarness("block")
    v = review_order(order(), jev=(None, h))
    assert (v.verdict, v.source) == ("block", "jev")
    assert "no leverage" in h.calls[0]


def test_fails_closed_when_jev_errors():
    v = review_order(order(), jev=(None, FakeHarness(raises=True)))
    assert (v.verdict, v.source) == ("review", "unavailable")


def test_describe_mentions_size_and_trigger():
    text = describe(order())
    assert "BTC-USD" in text and "8.0% of equity" in text and "entry" in text


class FakeCore:
    UNTRUSTED = ""

    def __init__(self, score, wallet):
        self.answers = {"scam_risk": score, "wallet_ask": wallet}

    @staticmethod
    def Score(**kw):
        return kw

    @staticmethod
    def Noul(**kw):
        return kw

    def decide(self, state, questions):
        assert set(questions) == {"scam_risk", "wallet_ask"}
        return self.answers


def test_promo_risk_flags_scammy_text():
    res = promo_risk("presale 2x guaranteed", jev=(FakeCore(2.0, 0.97), None))
    assert len(res["flags"]) == 2


def test_promo_risk_passes_ordinary_text():
    assert promo_risk("cat pics", jev=(FakeCore(0.1, 0.02), None))["flags"] == []
