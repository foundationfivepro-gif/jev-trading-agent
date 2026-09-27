# Jev in the trading agent

[TypeSafe Jev](https://www.langchain.com/blog/building-a-harness-with-jev) is a
"System One" evaluation model: it takes a state and typed questions and returns
calibrated answers. It is reached through the Vercel AI Gateway as
`typesafe-ai/jev`, using the runtime in
[`jev-agent`](https://github.com/foundationfivepro-gif/jev-agent) (`core.decide`,
`harness.check_action`), which validates every answer before it is used.

## What it can do (measured from this repo's cloud session)

| Question type | Returns | Example here |
|---|---|---|
| `Noul` | probability that a statement is true | "Does the promo ask for wallet action?" gave 0.97 |
| `Choice` | the chosen option plus a probability per option | promo category: `presale_pitch` at 1.00 |
| `Score` | a position on an **ordered list** of levels | scam risk 2.00 on low/medium/high |

- **Several questions share one call.** Three questions took 760 ms and 540 input tokens, about $0.00002.
- **Price.** $0.042 per million input tokens; output is free. Limit: 32k tokens of state plus the longest question.
- **Type safety.** The SDK rejects malformed questions before any network call. Passing a Score a dict of levels instead of a list fails locally.

## Where it's used, and where it isn't

| Decision | Who decides | Why |
|---|---|---|
| Leverage, per-coin cap, universe, failed rug screen | **code** (`hard_rules`) | Known facts. Asked to judge a buy of a token that had failed the screen, Jev said `review` at 0.39 confidence, not `block`. |
| Does this order match the written trading policy? | **Jev** (`review_order`) | Plain-English policy with near-match judgement; block always wins |
| Does a token's promo text read as a scam? | **Jev** (`promo_risk`) | Free text that code can't judge |
| Backtest signals | **code** | Must stay deterministic and free to re-run |

The gate fails closed: if Jev is unreachable, errors or is unsure, the order is
marked `review`, and a person decides.

## Setup

1. Clone `jev-agent` next to this repo (or set `JEV_AGENT_DIR`) and run `pip install -r requirements.txt` there.
2. Make `AI_GATEWAY_API_KEY` available. In a claude.ai/code cloud environment, add it as an API credential for `ai-gateway.vercel.sh` (see the `jev-agent` README, "Cloud sessions").
3. `python -m trading_agent paper` now adds `verdict`, `verdict_source` and `verdict_reason` to each order.
   `python -m trading_agent screen file.json` judges each token's `description` text.
   `--no-jev` skips Jev on both; the hard rules still apply.
