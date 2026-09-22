"""
Correlation, and the top-five-ELIGIBLE rule. Phase 7, items 16 and 18.

THE CENTRAL ARCHITECTURAL RULE
-------------------------------
Phase 7 states it plainly: the live roster is

    TOP FIVE ELIGIBLE STRATEGIES AFTER RISK AND CORRELATION CONSTRAINTS

and *never* simply the five highest raw returns. The reason is visible in this
project's own arena: six of the sixteen paper funds are the same entry rule
(`pct_change(sma_200,3) > 0.02`) at different stop widths. Rank them on return
and the roster fills with six copies of one bet, sized as though it were six.
A portfolio of near-identical strategies has the concentration of one position
and the appearance of diversification, which is worse than holding one openly.

So selection is greedy with a correlation veto: take the best eligible
strategy, then refuse anything too correlated with what is already chosen. A
strategy can be excellent and still be excluded for being a duplicate of
something already on the roster. That is the rule working, not failing.

NOTHING HERE PROMOTES ANYTHING
-------------------------------
Item 18 is explicit: *no promotion to live yet*. This module computes who
*would* be eligible. It performs no lifecycle transition, and it must never
import `execution` or `broker` — the league is not permitted to reach the
broker. `propose()` returns a list; acting on it is a separate, later, human
decision.

CORRELATION ON SEVEN OBSERVATIONS IS NOT CORRELATION
------------------------------------------------------
The funds overlap on as few as 2 equity marks. A correlation from 2 points is
exactly +/-1 by construction and means nothing. Pairs with fewer than
`league.min_corr_overlap` shared marks are reported as UNKNOWN, and an unknown
correlation **blocks** rather than permits — the same fail-closed rule used for
unknown market cap and unknown liquidity, where a missing measurement is never
treated as an average one. Today that means almost nothing is eligible, which is
the honest state of a league whose oldest member has three weeks of history.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np

import league as lg
import scoreboard as sb
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("eligibility")

UNKNOWN = None


def _series(conn, kind: str, ref: str) -> dict:
    dates, eq = sb._equity_series(conn, kind, ref)
    if eq.size < 2:
        return {}
    rets = np.diff(eq) / np.where(eq[:-1] > 0, eq[:-1], 1.0)
    return dict(zip(dates[1:], rets))


def correlation(a: dict, b: dict, min_overlap: int) -> tuple:
    """
    (correlation, n_overlap). Returns (None, n) when the overlap is too thin.

    None is not zero. A pair sharing two marks correlates at exactly +/-1 by
    construction, and reporting that as a measurement would let two identical
    strategies onto the roster on the strength of an artifact.
    """
    shared = sorted(set(a) & set(b))
    n = len(shared)
    if n < min_overlap:
        return UNKNOWN, n
    x = np.array([a[d] for d in shared])
    y = np.array([b[d] for d in shared])
    if x.std() == 0 or y.std() == 0:
        return UNKNOWN, n
    return float(np.corrcoef(x, y)[0, 1]), n


def matrix(conn, cfg: dict) -> tuple:
    """Pairwise correlations across every non-retired strategy."""
    lcfg = cfg.get("league") or {}
    min_overlap = int(lcfg.get("min_corr_overlap", 30))
    rows = [r for r in lg.roster(conn) if r["state"] != lg.RETIRED]
    series = {r["strategy_key"]: _series(conn, r["source_kind"], r["source_ref"])
              for r in rows}
    out = {}
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            c, n = correlation(series[a["strategy_key"]], series[b["strategy_key"]],
                               min_overlap)
            out[(a["strategy_key"], b["strategy_key"])] = (c, n)
    return rows, out


def _pair(m: dict, a: str, b: str):
    return m.get((a, b)) or m.get((b, a)) or (UNKNOWN, 0)


def assess(conn, cfg: dict, formula: str = sb.DEFAULT_FORMULA) -> list:
    """
    Every strategy with its eligibility verdict and the reasons against it.

    Reasons are accumulated rather than short-circuited: knowing a strategy
    fails on three counts is more useful than knowing it failed on the first one
    checked, and a single reason invites fixing that one thing to get through.
    """
    lcfg = cfg.get("league") or {}
    max_dd = float(lcfg.get("max_drawdown", 0.25))
    min_trades = int(lcfg.get("min_forward_trades", 20))
    floor = sb.min_marks(cfg)

    board = {r["strategy_key"]: r for r in sb.build(conn, cfg, formula)}
    out = []
    for key, r in board.items():
        if r["state"] == lg.RETIRED:
            continue
        m, reasons = r["metrics"], []
        if not r["rankable"]:
            reasons.append(f"not rankable: {r['why_not']}")
        if m["n_marks"] < floor:
            reasons.append(f"forward record too short ({m['n_marks']}/{floor} marks)")
        if (m.get("n_trades") or 0) < min_trades:
            reasons.append(f"too few forward trades ({m.get('n_trades') or 0}/{min_trades})")
        if (m.get("max_drawdown") or 0) > max_dd:
            reasons.append(f"drawdown {m['max_drawdown']:.1%} exceeds {max_dd:.0%}")
        if (m.get("cumulative_return") or 0) <= 0:
            reasons.append("forward return is not positive")
        out.append({**r, "eligible": not reasons, "reasons": reasons})
    return sorted(out, key=lambda x: (not x["eligible"], -(x["score"] or -9e9)))


def propose(conn, cfg: dict, formula: str = sb.DEFAULT_FORMULA) -> dict:
    """
    Who WOULD form the live roster. Proposes; never promotes.

    Greedy with a correlation veto, and the veto fails closed: a pair whose
    correlation is unknown is treated as too correlated. Admitting an unmeasured
    pair is how five copies of one bet reach a roster that believes it holds
    five strategies.
    """
    lcfg = cfg.get("league") or {}
    cap = float(lcfg.get("max_correlation", 0.7))
    size = int(lcfg.get("live_roster_size", 5))

    rows = assess(conn, cfg, formula)
    _, corr = matrix(conn, cfg)

    chosen, rejected = [], []
    for r in rows:
        if not r["eligible"]:
            continue
        if len(chosen) >= size:
            rejected.append({**r, "veto": "roster is full"})
            continue
        blocker = None
        for c in chosen:
            val, n = _pair(corr, r["strategy_key"], c["strategy_key"])
            if val is UNKNOWN:
                blocker = (f"correlation with {c['name']} is UNKNOWN "
                           f"({n} shared marks) — an unmeasured pair is treated "
                           f"as correlated, never as independent")
                break
            if val > cap:
                blocker = f"correlated {val:.2f} with {c['name']} (cap {cap:.2f})"
                break
        if blocker:
            rejected.append({**r, "veto": blocker})
        else:
            chosen.append(r)
    return {"roster": chosen, "vetoed": rejected, "assessed": rows,
            "size": size, "cap": cap}


def render(res: dict, cfg: dict) -> str:
    L = ["", "  PROPOSED LIVE ROSTER — a proposal, not a promotion",
         f"  top {res['size']} ELIGIBLE after risk and correlation, never the "
         f"top {res['size']} by return", "  " + "-" * 82]
    if res["roster"]:
        for i, r in enumerate(res["roster"], 1):
            m = r["metrics"]
            L.append(f"  {i}. {r['name'][:26]:<28}score {r['score']:>7.3f}"
                     f"   return {m['cumulative_return']:>7.2%}")
    else:
        L += ["  NOBODY IS ELIGIBLE, and that is the correct answer today.", ""]
        n_el = sum(1 for x in res["assessed"] if x["eligible"])
        L.append(f"  {n_el} of {len(res['assessed'])} strategies cleared the "
                 f"eligibility rules.")

    if res["vetoed"]:
        L += ["", "  VETOED BY CORRELATION", "  " + "-" * 82]
        for r in res["vetoed"]:
            L.append(f"  {r['name'][:26]:<28}{r['veto']}")

    L += ["", "  WHY EACH STRATEGY IS NOT ELIGIBLE", "  " + "-" * 82]
    for r in res["assessed"]:
        if r["eligible"]:
            L.append(f"  {r['name'][:26]:<28}ELIGIBLE")
            continue
        L.append(f"  {r['name'][:26]:<28}{r['reasons'][0]}")
        for extra in r["reasons"][1:]:
            L.append(f"  {'':<28}{extra}")
    L += ["", "  No strategy is promoted by this module. Phase 7 item 18 is",
          "  explicit that there is no promotion to live yet, and there is no",
          "  code path from here to the broker.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--formula", default=sb.DEFAULT_FORMULA)
    ap.add_argument("--correlations", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    lg.init(conn); sb.init(conn)

    if a.correlations:
        rows, m = matrix(conn, cfg)
        known = {k: v for k, v in m.items() if v[0] is not UNKNOWN}
        print(f"\n  PAIRWISE CORRELATION — {len(m)} pairs, {len(known)} measurable")
        print(f"  Minimum overlap: "
              f"{(cfg.get('league') or {}).get('min_corr_overlap', 30)} shared marks")
        print("  " + "-" * 76)
        if not known:
            print("  NONE are measurable yet. Every pair shares too few equity")
            print("  marks; a correlation from a handful of points is exactly")
            print("  +/-1 by construction and means nothing.")
        for (x, y), (c, n) in sorted(known.items(), key=lambda kv: -abs(kv[1][0])):
            print(f"  {c:>6.2f}  ({n:>3} marks)  {x} <-> {y}")
        conn.close(); return 0

    print(render(propose(conn, cfg, a.formula), cfg))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
