"""
Addendum C (revision 2), Stage 4 — provenance-aware loading of real and
synthetic bars, and the five sensitivity modes.

Real rows pass through untouched. Synthetic rows come only from
data/universe/synthetic_v1.parquet and always carry `is_synthetic = True` and
`data_source`. The two are appended, never joined or blended.

    mode         what a backtest sees
    ---------    ---------------------------------------------------------------
    exclude      primary database only — today's survivorship-biased universe,
                 the baseline every other mode is compared against
    real_only    primary + FINSABER's delisted-inclusive S&P 500 prices (real
                 rows only, no synthetic); FINSABER fills tickers the primary
                 database lacks, never overrides one it has
    as_is        exclude + synthetic paths exactly as generated
    zero         as_is, with every synthetic delisting bar at -100% (the
                 pessimistic bound: each unpriced death was a total loss)
    optimistic   as_is, with every synthetic delisting return at 0% (the
                 optimistic bound: each unpriced death exited at its last price)

A strategy's result across all five is the honest statement of how much it
depends on the companies we cannot see. Synthetic modes are for retests and
stress bounds only — never strategy discovery or promotion gates, until a
generator passes the discriminability test (Stage 5; Addendum C question 5).

    from universe_loader import load_backtest_data
    df = load_backtest_data(conn, "2016-01-01", "2019-12-31", mode="zero")
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3

import pandas as pd

import data_providers as dp

SYNTH = "data/universe/synthetic_v3.parquet"
MODES = ("exclude", "real_only", "as_is", "zero", "optimistic")
COLUMNS = dp.BAR_COLUMNS + ["is_synthetic", "data_source"]


def _primary(conn, start, end, tickers=None) -> pd.DataFrame:
    where, params = "p.date BETWEEN ? AND ? AND s.security_type='common_stock' AND " \
                    "COALESCE(s.data_quality,'')=''", [start, end]
    if tickers:
        where += f" AND p.ticker IN ({','.join('?' * len(tickers))})"
        params += list(tickers)
    df = pd.read_sql_query(f"SELECT p.ticker, p.date, p.open, p.high, p.low, p.close, p.volume FROM prices p "
                           f"JOIN symbols s ON s.ticker = p.ticker WHERE {where}", conn, params=params)
    df["is_synthetic"], df["data_source"] = False, "primary"
    return df


def _finsaber(start, end, have: set, db="data/finsaber.db") -> pd.DataFrame:
    if not os.path.exists(db):
        return pd.DataFrame(columns=COLUMNS)
    f = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    df = pd.read_sql_query("SELECT symbol AS ticker, date, open, high, low, adj_close AS close, volume "
                           "FROM finsaber_prices WHERE date BETWEEN ? AND ?", f, params=(start, end))
    f.close()
    import finsaber
    fq = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    bad = finsaber.flagged(fq)
    fq.close()
    df = df[~df["ticker"].isin(have | bad)]
    df["is_synthetic"], df["data_source"] = False, "finsaber"
    return df


def _synthetic(start, end, mode: str, exclude: set) -> pd.DataFrame:
    if not os.path.exists(SYNTH):
        raise FileNotFoundError(f"{SYNTH} not built — run universe_synthetic.py --build")
    df = pd.read_parquet(SYNTH, filters=[("date", ">=", start), ("date", "<=", end)])
    # A dead company's ticker is often reused later by a DIFFERENT company we
    # hold real prices for. The synthetic history must never be read as that
    # security's, so on a collision it trades under its own company_id.
    df = df.copy()
    clash = df["ticker"].isin(exclude)
    df.loc[clash, "ticker"] = df.loc[clash, "company_id"]
    if mode in ("zero", "optimistic"):
        bar = df["is_delisting_bar"]
        prev = df.groupby("company_id")["close"].shift(1)
        df.loc[bar, "close"] = 0.0 if mode == "zero" else prev[bar].fillna(df.loc[bar, "open"])
        df.loc[bar, "low"] = df.loc[bar, ["low", "close"]].min(axis=1)
        df["data_source"] = df["data_source"] + f":{mode}"
    return df[COLUMNS + ["company_id", "cohort_id", "synthetic_reason", "is_delisting_bar"]]


def load_backtest_data(conn, start: str, end: str, mode: str = "exclude", tickers=None) -> pd.DataFrame:
    """Bars for [start, end] under one of MODES. Every row says where it came from."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    real = _primary(conn, start, end, tickers)
    if mode == "exclude":
        return real
    have = set(real["ticker"].unique())
    if mode == "real_only":
        return pd.concat([real, _finsaber(start, end, have)], ignore_index=True)
    all_real = set(t for (t,) in conn.execute("SELECT DISTINCT ticker FROM symbols"))
    syn = _synthetic(start, end, mode, all_real)
    return pd.concat([real, syn], ignore_index=True)


def synthetic_share(df: pd.DataFrame) -> dict:
    """Share of rows and of tickers that are synthetic, overall and by year (Stage 5 reporting)."""
    if df.empty:
        return {}
    y = pd.to_datetime(df["date"]).dt.year
    by = df.assign(_y=y).groupby("_y").agg(rows=("is_synthetic", "size"), synthetic=("is_synthetic", "sum"))
    return {"rows": int(len(df)), "synthetic_rows": int(df["is_synthetic"].sum()),
            "tickers": int(df["ticker"].nunique()),
            "synthetic_tickers": int(df.loc[df["is_synthetic"], "ticker"].nunique()),
            "by_year": {int(k): round(v.synthetic / v.rows, 4) for k, v in by.iterrows()}}


class UniverseProvider(dp.DataProvider):
    """A DataProvider over load_backtest_data, so dataset_compare and friends can use any mode."""

    def __init__(self, conn, mode: str = "as_is"):
        self.conn, self.mode = conn, mode

    def name(self) -> str:
        return f"universe:{self.mode}"

    def daily_bars(self, tickers, start, end):
        return load_backtest_data(self.conn, start, end, self.mode, tickers)[dp.BAR_COLUMNS]

    def universe(self, on_date):
        return sorted(load_backtest_data(self.conn, on_date, on_date, self.mode)["ticker"].unique())

    def coverage(self):
        return {"mode": self.mode}
