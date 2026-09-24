"""
Addendum C (revision 2), Stage 3 — synthetic price paths for dead companies
we hold no prices for.

**Synthetic data here corrects survivorship bias; it is not a substitute for
real data.** Every row is tagged, every company's path is reproducible from its
seed, and nothing here is ever written to the primary `prices` table.

WHO GETS A PATH
---------------
Layer A companies in scope that ended (delisted / stopped filing) with NO real
prices, and with evidence they were exchange-listed (Alpha Vantage, Internet
Archive, or a ticker). EDGAR-only filers with no listing evidence are excluded
by default (`include_edgar_only: false`): generating prices for companies that
may never have traded would inflate the universe with fiction.

HOW A PATH IS MADE (generation_method = residual_block_bootstrap_v1)
-------------------------------------------------------------------
  span      from max(first_seen, scope start, last_seen - max_years) to last_seen
  returns   r_t = beta * SPY_t + e_t. beta and annual idiosyncratic volatility
            are drawn from the company's cohort (Stage 2); e_t are 20-session
            blocks of REAL residuals from real dead companies, rescaled to the
            drawn volatility. Tied to the real market on every date.
  exit      the reason is the 8-K reason where Layer A has one, otherwise drawn
            from `exit_prior` and tagged `drawn:<reason>`.
              performance  final-year return drawn from the LOWER tail of the
                           real dead sample (p5-p25) — the sample is biased to
                           clean exits (Stage 2 caveat), so its lower tail is
                           the part that looks like failure — then a delisting
                           return N(-0.55, 0.15) on NASDAQ, N(-0.30, 0.15)
                           elsewhere (Shumway 1997; Shumway & Warther 1999)
              merger       final-year return from the whole sample's middle
                           (p25-p75); delisting return N(+0.01, 0.03) (Q8)
              other        whole-sample final-year return; delisting return 0
  price     starting close drawn from real first closes of common stocks in
            the primary database (log-uniform between their p10 and p90)
  bars      close is the path; open is the previous close; high/low widen the
            close by the day's absolute residual. Volume is NULL — unknown,
            never invented.

The exit prior (performance 0.40 / merger 0.55 / other 0.05) and the delisting
returns are literature-based ASSUMPTIONS, recorded in config and on every row.

    python universe_synthetic.py --build     writes data/universe/synthetic_v1.parquet
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

import universe_cohorts as uc

log = logging.getLogger("universe_synthetic")
OUT = "data/universe/synthetic_v3.parquet"
# v2 (2026-09-24): no-change days. Real dead companies are often illiquid —
# 1.6% of their days close unchanged (median) — and v1 had none, which alone let
# a classifier separate the two at AUC 0.987 (Stage 5). Each path now gets a
# flat-day share drawn from `flat_share` and closes unchanged on those days.
# v3 (2026-09-24): beta, total volatility, flat-day share and residual blocks are
# drawn JOINTLY from one real donor company, instead of independently and
# uniformly within the cohort's interquartile range (v2 AUC 0.903: too narrow a
# spread, and the joint structure lost). Idiosyncratic volatility is set so the
# TOTAL volatility matches the donor's, not added on top of the market's.
METHOD = "donor_block_bootstrap_v3"
DEFAULTS = {
    "seed": 20260924, "max_years": 10, "block": 20, "include_edgar_only": False,
    "flat_share": [0.0, 0.04],
    "exit_prior": {"performance": 0.40, "merger": 0.55, "other": 0.05},
    "delisting_return": {"performance_nasdaq": [-0.55, 0.15], "performance_other": [-0.30, 0.15],
                         "merger": [0.01, 0.03], "other": [0.0, 0.0]},
}
REASON_MAP = {"bankruptcy": "performance", "delisting_notice": "performance", "acquisition": "merger"}


def settings(cfg: dict) -> dict:
    s = (cfg.get("universe_reconstruction") or {}).get("synthetic") or {}
    return {**DEFAULTS, **s}


def seed_for(company_id: str, base: int) -> int:
    return int(hashlib.sha256(f"{base}:{company_id}".encode()).hexdigest()[:8], 16)


def targets(layer_a: pd.DataFrame, s: dict) -> pd.DataFrame:
    dead = layer_a[layer_a["in_scope"] & layer_a["status"].isin(["delisted", "ended"])
                   & ~(layer_a["has_primary_prices"] | layer_a["has_finsaber_prices"])]
    if not s["include_edgar_only"]:
        dead = dead[dead["listing_evidence"] != "edgar_only"]
    return dead[dead["last_seen"].notna()]


def donor_residuals(conn, sample: pd.DataFrame, spy: pd.Series) -> list:
    """Per real dead company: standardised residuals plus its beta, total daily vol and flat-day share."""
    fconn = sqlite3.connect("file:data/finsaber.db?mode=ro", uri=True) if os.path.exists("data/finsaber.db") else None
    out = []
    spy_r = spy.pct_change()
    for r in sample.itertuples(index=False):
        ser = uc._series(conn, fconn, r.ticker, r.source == "primary", None, 1260)
        ret = ser.pct_change().dropna()
        j = pd.concat([ret, spy_r], axis=1, join="inner").dropna()
        if len(j) < 120:
            continue
        b = r.beta if r.beta is not None and np.isfinite(r.beta) else 1.0
        raw = j.iloc[:, 0].to_numpy()
        e = raw - b * j.iloc[:, 1].to_numpy()
        e = e[np.isfinite(e)]
        e = np.clip(e, -0.5, 0.5)
        if e.std() > 0:
            out.append({"e": (e - e.mean()) / e.std(), "beta": float(b),
                        "vol": float(np.std(raw[-252:])), "flat": float((np.abs(raw[-252:]) < 1e-6).mean())})
    if fconn:
        fconn.close()
    return out


def _draw_dist(rng, d: dict | None, lo_q="p5", hi_q="p95", default=0.0) -> float:
    if not d:
        return default
    return float(rng.uniform(d[lo_q], d[hi_q]))


def generate(company: dict, spy: pd.Series, donors: list, art: dict, start_prices: np.ndarray,
             s: dict) -> pd.DataFrame:
    seed = seed_for(company["company_id"], s["seed"])
    rng = np.random.default_rng(seed)
    last = company["last_seen"][:10]
    scope_end = s.get("scope_end", "2024-12-31")
    # A company that died after the scope ends is still ALIVE at scope end: its
    # path stops there with no delisting bar (Addendum C question 1: 1996-2024).
    died_in_scope = last <= scope_end
    last = min(last, scope_end)
    first = max(company["first_seen"][:10] if isinstance(company["first_seen"], str) else "1996-01-02",
                art["settings"].get("scope_start", "1996-01-02"),
                (pd.Timestamp(last) - pd.DateOffset(years=s["max_years"])).date().isoformat())
    dates = spy.index[(spy.index >= first) & (spy.index <= last)]
    if len(dates) < 20:
        return pd.DataFrame()
    known = REASON_MAP.get(company.get("delisting_reason") or "")
    if known:
        reason, tag = known, known
    else:
        pr = s["exit_prior"]
        reason = rng.choice(list(pr), p=np.array(list(pr.values())) / sum(pr.values()))
        tag = f"drawn:{reason}"
    div = uc.division(company.get("sic"))
    cohort, level = uc.lookup(art, company.get("delisting_reason") or "unknown", div, "unknown")
    donor = donors[rng.integers(len(donors))]
    beta = float(np.clip(donor["beta"], -0.5, 3.0))
    m_var = float(np.nanvar(spy.pct_change().reindex(spy.index[-2520:]).to_numpy()))
    vol = float(np.sqrt(max(donor["vol"] ** 2 - beta ** 2 * m_var, (0.2 * donor["vol"]) ** 2)))

    n = len(dates)
    e = []
    d = donor["e"]
    while len(e) < n:
        if len(d) <= s["block"]:
            d = donors[rng.integers(len(donors))]["e"]
            continue
        i = rng.integers(len(d) - s["block"])
        e.extend(d[i:i + s["block"]])
    e = np.asarray(e[:n]) * vol
    m = spy.pct_change().reindex(dates).fillna(0.0).to_numpy()
    r = beta * m + e
    flat = rng.random(n) < donor["flat"]
    r[flat] = 0.0
    e[flat] = 0.0

    fy = cohort.get("final_year_return") or art["cohorts"]["all"]["final_year_return"]
    if not died_in_scope:
        target = None
    elif reason == "performance":
        target = rng.uniform(fy["p5"], fy["p25"])
        mu, sd = s["delisting_return"]["performance_nasdaq" if str(company.get("exchange", "")).upper()
                                      .startswith("NASDAQ") else "performance_other"]
    elif reason == "merger":
        target = rng.uniform(fy["p25"], fy["p75"])
        mu, sd = s["delisting_return"]["merger"]
    else:
        target = rng.uniform(fy["p5"], fy["p95"])
        mu, sd = s["delisting_return"]["other"]
    k = min(252, n)
    # Shape the final year on TRADED days only: a drift added to a no-change day
    # would un-flatten it, exactly in the window the Stage 5 test measures.
    live = ~flat[-k:]
    tail = np.prod(1 + r[-k:][live])
    if target is not None and tail > 0 and live.any():
        d = ((1 + target) / tail) ** (1 / live.sum()) - 1
        seg = r[-k:]
        seg[live] = (1 + seg[live]) * (1 + d) - 1
        r[-k:] = seg
    lo, hi = np.log(np.percentile(start_prices, 10)), np.log(np.percentile(start_prices, 90))
    p0 = float(np.exp(rng.uniform(lo, hi)))
    close = np.maximum(p0 * np.cumprod(1 + np.clip(r, -0.95, 3.0)), 0.01)
    dret = None if target is None else (float(np.clip(rng.normal(mu, sd), -1.0, 1.0)) if sd else float(mu))
    prev = np.concatenate([[p0], close[:-1]])
    wid = np.abs(e) / 2
    df = pd.DataFrame({"company_id": company["company_id"],
                       "ticker": company["ticker"] if isinstance(company["ticker"], str) else company["company_id"],
                       "date": dates, "open": prev, "high": np.maximum(close, prev) * (1 + wid),
                       "low": np.minimum(close, prev) * (1 - wid), "close": close, "volume": np.nan})
    df["is_delisting_bar"] = False
    if died_in_scope:
        final = df.iloc[[-1]].copy()
        final["close"] = max(float(close[-1]) * (1 + dret), 0.0)
        final["low"] = min(float(final["low"].iloc[0]), float(final["close"].iloc[0]))
        final["is_delisting_bar"] = True
        df = pd.concat([df.iloc[:-1], final], ignore_index=True)
    else:
        dret = None
    df["is_synthetic"] = True
    df["data_source"] = "synthetic_v3"
    df["cohort_id"] = f"{level}:{company.get('delisting_reason') or 'unknown'}|{div}"
    df["generation_method"] = METHOD
    df["synthetic_reason"] = tag
    df["delisting_return"] = dret
    df["synthetic_seed"] = seed
    return df


def build(conn, cfg: dict) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq
    s = settings(cfg)
    la = pd.read_parquet("data/universe/layer_a.parquet")
    art = json.load(open(uc.OUT))
    sample = pd.read_parquet("data/universe/cohort_sample_v1.parquet")
    spy = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' ORDER BY date", conn
                            ).set_index("date")["close"]
    donors = donor_residuals(conn, sample, spy)
    starts = np.array([c for (c,) in conn.execute(
        "SELECT close FROM (SELECT p.ticker, p.close, MIN(p.date) FROM prices p JOIN symbols s ON "
        "s.ticker=p.ticker WHERE s.security_type='common_stock' AND p.close>0 GROUP BY p.ticker)")])
    tg = targets(la, s)
    log.info(f"{len(tg):,} companies to generate from {len(donors)} donor residual series")
    writer, n_rows, n_co, reasons = None, 0, 0, {}
    batch = []
    for c in tg.to_dict("records"):
        df = generate(c, spy, donors, art, starts, s)
        if df.empty:
            continue
        batch.append(df)
        n_co += 1
        reasons[df["synthetic_reason"].iloc[0]] = reasons.get(df["synthetic_reason"].iloc[0], 0) + 1
        if len(batch) >= 200:
            t = pa.Table.from_pandas(pd.concat(batch, ignore_index=True), preserve_index=False)
            writer = writer or pq.ParquetWriter(OUT, t.schema)
            writer.write_table(t)
            n_rows += t.num_rows
            batch = []
    if batch:
        t = pa.Table.from_pandas(pd.concat(batch, ignore_index=True), preserve_index=False)
        writer = writer or pq.ParquetWriter(OUT, t.schema)
        writer.write_table(t)
        n_rows += t.num_rows
    if writer:
        writer.close()
    rep = {"companies": n_co, "rows": n_rows, "donors": len(donors), "by_reason": reasons,
           "settings": s, "cohort_artifact_sha256": art["sha256"], "method": METHOD,
           "sha256": hashlib.sha256(open(OUT, "rb").read()).hexdigest() if n_rows else None}
    json.dump(rep, open("data/universe/synthetic_v3_report.json", "w"), indent=1, default=str)
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Addendum C Stage 3: synthetic paths for unpriced dead companies.")
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    if args.build:
        conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
        print(json.dumps(build(conn, cfg), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
