"""
Pre-registered prospective test of the eight forward-positive families (Addendum F, Phase A4/A6).

The reported results of 2026-10-12 were found by looking at the forward record after the fact, so they cannot also be the
test. This registers (experiment_registry, locked) a rule that is evaluated only on entries made after registration, by
funds that already exist, once, at a fixed sample size. The registry refuses edits to the locked fields; changing the rule
requires a new version that stays in the record.

THE RULE (locked in the registry spec)
  families        lab_search, momentum, kf_seasonality, st_uptrend_pullback, bollinger_reversion, kf_mean_reversion,
                  st_momentum_1d, turn_of_month (membership frozen: funds created before registration only)
  sample          entries dated on or after START (2026-10-12: the first whose next-open fill, 2026-10-13, comes after registration), the first 20
                  pooled independent entry dates; evaluated once, 15 sessions after the 20th, so most trades have closed.
                  Positions still open are marked at the newest open and INCLUDED (a closed-trades-only sample would keep
                  the short holds and drop the slow losers).
  returns         net of the engine's modelled round-trip cost, next-open entry and exit on adjusted prices
                  (paper_trades_restated v2_next_open), and the same minus SPY over the same window
  a family passes ALL of: >= 12 own independent entry dates in the sample; mean excess over SPY > 0; one-sided max-T
                  adjusted p <= 0.05 across the registered families (sign-flip, dependence preserved) on excess returns;
                  date-block bootstrap 95% lower bound of the absolute net mean > 0.
  nothing else    no family, fund or rule may be added or redefined; interim looks are allowed but are labelled INTERIM and
                  decide nothing.

    ./venv/bin/python prospective_eval.py --register   # once
    ./venv/bin/python prospective_eval.py              # progress / evaluation
    ./venv/bin/python prospective_eval.py --complete   # record the result in the registry (only when evaluable)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys

import numpy as np
import pandas as pd

import forward_stats as fs
from universe import load_config

EXPERIMENT = "forward_families_prospective"
FAMILIES = ["lab_search", "momentum", "kf_seasonality", "st_uptrend_pullback", "bollinger_reversion",
            "kf_mean_reversion", "st_momentum_1d", "turn_of_month"]
START = "2026-10-12"
NEED_DATES = 20
LAG_SESSIONS = 15
MIN_OWN_DATES = 12
ALPHA = 0.05


def spec() -> dict:
    return {
        "primary_metric": "per family: mean excess return over SPY (net of modelled costs, next-open fills, adjusted prices), "
                          "one-sided max-T adjusted p across the registered families; absolute net mean with a date-block bootstrap",
        "universe": "paper_trades_restated v2_next_open plus open positions marked at the newest open, for funds in paper_runs "
                    "created before registration whose family is: " + ", ".join(FAMILIES),
        "entry_rule": "each fund's own, unchanged; no fund, family or rule is added or redefined after registration",
        "exit_rule": "each fund's own, unchanged",
        "holding_period": "as each strategy defines; positions still open at evaluation are marked at the newest open and included",
        "cost_assumptions": "the paper engine's modelled round-trip cost per trade; next-open fills on adjusted prices",
        "evaluation_period": f"entries dated >= {START} (first entries whose next-open fill comes after registration), the first {NEED_DATES} pooled independent "
                             f"entry dates; evaluated {LAG_SESSIONS} sessions after the {NEED_DATES}th",
        "data_version": "paper_trades_restated version v2_next_open; prices as stored on the evaluation date",
        "stopping_rule": f"one evaluation, at the fixed sample; interim looks are INTERIM and decide nothing; a second evaluation at "
                         f"{2 * NEED_DATES} pooled dates only for families that pass or reach p <= 0.15",
        "sample_size": f"{NEED_DATES} pooled independent entry dates; a family needs >= {MIN_OWN_DATES} of its own",
        "holdout_policy": "no tuning on these dates; the sealed 2023+ research holdout is not touched",
        "pass_rule": f">= {MIN_OWN_DATES} own dates AND mean excess over SPY > 0 AND max-T adjusted p <= {ALPHA} AND bootstrap lower bound of absolute net mean > 0",
        "families": FAMILIES, "start": START,
    }


def ensure_registered(conn) -> dict:
    import experiment_registry as er
    try:
        return er.get(conn, EXPERIMENT)
    except er.RegistryError:
        er.create(conn, EXPERIMENT,
                  "At least one of the eight listed forward families earns a positive return net of modelled costs at next-open fills, "
                  "beyond market drift and beyond what luck among the eight explains, over entries decided after registration. "
                  f"Fails if no family has a max-T adjusted p <= {ALPHA} on excess-over-SPY returns, a positive absolute bootstrap lower "
                  "bound and enough independent entry dates.", "claude", spec())
        er.register(conn, EXPERIMENT)
        return er.get(conn, EXPERIMENT)


# --- data --------------------------------------------------------------------------------------
def collect(conn, start: str, registered_at: str, families: list) -> pd.DataFrame:
    import audit_selection as a4
    sess = a4.sessions(conn)
    closed = pd.read_sql_query(
        f"""SELECT p.family, x.run_id, x.ticker, x.entry_date, x.exit_date, x.net_pct, x.cost_pct, 0 AS is_open
            FROM paper_trades_restated x JOIN paper_runs p ON p.run_id = x.run_id
            WHERE x.version='v2_next_open' AND x.entry_date >= ? AND p.created_at < ?
              AND p.family IN ({','.join('?' * len(families))})""", conn, params=(start, registered_at, *families))
    closed = a4.add_spy(conn, closed, sess)
    pos = pd.read_sql_query(
        f"""SELECT p.family, o.run_id, o.ticker, o.entry_date, NULL AS exit_date, o.entry_price, o.shares
            FROM paper_positions o JOIN paper_runs p ON p.run_id = o.run_id
            WHERE o.entry_date >= ? AND p.created_at < ? AND p.family IN ({','.join('?' * len(families))})""",
        conn, params=(start, registered_at, *families))
    if len(pos) and len(sess) > 1:
        last_open_date = sess[-1]
        op = pd.read_sql_query("SELECT ticker, date, open FROM prices WHERE date >= ? AND ticker IN (%s)" % ",".join("?" * (pos["ticker"].nunique() + 1)),
                               conn, params=(start, *pos["ticker"].unique().tolist(), "SPY"))
        omap = {(r.ticker, r.date): r.open for r in op.itertuples()}
        pos_ix = {d: i for i, d in enumerate(sess)}
        rows = []
        cost = closed.groupby("family")["cost_pct"].mean().to_dict()
        for r in pos.itertuples():
            i = pos_ix.get(r.entry_date)
            if i is None or i + 1 >= len(sess):
                continue
            ne = sess[i + 1]
            e, m = omap.get((r.ticker, ne)), omap.get((r.ticker, last_open_date))
            se, sm = omap.get(("SPY", ne)), omap.get(("SPY", last_open_date))
            if None in (e, m, se, sm) or ne >= last_open_date:
                continue
            net = (m / e - 1) * 100 - cost.get(r.family, 0.17)
            rows.append({"family": r.family, "run_id": r.run_id, "ticker": r.ticker, "entry_date": r.entry_date, "exit_date": None,
                         "net_pct": net, "cost_pct": cost.get(r.family, 0.17), "is_open": 1, "spy_pct": (sm / se - 1) * 100,
                         "excess_pct": net - (sm / se - 1) * 100})
        if rows:
            closed = pd.concat([closed, pd.DataFrame(rows)], ignore_index=True)
    return closed


def window(df: pd.DataFrame, sess: list) -> tuple:
    """(the first NEED_DATES pooled entry dates, evaluation date or None)."""
    dates = sorted(df["entry_date"].unique())
    first = dates[:NEED_DATES]
    if len(first) < NEED_DATES:
        return first, None
    i = sess.index(first[-1]) if first[-1] in sess else None
    ev = sess[i + LAG_SESSIONS] if i is not None and i + LAG_SESSIONS < len(sess) else None
    return first, ev


def decide(df: pd.DataFrame, families: list) -> pd.DataFrame:
    """Apply the registered pass rule to a sample (already limited to the registered window)."""
    dm = df.pivot_table(index="entry_date", columns="family", values="excess_pct", aggfunc="mean").reindex(columns=families)
    mt = fs.maxt_signflip(dm, reps=20000)
    rows = []
    for fam in families:
        g = df[df["family"] == fam]
        if g.empty:
            rows.append({"family": fam, "n": 0, "dates": 0, "mean_net": np.nan, "mean_excess": np.nan, "p_maxT": np.nan,
                         "boot_lo": np.nan, "open_share": np.nan, "pass": False, "why": "no trades"})
            continue
        boot = fs.bootstrap_by_cluster(g["net_pct"], g["entry_date"])
        dates = int(g["entry_date"].nunique())
        p = float(mt.loc[fam, "p_maxT"]) if fam in mt.index else np.nan
        me = float(g["excess_pct"].mean())
        ok = dates >= MIN_OWN_DATES and me > 0 and p == p and p <= ALPHA and boot["lo"] > 0
        why = [] if ok else [s for s, bad in (("too few own dates", dates < MIN_OWN_DATES), ("excess <= 0", me <= 0),
                                                ("max-T p > 0.05", not (p == p and p <= ALPHA)), ("bootstrap lower bound <= 0", boot["lo"] <= 0)) if bad]
        rows.append({"family": fam, "n": int(len(g)), "dates": dates, "mean_net": float(g["net_pct"].mean()), "mean_excess": me,
                     "p_maxT": p, "boot_lo": boot["lo"], "open_share": float(g["is_open"].mean()), "pass": bool(ok), "why": "; ".join(why)})
    return pd.DataFrame(rows)


def report(conn, complete: bool = False) -> str:
    import audit_selection as a4
    import experiment_registry as er
    e = ensure_registered(conn)
    sp = json.loads(e["spec"])
    df = collect(conn, sp["start"], e["registered_at"], sp["families"])
    sess = a4.sessions(conn)
    first, ev = window(df, sess)
    latest = sess[-1]
    L = [f"# Prospective test: {EXPERIMENT} v{e['version']} (registered {e['registered_at']}, status {e['status']})", "",
         f"Entries from {sp['start']}: {len(df):,} trades ({int(df['is_open'].sum()) if len(df) else 0} still open, marked) on "
         f"{df['entry_date'].nunique() if len(df) else 0} pooled entry dates; the test needs {NEED_DATES} and is evaluated "
         f"{LAG_SESSIONS} sessions after the {NEED_DATES}th. Latest stored session {latest}."]
    ready = bool(ev) and latest >= ev
    if not ready:
        L += ["", f"**NOT YET A TEST.** Pooled entry dates so far: {len(first)} of {NEED_DATES}; evaluation date "
              f"{ev or 'after the 20th date + 15 sessions'}. Anything below is INTERIM and decides nothing."]
    d = df[df["entry_date"].isin(first)] if len(first) else df
    if len(d):
        t = decide(d, sp["families"])
        L += ["", "| family | trades | own dates | mean net % | mean excess vs SPY % | max-T adj p | boot lower % | open share | pass | why not |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---|---|"]
        for r in t.itertuples():
            fm = lambda x, s="{:+.2f}": "n/a" if x != x else s.format(x)
            L.append(f"| {r.family} | {r.n:,} | {r.dates} | {fm(r.mean_net)} | {fm(r.mean_excess)} | {fm(r.p_maxT, '{:.3f}')} | {fm(r.boot_lo)} | "
                     f"{fm(r.open_share, '{:.2f}')} | {'PASS' if (r.__getattribute__('pass') and ready) else ('(interim)' if not ready else 'fail')} | {r.why} |")
        if ready:
            passed = [r.family for r in t.itertuples() if r.__getattribute__("pass")]
            L += ["", f"**Result: {len(passed)} of {len(sp['families'])} families pass** ({', '.join(passed) or 'none'}). "
                  "A pass is evidence worth a longer test, not proof of profitability."]
            if complete and e["status"] != "COMPLETE":
                if e["status"] == "REGISTERED":
                    er.start(conn, EXPERIMENT)
                er.complete(conn, EXPERIMENT, {"passed": passed, "table": json.loads(t.to_json(orient="records")),
                                               "evaluated_on": latest, "dates": first},
                            f"{len(passed)} of {len(sp['families'])} families passed the registered rule.")
                L.append("Recorded in the registry as COMPLETE.")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--complete", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    if a.register:
        e = ensure_registered(conn)
        print(f"{EXPERIMENT} v{e['version']} {e['status']} registered_at {e['registered_at']}")
        return 0
    print(report(conn, a.complete))
    return 0


if __name__ == "__main__":
    sys.exit(main())
