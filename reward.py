"""
Turns a simulated trade record into a single fitness number. Phase 08.

The search maximises whatever this returns, so every term here is a statement
about what counts as a good strategy — and every omission is a loophole the
search will find. Raw profit maximisation reliably discovers strategies that make
enormous concentrated bets; that was settled at design time and has not changed.

What has changed is that **net P&L in dollars is now reported alongside fitness
and is the headline number**. Fitness shapes the search; money decides whether
the result was worth having. A strategy with a beautiful Sharpe that loses money
is not interesting.

Five terms, each closing a specific hole:

- **Risk-adjusted return, net of costs.** Returns divided by their own volatility,
  with trading costs already deducted inside the simulator. High-turnover
  strategies pay for their turnover before they are scored.
- **Drawdown penalty.** A strategy that went 60% underwater keeps 40% of its
  score. Deep drawdowns are what make people abandon a system mid-run.
- **Small-sample shrinkage.** Four trades and a perfect record is luck. Scores
  with few trades are pulled toward zero.
- **Complexity penalty.** New with rule synthesis. Without it, trees grow until
  they memorise history — the standard failure of genetic programming on noisy
  data, and this data is very noisy.
- **Losing strategies score zero.** Not a negative number: zero. A strategy that
  loses money should not be ranked above another that loses more, because
  "less bad" is not a gradient worth climbing when the goal is making money.
- **Effect size.** Sharpe is a ratio and says nothing about how much money was
  at stake. Without this term the search's leader was a rule earning **$1 across
  25 trades** at a Sharpe of 6.92 — tiny, steady, and worthless. It outranked
  every real candidate and drew the whole population after it. The scale term
  ties the score to the excess the gate will demand later, so the search climbs
  toward strategies that could actually pass rather than away from them.

**Scored against the null, not against zero.** This is the correction that matters
most. Buying at random and holding five days was profitable in every window this
project tests on, because the market rose — so scoring against zero rewarded being
long in a bull market rather than picking well, and 52% of random strategies
passed the validation gate as a result. Fitness now measures **excess return over
what a random entry earns in the same window**, net of costs. A strategy that beats
zero has demonstrated nothing; one that beats the null has demonstrated selection.

**And the null is matched to the stocks the strategy bought, not just to the
window.** Charged a single market-wide null, the search's best answer was
`sma_200 < 8` — a price filter dressed as a strategy, and 58 of its 66 validation
survivors were the same rule with a different constant. Cheap stocks earn and
behave differently from expensive ones, and they are where survivorship bias is
worst, so "beat the market" was a gift to anything that simply bought cheap. Each
trade is now charged the null of its own price band; the rule has to beat the
cheap stocks it chose among.
"""
import runtime  # noqa: F401  — must precede numpy/pandas

import numpy as np

DEFAULTS = {
    "shrinkage_trades": 30,     # trade count at which shrinkage reaches ~0.7
    "complexity_free": 10,      # nodes allowed before the penalty starts
    "complexity_penalty": 0.02, # divides fitness as nodes grow beyond the free allowance
    "min_trades": 10,           # below this a result is not evidence of anything
    # Excess at which the scale term reaches 0.5. Set from the gate the strategy
    # must eventually clear, which control.py calibrates against noise — so this
    # is not a free parameter, and moving the gate moves this with it.
    "scale_half_usd": 900.0,
}


def params_from_config(config: dict) -> dict:
    """
    Reward parameters derived from the app config.

    Exists so the scale term cannot drift away from the gate it is meant to
    track. `control.py` calibrates `lab.gates.min_excess_pnl_usd` against noise;
    reading it here means recalibrating the gate automatically re-points the
    search at it, instead of leaving two numbers to be kept in step by hand.
    """
    gate = (config.get("lab", {}).get("gates", {}) or {}).get("min_excess_pnl_usd")
    p = dict(config.get("lab", {}).get("reward", {}) or {})
    if gate:
        p.setdefault("scale_half_usd", float(gate))
    return p


