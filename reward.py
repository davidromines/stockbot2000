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

**Scored against the null, not against zero.** This is the correction that matters
most. Buying at random and holding five days was profitable in every window this
project tests on, because the market rose — so scoring against zero rewarded being
long in a bull market rather than picking well, and 52% of random strategies
passed the validation gate as a result. Fitness now measures **excess return over
what a random entry earns in the same window**, net of costs. A strategy that beats
zero has demonstrated nothing; one that beats the null has demonstrated selection.
"""
import runtime  # noqa: F401  — must precede numpy/pandas

import numpy as np

DEFAULTS = {
    "shrinkage_trades": 30,     # trade count at which shrinkage reaches ~0.7
    "complexity_free": 10,      # nodes allowed before the penalty starts
    "complexity_penalty": 0.02, # divides fitness as nodes grow beyond the free allowance
    "min_trades": 10,           # below this a result is not evidence of anything
}


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
            cfg: dict | None = None) -> dict:
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

    # Excess over the null. `benchmark_net_pct` is what a random entry earned per
    # trade in this window, net of costs; charging it per trade converts a raw
    # P&L into "did this select better than chance".
    benchmark_usd = position_size_usd * (benchmark_net_pct / 100.0) * n
    excess = net - benchmark_usd
    excess_pnl = pnl - position_size_usd * (benchmark_net_pct / 100.0)

    if net <= 0:
        # Deliberately flat rather than negative: "loses less" is not a gradient
        # worth climbing when the objective is making money.
        return _zero(net, n, "unprofitable", excess)
    if excess <= 0:
        # Profitable but no better than buying at random. This is the case that
        # used to score well and should not.
        return _zero(net, n, "no better than the null", excess)

    sr = sharpe(excess_pnl, avg_hold_days=result.get("avg_hold_days", 5.0))
    dd = max_drawdown(excess_pnl, capital_usd)
    shrink = np.sqrt(n / (n + p["shrinkage_trades"]))

    # Multiplicative, not subtractive. A fixed subtraction has to be calibrated
    # against the scale of Sharpe, and gets it wrong the moment that scale moves —
    # the first version wiped out every candidate because a 0.1 penalty swamped
    # Sharpe values around 0.1. A multiplier is scale-free.
    excess = max(0, complexity - p["complexity_free"])
    penalty = 1.0 / (1.0 + p["complexity_penalty"] * excess)

    score = max(0.0, sr * (1 - dd) * shrink * penalty)
    return {
        "fitness": float(score),
        "net_pnl_usd": net,
        "excess_pnl_usd": float(excess),
        "benchmark_pnl_usd": float(benchmark_usd),
        "n_trades": n,
        "sharpe": float(sr),
        "sharpe_per_trade": sharpe_per_trade(excess_pnl),
        "max_drawdown": float(dd),
        "shrinkage": float(shrink),
        "complexity_multiplier": float(penalty),
        "avg_net_return_per_trade": float(pnl.mean() / capital_usd * n) if n else 0.0,
        "verdict": "beats the null",
    }


def _zero(net: float, n: int, why: str, excess: float = 0.0) -> dict:
    return {"fitness": 0.0, "net_pnl_usd": net, "excess_pnl_usd": float(excess),
            "benchmark_pnl_usd": 0.0, "n_trades": n, "sharpe": 0.0,
            "sharpe_per_trade": 0.0,
            "max_drawdown": 0.0, "shrinkage": 0.0, "complexity_multiplier": 0.0,
            "avg_net_return_per_trade": 0.0, "verdict": why}
