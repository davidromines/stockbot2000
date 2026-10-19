"""
Evidence-gated allocator — SHADOW ONLY (Stage AD6, Addendum H Phase E). Places nothing, assigns nothing.

Every day it answers: "if capital followed the evidence, which strategies would hold the medium-term slots, and how
does that differ from what holds them?" and records the answer in `allocator_shadow` for comparison over time.

**Eligibility** = the existing gates (ranking + slots.assess: a losing or worst-case-losing backtest, the unseen-2023
window, kill switches, accounting, stale data, stop plan, arming). Nothing here relaxes them.

**Ranking = a posterior, not a backtest score.** With a skeptical prior centred on zero (the corrected forward test
finds 0 of 54 families positive), each strategy's expected net return per 20 sessions held is a precision-weighted
combination of
  - its backtest score, treated as a NOISY measurement whose reliability equals the measured predictive power of
    backtests for later returns (rank correlation `backtest_reliability`, 0.2 from the 10-13 audit): the backtest's
    weight is that reliability, not 1;
  - its forward record (paper + live), with variance sd^2 / n (sd per 20 sessions from the survivorship dispersion
    where measured, else `fallback_sd20`; n = closed forward trades, capped at `max_forward_n` because trades share
    dates).
Ordered by posterior per unit of risk (posterior / sd20). A challenger must beat a holder by the switching cost.
Slots it would leave empty stay empty (cash) - it never fills a slot with a strategy whose posterior is <= 0.

    ./venv/bin/python allocator.py            # print today's shadow plan against the live holders
    ./venv/bin/python allocator.py --record   # also append it to allocator_shadow (daily.sh [9i3])
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone

from universe import load_config

DEFAULTS = {"prior_sd20": 0.01,             # spread of TRUE expected returns across strategies, per 20 sessions
            "backtest_reliability": 0.2,    # measured: backtest rank vs later return (audit B3, 2026-10-13)
            "fallback_sd20": 0.10,          # per-20-session sd where the dispersion is not yet measured
            "max_forward_n": 30,            # forward trades share dates: cap their count
            "switching_cost": 0.004,
            "max_per_family": 1}


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **((cfg or {}).get("allocator") or {})}


def posterior(backtest: float | None, forward: float | None, n: int, sd20: float | None, s: dict) -> dict:
    """Normal-normal shrinkage of the expected net return per 20 sessions towards zero."""
    tau2 = s["prior_sd20"] ** 2
    rho = min(max(float(s["backtest_reliability"]), 1e-6), 0.999)
    prec, num = 1.0 / tau2, 0.0
    w_b = w_f = 0.0
    if backtest is not None:
        v_b = tau2 * (1 - rho) / rho                   # chosen so the backtest's shrinkage factor alone equals rho
        prec += 1 / v_b
        num += backtest / v_b
        w_b = 1 / v_b
    sd = sd20 or s["fallback_sd20"]
    n_eff = min(int(n or 0), int(s["max_forward_n"]))
    if forward is not None and n_eff > 0:
        v_f = sd ** 2 / n_eff
        prec += 1 / v_f
        num += forward / v_f
        w_f = 1 / v_f
    mean = num / prec
    return {"post": mean, "post_sd": prec ** -0.5, "post_risk_adj": mean / sd, "sd20": sd,
            "w_backtest": w_b / prec, "w_forward": w_f / prec}


def plan(rows: list, holders: dict, n_slots: int, s: dict, too_similar=None) -> dict:
    """rows: slots.assess output (eligible flag, score, forward, forward_trades, sd_20, family, keys).
    holders: {slot: {strategy_key, version}} for the medium-term slots. Returns the shadow choice and the comparison."""
    scored = []
    for r in rows:
        if not r.get("eligible"):
            continue
        p = posterior(r.get("score"), r.get("forward"), r.get("forward_trades") or 0, r.get("sd_20"), s)
        scored.append({**{k: r.get(k) for k in ("strategy_key", "version", "family", "score", "forward",
                                                "forward_trades")}, **p})
    scored.sort(key=lambda x: -x["post_risk_adj"])
    held_keys = {(h["strategy_key"], h["version"]) for h in holders.values() if h}
    by_key = {(x["strategy_key"], x["version"]): x for x in scored}
    chosen, fams = [], {}
    # a holder keeps its place unless someone outside beats it by the switching cost (in posterior units)
    for x in scored:
        if len(chosen) >= n_slots or x["post"] <= 0:
            break
        if fams.get(x["family"], 0) >= s["max_per_family"]:
            continue
        if too_similar and too_similar(x, chosen):
            continue
        chosen.append(x)
        fams[x["family"]] = fams.get(x["family"], 0) + 1
    keep, swap = [], []
    for k in held_keys:
        h = by_key.get(k)
        if h is None:
            continue
        weakest_in = min((c for c in chosen if (c["strategy_key"], c["version"]) not in held_keys),
                         key=lambda c: c["post"], default=None)
        if (h["strategy_key"], h["version"]) in {(c["strategy_key"], c["version"]) for c in chosen}:
            keep.append(h)
        elif weakest_in is None or weakest_in["post"] - h["post"] < s["switching_cost"]:
            keep.append(h)                                # not beaten by enough to pay for the switch
        else:
            swap.append((h, weakest_in))
    return {"shadow": chosen, "keep": keep, "swap": swap, "ranked": scored,
            "overlap": len(held_keys & {(c["strategy_key"], c["version"]) for c in chosen}),
            "cash_slots": max(0, n_slots - len(chosen))}


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS allocator_shadow (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, holders TEXT NOT NULL, shadow TEXT NOT NULL,
        swaps TEXT NOT NULL, cash_slots INTEGER, settings TEXT NOT NULL)""")
    conn.commit()