def sharpe_per_trade(pnl: np.ndarray) -> float:
    """
    Sharpe in per-trade units: mean over standard deviation, unannualised.

    The deflated Sharpe correction needs this, not the annualised figure. Its
    formula compares an observed Sharpe against the expected maximum of many
    noisy Sharpe *estimates*, and both have to be measured over the same
    observations. Feeding it an annualised number while telling it the sample
    size is a trade count compares two different quantities.
    """
    if pnl.size < 2:
        return 0.0
    sd = float(pnl.std(ddof=1))
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(pnl.mean() / sd)


def sharpe(pnl: np.ndarray, periods_per_year: float = 252.0,
           avg_hold_days: float = 5.0) -> float:
    """
    Annualised Sharpe of the per-trade P&L series.

    Scaled by trades per year rather than days, since the series is per-trade and
    positions overlap. Approximate by construction — it ranks candidates, it is
    not a figure to quote.
    """
    if pnl.size < 2:
        return 0.0
    sd = float(pnl.std(ddof=1))
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    trades_per_year = periods_per_year / max(avg_hold_days, 1.0)
    return float(pnl.mean() / sd * np.sqrt(trades_per_year))


def max_drawdown(pnl: np.ndarray, capital_usd: float) -> float:
    """
    Worst peak-to-trough fall of the equity curve, as a fraction of capital.

    Measured against an equity curve that starts at `capital_usd`, not against
    cumulative profit. Drawdown relative to cumulative profit is meaningless
    early in a series — the first losing trade after a small gain shows as a
    near-total drawdown, which would penalise every strategy almost equally and
    make the term useless.
    """
    if pnl.size == 0 or capital_usd <= 0:
        return 0.0
    equity = capital_usd + np.cumsum(pnl)
    peak = np.maximum.accumulate(np.maximum(equity, capital_usd))
    dd = 1 - equity / peak
    return float(np.clip(np.nanmax(dd), 0.0, 1.0))


