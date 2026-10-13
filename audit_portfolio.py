"""
Addendum F, Phases C2 and C3 — comparable strategy metrics and the five-slot portfolio (read-only; shadow only).

C2  Are strategies with different holding periods compared on a defensible basis?  Net per trade, per dollar
    deployed, per holding session, per 20 sessions (what the ranking uses), capital utilisation, turnover, costs,
    drawdown and uncertainty are computed side by side from the honest (next-open, costs deducted) record; the rank
    agreement between the bases shows how much the choice of basis alone changes who looks best.
C3  Are the five slots five different bets?  Holdings, sectors, beta and realised co-movement of the live positions
    and of the strategies behind them, then a shadow comparison of the current top-five rule with a
    portfolio-aware alternative, evaluated chronologically on the same snapshots as the ranking audit.

    ./venv/bin/python audit_portfolio.py       # prints and writes reports/audit_portfolio_<date>.md
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import audit_ranking as ar
import forward_stats as fs
from universe import load_config

MIN_TRADES = 20
CORR_VETO = 0.7


# --- C2 ----------------------------------------------------------------------------------------
def hold_sessions(tr: pd.DataFrame, sess: list) -> pd.Series:
    pos = {d: i for i, d in enumerate(sess)}
    e, x = tr["entry_date"].map(pos), tr["exit_date"].map(pos)
    return (x - e).clip(lower=1)


def comparability(conn) -> dict:
    import audit_selection as a4
    sess = a4.sessions(conn)
    tr = pd.read_sql_query(
        """SELECT x.run_id, x.ticker, x.entry_date, x.exit_date, x.net_pct, x.gross_pct, x.cost_pct, p.family, p.capital_usd
           FROM paper_trades_restated x JOIN paper_runs p ON p.run_id = x.run_id WHERE x.version='v2_next_open'""", conn)
    tr["hold"] = hold_sessions(tr, sess)
    eq = pd.read_sql_query("SELECT run_id, date, positions_usd, equity_usd FROM paper_equity", conn)
    rows = []
    for rid, g in tr.groupby("run_id"):
        if len(g) < MIN_TRADES:
            continue
        e = eq[eq["run_id"] == rid].sort_values("date")
        util = float((e["positions_usd"] / e["equity_usd"]).mean()) if len(e) else np.nan
        if len(e) >= 5:
            peak = e["equity_usd"].cummax()
            dd = float(((peak - e["equity_usd"]) / peak).max() * 100)
            life = len(e)
        else:
            dd, life = np.nan, len(e)
        h = float(g["hold"].mean())
        b = fs.bootstrap_by_cluster(g["net_pct"], g["entry_date"], reps=1000) if g["entry_date"].nunique() >= 3 else {"lo": np.nan, "hi": np.nan}
        rows.append({"run_id": rid, "family": g["family"].iloc[0], "trades": len(g), "dates": g["entry_date"].nunique(),
                     "per_trade": float(g["net_pct"].mean()), "median": float(g["net_pct"].median()), "hold": h,
                     "per_session": float(g["net_pct"].mean() / h), "per_20": float(g["net_pct"].mean() * 20 / max(h, 5)),
                     "cost": float(g["cost_pct"].mean()), "util": util, "dd": dd, "life": life,
                     "turnover_per_session": len(g) / max(life, 1), "ci_lo": b["lo"], "ci_hi": b["hi"],
                     # return on the whole fund per session: what a dollar of capital earned, idle cash included
                     "fund_per_session": float((e["equity_usd"].iloc[-1] / e["equity_usd"].iloc[0] - 1) * 100 / max(life - 1, 1)) if len(e) >= 5 else np.nan})
    d = pd.DataFrame(rows)
    bases = ["per_trade", "per_session", "per_20", "fund_per_session"]
    rho = pd.DataFrame({a: {b: float(d[a].rank().corr(d[b].rank())) for b in bases} for a in bases})
    top = {b: set(d.sort_values(b, ascending=False).head(10)["run_id"]) for b in bases}
    overlap = {b: len(top["per_trade"] & top[b]) for b in bases}
    return {"table": d, "rho": rho, "overlap": overlap}


# --- C3 ----------------------------------------------------------------------------------------
def live_holdings(conn) -> pd.DataFrame:
    """Open LIVE slot positions: the latest OPEN per slot without a later CLOSE."""
    t = pd.read_sql_query("SELECT id, slot_id, action, symbol, quantity, price, at FROM slot_trades WHERE mode='LIVE' ORDER BY id", conn)
    held = {}
    for r in t.itertuples():
        if r.action == "OPEN":
            held[r.slot_id] = (r.symbol, r.quantity, r.price, r.at)
        elif r.action == "CLOSE":
            held.pop(r.slot_id, None)
    return pd.DataFrame([{"slot": k, "symbol": v[0], "qty": v[1], "entry": v[2], "at": v[3]} for k, v in sorted(held.items())])


def exposure(conn) -> dict:
    import industry
    h = live_holdings(conn)
    if h.empty:
        return {"holdings": h}
    px = pd.read_sql_query(f"SELECT ticker, date, close FROM prices WHERE ticker IN ({','.join('?' * len(h))}) AND date >= date('now','-400 day')",
                           conn, params=tuple(h["symbol"]))
    wide = px.pivot(index="date", columns="ticker", values="close").sort_index()
    rets = wide.pct_change().dropna(how="all")
    spy = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' AND date >= date('now','-400 day') ORDER BY date", conn).set_index("date")["close"].pct_change()
    corr = rets.corr()
    pair = corr.where(~np.eye(len(corr), dtype=bool)).stack()
    ew = rets.mean(axis=1)
    out = {"holdings": h}
    h["last"] = h["symbol"].map(wide.ffill().iloc[-1])
    h["mark_pct"] = (h["last"] / h["entry"] - 1) * 100
    prev, conn.row_factory = conn.row_factory, sqlite3.Row         # industry.py reads rows by name
    h["division"] = [industry.classify_as_of(conn, s, wide.index[-1])["label"] for s in h["symbol"]]
    conn.row_factory = prev
    h["beta"] = [(conn.execute("SELECT beta FROM risk_metrics WHERE ticker=? ORDER BY date DESC LIMIT 1", (s,)).fetchone() or [np.nan])[0] for s in h["symbol"]]
    out["holdings"] = h
    out["corr"] = corr
    out["avg_pair_corr"] = float(pair.mean())
    single_vol = float(rets.std().mean())
    out["diversification_ratio"] = float(single_vol / ew.std()) if ew.std() else np.nan   # 1.0 = one bet, sqrt(5)=2.24 = five independent bets
    j = pd.concat([ew, spy], axis=1, join="inner").dropna()
    out["beta_to_spy"] = float(np.cov(j.iloc[:, 0], j.iloc[:, 1])[0, 1] / j.iloc[:, 1].var())
    out["sessions"] = int(len(rets))
    out["tail_corr_note"] = None
    return out


def strategy_links(conn, cfg) -> pd.DataFrame:
    import slots
    import strategy_diversity as sd
    cur = {k: v for k, v in slots.current(conn, cfg).items() if v}
    keys = [(k, v["strategy_key"], v["version"]) for k, v in cur.items()]
    rows = []
    for i, (si, ki, vi) in enumerate(keys):
        for sj, kj, vj in keys[i + 1:]:
            rows.append({"a": si, "b": sj, "corr": sd.lookup(conn, (ki, vi), (kj, vj))})
    return pd.DataFrame(rows)


def shadow_selection(conn) -> pd.DataFrame:
    """Top-five by stored score vs top-five by empirical-Bayes estimate, both with one-per-family and the 0.7
    correlation veto where a correlation is stored; realised = later honest mean of the chosen funds."""
    import strategy_diversity as sd
    rh, tr = ar.history(conn), ar.trades(conn)
    fam = dict(conn.execute("SELECT strategy_key, family FROM league_strategies"))
    out = []
    for d in sorted(rh["date"].unique()):
        h = rh[(rh["date"] == d) & rh["run_id"].notna() & (rh["passes_gate"] == 1)].drop_duplicates("run_id").copy()
        o = ar.outcomes(tr, d)
        h = h.merge(o, left_on="run_id", right_index=True)
        if len(h) < ar.MIN_FUNDS:
            continue
        h["eb"] = h["run_id"].map(ar.eb_estimates(tr, d))
        res = {"date": d, "funds": len(h)}
        for name, col in (("current", "score"), ("aware", "eb")):
            chosen = []
            for r in h.sort_values(col, ascending=False).itertuples():
                f_ = fam.get(r.strategy_key)
                if any(fam.get(c.strategy_key) == f_ for c in chosen):
                    continue
                if any((sd.lookup(conn, (r.strategy_key, r.version), (c.strategy_key, c.version)) or 0) > CORR_VETO for c in chosen):
                    continue
                chosen.append(r)
                if len(chosen) == 5:
                    break
            res[name] = float(np.mean([c.realised for c in chosen]) * 100) if chosen else np.nan
            res[name + "_n"] = len(chosen)
        res["pool"] = float(h["realised"].mean() * 100)
        out.append(res)
    return pd.DataFrame(out)


# --- report ------------------------------------------------------------------------------------
def f(x, s="{:+.2f}"):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else s.format(x)


def render(conn, cfg, as_of: str) -> str:
    c2, ex, links, sh = comparability(conn), exposure(conn), strategy_links(conn, cfg), shadow_selection(conn)
    d = c2["table"]
    L = ["# Phase C2-C3: comparable metrics and the five-slot portfolio", "",
         f"Computed {as_of}, read-only. Honest basis: next-open fills, modelled costs deducted. {len(d)} funds with >= {MIN_TRADES} trades.", "",
         "## C2. Are strategies compared on a defensible basis?", "",
         "The ranking scales each strategy's per-trade figure to 20 sessions using that strategy's own holding period (floor 5). Four bases for the same funds:", "",
         "- **per trade**: mean net return of a trade;",
         "- **per holding session**: per-trade mean divided by mean sessions held;",
         "- **per 20 sessions**: the ranking's basis (per trade x 20 / max(hold, 5));",
         "- **per fund session**: what the whole fund earned per session including idle cash (the dollar actually available to the owner earns this).", "",
         "Rank correlation between the bases (Spearman, across funds):", "",
         "| | " + " | ".join(c2["rho"].columns) + " |", "|---|" + "---:|" * len(c2["rho"].columns)]
    for a, r in c2["rho"].iterrows():
        L.append(f"| {a} | " + " | ".join(f"{v:+.2f}" for v in r) + " |")
    L += ["", "Overlap of each basis's top 10 with the per-trade top 10: " + ", ".join(f"{b} {n}/10" for b, n in c2["overlap"].items()) + ".", "",
          f"Holding period (sessions) across funds: median {d['hold'].median():.1f}, 10th to 90th percentile {d['hold'].quantile(.1):.1f} to {d['hold'].quantile(.9):.1f}; "
          f"capital utilisation (positions / equity) median {d['util'].median():.0%}; turnover median {d['turnover_per_session'].median():.1f} trades per session of fund life; "
          f"cost per trade median {d['cost'].median():.2f} %.", "",
          "The five best funds on each basis (honest net, with the date-block interval of the per-trade mean):", "",
          "| basis | fund family | trades | dates | per trade % | 95% interval | hold | per session % | per 20 % | util |", "|---|---|---:|---:|---:|---|---:|---:|---:|---:|"]
    for b in ("per_trade", "per_20", "fund_per_session"):
        for r in d.sort_values(b, ascending=False).head(5).itertuples():
            L.append(f"| {b} | {r.family} | {r.trades} | {r.dates} | {f(r.per_trade)} | {f(r.ci_lo)} to {f(r.ci_hi)} | {r.hold:.1f} | {f(r.per_session)} | {f(r.per_20)} | {f(r.util, '{:.0%}')} |")
    ov = c2["overlap"]
    L += ["", f"Reading: the ranking's basis (per 20 sessions) is rank-identical to per trade (Spearman {c2['rho'].loc['per_20', 'per_trade']:+.2f}, top-10 overlap {ov['per_20']}/10) because "
          f"most holds are shorter than its 5-session floor, so it multiplies every such fund by the same constant and the holding-period adjustment does nothing for them. "
          f"Per holding session keeps {ov['per_session']} of the per-trade top 10; per fund session (idle cash included) keeps {ov['fund_per_session']}. "
          "The intervals around the top funds cross zero, and several top funds have a single entry date (no interval possible). "
          "A common framework reports all four bases and an interval beside each other; ranking on one of them is a decision for after the prospective test (A6).", "",
                    "## C3. Are the five slots five different bets?", ""]
    h = ex["holdings"]
    if len(h):
        L += ["Live positions now:", "", "| slot | symbol | entry | mark since entry % | industry division | beta |", "|---:|---|---:|---:|---|---:|"]
        for r in h.itertuples():
            L.append(f"| {r.slot} | {r.symbol} | {r.entry:.2f} | {f(r.mark_pct)} | {r.division} | {f(r.beta, '{:.2f}')} |")
        L += ["", f"Over the last year of daily closes ({ex['sessions']} sessions): average pairwise correlation of the five holdings {ex['avg_pair_corr']:+.2f}; "
              f"equal-weight beta to SPY {ex['beta_to_spy']:.2f}; diversification ratio {ex['diversification_ratio']:.2f} (1.00 = one bet, 2.24 = five independent bets of equal risk). "
              f"Mean beta of the five holdings {h['beta'].mean():.2f}.", ""]
        pairs = ex["corr"]
        L += ["| | " + " | ".join(pairs.columns) + " |", "|---|" + "---:|" * len(pairs.columns)]
        for a, r in pairs.iterrows():
            L.append(f"| {a} | " + " | ".join(f"{v:+.2f}" for v in r) + " |")
    L += ["", "Strategy-level correlation of the five holders (stored weekly series 2023 to today, `strategy_correlation`):", ""]
    if len(links):
        L += ["| slot pair | correlation |", "|---|---:|"]
        for r in links.itertuples():
            L.append(f"| {r.a}-{r.b} | {f(r.corr) if r.corr is not None else 'unmeasured'} |")
        L.append("")
    L += ["## Shadow comparison: current top-five rule vs a portfolio-aware alternative", "",
          "Both pick five funds per snapshot with one-per-family and the 0.7 correlation veto where a correlation is stored. They differ in the estimate they sort by: the stored score "
          "(current) or the empirical-Bayes estimate that shrinks each fund toward the pool by its date-based uncertainty (alternative). Realised = later honest net mean of the chosen funds, "
          "%, average of the five.", "",
          "| snapshot | funds | current | alternative | pool mean |", "|---|---:|---:|---:|---:|"]
    for r in sh.itertuples():
        L.append(f"| {r.date} | {r.funds} | {f(r.current)} | {f(r.aware)} | {f(r.pool)} |")
    if len(sh):
        L += ["", f"Mean over {len(sh)} snapshots: current {f(sh['current'].mean())} %, alternative {f(sh['aware'].mean())} %, pool {f(sh['pool'].mean())} %; "
              f"the alternative was at least as good on {int((sh['aware'] >= sh['current']).sum())} of {len(sh)} snapshots."]
    L += ["", "## What could be wrong with this analysis", "",
          "- Outcomes are 1 to 11 sessions long and from one regime; snapshots overlap heavily, so the comparison has fewer independent observations than rows.",
          "- Holdings correlation uses a year of daily closes of five names: it describes the exposure the positions carry, not the strategies' signals.",
          "- Sector and beta are heuristics (SIC division from the latest filing; monthly beta); the diversification ratio assumes equal weights.",
          "- The alternative is a shadow estimator only; it ignores the cash and settled-funds constraints, and it is not recommended for live use on this evidence.",
          "- Funds with fewer than 20 honest trades are excluded from C2; stand-in, pair and value slot holders have no paper run."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    now = datetime.now(timezone.utc)
    text = render(conn, cfg, now.strftime("%Y-%m-%d %H:%M UTC"))
    out = Path("reports") / f"audit_portfolio_{now:%Y-%m-%d}.md"
    out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
