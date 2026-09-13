"""
The conviction book. Buy and hold on fundamentals, reviewed weekly. Phase 4.

Everything else in this project trades on price over days to weeks. That is the
high-turnover regime, and the evidence there is bad: Novy-Marx & Velikov find
that **few anomalies with one-sided monthly turnover above 50% survive
transaction costs**, while most below it do — and the survivors are Value, Gross
Profitability and Size, rebalanced annually. Our own results agree from the other
side: costs take 87% of gross profit, 0 of 20 published technical rules beat the
null, and six searches produced six measurement artifacts.

So this module is not another strategy. It is a different *regime*: hold a
concentrated book of financially strong, cheap companies, look at it once a week,
and only sell when the reason for owning it stops being true.

**Turnover is the whole point, and it is measured.** If a conviction strategy
churns like the swing search, it has failed regardless of its return, because it
will lose to costs the same way everything else has. `--report` prints monthly
turnover next to the return, and a strategy above roughly 50% should be read as
being back in the regime where the evidence says it cannot win.

**Hysteresis is deliberate.** A name is bought when it ranks in the top
`entry_pct` and sold only when it falls out of the much wider `exit_pct`. Buying
and selling at the same threshold makes a portfolio thrash on noise around the
boundary — a stock oscillating either side of the line is traded every week for
no reason. The gap between the two bands is what converts "review weekly" into
"trade rarely", and it is what the user's framing — *hold while fundamentals
remain strong, sell when they change* — actually requires.

Everything is point-in-time: the screens read `daily_fundamentals`, which is
lagged two days past each filing date and never looks backwards from a period
end.

Usage:
    python conviction.py --list
    python conviction.py --backtest piotroski_value
    python conviction.py --backtest-all
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np
import pandas as pd

import costs as costs_mod
import storage
from fundamental_features import FUNDAMENTAL_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("conviction")


# -- the screens -------------------------------------------------------------
#
# `score` returns a Series where higher is better. `requires` lists the columns
# that must be present for a row to be scoreable at all — a company missing them
# is skipped rather than scored as zero, because "no data" is not "bad".

def _rank(s: pd.Series) -> pd.Series:
    """Cross-sectional percentile, 0..1, robust to scale and to outliers."""
    return s.rank(pct=True, na_option="keep")


SCREENS = {
    "piotroski_value": dict(
        requires=["piotroski_f", "book_to_market"],
        note="Piotroski (2000). Cheap on book-to-market AND financially strong. "
             "High F-Score inside high book-to-market earned 13.4% mean annual "
             "market-adjusted return, beating the full value portfolio by 7.5 "
             "points and low-F-Score names by 23. The single best-evidenced "
             "value screen there is.",
        score=lambda d: _rank(d["book_to_market"]) * 0.5 + _rank(d["piotroski_f"]) * 0.5),

    "magic_formula": dict(
        requires=["ebit_to_ev", "roic"],
        note="Greenblatt. Rank on earnings yield (EBIT/EV) and return on capital, "
             "sum the ranks. Coverage is the binding constraint here, not the "
             "idea: roic needs long-term debt, which only ~27% of filings tag.",
        score=lambda d: _rank(d["ebit_to_ev"]) * 0.5 + _rank(d["roic"]) * 0.5),

    "quality_value": dict(
        requires=["gross_profitability", "book_to_market"],
        note="Novy-Marx ValProf. Gross profitability is 'the other side of "
             "value': roughly as powerful as book-to-market and nearly "
             "uncorrelated with it, which makes the pair far stronger than "
             "either alone.",
        score=lambda d: _rank(d["gross_profitability"]) * 0.5 + _rank(d["book_to_market"]) * 0.5),

    "conservative": dict(
        requires=["piotroski_f", "asset_growth", "chs_distress"],
        note="Quality with the two best-documented red flags removed. Cooper et "
             "al (2008) find asset growth the strongest balance-sheet predictor "
             "of poor returns, and CHS predicts outright failure. Buys strong "
             "companies that are not empire-building and not dying.",
        score=lambda d: (_rank(d["piotroski_f"]) * 0.5
                         + (1 - _rank(d["asset_growth"])) * 0.25
                         + (1 - _rank(d["chs_distress"])) * 0.25)),

    "deep_value": dict(
        requires=["book_to_market", "earnings_yield", "altman_z"],
        note="Cheap on two measures with a solvency floor. Deep value without a "
             "distress screen is how a value portfolio fills up with companies "
             "that are cheap because they are failing — which is exactly the "
             "trap our own search fell into for two days.",
        score=lambda d: (_rank(d["book_to_market"]) * 0.4
                         + _rank(d["earnings_yield"]) * 0.4
                         + _rank(d["altman_z"]) * 0.2)),
}


def _load_panel(conn, cfg, start: str, end: str) -> pd.DataFrame:
    """
    Weekly review dates joined to fundamentals and prices.

    Sampled weekly rather than daily because the book is reviewed weekly: loading
    every trading day would be seven times the memory to answer the same question.
    """
    extra = [c for c in ("ebit_to_ev", "roic") if c not in FUNDAMENTAL_COLS]
    cols = ",".join(f"d.{c}" for c in FUNDAMENTAL_COLS)
    join_extra = ""
    if extra:
        # ebit_to_ev and roic live only in `fundamentals`; join them per filing.
        join_extra = ",".join(f"fu.{c}" for c in extra)
        q = f"""
            SELECT d.ticker, d.date, p.close, d.days_since_filing, {cols}, {join_extra}
            FROM daily_fundamentals d
            JOIN prices p ON p.ticker = d.ticker AND p.date = d.date
            LEFT JOIN fundamentals fu ON fu.ticker = d.ticker
                 AND fu.filed = (SELECT MAX(f2.filed) FROM fundamentals f2
                                 WHERE f2.ticker = d.ticker
                                   AND REPLACE(f2.filed,'-','') <= REPLACE(d.date,'-',''))
            WHERE d.date BETWEEN ? AND ? AND p.close >= ?
              AND strftime('%w', d.date) = '3'
        """
    else:
        q = f"""SELECT d.ticker, d.date, p.close, d.days_since_filing, {cols}
                FROM daily_fundamentals d
                JOIN prices p ON p.ticker=d.ticker AND p.date=d.date
                WHERE d.date BETWEEN ? AND ? AND p.close >= ?
                  AND strftime('%w', d.date) = '3'"""
    df = pd.read_sql_query(q, conn, params=(start, end, cfg["risk"].get("min_price") or 0))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def backtest(conn, cfg, name: str, start="2010-01-01", end="2026-09-11",
             n_hold=20, entry_pct=0.90, exit_pct=0.60, capital=10000.0) -> dict:
    """
    Run one conviction screen with weekly review.

    Equal-weighted, `n_hold` names, reviewed every Wednesday. A name is bought
    when it ranks above `entry_pct` and held until it falls below `exit_pct` —
    the gap between the two is the hysteresis that keeps turnover low.

    Capital is $10,000 rather than the project's $100 mandate, because this is a
    measurement of the strategy, not a plan for the account. Twenty equal
    positions out of $100 would be $5 each, below the price of a single share of
    most things worth owning, and the resulting rounding would swamp the result.
    """
    sc = SCREENS[name]
    df = _load_panel(conn, cfg, start, end)
    if df.empty:
        raise SystemExit("No weekly panel — has fundamental_features.py been built?")

    cm = costs_mod.CostModel(cfg)
    dates = sorted(df["date"].unique())
    holdings: dict = {}          # ticker -> shares
    cash = capital
    equity_curve, trades, turnover_rows = [], 0, []

    for dt in dates:
        day = df[df["date"] == dt].copy()
        need = sc["requires"]
        day = day.dropna(subset=[c for c in need if c in day.columns])
        if len(day) < n_hold * 2:
            continue
        try:
            day["score"] = sc["score"](day)
        except Exception:
            continue
        day = day.dropna(subset=["score"])
        if day.empty:
            continue
        day["pct"] = day["score"].rank(pct=True)
        px = dict(zip(day["ticker"], day["close"]))

        # mark to market before trading
        pos_val = sum(sh * px.get(t, 0.0) for t, sh in holdings.items())
        equity = cash + pos_val

        # --- sells: only names that have fallen out of the wide band ----------
        ranks = dict(zip(day["ticker"], day["pct"]))
        sold = 0
        for t in list(holdings):
            r = ranks.get(t)
            p = px.get(t)
            if p is None:
                continue                    # unpriceable this week; revisit next
            if r is None or r < exit_pct:
                proceeds = holdings[t] * p
                cash += proceeds - float(cm.round_trip(proceeds, 5e7, holdings[t])) / 2
                del holdings[t]
                sold += 1; trades += 1

        # --- buys: fill empty slots from the narrow band ----------------------
        want = day[day["pct"] >= entry_pct].sort_values("score", ascending=False)
        bought = 0
        for t in want["ticker"]:
            if len(holdings) >= n_hold:
                break
            if t in holdings:
                continue
            size = equity / n_hold
            if cash < size or px.get(t, 0) <= 0:
                continue
            sh = size / px[t]
            cash -= size
            cash -= float(cm.round_trip(size, 5e7, sh)) / 2
            holdings[t] = sh
            bought += 1; trades += 1

        pos_val = sum(sh * px.get(t, 0.0) for t, sh in holdings.items())
        equity_curve.append((pd.Timestamp(dt), cash + pos_val, len(holdings)))
        if len(holdings):
            turnover_rows.append((sold + bought) / max(len(holdings), 1))

    if len(equity_curve) < 10:
        raise SystemExit(f"{name}: too few review dates to measure.")
    eq = pd.DataFrame(equity_curve, columns=["date", "equity", "n"]).set_index("date")
    yrs = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    final = float(eq["equity"].iloc[-1])
    cagr = (final / capital) ** (1 / yrs) - 1 if final > 0 else -1.0
    dd = float((1 - eq["equity"] / eq["equity"].cummax()).max())
    wk = eq["equity"].pct_change().dropna()
    sharpe = float(wk.mean() / wk.std() * np.sqrt(52)) if wk.std() > 0 else 0.0
    # Weekly turnover -> monthly, which is the unit the cost literature uses.
    monthly_turnover = float(np.mean(turnover_rows) * 52 / 12) if turnover_rows else 0.0
    return {"name": name, "cagr": cagr, "max_dd": dd, "sharpe": sharpe,
            "final": final, "years": yrs, "trades": trades,
            "monthly_turnover": monthly_turnover, "reviews": len(eq),
            "equity": eq}


def _benchmark(conn, start, end, capital=10000.0) -> dict:
    """SPY over the same dates. The only comparison that means anything."""
    r = pd.read_sql_query(
        "SELECT date, close FROM prices WHERE ticker='SPY' AND date BETWEEN ? AND ? "
        "AND close>0 ORDER BY date", conn, params=(start, end))
    if len(r) < 10:
        return {}
    yrs = max((pd.Timestamp(r["date"].iloc[-1]) - pd.Timestamp(r["date"].iloc[0])).days / 365.25, 1e-9)
    total = r["close"].iloc[-1] / r["close"].iloc[0]
    eq = capital * r["close"] / r["close"].iloc[0]
    return {"cagr": total ** (1 / yrs) - 1, "final": float(eq.iloc[-1]),
            "max_dd": float((1 - eq / eq.cummax()).max())}


def report(results: list, bench: dict) -> None:
    print(f"\n  CONVICTION BOOK — buy and hold, reviewed weekly, sold on deterioration")
    print(f"  {'strategy':<20}{'CAGR':>9}{'max DD':>9}{'Sharpe':>9}"
          f"{'turnover/mo':>13}{'trades':>9}  regime")
    print("  " + "-" * 84)
    for r in sorted(results, key=lambda x: -x["cagr"]):
        # The cost literature's dividing line: above ~50% monthly turnover, few
        # anomalies survive costs. Below it, most do.
        regime = "LOW — costs survivable" if r["monthly_turnover"] < 0.50 else \
                 "HIGH — back in the losing regime"
        print(f"  {r['name']:<20}{r['cagr']:>+8.1%}{r['max_dd']:>9.0%}"
              f"{r['sharpe']:>9.2f}{r['monthly_turnover']:>12.0%}{r['trades']:>9,}  {regime}")
    if bench:
        print("  " + "-" * 84)
        print(f"  {'SPY (same dates)':<20}{bench['cagr']:>+8.1%}{bench['max_dd']:>9.0%}"
              f"{'—':>9}{'—':>12}{'—':>9}")
    print("\n  Turnover is the number to read first. A conviction strategy that churns")
    print("  has failed regardless of its return: it is back in the regime where the")
    print("  evidence says trading costs eat the edge, which is where every price-based")
    print("  strategy in this project has already died.")
    print("\n  These are backtests on survivorship-biased data — 7,062 delisted companies")
    print("  are absent — and the value screens shop among cheap, distressed-looking")
    print("  names, which is exactly where that bias is worst. Treat as ranking, not")
    print("  forecast, and read bias_exposure.py alongside.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--backtest", metavar="NAME")
    ap.add_argument("--backtest-all", action="store_true")
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-09-11")
    ap.add_argument("--hold", type=int, default=20)
    ap.add_argument("--entry", type=float, default=0.90)
    ap.add_argument("--exit", dest="exit_pct", type=float, default=0.60)
    a = ap.parse_args()

    if a.list:
        for k, v in SCREENS.items():
            print(f"\n  {k}")
            print(f"    needs : {', '.join(v['requires'])}")
            print(f"    {v['note']}")
        return

    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    names = list(SCREENS) if a.backtest_all else ([a.backtest] if a.backtest else list(SCREENS))
    out = []
    for n in names:
        if n not in SCREENS:
            log.error(f"unknown screen: {n}"); continue
        try:
            r = backtest(conn, cfg, n, a.start, a.end, a.hold, a.entry, a.exit_pct)
            out.append(r)
            log.info(f"{n}: CAGR {r['cagr']:+.1%}, turnover {r['monthly_turnover']:.0%}/mo")
        except SystemExit as e:
            log.error(f"{n}: {e}")
    if out:
        report(out, _benchmark(conn, a.start, a.end))
    conn.close()


if __name__ == "__main__":
    main()
