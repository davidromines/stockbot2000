"""
Market regimes, defined in advance. Phase 6 §21.

Results are broken down by regime so a strategy that works only in one unusual
market is visible. The spec's rule is the load-bearing part: *use predefined
regime definitions; do not cherry-pick regimes after seeing results.* So every
definition lives in `config.yaml` `regimes:` and was fixed before any result:

    bull / bear          SPY close above / below its 200-day average
    high_vol / low_vol   SPY 20-day realised vol above / below its median over the window
    crisis / normal      SPY more than 20% below / within 20% of its 52-week high
    high_rate / low_rate 3-month T-bill yield at or above / below `high_rate_pct` (2.0%)

The SPY labels are robustness.regime_labels (Phase 13 §28), extended here with
rates. A fixed level, not a percentile of the window: a percentile would make
"high" mean different things in 2012 and 2023, and 2.0% was chosen as the
line between the zero-rate era (2009-2015, 2020-21) and the rest, before any
strategy was looked at through it.

The rates series is stored in `rates` (append-safe upsert by series and date):

    FRED DGS3MO      the official 3-month constant-maturity yield (primary)
    yfinance ^IRX    13-week T-bill discount yield (fallback, labelled as such)

Without a rates series the rate regimes are reported UNAVAILABLE, never
guessed.

    python regimes.py --load-rates           fetch / top up the rates series
    python regimes.py --forward              every forward fund's daily P&L by regime
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import io
import logging
import sqlite3
import sys

import pandas as pd

log = logging.getLogger("regimes")

DEFAULTS = {"high_rate_pct": 2.0, "rate_series": "DGS3MO"}
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


def settings(cfg: dict | None) -> dict:
    return {**DEFAULTS, **((cfg or {}).get("regimes") or {})}


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rates (
            series  TEXT NOT NULL,
            date    TEXT NOT NULL,
            value   REAL NOT NULL,
            source  TEXT NOT NULL,
            PRIMARY KEY (series, date)
        )""")
    conn.commit()


# --- loading -------------------------------------------------------------------

def parse_fred(text: str, series: str) -> pd.DataFrame:
    """FRED's CSV: a date column and the series column; '.' marks a missing day."""
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    date_col = next(c for c in df.columns if c.lower() in ("date", "observation_date"))
    df = df.rename(columns={date_col: "date", series: "value"})[["date", "value"]]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna()


def fetch_fred(series: str) -> pd.DataFrame:
    import requests
    r = requests.get(FRED_URL.format(series=series), timeout=30)
    r.raise_for_status()
    return parse_fred(r.text, series)


def fetch_irx() -> pd.DataFrame:
    import yfinance as yf
    h = yf.Ticker("^IRX").history(period="max", auto_adjust=False)
    if h.empty:
        return pd.DataFrame(columns=["date", "value"])
    return pd.DataFrame({"date": h.index.strftime("%Y-%m-%d"), "value": h["Close"].to_numpy()}).dropna()


def load_rates(conn, cfg: dict | None = None, fetchers=None) -> dict:
    """Primary source first; the fallback only if the primary returns nothing. Idempotent."""
    init(conn)
    s = settings(cfg)
    fetchers = fetchers or [(s["rate_series"], "fred", lambda: fetch_fred(s["rate_series"])),
                            (s["rate_series"], "yfinance_^IRX", fetch_irx)]
    for series, source, fn in fetchers:
        try:
            df = fn()
        except Exception as e:                               # noqa: BLE001
            log.warning(f"{source}: {type(e).__name__}: {e}")
            continue
        if df is None or df.empty:
            continue
        conn.executemany("INSERT OR REPLACE INTO rates VALUES (?,?,?,?)",
                         [(series, str(d)[:10], float(v), source) for d, v in zip(df["date"], df["value"])])
        conn.commit()
        return {"series": series, "source": source, "rows": int(len(df)),
                "last": str(df["date"].iloc[-1])[:10]}
    return {"series": s["rate_series"], "source": None, "rows": 0}


# --- labels ----------------------------------------------------------------------

def _has_table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def rate_labels(conn, start: str, end: str, cfg: dict | None = None) -> pd.DataFrame:
    """date, high_rate — forward-filled over non-publishing days. Empty without a series."""
    s = settings(cfg)
    # Check, don't try: a failed pandas query rolls the connection back, which
    # would discard a caller's uncommitted writes on a shared connection.
    if not _has_table(conn, "rates"):
        return pd.DataFrame(columns=["date", "high_rate"])
    r = pd.read_sql_query("SELECT date, value FROM rates WHERE series=? AND date <= ? ORDER BY date",
                          conn, params=(s["rate_series"], end))
    if r.empty:
        return r.assign(high_rate=pd.Series(dtype=bool))[["date", "high_rate"]]
    r["high_rate"] = r["value"] >= float(s["high_rate_pct"])
    return r[["date", "high_rate"]]


