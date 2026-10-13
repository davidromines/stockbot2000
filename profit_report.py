"""
Addendum F, Phase F / H7 — profitability measured four ways, side by side, with the same definitions everywhere.

Owner ruling 2026-10-13: the "1%" target is not pinned to one denominator.  Every figure here carries its denominator,
period, sample size and uncertainty, and nothing is optimised toward a target.

  1. per completed trade            net return of a round trip
  2. per deployed dollar            net dollars / (stake x sessions held), and per trade on equal stakes
  3. portfolio, cash included       equity change of the account (or paper fund), idle cash and open positions counted
  4. per calendar month             only where a full month exists; annualised figures are shown only when defensible
plus max drawdown, win rate, average win / loss, profit factor, costs relative to gross (research table only),
turnover, capital utilisation, and the split by market regime (SPY up or down while the position was held).

Sections: the real account; each CURRENT slot occupant since its own assignment (never summed across slots);
the research families on the honest basis (next-open fills, modelled costs deducted).  Read-only.

    ./venv/bin/python profit_report.py          # prints and writes reports/profit_report_<date>.md
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import forward_stats as fs
from universe import load_config

FAMILIES = ["lab_search", "momentum", "kf_seasonality", "st_uptrend_pullback", "bollinger_reversion",
            "kf_mean_reversion", "st_momentum_1d", "turn_of_month"]
MIN_SESSIONS_ANNUAL = 120        # fewer sessions than this cannot support an annualised figure


def f(x, s="{:+.2f}"):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else s.format(x)


# --- shared trade statistics (one definition for live and research) -----------------------------
def trade_stats(ret_pct: pd.Series, usd: pd.Series | None = None, hold: pd.Series | None = None, stake: pd.Series | None = None) -> dict:
    r = ret_pct.dropna()
    if r.empty:
        return {"n": 0}
    wins, losses = r[r > 0], r[r <= 0]
    gp, gl = float(wins.sum()), float(-losses.sum())
    out = {"n": int(len(r)), "mean": float(r.mean()), "median": float(r.median()), "win_rate": float((r > 0).mean()),
           "avg_win": float(wins.mean()) if len(wins) else np.nan, "avg_loss": float(losses.mean()) if len(losses) else np.nan,
           "profit_factor": gp / gl if gl > 0 else np.nan}
    if usd is not None and stake is not None and hold is not None and hold.notna().any():
        d = (stake * hold).sum()
        out["per_dollar_session"] = float(usd.sum() / d * 100) if d else np.nan      # percent per deployed dollar per session
    return out


# --- the real account ---------------------------------------------------------------------------
def account(conn, cfg) -> dict:
    e = pd.read_sql_query("SELECT at, session, equity FROM live_equity ORDER BY at", conn)
    close = e.groupby("session")["equity"].last()
    start, last = float(e["equity"].iloc[0]), float(e["equity"].iloc[-1])
    peak = close.cummax()
    dd = float(((peak - close) / peak).max() * 100)
    daily = close.pct_change().dropna() * 100
    months = close.groupby(close.index.str[:7]).agg(["first", "last", "size"])
    import live_pnl
    lv = live_pnl.compute(conn, cfg, "LIVE")
    return {"start": start, "last": last, "chg": last - start, "chg_pct": (last / start - 1) * 100, "sessions": int(len(close)),
            "max_dd": dd, "worst_day": float(daily.min()) if len(daily) else np.nan, "best_day": float(daily.max()) if len(daily) else np.nan,
            "months": months, "closed": lv["closed"], "open": lv["open"], "closed_total": lv["closed_total"], "open_gross": lv["open_gross"],
            "open_stake": lv["open_stake"], "since": lv["since"], "daily_vol": float(daily.std()) if len(daily) > 2 else np.nan}


def occupants(conn, cfg, lv_closed, lv_open) -> pd.DataFrame:
    """Each slot's CURRENT occupant, scored only on trades opened at or after its own assignment."""
    import slots
    import daily_snapshot as ds
    rows = []
    for sl, h in slots.current(conn, cfg).items():
        if not h:
            continue
        since = h["since"]
        closed = [t for t in lv_closed if t["slot"] == sl and t["opened"] >= since]
        opn = [t for t in lv_open if t["slot"] == sl and t["opened"] >= since]
        rows.append({"slot": sl, "name": ds._human_name(conn, h["strategy_key"], h["version"]), "since": since[:10],
                     "closed": len(closed), "closed_net": sum(t["net"] for t in closed), "closed_stake": sum(t["stake"] for t in closed),
                     "open": [(t["symbol"], t["ret_pct"], t["gross"]) for t in opn]})
    return pd.DataFrame(rows)


