"""
Stop study from the forward record (Stage AD3.6). Read-only research; changes no stop.

For every restated paper trade (`paper_trades_restated`, next-open fills): the maximum adverse excursion (MAE: the
worst low between the fill and the exit, against the fill) and the maximum favourable excursion (MFE: the best high),
both in units of the stock's ATR(14) at entry, beside the stop the strategy actually carries (genome
`risk.stop_atr_multiple`). Per family:

    winners' MAE p50 / p90   how far trades that ended positive went against us first. A stop tighter than the p90
                             would have stopped out more than one winner in ten.
    losers' MFE p50          how far trades that ended negative were up first (a trailing stop's opportunity)
    configured stop          median stop multiple of the family's funds
    losers past p90          the share of losers whose MAE went beyond the winners' p90 (the losses a stop at that
                             width would have cut), and their mean loss

Caveat that dominates: the forward record is weeks long, so most trades are short and the medium-term families' trades
that closed are mostly early exits. This informs a backtest of stop widths; it is not itself a reason to change one.

    ./venv/bin/python stop_study.py [--write]
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


def trades(conn) -> pd.DataFrame:
    import restate_paper
    t = pd.read_sql("SELECT r.run_id, r.ticker, r.entry_date, r.exit_date, r.entry_open_next, r.net_pct, r.corporate_action, "
                    "p.family, p.strategy FROM paper_trades_restated r JOIN paper_runs p ON p.run_id=r.run_id "
                    "WHERE r.version=? AND r.corporate_action=0 AND r.entry_open_next > 0", conn, params=(restate_paper.VERSION,))
    def mult(js):
        try:
            g = json.loads(js or "{}")
            return float(((g.get("genome") or g).get("risk") or {}).get("stop_atr_multiple")) \
                if ((g.get("genome") or g).get("risk") or {}).get("stop_atr_multiple") else np.nan
        except (TypeError, ValueError, AttributeError):
            return np.nan
    t["stop_mult"] = t["strategy"].map(mult)
    return t.drop(columns=["strategy"])


def excursions(conn, t: pd.DataFrame) -> pd.DataFrame:
    """MAE / MFE per trade in ATR units, from daily highs and lows strictly after the entry date up to the exit date."""
    out = []
    for tk, g in t.groupby("ticker"):
        lo, hi = g["entry_date"].min(), g["exit_date"].max()
        px = pd.read_sql("SELECT date, high, low FROM prices WHERE ticker=? AND date > ? AND date <= ? ORDER BY date",
                         conn, params=(tk, lo, hi)).set_index("date")
        atr = pd.read_sql("SELECT date, atr_14 FROM features WHERE ticker=? AND date >= ? AND date <= ?", conn,
                          params=(tk, lo, hi)).set_index("date")["atr_14"]
        for r in g.itertuples():
            path = px[(px.index > r.entry_date) & (px.index <= r.exit_date)]
            a = atr.get(r.entry_date)
            if path.empty or not a or a != a:
                continue
            e = float(r.entry_open_next)
            out.append({"family": r.family, "net_pct": r.net_pct, "stop_mult": r.stop_mult,
                        "mae_atr": float((path["low"].min() - e) / a), "mfe_atr": float((path["high"].max() - e) / a)})
    return pd.DataFrame(out)


def summarize(x: pd.DataFrame, min_trades: int = 30) -> pd.DataFrame:
    rows = []
    for fam, g in x.groupby("family"):
        if len(g) < min_trades:
            continue
        w, l_ = g[g.net_pct > 0], g[g.net_pct <= 0]
        p90 = float(w["mae_atr"].quantile(0.10)) if len(w) else np.nan        # MAE is negative: the 10th pct is the deep tail
        beyond = l_[l_["mae_atr"] < p90] if p90 == p90 else l_.iloc[:0]
        rows.append({"family": fam, "trades": len(g), "win": len(w) / len(g),
                     "winners_mae_p50": float(w["mae_atr"].median()) if len(w) else np.nan, "winners_mae_p90": p90,
                     "losers_mfe_p50": float(l_["mfe_atr"].median()) if len(l_) else np.nan,
                     "stop_mult": float(g["stop_mult"].median()), "losers_beyond": len(beyond) / len(l_) if len(l_) else np.nan,
                     "loss_beyond": float(beyond["net_pct"].mean()) if len(beyond) else np.nan})
    return pd.DataFrame(rows).sort_values("trades", ascending=False) if rows else pd.DataFrame()


def render(s: pd.DataFrame) -> str:
    L = [f"# Stop study — {date.today().isoformat()} (Stage AD3.6)", "",
         "From the restated forward record (next-open fills; corporate-action trades excluded). Excursions in ATR(14) at entry; "
         "negative = against the position.", "",
         "| family | trades | win | winners' MAE p50 | winners' MAE p90 | losers' MFE p50 | configured stop (ATR) | losers beyond p90 | their mean loss |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    f = lambda v, s_="{:+.2f}": "n/a" if v != v else s_.format(v)       # noqa: E731
    for r in s.itertuples():
        L.append(f"| {r.family} | {r.trades} | {r.win:.0%} | {f(r.winners_mae_p50)} | {f(r.winners_mae_p90)} | {f(r.losers_mfe_p50)} | "
                 f"{f(r.stop_mult, '{:.1f}')} | {f(r.losers_beyond, '{:.0%}')} | {f(r.loss_beyond, '{:+.2f}%')} |")
    L += ["", "Reading: a configured stop wider than the winners' p90 (more negative) leaves losses running that winners never "
          "needed; one tighter than the p90 stops out winners. Losers' MFE shows what a trailing stop could have kept. "
          "The record is weeks long and short-hold dominated: test any change in a backtest first (exit_sweep.py)."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    s = summarize(excursions(conn, trades(conn)))
    text = render(s)
    print(text)
    if a.write:
        p = ROOT / "reports" / f"stop_study_{date.today().isoformat()}.md"
        p.write_text(text)
        print(f"written {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
