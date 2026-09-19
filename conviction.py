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

def _buffett_score(d: pd.DataFrame) -> pd.Series:
    """Quality + cheapness + low beta, the two legs of Buffett we can reproduce."""
    import buffett
    q = buffett.quality_score(d)
    val = _rank(d["book_to_market"], d) if "book_to_market" in d else 0.0
    # Betting against beta: low beta is the whole point, so it is ranked inverted
    # and carried as its own leg rather than folded into the quality safety score.
    bab = (1 - _rank(d["beta"], d)) if "beta" in d and d["beta"].notna().any() else 0.0
    # The quality composite is ranked within bucket too. Its own inputs are left
    # on global z-scores inside `quality_score`: gross profitability correlates
    # -0.03 with size and beta -0.03, so there is nothing there to neutralise,
    # and rebuilding QMJ's internals per bucket would thin each group to the
    # point where the z-scores stop meaning anything.
    return _rank(q, d) * 0.5 + val * 0.3 + (bab * 0.2 if np.ndim(bab) else 0.0)


SIZE_COL = "market_cap"
SIZE_BUCKET_COL = "size_bucket"


def _rank(s: pd.Series, d: pd.DataFrame | None = None) -> pd.Series:
    """
    Percentile, 0..1 — computed **within the row's size bucket** where one exists.

    Why this is not a plain cross-sectional rank any more. Book-to-market has
    market cap in its denominator, and large companies carry most of their worth
    in brand, goodwill and other things a balance sheet does not hold. So B/M
    correlates -0.35 with log size across our own panel, and ranking on it sorts
    toward small before it sorts toward cheap. Every "value" pick this book made
    was in the bottom half of the market by size, three of five in the bottom
    quartile, from a universe whose median company is $3.1B.

    That tilt is not itself an error — the size premium is real and these screens
    are supposed to lean small. It is an error *here*, on this data, because
    microcaps are exactly where our 7,062 missing delisted companies concentrate.
    The screens were validated on a sample that omits the small companies that
    died, so their small-cap leg is the least trustworthy thing they do.

    Ranking within bucket asks the question the screen was meant to ask: not
    "which company is cheapest" — that is mostly "which is smallest" — but "which
    company is cheapest relative to companies of its own size".

    Pass the frame to neutralise; call it with one argument for a global rank,
    which is still correct wherever size is not in the denominator.
    """
    if d is not None and SIZE_BUCKET_COL in getattr(d, "columns", ()):
        return s.groupby(d[SIZE_BUCKET_COL], observed=True).rank(
            pct=True, na_option="keep")
    return s.rank(pct=True, na_option="keep")


SCREENS = {
    "piotroski_value": dict(
        requires=["piotroski_f", "book_to_market"],
        note="Piotroski (2000). Cheap on book-to-market AND financially strong. "
             "High F-Score inside high book-to-market earned 13.4% mean annual "
             "market-adjusted return, beating the full value portfolio by 7.5 "
             "points and low-F-Score names by 23. The single best-evidenced "
             "value screen there is.",
        score=lambda d: _rank(d["book_to_market"], d) * 0.5 + _rank(d["piotroski_f"], d) * 0.5),

    "magic_formula": dict(
        requires=["ebit_to_ev", "roic"],
        note="Greenblatt. Rank on earnings yield (EBIT/EV) and return on capital, "
             "sum the ranks. Coverage is the binding constraint here, not the "
             "idea: roic needs long-term debt, which only ~27% of filings tag.",
        score=lambda d: _rank(d["ebit_to_ev"], d) * 0.5 + _rank(d["roic"], d) * 0.5),

    "quality_value": dict(
        requires=["gross_profitability", "book_to_market"],
        note="Novy-Marx ValProf. Gross profitability is 'the other side of "
             "value': roughly as powerful as book-to-market and nearly "
             "uncorrelated with it, which makes the pair far stronger than "
             "either alone.",
        score=lambda d: _rank(d["gross_profitability"], d) * 0.5 + _rank(d["book_to_market"], d) * 0.5),

    "conservative": dict(
        requires=["piotroski_f", "asset_growth", "chs_distress"],
        note="Quality with the two best-documented red flags removed. Cooper et "
             "al (2008) find asset growth the strongest balance-sheet predictor "
             "of poor returns, and CHS predicts outright failure. Buys strong "
             "companies that are not empire-building and not dying.",
        score=lambda d: (_rank(d["piotroski_f"], d) * 0.5
                         + (1 - _rank(d["asset_growth"], d)) * 0.25
                         + (1 - _rank(d["chs_distress"], d)) * 0.25)),

    "buffett": dict(
        requires=["book_to_market", "roe"],
        note="Frazzini, Kabiller & Pedersen took Berkshire apart and found the "
             "alpha vanishes once you control for Betting-Against-Beta and "
             "Quality-Minus-Junk. So: cheap, safe, quality, low beta. What CANNOT "
             "be copied is the third leg — about 1.6x leverage funded by "
             "insurance float at below-Treasury cost, which is a large part of "
             "the record and unavailable to any retail account.",
        score=lambda d: _buffett_score(d)),

    "deep_value": dict(
        requires=["book_to_market", "earnings_yield", "altman_z"],
        note="Cheap on two measures with a solvency floor. Deep value without a "
             "distress screen is how a value portfolio fills up with companies "
             "that are cheap because they are failing — which is exactly the "
             "trap our own search fell into for two days.",
        score=lambda d: (_rank(d["book_to_market"], d) * 0.4
                         + _rank(d["earnings_yield"], d) * 0.4
                         + _rank(d["altman_z"], d) * 0.2)),
}


