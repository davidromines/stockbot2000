"""
Buffett's method, decomposed and implemented. Quality Minus Junk plus low beta.

Frazzini, Kabiller & Pedersen (*Buffett's Alpha*) took Berkshire's fifty-year
record apart and found something deflating and useful: **the alpha becomes
statistically insignificant once you control for exposure to Betting-Against-Beta
and Quality-Minus-Junk.** Berkshire's Sharpe is 0.76 — the best of any stock or
fund with a 30-year history, and nowhere near the mythology. Their summary is
that the returns are "neither luck nor magic, but rather the reward for the use
of leverage combined with a focus on cheap, safe, quality stocks."

So the method is reproducible in three parts, and we can build two of them:

  1. QUALITY  — Asness, Frazzini & Pedersen's QMJ score. Implemented below.
  2. LOW BETA — betting against beta. Implemented; computed from our own prices.
  3. LEVERAGE — about 1.6x, funded by insurance float at below-Treasury cost.
                **Not implementable, and not a detail.**

Point 3 deserves emphasis rather than a footnote. Roughly speaking, unlevered
quality-value returns get multiplied by 1.6, and Buffett's funding cost was
*negative* in some years because policyholders paid him to hold their money. A
retail account borrows at margin rates far above Treasuries, if at all. We can
copy the stock selection; we cannot copy the balance sheet, and the balance sheet
is a large part of the record.

QMJ CONSTRUCTION, from the paper
--------------------------------
Each component is converted to a cross-sectional rank, standardised to a z-score,
averaged within its group, and the groups averaged again:

  Profitability = z(z_gpoa + z_roe + z_roa + z_cfoa + z_gmar + z_acc)
  Growth        = z(five-year growth in each of the above)
  Safety        = z(z_bab + z_ivol + z_lev + z_o + z_z + z_evol)
  Payout        = z(z_eiss + z_diss + z_npop)
  Quality       = z(Profitability + Growth + Safety + Payout)

Ranks rather than raw values, deliberately: accounting ratios have savage
outliers — a company with near-zero equity produces an ROE in the thousands — and
a mean-based z-score on raw values would let one such firm dominate the whole
cross-section.

WHAT IS MISSING HERE, STATED PLAINLY
------------------------------------
- **Payout is partial.** NPOP needs dividends, which this database does not hold.
  Equity issuance is used, debt issuance is derived; the dividend leg is absent.
- **Growth is shortened.** The paper uses five-year growth in each profitability
  measure. Our fundamentals begin in 2009, so a full five-year window only exists
  from 2014, and our stored growth metrics are one-year. The growth leg is
  therefore one-year, which is a different and noisier quantity.
- **Leverage is absent entirely**, as above.

A score missing two of four legs is not QMJ. It is a quality score built on QMJ's
recipe, and it is labelled that way everywhere it appears.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np
import pandas as pd

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buffett")

BETA_WINDOW = 252          # one year of daily returns
MIN_OBS = 120


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_metrics (
            ticker  TEXT NOT NULL,
            date    TEXT NOT NULL,
            beta    REAL,      -- vs SPY, one year of daily returns
            ivol    REAL,      -- annualised residual volatility from that fit
            PRIMARY KEY (ticker, date)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_risk_date ON risk_metrics(date)")
    conn.commit()


def build_risk(conn, start="2009-01-01", limit=None, stride=21) -> None:
    """
    Rolling beta and idiosyncratic volatility against SPY.

    Both legs of QMJ's Safety score need these, and neither exists anywhere else
    in the project. Sampled every `stride` trading days rather than daily: beta
    over a 252-day window barely moves in a day, and computing it daily would be
    twenty times the work for the same number.

    Idiosyncratic volatility is the residual standard deviation from the same
    regression, annualised — the part of a stock's movement the market does not
    explain, which is what "safe" means in this context.
    """
    init(conn)
    spy = pd.read_sql_query(
        "SELECT date, close FROM prices WHERE ticker='SPY' AND close>0 ORDER BY date", conn)
    if spy.empty:
        raise SystemExit("No SPY history — cannot compute beta.")
    spy["r"] = np.log(spy["close"]).diff()
    spy = spy.dropna().set_index("date")

    tickers = [r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM daily_fundamentals ORDER BY ticker")]
    if limit:
        tickers = tickers[:limit]
    log.info(f"Computing beta and ivol for {tickers and len(tickers):,} tickers")

    out, n = [], 0
    for t in tickers:
        px = pd.read_sql_query(
            "SELECT date, close FROM prices WHERE ticker=? AND date>=? AND close>0 "
            "ORDER BY date", conn, params=(t, start))
        if len(px) < MIN_OBS + 5:
            continue
        px["r"] = np.log(px["close"]).diff()
        px = px.dropna().set_index("date")
        j = px.join(spy["r"].rename("m"), how="inner").dropna()
        if len(j) < MIN_OBS:
            continue
        rs, ms = j["r"].to_numpy(), j["m"].to_numpy()
        dates = j.index.to_numpy()
        for i in range(MIN_OBS, len(j), stride):
            a, b = max(0, i - BETA_WINDOW), i
            x, y = ms[a:b], rs[a:b]
            if len(x) < MIN_OBS:
                continue
            vx = x.var()
            if vx < 1e-12:
                continue
            beta = float(np.cov(y, x)[0, 1] / vx)
            resid = y - beta * x
            ivol = float(resid.std() * np.sqrt(252))
            if np.isfinite(beta) and np.isfinite(ivol):
                out.append((t, str(dates[b - 1]), beta, ivol))
        n += 1
        if len(out) >= 50000:
            conn.executemany("INSERT OR REPLACE INTO risk_metrics "
                             "(ticker,date,beta,ivol) VALUES (?,?,?,?)", out)
            conn.commit(); out = []
        if n % 400 == 0:
            log.info(f"  {n:,}/{len(tickers):,} tickers")
    if out:
        conn.executemany("INSERT OR REPLACE INTO risk_metrics "
                         "(ticker,date,beta,ivol) VALUES (?,?,?,?)", out)
    conn.commit()
    tot = conn.execute("SELECT COUNT(*) FROM risk_metrics").fetchone()[0]
    log.info(f"risk_metrics: {tot:,} rows across {n:,} tickers")


def _z(s: pd.Series) -> pd.Series:
    """
    Rank, then standardise. The paper's construction, and not interchangeable
    with a plain z-score on raw values: accounting ratios carry savage outliers —
    a company with near-zero book equity produces an ROE in the thousands — and a
    mean-based z on raw values lets one such firm dominate the cross-section.
    """
    r = s.rank(method="average", na_option="keep")
    mu, sd = r.mean(), r.std()
    return (r - mu) / sd if sd and np.isfinite(sd) and sd > 0 else r * 0.0


def quality_score(d: pd.DataFrame) -> pd.Series:
    """
    QMJ-style quality. Profitability + Growth + Safety + Payout, each z-scored.

    Explicitly *QMJ-style*, not QMJ: the payout leg has no dividend data and the
    growth leg is one-year rather than five. Both gaps are documented at the top
    of this module. Components that are entirely absent are dropped from their
    group rather than treated as zero, because a missing measurement is not a
    neutral one — scoring it zero would rank an unmeasured company as exactly
    average and let it into the portfolio on the strength of nothing.
    """
    def grp(cols, invert=()):
        parts = []
        for c in cols:
            if c in d.columns and d[c].notna().any():
                z = _z(d[c])
                parts.append(-z if c in invert else z)
        return _z(pd.concat(parts, axis=1).mean(axis=1)) if parts else None

    profitability = grp(["gross_profitability", "roe", "roa", "cash_roa",
                         "gross_margin", "accruals"], invert=("accruals",))
    growth = grp(["earnings_growth", "book_growth", "revenue_growth"])
    safety = grp(["beta", "ivol", "debt_to_equity", "ohlson_o", "altman_z", "evol"],
                 invert=("beta", "ivol", "debt_to_equity", "ohlson_o", "evol"))
    payout = grp(["net_share_issuance"], invert=("net_share_issuance",))

    legs = [x for x in (profitability, growth, safety, payout) if x is not None]
    if not legs:
        return pd.Series(np.nan, index=d.index)
    return _z(pd.concat(legs, axis=1).mean(axis=1))
