"""
Earnings-date study (Stage AD3.5). Read-only research. Decides nothing by itself: a rule it supports must still be
backtested before any strategy uses it.

Question: should a strategy that is not ABOUT earnings avoid holding a stock across its earnings announcement?

Method (pre-stated): for every 8-K item 2.02 (results of operations) in `edgar_events`, 2015-2025, on a liquid common
stock (>= $5, >= $1M/day): the event window = next open after the session before the announcement to the next open
`AFTER` sessions after it (an announcement accepted after 16:00 New York time belongs to the next session). Control = the
same stock's window of the same length ending `GAP` sessions before the event window, with no announcement inside it.
Both measured as excess return over SPY over the same opens.

Reported: mean excess (event vs control, paired by event, with a t), dispersion (sd and the share of |excess| > 10%).
Reading, stated in advance: if the event mean is not significantly above the control's AND the event sd is more than
1.3x the control's, holding through earnings adds risk without paying for it -> a "skip entries within N sessions
before a scheduled report" rule is worth backtesting for non-earnings strategies. Otherwise not.

    ./run_bounded.sh ./venv/bin/python earnings_study.py [--write]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

ROOT = Path(__file__).resolve().parent
BEFORE, AFTER, GAP = 1, 5, 10
START, END = "2015-01-01", "2025-12-31"


def events(conn, start=START, end=END) -> pd.DataFrame:
    e = pd.read_sql("SELECT DISTINCT ticker, filed, accepted FROM edgar_events WHERE item='2.02' AND form LIKE '8-K%' "
                    "AND filed >= ? AND filed <= ? AND ticker IS NOT NULL", conn, params=(start, end))
    acc = pd.to_datetime(e["accepted"], utc=True, errors="coerce").dt.tz_convert("America/New_York")
    after_close = acc.dt.hour * 60 + acc.dt.minute >= 16 * 60
    e["day"] = acc.dt.strftime("%Y-%m-%d").where(acc.notna(), e["filed"])
    e["after_close"] = after_close.fillna(False)
    return e[["ticker", "day", "after_close"]].drop_duplicates()


def windows(conn, ev: pd.DataFrame, spy: pd.Series, panel_open: dict, dv: dict) -> pd.DataFrame:
    """Event and control excess returns per announcement."""
    days = list(spy.index)
    arr = np.array(days)
    pos = {d: i for i, d in enumerate(days)}
    out = []
    by_t = {t: set(g["day"]) for t, g in ev.groupby("ticker")}
    for r in ev.itertuples():
        o = panel_open.get(r.ticker)
        if o is None:
            continue
        # the event session: the first session on or after the announcement day; the next one when it came after the close
        i = int(np.searchsorted(arr, r.day))
        if i >= len(days):
            continue
        if r.after_close and days[i] == r.day:
            i += 1
        a, b = i - BEFORE, i + AFTER                       # open of session a .. open of session b
        ca, cb = a - GAP - (b - a), a - GAP
        if ca < 0 or b >= len(days):
            continue
        ev_days = {pos[d] for d in by_t.get(r.ticker, ()) if d in pos}
        if any(ca <= k <= cb for k in ev_days):
            continue                                       # the control window holds an announcement too
        d_a, d_b, d_ca, d_cb = days[a], days[b], days[ca], days[cb]
        if not all(x in o.index for x in (d_a, d_b, d_ca, d_cb)):
            continue
        if (dv.get(r.ticker, {}).get(d_a) or 0) < 1e6 or o[d_a] < 5:
            continue
        spy_ev = spy[d_b] / spy[d_a] - 1
        spy_c = spy[d_cb] / spy[d_ca] - 1
        out.append({"ticker": r.ticker, "day": days[i], "event": o[d_b] / o[d_a] - 1 - spy_ev,
                    "control": o[d_cb] / o[d_ca] - 1 - spy_c})
    d = pd.DataFrame(out)
    return d[(d["event"].abs() < 3) & (d["control"].abs() < 3)] if len(d) else d


def load(conn, tickers: list, start: str, end: str) -> tuple:
    spy = pd.read_sql("SELECT date, open FROM prices WHERE ticker='SPY' AND date >= ? AND date <= ? ORDER BY date", conn,
                      params=(start, end)).set_index("date")["open"]
    opens, dvs = {}, {}
    for k in range(0, len(tickers), 400):
        chunk = tickers[k:k + 400]
        q = ",".join("?" * len(chunk))
        px = pd.read_sql(f"SELECT ticker, date, open FROM prices WHERE ticker IN ({q}) AND date >= ? AND date <= ?", conn,
                         params=(*chunk, start, end))
        for t, g in px.groupby("ticker"):
            opens[t] = g.set_index("date")["open"]
        f = pd.read_sql(f"SELECT ticker, date, dollar_volume_20 FROM features WHERE ticker IN ({q}) AND date >= ? AND date <= ?",
                        conn, params=(*chunk, start, end))
        for t, g in f.groupby("ticker"):
            dvs[t] = dict(zip(g["date"], g["dollar_volume_20"]))
    return spy, opens, dvs


def summarize(d: pd.DataFrame) -> dict:
    if d.empty:
        return {"n": 0}
    diff = d["event"] - d["control"]
    t = diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))) if len(diff) > 2 else float("nan")
    sd_e, sd_c = float(d["event"].std()), float(d["control"].std())
    big_e, big_c = float((d["event"].abs() > 0.10).mean()), float((d["control"].abs() > 0.10).mean())
    supports = (not (t >= 2)) and sd_e > 1.3 * sd_c
    return {"n": int(len(d)), "mean_event": float(d["event"].mean()), "mean_control": float(d["control"].mean()),
            "diff": float(diff.mean()), "t": float(t), "sd_event": sd_e, "sd_control": sd_c, "big_event": big_e,
            "big_control": big_c, "supports_skip_rule": bool(supports)}


def render(s: dict) -> str:
    if not s.get("n"):
        return "# Earnings-date study\n\nNo events.\n"
    f = lambda v: f"{v:+.2%}"                     # noqa: E731
    return "\n".join([
        f"# Earnings-date study — {date.today().isoformat()} (Stage AD3.5)", "",
        f"{s['n']:,} announcements (8-K 2.02, {START[:4]}-{END[:4]}), liquid common stock. Window: open of the session "
        f"before the announcement to the open {AFTER} sessions after; control: the same stock, same length, ending {GAP} "
        "sessions earlier, no announcement inside. Excess over SPY.", "",
        "| | across the announcement | control | difference (t) |", "|---|---:|---:|---:|",
        f"| mean excess | {f(s['mean_event'])} | {f(s['mean_control'])} | {f(s['diff'])} ({s['t']:+.1f}) |",
        f"| sd of excess | {s['sd_event']:.2%} | {s['sd_control']:.2%} | x{s['sd_event'] / s['sd_control']:.2f} |",
        f"| share with |excess| > 10% | {s['big_event']:.1%} | {s['big_control']:.1%} | |", "",
        ("**Reading (rule stated before running): holding through earnings adds risk without a measurable reward — a skip "
         "rule is worth backtesting for non-earnings strategies.**" if s["supports_skip_rule"] else
         "**Reading (rule stated before running): the evidence does not support a skip rule.**"), "",
        "Caveats: survivors only (the database's own bias); 8-K 2.02 marks the release, which can precede the call; "
        "a one-sided read on the mean; this is a population average, not any one strategy's trades."]) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    ev = events(conn)
    spy, opens, dvs = load(conn, sorted(ev["ticker"].unique()), "2014-06-01", "2026-03-31")
    s = summarize(windows(conn, ev, spy, opens, dvs))
    text = render(s)
    print(text)
    if a.write:
        p = ROOT / "reports" / f"earnings_study_{date.today().isoformat()}.md"
        p.write_text(text)
        print(f"written {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