def labels(conn, start: str, end: str, cfg: dict | None = None) -> pd.DataFrame:
    """Every predefined regime per SPY session: bull, high_vol, crisis, high_rate (None if unknown)."""
    import robustness
    spy = robustness.regime_labels(conn, start, end)
    spy = spy[spy["date"] <= end]
    rl = rate_labels(conn, start, end, cfg)
    if rl.empty or spy.empty:
        return spy.assign(high_rate=None)
    # The rate known ON a date is the latest published on or before it.
    left = spy.assign(_d=pd.to_datetime(spy["date"])).sort_values("_d")
    right = rl.assign(_d=pd.to_datetime(rl["date"])).drop(columns="date").sort_values("_d")
    m = pd.merge_asof(left, right, on="_d", direction="backward").drop(columns="_d")
    m["high_rate"] = m["high_rate"].astype(object).where(m["high_rate"].notna(), None)
    return m.reset_index(drop=True)


PAIRS = (("bull", "bull", "bear"), ("high_vol", "high_vol", "low_vol"),
         ("crisis", "crisis", "normal"), ("high_rate", "high_rate", "low_rate"))


def breakdown(pnl: pd.DataFrame, lab: pd.DataFrame, min_obs: int = 20) -> dict:
    """pnl: date, pnl_usd. Sum, count and mean per regime; flags a regime with enough obs and net < 0."""
    m = pnl.merge(lab, on="date", how="left")
    out, bad = {}, []
    for col, yes, no in PAIRS:
        if col not in m or m[col].isna().all():
            out[yes] = out[no] = {"unavailable": "no series for this regime"}
            continue
        for flag, name in ((True, yes), (False, no)):
            sub = m[m[col] == flag]["pnl_usd"]
            out[name] = {"obs": int(len(sub)), "net_usd": round(float(sub.sum()), 2),
                         "mean_usd": round(float(sub.mean()), 4) if len(sub) else None}
            if len(sub) >= min_obs and sub.sum() < 0:
                bad.append(name)
    return {"by_regime": out, "negative_regimes": bad, "min_obs": min_obs}


def forward(conn, cfg: dict | None = None) -> dict:
    """Each forward fund's daily equity change, broken down by regime. Weeks of data: read as a log, not a verdict."""
    funds = {}
    for label, table, q in (
            ("paper", "paper_equity", "SELECT run_id, date, equity_usd FROM paper_equity ORDER BY run_id, date"),
            ("pair", "pair_fund_equity", "SELECT name, date, equity_usd FROM pair_fund_equity ORDER BY name, date")):
        if not _has_table(conn, table):
            continue
        df = pd.read_sql_query(q, conn)
        df.columns = ["fund", "date", "equity"]
        for f, g in df.groupby("fund"):
            g = g.sort_values("date")
            funds[f"{label}:{f}"] = pd.DataFrame({"date": g["date"], "pnl_usd": g["equity"].diff()}).dropna()
    if not funds:
        return {}
    lo = min(v["date"].min() for v in funds.values() if len(v))
    hi = max(v["date"].max() for v in funds.values() if len(v))
    lab = labels(conn, lo, hi, cfg)
    return {k: breakdown(v, lab) for k, v in funds.items() if len(v)}


def render_forward(res: dict) -> str:
    names = ["bull", "bear", "high_vol", "low_vol", "crisis", "normal", "high_rate", "low_rate"]
    L = ["", "  FORWARD P&L BY PREDEFINED REGIME (Phase 6 §21) — daily equity change, USD",
         "  " + f"{'fund':<30}" + "".join(f"{n:>11}" for n in names)]
    for k, r in sorted(res.items()):
        cells = []
        for n in names:
            v = r["by_regime"].get(n, {})
            cells.append(f"{'n/a':>11}" if "unavailable" in v else f"{v['net_usd']:>+8.2f}/{v['obs']:<2}")
        L.append(f"  {k[:30]:<30}" + "".join(cells))
    L += ["  cell = net USD / sessions. Weeks of forward data cover few regimes;",
          "  an empty cell is absence of evidence, not a result.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Predefined market regimes (Phase 6 §21).")
    ap.add_argument("--load-rates", action="store_true")
    ap.add_argument("--forward", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    init(conn)
    if a.load_rates:
        r = load_rates(conn, cfg)
        print(f"  rates: {r['rows']} rows from {r['source'] or 'NO SOURCE'}"
              + (f", last {r['last']}" if r.get("last") else ""))
        if not r["rows"]:
            return 1
    if a.forward or not a.load_rates:
        print(render_forward(forward(conn, cfg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