def fitness(result: dict, complexity: int, capital_usd: float = 100.0,
            benchmark_net_pct: float = 0.0, position_size_usd: float = 10.0,
            benchmark_curve: dict | None = None, cfg: dict | None = None,
            benchmark_surface: dict | None = None) -> dict:
    """
    Score one simulated strategy. Returns the fitness and every component.

    Components are returned rather than folded away so a winning genome can be
    interrogated later: knowing a strategy scored well *because* of shrinkage
    rather than Sharpe is the difference between trusting it and not.
    """
    p = {**DEFAULTS, **(cfg or {})}
    pnl = np.asarray(result.get("pnl_series", []), dtype="float64")
    n = int(result.get("n_trades", 0))
    net = float(result.get("net_pnl_usd", 0.0))

    if n < p["min_trades"]:
        return _zero(net, n, "too few trades")

    # Excess over the null, charged at the strategy's ACTUAL holding period.
    # A fixed-horizon null lets a strategy manufacture excess by simply holding
    # longer: the null is +0.066% over 5 days and +2.128% over 40, so scoring a
    # 40-day strategy against the 5-day figure hands it 32x more credit than it
    # earned. The search found that loophole immediately.
    #
    # The price dimension is charged the same way: each trade against the null of
    # the band it entered in, averaged over the trades actually taken. A strategy
    # whose entries are all sub-$10 is measured against sub-$10 stocks.
    hold = float(result.get("avg_hold_days", 5.0) or 5.0)
    null_pct = None
    if benchmark_surface:
        from benchmark import null_vector
        null_pct = null_vector(benchmark_surface, result.get("entry_price"), hold)
        benchmark_net_pct = float(null_pct.mean()) if null_pct.size else 0.0
    elif benchmark_curve:
        from benchmark import null_for_hold
        benchmark_net_pct = null_for_hold(benchmark_curve, hold)
    benchmark_usd = position_size_usd * (benchmark_net_pct / 100.0) * n
    excess = net - benchmark_usd
    if null_pct is not None and null_pct.size == pnl.size:
        excess_pnl = pnl - position_size_usd * (null_pct / 100.0)
    else:
        excess_pnl = pnl - position_size_usd * (benchmark_net_pct / 100.0)

    if net <= 0:
        # Deliberately flat rather than negative: "loses less" is not a gradient
        # worth climbing when the objective is making money.
        return _zero(net, n, "unprofitable", excess, benchmark_net_pct, benchmark_usd, hold)
    if excess <= 0:
        # Profitable but no better than buying at random. This is the case that
        # used to score well and should not.
        return _zero(net, n, "no better than the null", excess,
                     benchmark_net_pct, benchmark_usd, hold)

    sr = sharpe(excess_pnl, avg_hold_days=result.get("avg_hold_days", 5.0))
    dd = max_drawdown(excess_pnl, capital_usd)
    shrink = np.sqrt(n / (n + p["shrinkage_trades"]))

    # Multiplicative, not subtractive. A fixed subtraction has to be calibrated
    # against the scale of Sharpe, and gets it wrong the moment that scale moves —
    # the first version wiped out every candidate because a 0.1 penalty swamped
    # Sharpe values around 0.1. A multiplier is scale-free.
    # Named `excess_nodes`, not `excess`. Reusing the latter silently clobbered
    # the excess P&L computed above, so every result reported its node overage as
    # its excess dollars — which read as 0 for simple trees and made the gates
    # compare node counts against a dollar threshold.
    excess_nodes = max(0, complexity - p["complexity_free"])
    penalty = 1.0 / (1.0 + p["complexity_penalty"] * excess_nodes)

    # Saturating rather than linear: above the gate, more money should not keep
    # buying rank indefinitely, or the search drifts back toward concentrated
    # bets — the failure the risk-adjusted reward exists to prevent. Half weight
    # at the gate, approaching full weight well above it.
    half = float(p["scale_half_usd"]) or 1.0
    scale = excess / (excess + half)

    score = max(0.0, sr * (1 - dd) * shrink * penalty * scale)
    return {
        "fitness": float(score),
        "net_pnl_usd": net,
        "excess_pnl_usd": float(excess),
        "benchmark_pnl_usd": float(benchmark_usd),
        "benchmark_net_pct": float(benchmark_net_pct),
        "avg_hold_days": hold,
        "n_trades": n,
        "sharpe": float(sr),
        "sharpe_per_trade": sharpe_per_trade(excess_pnl),
        "max_drawdown": float(dd),
        "shrinkage": float(shrink),
        "complexity_multiplier": float(penalty),
        "scale_multiplier": float(scale),
        "avg_net_return_per_trade": float(pnl.mean() / capital_usd * n) if n else 0.0,
        "verdict": "beats the null",
    }


def _zero(net: float, n: int, why: str, excess: float = 0.0,
          benchmark_net_pct: float = 0.0, benchmark_usd: float = 0.0,
          hold: float = 0.0) -> dict:
    """
    A scored-zero result, carrying the benchmark that produced it.

    The benchmark fields used to be hardcoded to zero here, which made a
    rejection unreadable: a strategy that failed *because* it was charged a 9%
    null reported having been charged nothing. The fitness is zero; the reason
    should still be legible.
    """
    return {"fitness": 0.0, "net_pnl_usd": net, "excess_pnl_usd": float(excess),
            "benchmark_pnl_usd": float(benchmark_usd),
            "benchmark_net_pct": float(benchmark_net_pct),
            "avg_hold_days": float(hold), "n_trades": n, "sharpe": 0.0,
            "sharpe_per_trade": 0.0,
            "max_drawdown": 0.0, "shrinkage": 0.0, "complexity_multiplier": 0.0,
            "scale_multiplier": 0.0,
            "avg_net_return_per_trade": 0.0, "verdict": why}