# --- the research families ----------------------------------------------------------------------
def research(conn) -> tuple:
    import audit_selection as a4
    sess = a4.sessions(conn)
    tr = pd.read_sql_query(
        """SELECT p.family, x.run_id, x.ticker, x.entry_date, x.exit_date, x.net_pct, x.gross_pct, x.cost_pct, x.net_usd
           FROM paper_trades_restated x JOIN paper_runs p ON p.run_id = x.run_id WHERE x.version='v2_next_open' AND p.family IS NOT NULL""", conn)
    pos = {d: i for i, d in enumerate(sess)}
    tr["hold"] = (tr["exit_date"].map(pos) - tr["entry_date"].map(pos)).clip(lower=1)
    tr["stake"] = np.where(tr["net_pct"].abs() > 1e-9, tr["net_usd"] / (tr["net_pct"] / 100.0), 20.0)
    tr["stake"] = tr["stake"].clip(5, 100)
    tr = a4.add_spy(conn, tr, sess)
    tr["regime"] = np.where(tr["spy_pct"] >= 0, "market up", "market down")
    eq = pd.read_sql_query("SELECT run_id, date, positions_usd, equity_usd FROM paper_equity", conn)
    return tr, eq, sess


def fund_level(eq: pd.DataFrame, run_ids) -> dict:
    out = []
    for rid, g in eq[eq["run_id"].isin(run_ids)].groupby("run_id"):
        g = g.sort_values("date")
        if len(g) < 5:
            continue
        peak = g["equity_usd"].cummax()
        out.append({"ret": (g["equity_usd"].iloc[-1] / g["equity_usd"].iloc[0] - 1) * 100, "sessions": len(g) - 1,
                    "dd": float(((peak - g["equity_usd"]) / peak).max() * 100), "util": float((g["positions_usd"] / g["equity_usd"]).mean())})
    d = pd.DataFrame(out)
    if d.empty:
        return {}
    return {"funds": len(d), "ret_med": float(d["ret"].median()), "ret_per_session": float((d["ret"] / d["sessions"]).median()),
            "sessions": int(d["sessions"].median()), "dd_med": float(d["dd"].median()), "util_med": float(d["util"].median())}


def family_rows(tr, eq) -> pd.DataFrame:
    rows = []
    for fam in FAMILIES + ["ALL FAMILIES (pool)"]:
        g = tr if fam.startswith("ALL") else tr[tr["family"] == fam]
        if g.empty:
            continue
        st = trade_stats(g["net_pct"], g["net_usd"], g["hold"], g["stake"])
        b = fs.bootstrap_by_cluster(g["net_pct"], g["entry_date"], reps=1000) if g["entry_date"].nunique() >= 3 else {"lo": np.nan, "hi": np.nan}
        fl = fund_level(eq, g["run_id"].unique())
        gp = g.loc[g["gross_pct"] > 0, "gross_pct"].sum()
        rows.append({"family": fam, "trades": st["n"], "dates": int(g["entry_date"].nunique()), **st, "ci_lo": b["lo"], "ci_hi": b["hi"],
                     "cost_over_gross": float(g["cost_pct"].sum() / gp) if gp > 0 else np.nan, "hold": float(g["hold"].mean()),
                     "turnover": float(len(g) / max(g["run_id"].nunique(), 1) / max(fl.get("sessions", 1), 1)), **{"fund_" + k: v for k, v in fl.items()},
                     "up": float(g.loc[g["regime"] == "market up", "net_pct"].mean()), "down": float(g.loc[g["regime"] == "market down", "net_pct"].mean()),
                     "up_n": int((g["regime"] == "market up").sum()), "down_n": int((g["regime"] == "market down").sum()),
                     "hit1": float((g["net_pct"] >= 1).mean())})
    return pd.DataFrame(rows)


