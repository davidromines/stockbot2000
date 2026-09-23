"""
Grid-DCA on crypto, scored against the null. Phase 12, item 41.

THE STRATEGY
------------
The genome described by the SETS repository and recorded in the research
library as `social:sets_machine`: a long-only grid that buys at fixed spacing
below an entry reference, averages down across levels, takes profit at a
percentage above the average fill, and stops out at a percentage below the
deepest level.

Eight genes: lookback, entry threshold, grid levels, spacing, size multiplier,
take-profit, stop, and max hold.

WHY THIS IS MEASURED BEFORE ANY FUND HOLDS IT
-----------------------------------------------
Grid-DCA is structurally long-biased: it buys dips and sells rallies, so in a
rising market it produces a stream of small wins regardless of whether it has
any edge. That is precisely the shape that scoring against zero rewards — and
it is why the crypto null exists. **A grid that returns +3% while its symbol's
null returns +4% has lost money relative to doing nothing at random.**

The SETS author says as much in his own VALIDATION.md: *"It is not evidence of
a durable edge, and on that window buy & hold returned more."*

So every result here carries three numbers, not one: the raw return, the null
for that symbol and holding period, and the excess. Only the third means
anything.

FILLS
-----
Entry at the NEXT bar's open after the signal bar, exits likewise, matching
`crypto_data`'s recorded convention and the null's. A grid measured on one
convention against a null measured on another is a rigged comparison.

COSTS ARE THE WHOLE STORY HERE
--------------------------------
The first run of this module charged nothing and reported 10 of 10 symbols
beating their null with win rates of 89-93%. That is the shape of every
artifact this project has already caught, and the cause was immediate: a grid
makes MULTIPLE fills per trade — one per level entered, plus the exit — and
Coinbase's retail taker fee is 0.60% per fill.

A three-level grid that fills two levels and exits pays three taker fees,
roughly 1.8% round trip, against a take-profit of 2.0%. The strategy's entire
gross edge is inside its own fee bill, which is the general reason grid and
martingale systems look wonderful before costs and are unrunnable after.

Fees are charged per FILL, not per trade, because that is how an exchange
charges them and averaging them per trade would understate a deep grid by the
number of levels it entered.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import itertools
import logging

import numpy as np

import crypto_benchmark as cb
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cgrid")

DEFAULT = {"lookback": 24, "entry_drop": 0.02, "levels": 3, "spacing": 0.015,
           "size_mult": 1.5, "take_profit": 0.02, "stop": 0.12, "max_hold": 168}

# Coinbase Advanced Trade retail taker fee at the volume tier a $100 account
# occupies. Maker is lower, but a grid that must fill to work cannot assume it
# posts — assuming maker fees is assuming the fills you wanted, which is the
# same optimism as filling at the close that produced the signal.
TAKER_FEE = 0.006


def _bars(conn, symbol: str, interval: str):
    rows = conn.execute(
        "SELECT open_time, open, high, low, close FROM crypto_prices "
        "WHERE symbol=? AND interval=? ORDER BY open_time",
        (symbol, interval)).fetchall()
    if not rows:
        return None
    a = np.array([[r[1], r[2], r[3], r[4]] for r in rows], dtype="float64")
    return {"open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3],
            "n": len(rows)}


def run(conn, symbol: str, interval: str, g: dict | None = None) -> dict:
    """
    One grid genome over one symbol's full history.

    Sequential rather than vectorised: a grid's state — which levels have
    filled, the running average — depends on its own history, so there is no
    honest vectorised form. The cost is speed on a few thousand bars, which
    does not matter for ten symbols.
    """
    g = {**DEFAULT, **(g or {})}
    b = _bars(conn, symbol, interval)
    if not b or b["n"] < g["lookback"] + g["max_hold"] + 4:
        return {"symbol": symbol, "trades": 0,
                "note": "not enough bars for this genome"}

    o, hi, lo, c = b["open"], b["high"], b["low"], b["close"]
    n = b["n"]
    # Rolling reference, causal: the mean of the PRIOR `lookback` closes,
    # never including the current bar.
    ref = np.full(n, np.nan)
    if n > g["lookback"]:
        cs = np.cumsum(np.insert(c, 0, 0.0))
        ref[g["lookback"]:] = (cs[g["lookback"]:-1] - cs[:-g["lookback"] - 1]) / g["lookback"]

    trades, i = [], g["lookback"] + 1
    while i < n - 2:
        if not np.isfinite(ref[i]) or c[i] > ref[i] * (1 - g["entry_drop"]):
            i += 1
            continue
        # Signal on bar i's close -> first fill at bar i+1's open.
        entry_i = i + 1
        base = o[entry_i]
        if not np.isfinite(base) or base <= 0:
            i += 1
            continue

        filled = [(base, 1.0)]
        size = 1.0
        exit_i, exit_px, reason = None, None, "hold_expiry"
        deepest = base * (1 - g["spacing"] * g["levels"])

        for j in range(entry_i + 1, min(entry_i + g["max_hold"], n)):
            # Deeper levels fill on the way down, at the level price.
            nxt = len(filled)
            if nxt < g["levels"]:
                lvl = base * (1 - g["spacing"] * nxt)
                if lo[j] <= lvl:
                    size *= g["size_mult"]
                    filled.append((lvl, size))
            avg = sum(p * s for p, s in filled) / sum(s for _, s in filled)
            if lo[j] <= deepest * (1 - g["stop"]):
                exit_i, exit_px, reason = j, deepest * (1 - g["stop"]), "stop"
                break
            if hi[j] >= avg * (1 + g["take_profit"]):
                exit_i, exit_px, reason = j, avg * (1 + g["take_profit"]), "take_profit"
                break
        if exit_i is None:
            exit_i = min(entry_i + g["max_hold"], n - 1)
            exit_px = o[exit_i]
        avg = sum(p * s for p, s in filled) / sum(s for _, s in filled)
        gross = (exit_px - avg) / avg * 100.0
        # One fee per entry fill, plus one on the exit.
        n_fills = len(filled) + 1
        fee_pct = n_fills * TAKER_FEE * 100.0
        trades.append({"entry_i": entry_i, "exit_i": exit_i,
                       "gross_pct": gross, "fees_pct": fee_pct,
                       "ret_pct": gross - fee_pct,
                       "bars": exit_i - entry_i, "reason": reason,
                       "fills": n_fills, "levels": len(filled)})
        i = exit_i + 1

    if not trades:
        return {"symbol": symbol, "trades": 0, "note": "no entries triggered"}

    r = np.array([t["ret_pct"] for t in trades])
    gross = np.array([t["gross_pct"] for t in trades])
    fees = np.array([t["fees_pct"] for t in trades])
    holds = np.array([t["bars"] for t in trades])
    mean_hold = int(round(holds.mean()))
    # Charge the null of THIS symbol at the nearest measured holding period.
    grid_holds = sorted(cb.HOLDS)
    nearest = min(grid_holds, key=lambda h: abs(h - mean_hold))
    null = cb.null_for(conn, symbol, interval, nearest)
    return {
        "symbol": symbol, "interval": interval, "genome": g,
        "trades": len(trades), "mean_pct": float(r.mean()),
        "mean_gross_pct": float(gross.mean()),
        "mean_fees_pct": float(fees.mean()),
        "mean_fills": float(np.mean([t["fills"] for t in trades])),
        "gross_win_rate": float((gross > 0).mean()),
        "median_pct": float(np.median(r)),
        "win_rate": float((r > 0).mean()), "total_pct": float(r.sum()),
        "mean_hold_bars": mean_hold, "null_hold_bars": nearest,
        "null_pct": null,
        # The only number that means anything.
        "excess_pct": (float(r.mean()) - null) if null is not None else None,
        "stops": sum(1 for t in trades if t["reason"] == "stop"),
        "take_profits": sum(1 for t in trades if t["reason"] == "take_profit"),
    }


def sweep(conn, interval: str = "1h", symbols=None) -> list:
    syms = symbols or [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM crypto_prices WHERE interval=? ORDER BY symbol",
        (interval,))]
    return [run(conn, s, interval) for s in syms]


def render(rows: list) -> str:
    ok = [r for r in rows if r.get("trades")]
    L = ["", "  GRID-DCA vs THE NULL", "  " + "-" * 82,
         f"  {'symbol':<12}{'trades':>7}{'gross%':>9}{'fees%':>8}{'net%':>9}"
         f"{'null%':>8}{'excess%':>10}{'win':>6}"]
    for r in sorted(ok, key=lambda x: -(x["excess_pct"] or -9e9)):
        ex = "—" if r["excess_pct"] is None else f"{r['excess_pct']:+.3f}"
        nu = "—" if r["null_pct"] is None else f"{r['null_pct']:+.3f}"
        L.append(f"  {r['symbol']:<12}{r['trades']:>7}{r['mean_gross_pct']:>9.3f}"
                 f"{r['mean_fees_pct']:>8.3f}{r['mean_pct']:>9.3f}"
                 f"{nu:>8}{ex:>10}{r['win_rate']:>6.0%}")
    for r in rows:
        if not r.get("trades"):
            L.append(f"  {r['symbol']:<12}{'—':>8}   {r.get('note','')}")
    beat = [r for r in ok if (r["excess_pct"] or 0) > 0]
    gross_beat = [r for r in ok
                  if (r["mean_gross_pct"] - (r["null_pct"] or 0)) > 0]
    L += ["  " + "-" * 82, "",
          f"  {len(beat)} of {len(ok)} symbols beat their own null AFTER fees.",
          f"  {len(gross_beat)} of {len(ok)} did before fees.", ""]
    if ok:
        avg_fee = sum(r["mean_fees_pct"] for r in ok) / len(ok)
        avg_fills = sum(r["mean_fills"] for r in ok) / len(ok)
        L += [f"  Fees average {avg_fee:.2f}% per trade across {avg_fills:.1f}",
              f"  fills at {TAKER_FEE:.2%} each, against a {DEFAULT['take_profit']:.0%}",
              "  take-profit. A grid's entire gross edge sits inside its own fee",
              "  bill, which is why grid and martingale systems look wonderful",
              "  before costs and are unrunnable after.", "",
              "  Grid-DCA is also structurally long-biased: it buys dips and",
              "  sells rallies, so in a rising market it prints small wins",
              "  whether or not it has an edge.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--symbols", nargs="*")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    print(render(sweep(conn, a.interval, a.symbols)))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