def run(conn, cfg: dict, record: bool = False) -> dict:
    import slots
    s = settings(cfg)
    rows = slots.assess(conn, cfg)
    reserved = slots.intraday_reserved(cfg)
    held = {k: v for k, v in slots.current(conn, cfg).items() if k not in reserved}
    try:
        import strategy_diversity as sd
        mx = slots.settings(cfg)["max_correlation"]

        def too_similar(x, chosen):
            for o in chosen:
                c = sd.lookup(conn, (x["strategy_key"], x["version"]), (o["strategy_key"], o["version"]))
                if c is not None and c > mx:
                    return True
            return False
    except Exception:                                          # noqa: BLE001 — the family cap still applies
        too_similar = None
    p = plan(rows, held, len(held), s, too_similar)
    if record:
        init(conn)
        brief = lambda x: {"key": x["strategy_key"], "v": x["version"], "post": x["post"],   # noqa: E731
                           "post_risk_adj": x["post_risk_adj"], "score": x["score"]}
        conn.execute("INSERT INTO allocator_shadow (at, holders, shadow, swaps, cash_slots, settings) VALUES (?,?,?,?,?,?)",
                     (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      json.dumps({str(k): (v or {}).get("strategy_key") for k, v in held.items()}),
                      json.dumps([brief(x) for x in p["shadow"]]),
                      json.dumps([[brief(a), brief(b)] for a, b in p["swap"]]), p["cash_slots"], json.dumps(s)))
        conn.commit()
    return {**p, "held": held}


def render(p: dict) -> str:
    L = ["ALLOCATOR (shadow, Stage AD6) — what evidence-weighted capital would hold, against what does", ""]
    L.append("  live holders: " + ", ".join(f"slot {k} {(v or {}).get('strategy_key', 'cash')}" for k, v in p["held"].items()))
    L.append("  shadow choice: " + (", ".join(f"{x['strategy_key']} (post {x['post']:+.2%}, x{x['w_backtest']:.0%} backtest)"
                                             for x in p["shadow"]) or "none: every posterior <= 0 -> cash"))
    L.append(f"  overlap {p['overlap']} of {len(p['held'])}; cash slots in shadow {p['cash_slots']}")
    for h, c in p["swap"]:
        L.append(f"  would replace {h['strategy_key']} ({h['post']:+.2%}) with {c['strategy_key']} ({c['post']:+.2%})")
    L += ["", "  top 10 by posterior per unit of risk:"]
    for x in p["ranked"][:10]:
        L.append(f"    {x['strategy_key'][:34]:<34} post {x['post']:+.3%} (sd {x['post_sd']:.2%}) per 20 sessions  "
                 f"backtest {x['score'] if x['score'] is not None else float('nan'):+.2%}  forward "
                 f"{x['forward'] if x['forward'] is not None else float('nan'):+.2%} n={x['forward_trades'] or 0}")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    print(render(run(conn, cfg, a.record)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
