"""
Generator v5 (Stage M4) — dead companies built from evidence first.

Research and diagnosis: docs/STAGE_M_RESEARCH.md. v4 guessed the exit reason
for 99% of its companies and built failures from the lower tail of BUYOUT
final years, so its "failed" companies ended at a median $5.04 — still
buyable the day before they died — and only 13% ever looked distressed. Real
failures in our own data fall from their last $5 close to below $2 in a
median 51 sessions (-68%), at ~121% annualised volatility.

WHAT CHANGES FROM v4 (everything else is v4, which passes the realism gate)
---------------------------------------------------------------------------
1. EXIT TYPE from SEC filings where they exist (dead_evidence.py: Form 25,
   DEFM14A, SC TO-T, SC 13E3, 8-K 1.03 / 2.01 / 3.01, SIC 6770). Only where
   the filings are silent is the type drawn — from the literature's mix of
   DEATHS by exchange (moves to another exchange removed, since those
   companies still have prices). NOT recalibrated on the classified companies:
   buyouts are far more visible in filings than failures, so that mix is biased
   toward buyouts (reported beside the prior, never used):
       Nasdaq 1972-95   performance 59%, merger 35%, other 6%   (Shumway & Warther 1999, T.I)
       NYSE/AMEX 62-93  performance 31%, merger 65%, other 4%   (Shumway 1997, T.I)
   Every row says which: `evidence:<type>` or `prior:<type>`. Companies whose
   filings show an exchange transfer (`transfer_not_death`) are not generated.
2. FAILURES (performance, bankruptcy) copy a REAL distress episode from our
   own database (distress_donors.py, 1,127 episodes): the donor's residuals
   from a year before its last $5 close, through the collapse, and — for
   donors that later died — on to their end. A survivor donor's path stops at
   its distress point; the slide from there to delisting is drawn from the
   dead donors' own post-distress residuals. Price level: the donor's own real
   price at its last $5 close, so the company leaves a $5-floor universe the
   way real failures do, and not the day it dies.
3. DELISTING RETURN for failures from Shumway's measured distribution, not a
   narrow normal: a mass at -100% (worthless) plus a wide body.
       NYSE/AMEX  P(worthless) 0.11, body N(-0.25, 0.45)  -> mean ~-0.33 (Shumway 1997 T.V: -29.9%, sd 48.9%)
       Nasdaq     P(worthless) 0.20, body N(-0.44, 0.40)  -> mean ~-0.55 (Shumway & Warther 1999: -55% effective)
   The body is clipped to [-0.99, +2.0]. These parameters are ASSUMPTIONS fitted
   to the published means and spreads; they are in config and on every row.
4. SPACs (SIC 6770 or a blank-check name with no acquisition evidence) are
   trust shells: ~$10 with ~0.1% daily noise and a slight upward drift for the
   interest, redeemed at the last price. v4 gave them market beta and
   dead-company volatility.
5. SCOPE: EDGAR-only filers v4 excluded come in when they filed a Form 25 —
   the exchange's own delisting form, so proof of a listing (3,307 companies,
   much of the pre-2007 hole).

NOT YET (next steps, stated): 10-K Item 5 quarterly high/low anchors and filed
deal prices (M2b, a network pass over the filings); the twin test (M5).

    ./run_bounded.sh ./venv/bin/python universe_synthetic_v5.py --build
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import universe_cohorts as uc
import universe_synthetic as v4

log = logging.getLogger("universe_synthetic_v5")
OUT = Path("data/universe/synthetic_v5.parquet")
METHOD = "evidence_distress_v5"
COLS = ["company_id", "ticker", "date", "open", "high", "low", "close", "volume", "is_delisting_bar", "is_synthetic",
        "data_source", "cohort_id", "generation_method", "synthetic_reason", "final_year", "delisting_return",
        "synthetic_seed", "event_date", "template"]

DEFAULTS = {
    "prior_by_exchange": {
        "NASDAQ": {"performance": 0.59, "merger": 0.35, "other": 0.06},
        "NYSE": {"performance": 0.31, "merger": 0.65, "other": 0.04},
        "AMEX": {"performance": 0.31, "merger": 0.65, "other": 0.04},
        "other": {"performance": 0.45, "merger": 0.50, "other": 0.05},
    },
    "min_calibration": 200,
    "delisting_mixture": {
        "NASDAQ": {"p_worthless": 0.20, "mu": -0.44, "sd": 0.40},
        "other": {"p_worthless": 0.11, "mu": -0.25, "sd": 0.45},
    },
    "spac": {"price": 10.0, "daily_sd": 0.001, "annual_drift": 0.02},
    "include_form25_edgar_only": True,
}
EVIDENCE_TO_KIND = {"acquired": "merger", "going_private": "other", "voluntary": "other",
                    "performance": "performance", "bankruptcy": "performance", "spac": "spac"}


def settings(cfg: dict) -> dict:
    s = ((cfg.get("universe_reconstruction") or {}).get("synthetic_v5") or {})
    return {**DEFAULTS, **s}


def exch_key(x) -> str:
    x = str(x or "").upper()
    return "NASDAQ" if x.startswith("NASDAQ") else "NYSE" if x.startswith("NYSE") and "MKT" not in x \
        else "AMEX" if ("AMEX" in x or "MKT" in x or "AMERICAN" in x) else "other"


def calibrated_prior(ev: pd.DataFrame, s: dict) -> dict:
    """Literature prior per exchange, replaced by the evidence mix where enough companies are classified."""
    pr = json.loads(json.dumps(s["prior_by_exchange"]))
    known = ev[ev["exit_type"].isin(["acquired", "performance", "bankruptcy", "going_private", "voluntary"])].copy()
    known["kind"] = known["exit_type"].map(EVIDENCE_TO_KIND)
    known["ex"] = known["exchange"].map(exch_key)
    for ex, g in known.groupby("ex"):
        if len(g) >= s["min_calibration"]:
            vc = g["kind"].value_counts(normalize=True)
            pr[ex] = {k: float(vc.get(k, 0.0)) for k in ("performance", "merger", "other")}
            pr[ex]["_n"] = int(len(g))
    return pr


def targets(la: pd.DataFrame, ev: pd.DataFrame, s: dict) -> pd.DataFrame:
    base = v4.targets(la, {"include_edgar_only": False})
    if s["include_form25_edgar_only"] and len(ev):
        f25 = set(ev.loc[ev["delist_form_date"].notna(), "company_id"])
        extra = la[la["in_scope"] & la["status"].isin(["delisted", "ended"])
                   & ~(la["has_primary_prices"] | la["has_finsaber_prices"])
                   & (la["listing_evidence"] == "edgar_only") & la["company_id"].isin(f25) & la["last_seen"].notna()]
        base = pd.concat([base, extra], ignore_index=True).drop_duplicates("company_id")
    return base


def _delist_return(rng, exch: str, s: dict) -> float:
    m = s["delisting_mixture"]["NASDAQ" if exch == "NASDAQ" else "other"]
    if rng.random() < m["p_worthless"]:
        return -1.0
    return float(np.clip(rng.normal(m["mu"], m["sd"]), -0.99, 2.0))


def failure(company: dict, spy: pd.Series, v4donors: list, dd: list, post_pool: list, s: dict, rng,
            dates: pd.Index, died: bool) -> tuple:
    """(returns, residuals, index of the last $5 close) for a failed company on `dates`."""
    n = len(dates)
    m = spy.pct_change().reindex(dates).fillna(0.0).to_numpy()
    end_year = int(str(dates[-1])[:4])
    w = np.array([1.0 / (1 + abs(d["year"] - end_year)) for d in dd])
    d = dd[rng.choice(len(dd), p=w / w.sum())]
    resid = np.asarray(d["resid"], dtype=float)
    flat_src = np.abs(np.asarray(d["ret"], dtype=float)) < 1e-6   # the donor's own no-change days
    if d["died"]:
        seg, fseg = resid, flat_src                    # its own road to the end
    else:
        # A survivor's path stops at its distress point; the slide from there to
        # delisting is a real dead donor's post-distress residuals (and its no-change days).
        pe, pf = post_pool[rng.integers(len(post_pool))]
        seg = np.concatenate([resid[: d["t_offset"] + 1], pe])
        fseg = np.concatenate([flat_src[: d["t_offset"] + 1], pf])
    a_pos = d["a_offset"]                              # the last $5 close, inside seg
    if len(seg) >= n:
        cut = len(seg) - n
        e, flat, a_idx = seg[cut:], fseg[cut:], max(0, a_pos - cut)
    else:
        # Normal life before the donor segment, v4's way: 20-session blocks of real
        # dead-company residuals, scaled to the donor's own pre-collapse volatility.
        k = n - len(seg)
        vol = float(np.std(seg[: max(20, a_pos)])) or 0.02
        pre = []
        while len(pre) < k:
            src = v4donors[rng.integers(len(v4donors))]["e"]
            if len(src) > 20:
                i = rng.integers(len(src) - 20)
                pre.extend(src[i:i + 20])
        e, a_idx = np.concatenate([np.asarray(pre[:k]) * vol, seg]), k + a_pos
        flat = np.concatenate([rng.random(k) < float(fseg.mean()), fseg])
    beta = float(np.clip(d["beta"], -0.5, 3.0))
    r = np.clip(beta * m + e, -0.95, 3.0)
    r[flat], e = 0.0, np.where(flat, 0.0, e)
    # Keep the real event where it happened: over (A, T] the synthetic fall is set to the
    # donor's own real fall, by a constant daily adjustment on traded days. Without it the
    # re-laid market left some paths just above the distress line at T, crossing it later
    # inside the spliced post-distress slide — penny-stock bid-ask bounce — which is what
    # the realism test picked up (lag-1 autocorrelation -0.041 vs -0.009 real).
    t_idx = a_idx + (d["t_offset"] - d["a_offset"])
    if a_idx < t_idx < n:
        live = ~flat[a_idx + 1: t_idx + 1]
        got = float(np.prod(1 + r[a_idx + 1: t_idx + 1]))
        if live.any() and got > 0 and d["fall"] > -1:
            adj = ((1 + d["fall"]) / got) ** (1 / live.sum()) - 1
            seg_r = r[a_idx + 1: t_idx + 1]
            seg_r[live] = (1 + seg_r[live]) * (1 + adj) - 1
            r[a_idx + 1: t_idx + 1] = seg_r
    return r, e, a_idx, d


SPAC_SQL = ("SELECT ticker FROM symbols WHERE security_type='common_stock' AND (upper(name) LIKE '%ACQUISITION CORP%' "
            "OR upper(name) LIKE '%ACQUISITION CO%' OR upper(name) LIKE '%ACQUISITION LTD%') ORDER BY ticker")


def spac_library(conn, parity: int | None = None) -> list:
    """Daily returns of REAL SPAC shares (blank-check common stock we hold prices for).

    A first model (flat $10 with 0.1% noise) was told apart from real SPACs at
    AUC 1.00: real ones do not trade at all on ~55% of days and jump on
    redemption and deal news (kurtosis ~9). So synthetic SPACs copy a real one.
    `parity` keeps half out, for the validation build."""
    spy = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' ORDER BY date", conn
                            ).set_index("date")["close"].pct_change()
    out = []
    for i, (t,) in enumerate(conn.execute(SPAC_SQL).fetchall()):
        if parity is not None and i % 2 != parity:
            continue
        px = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker=? ORDER BY date", conn,
                               params=(t,)).set_index("date")["close"]
        j = pd.concat([px.pct_change().rename("r"), spy.rename("m")], axis=1, join="inner").dropna()
        if len(j) < 60:
            continue
        y, m = np.clip(j["r"].to_numpy(), -0.9, 3.0), j["m"].to_numpy()
        beta = float(np.cov(y, m)[0, 1] / np.var(m)) if np.var(m) > 0 else 0.0
        # Residual and beta, like the failure donors: copying raw returns onto other dates
        # erased the SPAC's small co-movement with its own market (the test's top tell, beta).
        out.append((t, y - beta * m, np.abs(y) < 1e-9, beta))
    return out


def spac_path(dates: pd.Index, s: dict, rng, donors: list, spy: pd.Series) -> tuple:
    """(dates, closes, template): a real SPAC's residuals plus beta x this path's own market, on the
    last of these dates, from the trust price; its no-change days stay no-change days. A donor with
    a shorter history shortens the synthetic life — repeating it to fill the gap left visible joins."""
    tick, e, flat, beta = donors[rng.integers(len(donors))]
    n = min(len(dates), len(e))
    dates = dates[-n:]
    m = spy.pct_change().reindex(dates).fillna(0.0).to_numpy()
    r = np.where(flat[-n:], 0.0, beta * m + e[-n:])
    return dates, s["spac"]["price"] * np.cumprod(1 + r), tick


def build(conn, cfg: dict, out: Path | None = None, donor_parity: int | None = None) -> dict:
    """donor_parity 0/1 builds from half the distress donors — the validation build; the other half is the test."""
    out = Path(out or OUT)
    import pyarrow as pa
    import pyarrow.parquet as pq
    import dead_evidence as de
    s4 = v4.settings(cfg)
    s = settings(cfg)
    la = pd.read_parquet("data/universe/layer_a.parquet")
    ev = pd.read_parquet(de.OUT) if de.OUT.exists() else pd.DataFrame(columns=["company_id", "exit_type"])
    evm = ev.set_index("company_id") if len(ev) else ev
    # Unknown exits use the LITERATURE prior, not the mix of evidence-classified exits:
    # acquisitions leave loud filings (proxies, tender offers) while failures often just
    # stop filing, so the classified mix over-represents buyouts (NASDAQ: 63% merger by
    # evidence vs 35% in Shumway & Warther). The evidence mix is reported, not used.
    prior = s["prior_by_exchange"]
    evidence_mix = calibrated_prior(ev, {**s, "min_calibration": 1}) if len(ev) else {}
    art = json.load(open(uc.OUT))
    sample = pd.read_parquet("data/universe/cohort_sample_v1.parquet")
    spy = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' ORDER BY date", conn
                            ).set_index("date")["close"]
    v4donors = v4.donor_residuals(conn, sample, spy)
    ddf = pd.read_parquet("data/universe/distress_donors.parquet")
    dd = [{"year": int(r.year), "died": bool(r.died), "beta": float(r.beta), "a_offset": int(r.a_offset),
           "t_offset": int(r.t_offset), "resid": json.loads(r.resid), "ret": json.loads(r.ret),
           "price_a": float(r.price_a), "fall": float(r.fall_a_to_t), "ticker": r.ticker}
          for i, r in enumerate(ddf.itertuples()) if donor_parity is None or i % 2 == donor_parity]
    post_pool = [(np.asarray(x["resid"][x["t_offset"] + 1:], dtype=float),
                  np.abs(np.asarray(x["ret"][x["t_offset"] + 1:], dtype=float)) < 1e-6) for x in dd
                 if x["died"] and len(x["resid"]) - x["t_offset"] > 20]
    spac_donors = spac_library(conn, donor_parity)
    starts = np.array([c for (c,) in conn.execute(
        "SELECT close FROM (SELECT p.ticker, p.close, MIN(p.date) FROM prices p JOIN symbols s ON "
        "s.ticker=p.ticker WHERE s.security_type='common_stock' AND p.close>0 GROUP BY p.ticker)")])
    tg = targets(la, ev, s)
    if len(ev):
        not_dead = set(ev.loc[ev["exit_type"] == "transfer_not_death", "company_id"])
        tg = tg[~tg["company_id"].isin(not_dead)]      # moved exchange, still filing: not a death
    log.info(f"{len(tg):,} companies; {len(dd)} distress donors ({len(post_pool)} with a real post-distress slide); "
             f"{len(v4donors)} v4 donors")
    writer, n_rows, counts = None, 0, {}
    batch = []
    for c in tg.to_dict("records"):
        seed = v4.seed_for(c["company_id"], s4["seed"])
        rng = np.random.default_rng(seed + 5)
        e_row = evm.loc[c["company_id"]] if len(ev) and c["company_id"] in evm.index else None
        etype = None if e_row is None else str(e_row["exit_type"])
        if etype in EVIDENCE_TO_KIND:
            kind, tag = EVIDENCE_TO_KIND[etype], f"evidence:{etype}"
        elif v4.REASON_MAP.get(c.get("delisting_reason") or ""):
            kind = v4.REASON_MAP[c["delisting_reason"]]
            tag = f"evidence:{c['delisting_reason']}"
        elif de.BLANK_CHECK.search(str(c.get("name") or "")):
            kind, tag = "spac", "evidence:blank-check name"
        else:
            p = prior.get(exch_key(c.get("exchange")), prior["other"])
            ks = ["performance", "merger", "other"]
            pv = np.array([p[k] for k in ks], dtype=float)
            kind = str(rng.choice(ks, p=pv / pv.sum()))
            tag = f"prior:{kind}"
        if kind in ("merger", "other"):
            s_local = {**s4, "exit_prior": {kind: 1.0}}
            df = v4.generate({**c, "delisting_reason": None}, spy, v4donors, art, starts, s_local)
            if df.empty:
                continue
            df["event_date"] = None
            df["template"] = None              # v4 method: a real buyout final year, not recorded by v4
        else:
            last = min(c["last_seen"][:10], s4.get("scope_end", "2024-12-31"))
            died = c["last_seen"][:10] <= s4.get("scope_end", "2024-12-31")
            first = max(c["first_seen"][:10] if isinstance(c["first_seen"], str) else "1996-01-02",
                        art["settings"].get("scope_start", "1996-01-02"),
                        (pd.Timestamp(last) - pd.DateOffset(years=s4["max_years"])).date().isoformat())
            if kind == "spac":
                # A SPAC must merge or liquidate within its charter deadline (typically 24
                # months, extensions rarely past 36): a longer "history" is a reused name.
                first = max(first, (pd.Timestamp(last) - pd.DateOffset(years=3)).date().isoformat())
            dates = spy.index[(spy.index >= first) & (spy.index <= last)]
            if len(dates) < 20:
                continue
            ex = exch_key(c.get("exchange"))
            if kind == "spac":
                dates, close, template = spac_path(dates, s, rng, spac_donors, spy)
                e = np.zeros(len(dates))
                dret = 0.0 if died else None
                final_kind = "spac_trust"
                event = None
            else:
                r, e, a_idx, dn = failure(c, spy, v4donors, dd, post_pool, s, rng, dates, died)
                # The donor's own real price at its last tradeable close (typically just over
                # $5): a level drawn from $5-8 made synthetic failures take twice as long to
                # reach distress as real ones (101 vs 51 sessions).
                lvl = float(dn["price_a"])
                growth = np.cumprod(1 + r)
                close = np.maximum(lvl * growth / growth[a_idx], 0.01)
                dret = _delist_return(rng, ex, s) if died else None
                final_kind = "distress_donor"
                event = str(dates[a_idx])
                template = dn["ticker"]
            prev = np.concatenate([[close[0]], close[:-1]])
            wid = np.abs(e) / 2
            df = pd.DataFrame({"company_id": c["company_id"],
                               "ticker": c["ticker"] if isinstance(c["ticker"], str) else c["company_id"],
                               "date": dates, "open": prev, "high": np.maximum(close, prev) * (1 + wid),
                               "low": np.minimum(close, prev) * (1 - wid), "close": close, "volume": np.nan})
            df["is_delisting_bar"] = False
            if died:
                fin = df.iloc[[-1]].copy()
                fin["close"] = max(float(close[-1]) * (1 + dret), 0.0)
                fin["low"] = min(float(fin["low"].iloc[0]), float(fin["close"].iloc[0]))
                fin["is_delisting_bar"] = True
                df = pd.concat([df.iloc[:-1], fin], ignore_index=True)
            df["is_synthetic"] = True
            df["cohort_id"] = f"v5:{kind}|{ex}"
            df["final_year"] = final_kind
            df["delisting_return"] = dret
            df["synthetic_seed"] = seed
            df["event_date"] = event           # failures: the last close at the tradeable level
            df["template"] = template          # the REAL company whose path this copies
        df["data_source"] = "synthetic_v5"
        df["generation_method"] = METHOD
        df["synthetic_reason"] = tag
        counts[tag] = counts.get(tag, 0) + 1
        batch.append(df[COLS])
        if len(batch) >= 200:
            t = pa.Table.from_pandas(pd.concat(batch, ignore_index=True), preserve_index=False)
            writer = writer or pq.ParquetWriter(out, t.schema)
            writer.write_table(t.cast(writer.schema))
            n_rows += t.num_rows
            batch = []
    if batch:
        t = pa.Table.from_pandas(pd.concat(batch, ignore_index=True), preserve_index=False)
        writer = writer or pq.ParquetWriter(out, t.schema)
        writer.write_table(t.cast(writer.schema))
        n_rows += t.num_rows
    if writer:
        writer.close()
    rep = {"companies": int(sum(counts.values())), "rows": int(n_rows), "by_reason": counts,
           "prior_used": prior, "evidence_mix_not_used": evidence_mix, "settings": s, "distress_donors": len(dd), "post_distress_pool": len(post_pool),
           "method": METHOD}
    if donor_parity is None:
        Path("data/universe/synthetic_v5_report.json").write_text(json.dumps(rep, indent=1, default=str))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Synthetic dead companies, v5 (Stage M4).")
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True, timeout=60)
    if a.build:
        rep = build(conn, cfg)
        print(json.dumps({k: rep[k] for k in ("companies", "rows", "by_reason", "prior_used")}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