def _load_panel(conn, cfg, start: str, end: str) -> pd.DataFrame:
    """
    Weekly review dates joined to fundamentals and prices.

    Sampled weekly rather than daily because the book is reviewed weekly: loading
    every trading day would be seven times the memory to answer the same question.

    **Both tradeability floors apply here, not just price.** This filtered on
    `min_price` alone for its whole life, so `min_dollar_volume` — the $1M/day
    floor the scanner has always enforced — was silently absent from every
    fundamental screen. It surfaced MXC as the book's top pick, agreed on by two
    systems, at $890k/day against that floor. Value ratios have market cap in the
    denominator, so a value screen walks toward small and illiquid names on its
    own; running it with the liquidity floor switched off let it walk all the way
    to names a $20 order moves.
    """
    # `market_cap` and the two Greenblatt inputs live only in `fundamentals`,
    # so the as-of join is unconditional now. Joining on the latest filing at or
    # before the review date keeps it point-in-time: `value_metrics._market_cap`
    # multiplies shares taken FROM the filing by the price ON the filing date,
    # never by a current share count, which would be look-ahead precisely where
    # it does most damage — dilution is what distressed companies do next.
    extra = [c for c in ("ebit_to_ev", "roic") if c not in FUNDAMENTAL_COLS]
    cols = ",".join(f"d.{c}" for c in FUNDAMENTAL_COLS)
    join_extra = "".join(f", fu.{c}" for c in extra + ["market_cap"])
    q = f"""
        SELECT d.ticker, d.date, p.close, d.days_since_filing, {cols}{join_extra}
        FROM daily_fundamentals d
        JOIN prices p ON p.ticker = d.ticker AND p.date = d.date
        JOIN features fe ON fe.ticker = d.ticker AND fe.date = d.date
        LEFT JOIN fundamentals fu ON fu.ticker = d.ticker
             AND fu.filed = (SELECT MAX(f2.filed) FROM fundamentals f2
                             WHERE f2.ticker = d.ticker
                               AND REPLACE(f2.filed,'-','') <= REPLACE(d.date,'-',''))
        WHERE d.date BETWEEN ? AND ? AND p.close >= ?
          AND fe.dollar_volume_20 >= ?
          AND strftime('%w', d.date) = '3'
          AND d.ticker IN (SELECT ticker FROM symbols
                           WHERE security_type IN ('common_stock','adr')
                             AND data_quality IS NULL)
    """
    df = pd.read_sql_query(q, conn, params=(start, end,
                                            cfg["risk"].get("min_price") or 0,
                                            cfg["risk"].get("min_dollar_volume") or 0))
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    # Book-to-market above this is a broken share count, not a cheap company.
    # National Presto surfaced at B/M 400 because its market cap resolved to
    # $988k for a company worth hundreds of millions — the shares-outstanding
    # tag had picked up a fragment. A real equity almost never trades above
    # about 5x book, and letting these through puts data errors at the top of a
    # value screen, which is precisely where a value screen is most credulous.
    if "book_to_market" in df:
        bad = df["book_to_market"] > 10
        if bad.any():
            df.loc[bad, "book_to_market"] = np.nan
    # Beta and idiosyncratic volatility for the Buffett screen's low-beta and
    # safety legs. Sampled monthly in risk_metrics, so joined as-of backwards:
    # a weekly review uses the most recent beta already computed, never a future
    # one.
    risk = pd.read_sql_query(
        "SELECT ticker, date, beta, ivol FROM risk_metrics WHERE date BETWEEN ? AND ?",
        conn, params=(str(pd.Timestamp(start) - pd.Timedelta(days=400))[:10], end))
    if not risk.empty:
        risk["date"] = pd.to_datetime(risk["date"])
        df = pd.merge_asof(df.sort_values("date"), risk.sort_values("date"),
                           on="date", by="ticker", direction="backward")
    return add_size_buckets(df, cfg)


def add_size_buckets(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Label each row with its size bucket, assigned within its own review date.

    **Within the date, never pooled across dates.** Pooling would make the
    buckets a calendar variable rather than a size one: the market roughly
    quadrupled over the backtest window, so a company of unchanged real size
    drifts from "small" to "large" without doing anything, and by the last years
    almost every row would sit in the top bucket. Ranking inside a date compares
    each company against the companies it was actually competing with.

    Rows with no market cap get their own bucket rather than being dropped or
    folded into the middle. A missing measurement is not an average one — the
    same reasoning `buffett.quality_score` applies to its own components.
    """
    if df.empty or SIZE_COL not in df.columns:
        return df
    n = int((cfg.get("conviction", {}) or {}).get("size_buckets", 5))
    cap = pd.to_numeric(df[SIZE_COL], errors="coerce")
    cap = cap.where(cap > 0)

    # An explicit loop over date groups, NOT groupby().apply(). The apply form
    # returns a Series for a many-group frame and a DataFrame for a single-group
    # one, so assigning its result to one column worked on a 20-day panel and
    # raised "Cannot set a DataFrame with multiple columns" the first time paper
    # trading called it with a single review date. Shape that depends on group
    # count is not something to rely on.
    out = pd.Series("no_cap", index=df.index, dtype="object")
    labels = [f"q{i + 1}" for i in range(n)]
    for _, idx in df.groupby("date", observed=True).groups.items():
        v = cap.loc[idx]
        ok = v.notna()
        # Fewer distinct values than buckets makes qcut raise rather than
        # degrade, and a thin early date should not take the whole run down.
        if ok.sum() < n * 2:
            continue
        have = ok[ok].index
        try:
            out.loc[have] = pd.qcut(np.log(v[have]), n, labels=labels).astype(object)
        except ValueError:
            out.loc[have] = "q1"

    df = df.copy()
    df[SIZE_BUCKET_COL] = out
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
