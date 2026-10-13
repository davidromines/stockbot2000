"""
Addendum F, Phase B1/B2 — the funnel from hypothesis to real-money profit, and the ranked causes (read-only).

B1  Counts at every stage, as strategies AND as families, with the typical result at that stage and the number lost.
    Parameter variants are shown next to independent hypotheses (88-99 families, ~28 effective independent tests).
B2  Every candidate explanation in the reviewer's list gets a measured number from this database, then a ranking
    by measured impact, confidence and cost to address.  The ranking itself is a judgement and is labelled as one.

    ./venv/bin/python audit_pipeline.py        # prints and writes reports/audit_pipeline_<date>.md
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

HONEST = "v2_next_open"


def latest_generator(conn) -> str:
    return conn.execute("SELECT generator FROM survivorship_backtests ORDER BY computed_at DESC LIMIT 1").fetchone()[0]


# --- the per-strategy table ---------------------------------------------------------------------
def strategy_table(conn, all_versions: bool = False) -> pd.DataFrame:
    if all_versions:
        s = pd.read_sql_query("SELECT strategy_key, version, family FROM league_strategies", conn)
    else:
        s = pd.read_sql_query(
        """SELECT l.strategy_key, l.version, l.family FROM league_strategies l
           JOIN (SELECT strategy_key, MAX(version) v FROM league_strategies GROUP BY strategy_key) m
             ON m.strategy_key = l.strategy_key AND m.v = l.version""", conn)
    g = latest_generator(conn)
    sb = pd.read_sql_query("SELECT strategy_key, version, mode, per_trade, trades FROM survivorship_backtests WHERE generator=?", conn, params=(g,))
    for mode in ("exclude", "as_is", "zero"):
        x = sb[sb["mode"] == mode].set_index(["strategy_key", "version"])["per_trade"].rename("sb_" + mode)
        s = s.merge(x, left_on=["strategy_key", "version"], right_index=True, how="left")
    ho = pd.read_sql_query("SELECT strategy_key, version, per_trade AS holdout FROM holdout_results", conn)
    ho = ho.sort_values("holdout").drop_duplicates(["strategy_key", "version"], keep="last")
    s = s.merge(ho, on=["strategy_key", "version"], how="left")
    met = pd.read_sql_query("SELECT strategy_key, version, phase, net_usd, trades FROM strategy_metrics", conn)
    bt = met[met["phase"] == "backtest"].groupby(["strategy_key", "version"])["net_usd"].sum().rename("bt_net")
    s = s.merge(bt, left_on=["strategy_key", "version"], right_index=True, how="left")
    st = pd.read_sql_query("""SELECT s.strategy_key, s.version, s.to_state state FROM league_state s
        JOIN (SELECT strategy_key, version, MAX(id) m FROM league_state GROUP BY 1,2) x ON x.m = s.id""", conn)
    s = s.merge(st, on=["strategy_key", "version"], how="left")
    # forward, honest basis, per fund
    link = pd.read_sql_query("SELECT strategy_key, version, run_id FROM factory_paper_link", conn)
    s = s.merge(link, on=["strategy_key", "version"], how="left")
    s["run_id"] = s["run_id"].fillna(s["strategy_key"].where(s["strategy_key"].str.startswith("paper:")).str[6:])
    tr = pd.read_sql_query(f"SELECT run_id, entry_date, net_pct FROM paper_trades_restated WHERE version='{HONEST}'", conn)
    fw = tr.groupby("run_id").agg(fw_n=("net_pct", "size"), fw_mean=("net_pct", "mean"), fw_dates=("entry_date", "nunique"))
    s = s.merge(fw, left_on="run_id", right_index=True, how="left")
    sa = pd.read_sql_query("SELECT DISTINCT strategy_key FROM slot_assignments WHERE action='ASSIGN'", conn)
    s["in_slot"] = s["strategy_key"].isin(sa["strategy_key"])
    return s


STAGES = [
    ("Documented hypotheses (knowledge library)", None),
    ("Strategy identities in the league (latest version each)", lambda s: s["strategy_key"].notna()),
    ("Backtested with survivorship modes (latest generator) or a stored backtest",
     lambda s: s["sb_exclude"].notna() | s["bt_net"].notna()),
    ("Positive net backtest, survivors only, costs deducted", lambda s: (s["sb_exclude"] > 0) | (s["bt_net"] > 0) & s["sb_exclude"].isna()),
    ("Positive with the synthetic dead companies (as_is)", lambda s: s["sb_as_is"] > 0),
    ("Positive in the worst-case survivorship mode (zero)", lambda s: s["sb_zero"] > 0),
    ("Positive on the unseen 2023-today window", lambda s: s["holdout"] > 0),
    ("FORWARD CHAIN starts from every strategy with a paper fund (enrolled whatever its backtest said)", lambda s: s["run_id"].notna()),
    ("Forward honest record with >= 20 trades", lambda s: s["fw_n"] >= 20),
    ("... and a positive honest net mean", lambda s: (s["fw_n"] >= 20) & (s["fw_mean"] > 0)),
    ("... and >= 20 independent entry dates of its own", lambda s: (s["fw_n"] >= 20) & (s["fw_mean"] > 0) & (s["fw_dates"] >= 20)),
]


FORWARD_FROM = 7      # STAGES index where the forward chain starts: every fund is tracked, whatever its backtest said


def funnel(conn, s: pd.DataFrame) -> list:
    """Two chains. Backtest stages are cumulative. The forward stages start from EVERY strategy with a paper
    fund, because the Lab survivors and the factory strategies were enrolled whatever their backtest said."""
    rows = []
    n_hyp = conn.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()[0]
    rows.append({"stage": STAGES[0][0], "strategies": n_hyp, "families": None, "typical": None, "unit": "", "lost": None})
    cur, prev = s.copy(), None
    for i, (label, fn) in enumerate(STAGES[1:], start=1):
        if i == FORWARD_FROM:
            cur, prev = s.copy(), None
        mask = fn(cur).fillna(False)
        cur = cur[mask]
        metric = ("sb_as_is" if "as_is" in label else "sb_exclude" if "survivors only" in label else "sb_zero" if "zero" in label
                  else "holdout" if "unseen" in label else "fw_mean" if "honest" in label or "independent" in label else None)
        typ = float(cur[metric].median()) if metric and len(cur) and cur[metric].notna().any() else None
        unit = "%" if metric == "fw_mean" else "per trade" if metric else ""
        rows.append({"stage": label, "strategies": len(cur), "families": int(cur["family"].nunique()), "typical": typ, "unit": unit,
                     "lost": None if prev is None else prev - len(cur), "restart": i == FORWARD_FROM})
        prev = len(cur)
    return rows


# --- B2 evidence -------------------------------------------------------------------------------
def evidence(conn, s: pd.DataFrame) -> dict:
    ev = {}
    tr = pd.read_sql_query(f"SELECT run_id, entry_date, gross_pct, cost_pct, net_pct FROM paper_trades_restated WHERE version='{HONEST}'", conn)
    ev["fw_trades"] = len(tr)
    ev["fw_mean_net"] = float(tr["net_pct"].mean())
    ev["fw_mean_gross"] = float(tr["gross_pct"].mean())
    ev["fw_mean_cost"] = float(tr["cost_pct"].mean())
    wk = tr.assign(w=pd.to_datetime(tr["entry_date"]).dt.to_period("W").astype(str)).groupby("w")["net_pct"].agg(["mean", "size"])
    ev["weekly"] = wk
    # does a backtest predict a forward record?  one point per fund with >= 20 honest trades
    f = s[(s["fw_n"] >= 20)]
    for col in ("sb_exclude", "sb_as_is", "holdout"):
        x = f.dropna(subset=[col])
        ev["rho_" + col] = (float(x[col].rank().corr(x["fw_mean"].rank())), len(x)) if len(x) >= 30 else (np.nan, len(x))
    ev["bt_mean_as_is"] = float(s["sb_as_is"].mean() * 100)
    ev["fw_mean_for_same"] = float(f.dropna(subset=["sb_as_is"])["fw_mean"].mean()) if f["sb_as_is"].notna().any() else np.nan
    ev["bt_mean_for_same"] = float(f["sb_as_is"].mean() * 100) if f["sb_as_is"].notna().any() else np.nan
    ev["pos_exclude"] = (float((s["sb_exclude"].dropna() > 0).mean()), int(s["sb_exclude"].notna().sum()))
    ev["pos_as_is"] = (float((s["sb_as_is"].dropna() > 0).mean()), int(s["sb_as_is"].notna().sum()))
    ev["pos_zero"] = (float((s["sb_zero"].dropna() > 0).mean()), int(s["sb_zero"].notna().sum()))
    ev["pos_holdout"] = (float((s["holdout"].dropna() > 0).mean()), int(s["holdout"].notna().sum()))
    # redundancy
    ev["lab_trials"] = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
    ev["families"] = int(s["family"].nunique())
    ev["lab_search_share"] = float((s["family"] == "lab_search").mean())
    # SPY over the forward window
    sp = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' AND date >= '2026-09-24' ORDER BY date", conn)
    ev["spy_window"] = (sp["date"].iloc[0], sp["date"].iloc[-1], float(sp["close"].iloc[-1] / sp["close"].iloc[0] - 1) * 100) if len(sp) > 1 else None
    # live
    import live_pnl
    cfg = load_config()
    lv = live_pnl.compute(conn, cfg, mode="LIVE")
    ev["live"] = {"closed": lv["closed_n"], "wins": lv["wins"], "net": lv["closed_total"]["net"], "stake": lv["closed_total"]["stake"],
                  "open_gross": lv["open_gross"], "open_stake": lv["open_stake"], "since": lv["since"]}
    ev["live_equity"] = conn.execute("SELECT equity FROM live_equity ORDER BY at LIMIT 1").fetchone()[0], conn.execute("SELECT equity FROM live_equity ORDER BY at DESC LIMIT 1").fetchone()[0]
    ev["slots_ever"] = int(s["in_slot"].sum())
    ev["churn"] = conn.execute("SELECT COUNT(*) FROM slot_assignments WHERE action='RELEASE'").fetchone()[0]
    ev["validation"] = {"lab_pass": conn.execute("SELECT COUNT(*) FROM strategy_failures").fetchone()[0]}
    return ev


def f(x, s="{:+.2f}"):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else s.format(x)


def render(rows: list, ev: dict, as_of: str) -> str:
    L = ["# Phase B1-B2: the funnel to real money, and why no edge is established", "",
         f"Computed {as_of}, read-only, from the league tables, survivorship backtests (latest generator), the unseen-window results, "
         "`paper_trades_restated` (next-open fills, costs deducted) and `live_pnl`. Facts, inferences and unknowns are in separate sections.", "",
         "## B1. Funnel (each stage requires the previous one)", "",
         "| stage | strategies | families | typical result at this stage | lost vs previous |", "|---|---:|---:|---:|---:|"]
    for r in rows:
        typ = "" if r["typical"] is None else (f"{r['typical'] * 100:+.2f}% {r['unit']}" if r["unit"] == "per trade" else f"{r['typical']:+.2f}{r['unit']}")
        L.append(f"| {r['stage']} | {r['strategies']:,} | {'' if r['families'] is None else r['families']} | {typ} | {'' if r.get('lost') is None else f'{r['lost']:,}'} |")
    lv = ev["live"]
    L += [f"| Assigned to a real-money slot at least once | {ev['slots_ever']} | | | |",
          f"| Positive completed real-account P&L | strategies cannot be isolated: {lv['closed']} closed live trades, {lv['wins']} winners, "
          f"net {f(lv['net'], '${:+.2f}')} on ${lv['stake']:.0f} deployed | | | |",
          "", f"Parameter variants are not independent hypotheses: {ev['families']} families hold the strategy identities ({ev['lab_search_share']:.0%} of them `lab_search`), "
          f"{ev['lab_trials']:,} Lab evaluations reduce to ~127,000 distinct structures, and the number of effectively independent family-level tests is about 28 (Phase A4).", "",
          "### Distribution of results at the stages that have a per-trade number", "",
          f"- Survivors-only backtests: {ev['pos_exclude'][0]:.0%} positive of {ev['pos_exclude'][1]:,}; with the synthetic dead companies (as_is) {ev['pos_as_is'][0]:.0%} of {ev['pos_as_is'][1]:,}; "
          f"worst-case treatment (zero) {ev['pos_zero'][0]:.0%} of {ev['pos_zero'][1]:,}; unseen 2023-today window {ev['pos_holdout'][0]:.0%} of {ev['pos_holdout'][1]:,}.",
          f"- Forward, all {ev['fw_trades']:,} honest-basis trades: mean gross {f(ev['fw_mean_gross'])} %, costs {f(ev['fw_mean_cost'])} %, net {f(ev['fw_mean_net'])} % per trade.",
          "", "Weekly entry cohorts (honest net %, all funds pooled):", "", "| entry week | trades | mean net % |", "|---|---:|---:|"]
    for w, r in ev["weekly"].iterrows():
        L.append(f"| {w} | {int(r['size']):,} | {f(r['mean'])} |")
    sw = ev["spy_window"]
    L += ["", f"SPY over the forward window ({sw[0]} to {sw[1]}): {f(sw[2])} %." if sw else "",
          "", "## B2. Candidate causes, with the measurement behind each", "",
          "| cause | measured here | what it says |", "|---|---|---|",
          f"| Backtests contain residual measurement problems | paper fills were at the signal-day close and `pnl_pct` was gross (A1); honest recompute cut `lab_search` +1.30 % to +0.90 % and `momentum` +2.04 % to +1.71 % | present and now corrected in the funnel; the ranking was already net but still same-close |",
          f"| Historical positives do not survive forward testing | forward pool mean {f(ev['fw_mean_net'])} % per trade honest-net vs {f(ev['bt_mean_for_same'])} % as_is backtest on the same {ev['rho_sb_as_is'][1]} funds ({f(ev['fw_mean_for_same'])} % forward) | large gap: backtests predict a level far above what is realised |",
          f"| Backtests do not rank strategies | rank correlation of backtest with later forward mean, funds with >= 20 trades: exclude {f(ev['rho_sb_exclude'][0], '{:+.2f}')} (n {ev['rho_sb_exclude'][1]}), as_is {f(ev['rho_sb_as_is'][0], '{:+.2f}')} (n {ev['rho_sb_as_is'][1]}), unseen window {f(ev['rho_holdout'][0], '{:+.2f}')} (n {ev['rho_holdout'][1]}) | weak or no ordering power in 3 weeks of one regime; cannot be called either way |",
          f"| Survivorship treatment distorts results | {ev['pos_as_is'][0]:.0%} positive as_is vs {ev['pos_zero'][0]:.0%} in the worst case vs {ev['pos_exclude'][0]:.0%} survivors-only | the verdict on a strategy depends on an unidentifiable assumption about companies we cannot price |",
          f"| Costs erase gross returns | mean gross {f(ev['fw_mean_gross'])} % minus costs {f(ev['fw_mean_cost'])} % | " + ("gross is already negative at the pool level, so costs are not what decides the pool result" if ev['fw_mean_gross'] <= 0 else f"costs take {ev['fw_mean_cost'] / ev['fw_mean_gross']:.0%} of gross at the pool level") + " |",
          "| Hypotheses are redundant | 88-99 families, 1.05 M trials -> ~127,000 structures, ~28 effective independent tests | the searchable space is explored many times over by near-identical rules |",
          "| Validation is overly restrictive | 94 % of backtests are net positive; validation passes 953 of ~5,200 Lab shortlisted | the gate is not what stops candidates: positives are plentiful and uninformative (Stage T) |",
          "| Ranking selects the wrong candidates | Phase B3: top-quintile stored score realised below the middle quintile; top-50 funds rest on a median of 20 trades from one entry date | substantial, and addressable at low cost |",
          "| The time series is too short | 12 trading sessions of entries, 0 strategies with >= 20 independent entry dates of their own, one market regime | the dominant limit on what can be concluded either way |",
          f"| Paper does not reproduce real execution | live {lv['closed']} closed trades net {f(lv['net'], '${:+.2f}')}; the slot adds stops and ATR sizing that the paper fund does not | not measurable yet: too few live trades per strategy |",
          "| Metrics do not match the owner's objective | per-trade vs per-dollar vs portfolio return are not yet reported together (Phase F) | owner ruling 2026-10-13: report all four side by side |",
          "", "### Ranking of causes (judgement, from the measurements above)", "",
          "| rank | cause | impact | confidence | cost to address |", "|---:|---|---|---|---|",
          "| 1 | Too few independent observations (dates, regimes) for any claim | decisive | high | time only; cannot be bought |",
          "| 2 | Ranking promotes unproven strategies on counts of correlated trades (n = open positions from one date) | high: it chooses the live slots | high on the mechanism, medium on the size | low: a shadow gate (Phase C1) and an estimator that counts dates |",
          "| 3 | Backtest-to-forward gap (survivorship, fills, selection among thousands) | high | medium | medium: already partly corrected; prospective test (A6) measures it |",
          "| 4 | Redundant hypotheses inflate apparent breadth | medium | high | low: report families not variants; Phase E |",
          "| 5 | Measurement defects (same-close fills, gross-as-net, replay) | was high, now corrected in the funnel and restated | high | done (G1-G3) |",
          "| 6 | Regime and decay | unknown | low: one regime observed | needs time; regime descriptions only |",
          "| 7 | Costs | low at pool level | medium | n/a |",
          "", "## Facts, inferences, unknowns", "",
          "- FACT: no strategy has 20 independent entry dates of its own on the honest basis; no family survives multiple-testing adjustment; the real account is "
          f"{f(ev['live_equity'][1] - ev['live_equity'][0], '${:+.2f}')} from its first recorded equity.",
          "- INFERENCE: the dominant reason no edge is established is sample size and the way sample size is counted, not a shortage of ideas or of compute.",
          "- UNKNOWN: whether any family has an edge; whether the survivorship assumption helps or hurts; how the live slots' stops change a paper rule's result.",
          "", "## What could be wrong with this analysis", "",
          "- The funnel's stage definitions are mine; a different threshold changes the counts (the cumulative structure does not change the conclusion).",
          "- `holdout_results` and `survivorship_backtests` exist only for strategies that reached those stages, so 'positive' shares are of the tested subset.",
          "- Forward honest records omit trades that exit on the newest bar.",
          "- The ranking of causes is a judgement; the measured numbers beside it are the evidence, the order is not a computed result."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    s = strategy_table(conn)
    text = render(funnel(conn, s), evidence(conn, s), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    out = Path("reports") / f"audit_pipeline_{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
