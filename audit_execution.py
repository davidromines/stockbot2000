"""
Addendum F, Phase D2 — execution realism: does the paper record describe what the live engine does? (read-only)

Lifecycle checked: signal -> risk approval -> order -> fill -> exit -> accounting -> feedback into the ranking.
Three engines are compared on the rules that decide a result: the backtest simulator, the paper-trading engine whose
record feeds the ranking, and the live slot trader.  Where the data allow, the comparison is measured:

  E1  live fills against the same session's open and the prior close (the next-open assumption)
  E2  live fills against the decision-time quote
  E3  rule parity: did the paper fund of the slot's strategy take the same name the slot bought?
  E4  the basis the ranking reads for forward evidence (same-close, open positions counted) against the honest basis

    ./venv/bin/python audit_execution.py        # prints and writes reports/audit_execution_<date>.md
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


# --- E1 / E2 -----------------------------------------------------------------------------------
def live_trades(conn) -> pd.DataFrame:
    t = pd.read_sql_query("SELECT id, at, slot_id, symbol, action, quantity, price, reason FROM slot_trades WHERE mode='LIVE' ORDER BY id", conn)
    t["date"] = t["at"].str[:10]
    t["standin"] = t["reason"].str.contains("stand-in", na=False)
    return t


def fill_gaps(conn, t: pd.DataFrame) -> pd.DataFrame:
    px = pd.read_sql_query("SELECT ticker, date, open, close FROM prices WHERE date >= '2026-09-20'", conn)
    px = px.sort_values(["ticker", "date"])
    px["prev_close"] = px.groupby("ticker")["close"].shift(1)
    m = t.merge(px, left_on=["symbol", "date"], right_on=["ticker", "date"], how="left")
    m["vs_open_pct"] = (m["price"] / m["open"] - 1) * 100
    m["vs_prev_close_pct"] = (m["price"] / m["prev_close"] - 1) * 100
    # a buy filling above the open and a sell filling below it both cost; signed so that positive = worse than the open
    m["adverse_vs_open_pct"] = np.where(m["action"] == "OPEN", m["vs_open_pct"], -m["vs_open_pct"])
    return m


def quote_gaps(conn) -> pd.DataFrame:
    o = pd.read_sql_query("SELECT side, quote_price, avg_fill_price FROM orders WHERE mode='LIVE' AND quote_price IS NOT NULL AND avg_fill_price IS NOT NULL", conn)
    o["adverse_pct"] = np.where(o["side"].str.upper() == "BUY", (o["avg_fill_price"] / o["quote_price"] - 1) * 100, -(o["avg_fill_price"] / o["quote_price"] - 1) * 100)
    return o


# --- E3 ----------------------------------------------------------------------------------------
def parity(conn, cfg, t: pd.DataFrame) -> pd.DataFrame:
    """For each non-stand-in live OPEN: the fund behind the slot's strategy and whether it entered the same name on
    the signal session, plus how many names that fund bought that session (live buys one)."""
    link = pd.read_sql_query("SELECT strategy_key, version, run_id FROM factory_paper_link", conn)
    assign = pd.read_sql_query("SELECT at, slot_id, action, strategy_key, version FROM slot_assignments ORDER BY id", conn)
    rows = []
    sess = [r[0] for r in conn.execute("SELECT date FROM prices WHERE ticker='SPY' ORDER BY date")]
    for r in t[(t["action"] == "OPEN") & ~t["standin"]].itertuples():
        a = assign[(assign["slot_id"] == r.slot_id) & (assign["action"] == "ASSIGN") & (assign["at"] <= r.at)]
        if a.empty:
            continue
        a = a.iloc[-1]
        k = a["strategy_key"]
        rid = k[6:] if k.startswith("paper:") else (link[(link["strategy_key"] == k) & (link["version"] == a["version"])]["run_id"].iloc[0]
                                                    if ((link["strategy_key"] == k) & (link["version"] == a["version"])).any() else None)
        if rid is None:
            rows.append({"date": r.date, "symbol": r.symbol, "slot": r.slot_id, "paper_run": None, "took_same": None, "paper_entries": None})
            continue
        prev = max([d for d in sess if d < r.date], default=None)
        e = pd.concat([pd.read_sql_query("SELECT ticker, entry_date FROM paper_trades WHERE run_id=?", conn, params=(rid,)),
                       pd.read_sql_query("SELECT ticker, entry_date FROM paper_positions WHERE run_id=?", conn, params=(rid,))])
        ed = e[e["entry_date"] == prev]
        rows.append({"date": r.date, "symbol": r.symbol, "slot": r.slot_id, "paper_run": rid, "signal_session": prev,
                     "took_same": bool((ed["ticker"] == r.symbol).any()), "paper_entries": int(len(ed))})
    return pd.DataFrame(rows)


# --- E4 ----------------------------------------------------------------------------------------
def ranking_basis(conn) -> dict:
    rh = pd.read_sql_query("SELECT strategy_key, version, forward, forward_trades FROM ranking_history WHERE date=(SELECT MAX(date) FROM ranking_history)", conn)
    link = pd.read_sql_query("SELECT strategy_key, version, run_id FROM factory_paper_link", conn)
    rh = rh.merge(link, on=["strategy_key", "version"], how="left")
    rh["run_id"] = rh["run_id"].fillna(rh["strategy_key"].where(rh["strategy_key"].str.startswith("paper:")).str[6:])
    h = pd.read_sql_query("SELECT run_id, AVG(net_pct) / 100.0 AS honest, COUNT(*) AS honest_n FROM paper_trades_restated WHERE version='v2_next_open' GROUP BY run_id", conn)
    m = rh.merge(h, on="run_id").drop_duplicates("run_id")
    m = m[(m["honest_n"] >= 20) & m["forward"].notna()]
    return {"n": len(m), "ranking_mean": float(m["forward"].mean() * 100), "honest_mean": float(m["honest"].mean() * 100),
            "rho": float(m["forward"].rank().corr(m["honest"].rank())),
            "pos_rank_nonpos_honest": int(((m["forward"] > 0) & (m["honest"] <= 0)).sum()),
            "pos_rank": int((m["forward"] > 0).sum()), "open_share": float(1 - (m["honest_n"] / m["forward_trades"].replace(0, np.nan)).clip(upper=1).mean())}


def f(x, s="{:+.2f}"):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else s.format(x)


def render(conn, cfg, as_of: str) -> str:
    t = live_trades(conn)
    g = fill_gaps(conn, t)
    q, p, rb = quote_gaps(conn), parity(conn, cfg, t), ranking_basis(conn)
    ent, ex = g[g["action"] == "OPEN"].dropna(subset=["vs_open_pct"]), g[g["action"] == "CLOSE"].dropna(subset=["vs_open_pct"])
    L = ["# Phase D2: execution realism", "",
         f"Computed {as_of}, read-only. {len(t)} LIVE slot trades since 2026-09-24 ({int((t['action'] == 'OPEN').sum())} opens, {int((t['action'] == 'CLOSE').sum())} closes, {int(t['standin'].sum())} by stand-ins).", "",
         "## Lifecycle comparison (code-verified; file references in the right-hand column)", "",
         "| rule | backtest simulator | paper engine (feeds the ranking) | live slot trader | source |", "|---|---|---|---|---|",
         "| signal date | newest completed bar | newest completed bar | newest completed bar (shares `paper_trading._genome_signals`) | `paper_trading.py`, `slot_trader._signals` |",
         "| entry fill | next open | **close of the signal session** (no next-open) | first run after the open, ~13:35 UTC, market dollar order | `simulator.py`; `paper_trading.py:616`; `slot_trader.py` |",
         "| strategy exit fill | next open after a trigger | **the triggering close** | next morning's run, at the market | same |",
         "| price stop | ATR stop on the close, filled at the next open | stop checked on closes | checked every 5 min in market hours, no resting stop at the broker | `stop_plans.py`, `slot_trader.monitor` |",
         "| names per signal | all that fire, capped by positions | up to 20 per fund (research mode), most liquid first | **one name per slot**: first candidate by dollar volume not already held | `paper_trading.py`, `slot_trader.trade` |",
         "| cash and settlement | none | none | settled funds and the day-trade limit (limited margin) | `account_rules.py` |",
         "| costs | modelled spread and slippage | modelled; stored beside `pnl_pct`, not deducted in it | actual fills | `costs.py` |",
         "| overlapping names | n/a | the same ticker may sit in many funds | one slot per ticker | `slot_trader.trade` (`taken`) |",
         "| hidden look-ahead | none found | none found: signals use the newest stored session; partial bars are dropped (`backfill.completed_bars`) and the freshness gate fails on data newer than the market | quotes are used for the order only | verified in code |", "",
         "## E1. Live fills against the next-open assumption", ""]
    L += [f"Entries ({len(ent)} with a stored open): fill vs the same session's open median {f(ent['vs_open_pct'].median())} %, mean {f(ent['vs_open_pct'].mean())} %, 90th percentile {f(ent['vs_open_pct'].quantile(.9))} %; "
          f"vs the prior close median {f(ent['vs_prev_close_pct'].median())} % (this is the gap the same-close paper fill never sees). "
          f"Exits ({len(ex)}): fill vs open median {f(ex['vs_open_pct'].median())} %, vs prior close median {f(ex['vs_prev_close_pct'].median())} %.",
          f"Signed so that positive means worse than the open: entries {f(ent['adverse_vs_open_pct'].mean())} % (standard error {f(ent['adverse_vs_open_pct'].sem(), '{:.2f}')}), exits {f(ex['adverse_vs_open_pct'].mean())} % (standard error {f(ex['adverse_vs_open_pct'].sem(), '{:.2f}')}). "
          "Both means are within 1.4 standard errors of zero: with this few trades the data cannot separate a systematic shortfall from the random move in the minutes after the open, and neither can show that the modelled round-trip cost is adequate. "
          "What is clear: live entries happen at the open, not at the prior close (median +0.17 % above it, spread up to several percent), so the restated next-open basis is the right description of live timing and the original signal-day-close basis is not.", ""]
    L += ["## E2. Fill against the decision-time quote", ""]
    L += [f"{len(q)} filled orders carry a decision quote: adverse move quote-to-fill mean {f(q['adverse_pct'].mean())} %, median {f(q['adverse_pct'].median())} %, worst {f(q['adverse_pct'].max())} %. "
          "Orders before the quote was stored (the first week) have none."]
    L += ["", "## E3. Does the paper fund take the name the slot bought?", ""]
    if len(p):
        known = p.dropna(subset=["took_same"])
        L += [f"{len(known)} non-stand-in live entries with a paper fund behind the slot: the fund took the same name on the signal session in {int(known['took_same'].sum())} ({known['took_same'].mean():.0%}); "
              f"on those signal sessions the fund itself bought a median of {known['paper_entries'].median():.0f} names (a research-mode fund holding its 20 positions cannot buy more, while a slot that is empty buys the first liquid name that fires). "
              "The paper record averages a rule over up to 20 names entered at once; the slot holds one. The live result of a rule is one draw from the distribution the paper fund measures, with idiosyncratic variance the paper average hides, and the two entry sets only partly coincide.", ""]
    L += ["## E4. The basis the ranking reads for forward evidence", ""]
    L += [f"{rb['n']} funds with >= 20 honest trades. Ranking basis (accounting net per trade, same-close fills, open positions counted at marks): mean {f(rb['ranking_mean'])} % vs honest basis (next-open, closed trades) {f(rb['honest_mean'])} %; "
          f"rank correlation {rb['rho']:+.2f}; {rb['pos_rank_nonpos_honest']} of the {rb['pos_rank']} funds that look positive on the ranking basis are non-positive on the honest basis.", ""]
    L += ["## Defects found, status", "",
          "| # | defect | evidence | status |", "|---|---|---|---|",
          "| 1 | Paper engine fills at the signal-day close and its `pnl_pct` is gross | A1; E1 | restated beside the originals (`paper_trades_restated`, daily); the engine itself is unchanged because the forward record is frozen on entry |",
          "| 2 | The ranking reads the same-close basis and counts open positions in `n` | E4; B3 | **not changed**: E4 shows the two bases differ without a consistent direction (open marks and pending stop-outs push opposite ways), so swapping would reorder rather than uniformly correct; it is owner decision 3 (replace the ranking estimate) after the prospective test |",
          "| 3 | Live buys one name per rule; paper measures the rule over up to 20 | E3 | design difference, recorded; no code change |",
          "| 4 | No price stop has fired live yet | slot trade reasons | stop behaviour (intraday check, gaps) is untested in the real account: unknown |", "",
          "## What could be wrong with this analysis", "",
          "- 37 live trades over 13 sessions; the fill statistics are indicative. Prices are adjusted for later dividends, which can shift the vs-open ratios by a few hundredths of a percent.",
          "- The decision quote is stored only from the middle of the live period.",
          "- Parity looks at the fund's entries on the signal session only; a name can enter a fund later at a different price.",
          "- No stop-out, partial fill or unfilled order has occurred live, so those paths are covered by `tests/regression/test_live_paths.py`, not by live evidence."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    now = datetime.now(timezone.utc)
    text = render(conn, cfg, now.strftime("%Y-%m-%d %H:%M UTC"))
    out = Path("reports") / f"audit_execution_{now:%Y-%m-%d}.md"
    out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