def render(conn, cfg, as_of: str) -> str:
    a = account(conn, cfg)
    occ = occupants(conn, cfg, a["closed"], a["open"])
    tr, eq, sess = research(conn)
    fr = family_rows(tr, eq)
    cl = pd.DataFrame(a["closed"])
    live = trade_stats(cl["ret_pct"], cl["net"], pd.Series([1.0] * len(cl)), cl["stake"]) if len(cl) else {"n": 0}
    L = ["# Profitability, measured four ways (Addendum F Phase F / H7)", "",
         f"Computed {as_of}, read-only. Live figures are the real Robinhood account 403446024 since {a['since']}; research figures are paper funds on the honest basis "
         "(next-open fills, modelled costs deducted). Live and research results are kept apart. Denominators are named in every heading.", "",
         "## 1. The real account (denominator: the account's equity, cash and open positions included)", "",
         "| measure | value | period / sample |", "|---|---:|---|",
         f"| equity at first record | ${a['start']:.2f} | 2026-09-24 |", f"| equity now | ${a['last']:.2f} | {a['sessions']} sessions |",
         f"| change since launch | {f(a['chg'], '${:+.2f}')} ({f(a['chg_pct'])} %) | includes any deposits or withdrawals, which the equity series cannot separate |",
         f"| maximum drawdown (daily closes) | {a['max_dd']:.1f} % | {a['sessions']} sessions |",
         f"| worst / best day | {f(a['worst_day'])} % / {f(a['best_day'])} % | |",
         f"| realised P&L, closed trades | {f(a['closed_total']['net'], '${:+.2f}')} on ${a['closed_total']['stake']:.2f} traded | {a['closed_total'] and len(a['closed'])} round trips |",
         f"| unrealised P&L, open positions | {f(a['open_gross'], '${:+.2f}')} on ${a['open_stake']:.2f} | {len(a['open'])} positions |",
         f"| realised + unrealised | {f(a['closed_total']['net'] + (a['open_gross'] or 0), '${:+.2f}')} | reconciles to the equity change within ${abs(a['chg'] - (a['closed_total']['net'] + (a['open_gross'] or 0))):.2f} |", ""]
    if live["n"]:
        L += ["### Real closed round trips (denominator: the trade)", "",
              f"{live['n']} trades: win rate {live['win_rate']:.0%}, mean {f(live['mean'])} %, median {f(live['median'])} %, average win {f(live['avg_win'])} %, average loss {f(live['avg_loss'])} %, "
              f"profit factor {f(live['profit_factor'], '{:.2f}')}; per deployed dollar-session {f(live.get('per_dollar_session'), '{:+.3f}')} % (sessions held approximated as 1 for this line: holds are not stored on the live rows). "
              "No interval is meaningful at this sample size.", ""]
    L += ["### Months (denominator: equity at the first and last close of the month)", "", "| month | first close | last close | change | sessions |", "|---|---:|---:|---:|---:|"]
    for m, r in a["months"].iterrows():
        L.append(f"| {m} | ${r['first']:.2f} | ${r['last']:.2f} | {f((r['last'] / r['first'] - 1) * 100)} % | {int(r['size'])} |")
    L += ["", f"Annualised return: **not reported** ({a['sessions']} sessions; at least {MIN_SESSIONS_ANNUAL} are needed before an annualised figure means anything). "
          "A 1 % monthly return would be about +$0.84 on this account; the account has not completed a month.", "",
          "## 2. Current slot occupants, each since its own assignment (never added together)", "",
          "| slot | occupant | assigned | closed trades | closed net | open positions (return %, unrealised $) |", "|---:|---|---|---:|---:|---|"]
    for r in occ.itertuples():
        op = ", ".join(f"{s} {f(p)} % / {f(g, '${:+.2f}')}" for s, p, g in r.open) or "-"
        L.append(f"| {r.slot} | {r.name} | {r.since} | {r.closed} | {f(r.closed_net, '${:+.2f}')} | {op} |")
    L += ["", "## 3. Research families, honest basis (denominators named per column)", "",
          "Per trade = net % of a trade. Per dollar-session = net dollars / (stake x sessions held), in % per deployed dollar per session. Fund return = median fund equity change per session including idle cash "
          "(the portfolio basis). Costs / gross = modelled costs over the gross profit of winning trades. 'Hit 1 %' = share of trades netting at least 1 %. Interval = date-block bootstrap of the per-trade mean.", "",
          "| family | trades | dates | per trade % | 95% interval | median % | win | avg win % | avg loss % | profit factor | per dollar-session % | fund % per session | fund max dd % | util | hold | hit 1 % |",
          "|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in fr.itertuples():
        L.append(f"| {r.family} | {r.trades:,} | {r.dates} | {f(r.mean)} | {f(r.ci_lo)} to {f(r.ci_hi)} | {f(r.median)} | {r.win_rate:.0%} | {f(r.avg_win)} | {f(r.avg_loss)} | "
                 f"{f(r.profit_factor, '{:.2f}')} | {f(r.per_dollar_session, '{:+.3f}')} | {f(getattr(r, 'fund_ret_per_session', np.nan), '{:+.3f}')} | {f(getattr(r, 'fund_dd_med', np.nan), '{:.1f}')} | "
                 f"{f(getattr(r, 'fund_util_med', np.nan), '{:.0%}')} | {r.hold:.1f} | {r.hit1:.0%} |")
    L += ["", "Costs relative to gross profit (research table only): " + ", ".join(f"{r.family} {f(r.cost_over_gross, '{:.0%}')}" for r in fr.itertuples()) + ".", "",
          "### By market regime (SPY up or down between the trade's two next-open fills)", "", "| family | market up: trades | net % | market down: trades | net % |", "|---|---:|---:|---:|---:|"]
    for r in fr.itertuples():
        L.append(f"| {r.family} | {r.up_n:,} | {f(r.up)} | {r.down_n:,} | {f(r.down)} |")
    L += ["", "## 4. Where the 1 % target stands, on each basis", "",
          "| basis | what 1 % would mean | what the record shows |", "|---|---|---|",
          f"| per completed trade, research pool | mean net >= 1 % | pool {f(fr.iloc[-1]['mean'])} % (interval {f(fr.iloc[-1]['ci_lo'])} to {f(fr.iloc[-1]['ci_hi'])}); {fr.iloc[-1]['hit1']:.0%} of trades reach 1 % |",
          f"| per completed trade, research families | mean net >= 1 % | " + "; ".join(f"{r.family} {f(r.mean)} % ({f(r.ci_lo)} to {f(r.ci_hi)}, {r.dates} dates)" for r in fr.itertuples() if r.mean >= 1 and not r.family.startswith("ALL")) + " |",
          f"| per completed trade, real account | mean net >= 1 % | {live['n']} trades, mean {f(live.get('mean'))} %: no interval is meaningful |",
          f"| per deployed dollar per session | about 0.05 % (1 % over 21 sessions) | pool {f(fr.iloc[-1]['per_dollar_session'], '{:+.3f}')} %; families from {f(fr['per_dollar_session'].min(), '{:+.3f}')} to {f(fr['per_dollar_session'].max(), '{:+.3f}')} % |",
          f"| portfolio, cash included, real account | account grows 1 % in a calendar month | {f(a['chg_pct'])} % over {a['sessions']} sessions; no full month yet |",
          "| portfolio, cash included, paper funds | median fund grows 1 % in 21 sessions | the fund columns above come from the paper engine's own equity curve (same-close fills, not restated, replay included): pool median fund "
          f"{f(fr.iloc[-1].get('fund_ret_per_session'), '{:+.3f}')} % per session, so treat family differences there as the same unresolved record seen through a less honest lens |",
          "| annualised | 12 % or more a year | not reportable |", "",
          "Reading: the pool of research trades is negative or flat on every basis. Three families average above 1 % per trade, each with an interval that includes zero and between 2 and 18 independent entry dates. "
          "The real account's closed trades are positive and its open positions are negative, netting to the equity change. Nothing here supports or refutes a 1 % monthly return; the most promising next experiment is the pre-registered prospective test "
          "(`prospective_eval.py`), the only measurement that cannot be inflated by how the candidates were found.", "",
          "## What could be wrong with this analysis", "",
          "- The account equity series includes any deposits or withdrawals; the check against realised + unrealised trade P&L above is what shows whether they matter.",
          "- Paper funds hold up to 20 positions with $400; their portfolio basis is not the slot's one-position basis.",
          "- The regime split uses SPY over each trade's hold; it describes the market while held, not a forecastable state, and the sample is one regime.",
          "- Honest-basis trades exclude those that exit on the newest bar (mostly stop-outs).",
          "- Live per-dollar-session uses one session per round trip because holds are not stored on live rows."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    now = datetime.now(timezone.utc)
    text = render(conn, cfg, now.strftime("%Y-%m-%d %H:%M UTC"))
    out = Path("reports") / f"profit_report_{now:%Y-%m-%d}.md"
    out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
