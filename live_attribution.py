"""
Live attribution (Stage AD9.1-9.4): where the real account's money went, trade by trade. Read-only.

For every LIVE slot trade (OPEN paired with its CLOSE, or still open and marked at the last stored close):

    return       the trade's own price move (fill to fill; open trades to the last stored close)
    spy          what SPY did over the same days (entry-day open to exit-day close): the counterfactual for the
                 same dollars left in the market
    excess       return - spy: the selection result, separated from the market's move
    exit         the recorded reason (strategy exit, stop, slot released or reassigned, intraday ...)
    days         calendar days held
    vol_pct      the name's ATR(14)/close percentile among liquid common stocks on its entry date
    fill_vs_quote  the fill against the decision-time quote stored on the order (buys: positive = paid more)

and, for the account: equity first / latest / peak, the drawdown, realised + unrealised from the ledger, the gap
between the ledger and the equity change, and the equal-weight beta of the open book (risk_metrics).

The strategy-review alert at `strategy_review_percent` (drawdown_tiers.py, owner 2026-10-19) points at the report
this writes. It answers the review's question with numbers: are losses coming from prediction (excess < 0 on the
strategies' own exits), execution (fill vs quote), turnover (reassignment exits), or allocation (volatility / beta)?

    ./venv/bin/python live_attribution.py            # print
    ./venv/bin/python live_attribution.py --write    # also reports/live_attribution_<date>.md
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

ROOT = Path(__file__).resolve().parent


def trades(conn, mode: str = "LIVE") -> pd.DataFrame:
    """OPEN/CLOSE pairs from slot_trades for one mode; an unmatched OPEN is an open position (exit NaN)."""
    rows = pd.read_sql("SELECT id, at, slot_id, strategy_key, version, symbol, action, quantity, price, atr, "
                       "stop_plan, reason FROM slot_trades WHERE mode=? ORDER BY id", conn, params=(mode,))
    opens, out = {}, []
    for r in rows.itertuples():
        k = (r.slot_id, r.symbol)
        if r.action == "OPEN":
            opens[k] = r
        elif r.action == "CLOSE" and k in opens:
            o = opens.pop(k)
            out.append(_pair(o, r))
    for o in opens.values():
        out.append(_pair(o, None))
    return pd.DataFrame(out)


def _stop_width(o) -> float:
    try:
        plan = json.loads(o.stop_plan or "[]")
    except ValueError:
        return float("nan")
    mult = [x.get("atr_multiple") for x in plan if x.get("type") == "atr"]
    pct = [x.get("pct") for x in plan if "pct" in x]
    if mult and o.atr and o.price:
        return float(mult[0]) * float(o.atr) / float(o.price)
    return float(min(pct)) / 100 if pct else float("nan")


def _pair(o, c) -> dict:
    return {"slot": int(o.slot_id), "symbol": o.symbol, "strategy": o.strategy_key, "entry_at": o.at,
            "entry_date": o.at[:10], "entry": float(o.price), "qty": float(o.quantity),
            "exit_at": c.at if c is not None else None, "exit_date": c.at[:10] if c is not None else None,
            "exit": float(c.price) if c is not None else np.nan,
            "exit_reason": (c.reason if c is not None else "open"), "stop_width": _stop_width(o),
            "intraday": str(o.strategy_key).startswith("intraday:")}


def _last_close(conn, symbol: str, mode: str = "LIVE"):
    """The newest mark for an open position: the slot monitor's own live quote (slot_marks), else the last close."""
    m = conn.execute("SELECT at, price FROM slot_marks WHERE mode=? AND symbol=? AND price IS NOT NULL "
                     "ORDER BY id DESC LIMIT 1", (mode, symbol)).fetchone()
    r = conn.execute("SELECT date, close FROM prices WHERE ticker=? ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
    if m and (not r or m[0][:10] >= r[0]):
        return m[0][:10], float(m[1])
    return (r[0], float(r[1])) if r else (None, np.nan)


def _spy_over(spy: pd.DataFrame, a: str, b: str) -> float:
    """SPY from the open of the first session >= a to the close of the last session <= b."""
    s = spy[spy.index >= a]
    e = spy[spy.index <= b]
    if not len(s) or not len(e) or e.index[-1] < s.index[0]:
        return np.nan
    return float(e["close"].iloc[-1] / s["open"].iloc[0] - 1)


def _vol_percentile(conn, symbol: str, day: str) -> float:
    """ATR(14)/close percentile of `symbol` among common stocks >= $5 and >= $1M/day on the last stored date <= day."""
    d = conn.execute("SELECT MAX(date) FROM features WHERE date <= ?", (day,)).fetchone()[0]
    if not d:
        return np.nan
    f = pd.read_sql("SELECT f.ticker, f.atr_14 / p.close AS v FROM features f JOIN prices p ON p.ticker=f.ticker "
                    "AND p.date=f.date JOIN symbols s ON s.ticker=f.ticker WHERE f.date=? AND "
                    "s.security_type='common_stock' AND p.close >= 5 AND f.dollar_volume_20 >= 1e6", conn, params=(d,))
    me = f[f.ticker == symbol]
    if not len(me) or not len(f):
        return np.nan
    return float((f.v < me.v.iloc[0]).mean() * 100)


def _beta(conn, symbol: str) -> float:
    r = conn.execute("SELECT beta FROM risk_metrics WHERE ticker=? AND beta IS NOT NULL ORDER BY date DESC LIMIT 1",
                     (symbol,)).fetchone()
    return float(r[0]) if r else np.nan


def _fill_vs_quote(conn, symbol: str, at: str, side: str) -> float:
    """(fill / decision-time quote - 1) for the order nearest the trade time; positive = worse for a buy."""
    r = conn.execute("SELECT avg_fill_price, quote_price FROM orders WHERE mode='LIVE' AND symbol=? AND side=? AND "
                     "quote_price IS NOT NULL AND avg_fill_price IS NOT NULL AND substr(created_at,1,10)=? "
                     "ORDER BY ABS(julianday(created_at) - julianday(?)) LIMIT 1",
                     (symbol, side, at[:10], at)).fetchone()
    if not r or not r[1]:
        return np.nan
    v = float(r[0]) / float(r[1]) - 1
    return v if side == "BUY" else -v


def build(conn, mode: str = "LIVE") -> dict:
    t = trades(conn, mode)
    if t.empty:
        return {"trades": t, "account": {}, "by_exit": pd.DataFrame()}
    spy = pd.read_sql("SELECT date, open, close FROM prices WHERE ticker='SPY' AND date >= ? ORDER BY date", conn,
                      params=(t.entry_date.min(),)).set_index("date")
    marks = []
    for i, r in t.iterrows():
        if pd.isna(r.exit):
            d, px = _last_close(conn, r.symbol, mode)
            t.at[i, "exit"] = px
            marks.append(d)
        else:
            marks.append(r.exit_date)
    t["mark_date"] = marks
    t["ret"] = t.exit / t.entry - 1
    t["pnl"] = (t.exit - t.entry) * t.qty
    t["spy"] = [np.nan if r.intraday else _spy_over(spy, r.entry_date, r.mark_date) for r in t.itertuples()]
    t["excess"] = t.ret - t.spy
    t["days"] = [(pd.Timestamp(b) - pd.Timestamp(a)).days if b else np.nan for a, b in zip(t.entry_date, t.mark_date)]
    t["vol_pct"] = [_vol_percentile(conn, r.symbol, r.entry_date) for r in t.itertuples()]
    t["fill_vs_quote"] = [_fill_vs_quote(conn, r.symbol, r.entry_at, "BUY") for r in t.itertuples()]
    t["kind"] = np.where(t.exit_reason == "open", "open",
                         np.where(t.exit_reason.str.startswith("slot released"), "reassignment",
                                  np.where(t.exit_reason.str.startswith("intraday"), "intraday",
                                           np.where(t.exit_reason.str.contains("stop|take profit|time", case=False),
                                                    "stop/limit", "strategy exit"))))
    by_exit = t.groupby("kind").agg(trades=("ret", "size"), mean_ret=("ret", "mean"), mean_excess=("excess", "mean"),
                                    pnl=("pnl", "sum"), median_days=("days", "median"))
    eq = pd.read_sql("SELECT at, equity FROM live_equity ORDER BY at", conn)
    acct = {}
    if len(eq):
        first, last, peak = float(eq.equity.iloc[0]), float(eq.equity.iloc[-1]), float(eq.equity.max())
        closed = t[t.kind != "open"]
        acct = {"first": first, "latest": last, "peak": peak, "change": last - first,
                "drawdown_pct": (peak - last) / peak * 100 if peak else 0.0,
                "realised": float(closed.pnl.sum()), "unrealised": float(t[t.kind == "open"].pnl.sum()),
                "first_at": eq["at"].iloc[0], "latest_at": eq["at"].iloc[-1]}
        acct["ledger_gap"] = acct["change"] - (acct["realised"] + acct["unrealised"])
        held = t[t.kind == "open"]
        acct["book_beta"] = float(np.nanmean([_beta(conn, s) for s in held.symbol])) if len(held) else np.nan
        acct["spy_since_first"] = _spy_over(spy, eq["at"].iloc[0][:10], eq["at"].iloc[-1][:10])
    return {"trades": t, "account": acct, "by_exit": by_exit}


def verdict(r: dict) -> list:
    """The review's four questions, answered from the numbers (plain statements, no judgement words)."""
    t, b = r["trades"], r["by_exit"]
    out = []
    if t.empty:
        return ["no live trades"]
    own = t[t.kind.isin(["strategy exit", "stop/limit"])]
    if len(own):
        out.append(f"Prediction: {len(own)} trades closed by their own rule or stop, mean {own.ret.mean():+.2%}, "
                   f"{own.excess.mean():+.2%} vs SPY over the same days.")
    if "reassignment" in b.index:
        x = b.loc["reassignment"]
        out.append(f"Turnover: {int(x.trades)} of {int((t.kind != 'open').sum())} closed trades were forced by slot "
                   f"reassignment, mean {x.mean_ret:+.2%} ({x.mean_excess:+.2%} vs SPY), median hold "
                   f"{x.median_days:.0f} days.")
    fq = t.fill_vs_quote.dropna()
    if len(fq):
        out.append(f"Execution: buys filled {fq.mean():+.2%} against the decision-time quote on average "
                   f"({len(fq)} orders with a stored quote).")
    v = t.vol_pct.dropna()
    if len(v):
        out.append(f"Allocation: {int((v >= 75).sum())} of {len(v)} names were in the top volatility quartile at "
                   f"entry; open-book beta {r['account'].get('book_beta', float('nan')):.2f}.")
    return out


def render(r: dict) -> str:
    t, a = r["trades"], r["account"]
    L = [f"# Live attribution — {date.today().isoformat()}", ""]
    if a:
        L += [f"Account ${a['latest']:.2f} (first ${a['first']:.2f}, peak ${a['peak']:.2f}): "
              f"{a['change']:+.2f} ({a['change'] / a['first']:+.1%}); drawdown {a['drawdown_pct']:.1f}% from the peak. "
              f"SPY over the same period {a['spy_since_first']:+.1%}.",
              f"Ledger: realised {a['realised']:+.2f}, unrealised {a['unrealised']:+.2f}; gap to the equity change "
              f"{a['ledger_gap']:+.2f} (dividends, cash interest and rounding are not in the trade ledger).", ""]
    L += ["## What the numbers say", ""] + [f"- {x}" for x in verdict(r)] + [""]
    if not r["by_exit"].empty:
        b = r["by_exit"].copy()
        L += ["## By how the trade ended", "", "| ended by | trades | mean return | vs SPY | P&L $ | median days |",
              "|---|---:|---:|---:|---:|---:|"]
        for k, x in b.iterrows():
            L.append(f"| {k} | {int(x.trades)} | {x.mean_ret:+.2%} | {x.mean_excess:+.2%} | {x.pnl:+.2f} | "
                     f"{x.median_days:.0f} |")
        L.append("")
    if not t.empty:
        L += ["## Every trade", "", "| slot | symbol | entered | ended | days | return | SPY | vs SPY | vol pct | "
              "stop width | ended by |", "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
        f = lambda v, s="{:+.2%}": "n/a" if v != v else s.format(v)     # noqa: E731
        for x in t.itertuples():
            L.append(f"| {x.slot} | {x.symbol} | {x.entry_date} | {x.mark_date or ''} | {f(x.days, '{:.0f}')} | "
                     f"{f(x.ret)} | {f(x.spy)} | {f(x.excess)} | {f(x.vol_pct, '{:.0f}')} | "
                     f"{f(x.stop_width, '{:.0%}')} | {x.kind} |")
    L += ["", "SPY = entry-day open to exit-day close (open trades: to the last stored close). vol pct = ATR(14)/close "
          "percentile among liquid common stocks on the entry date. Read-only; changes nothing."]
    return "\n".join(L) + "\n"


def summary_line(r: dict) -> str:
    """One line for the daily report: the account against SPY over the same period."""
    a = r.get("account") or {}
    if not a:
        return ""
    return (f"Since {a['first_at'][:10]}: account {a['change'] / a['first']:+.1%}, SPY {a['spy_since_first']:+.1%} "
            f"over the same days.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--mode", default="LIVE")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    r = build(conn, a.mode)
    text = render(r)
    print(text)
    if a.write:
        p = ROOT / "reports" / f"live_attribution_{date.today().isoformat()}.md"
        p.write_text(text)
        print(f"written {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
