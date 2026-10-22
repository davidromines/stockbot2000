"""
Predict an earnings beat from fundamentals, buy an in-the-money call before the report (owner 2026-10-22: "use
fundamentals and value analysis to predict which stocks will beat earnings and then buy in the money calls").
Registered experiment `earnings_itm_call_v1`. Read-only research: nothing is written but its own files.

EVENTS  every quarterly surprise in `daily_sue` (SUE: EPS against the same quarter a year earlier, scaled by the
        company's own earlier variability; > 0 = a "beat"; NOT the analysts' consensus, which this project does not
        have). An event TRADES only if its earnings release has an SEC date (8-K item 2.02) at most 45 sessions before
        the filing the surprise comes from; the release's reaction session R follows earnings_study (after 16:00 New
        York = the next session). Without a release date there is no honest buy date, so the event is not traded.
PREDICT point in time. Features as of A = min(the buy date, 60 days before the filing): the last two surprises (only
        if filed by A), Piotroski F, book-to-market, gross profitability, accruals, ROA, earnings yield, asset growth
        (daily_fundamentals as of A) and the 120-session price change to A. Walk-forward by calendar year: a logistic
        regression trained only on surprises filed before 1 January of the year it scores. Selected: a predicted
        probability at or above the 80th percentile of the TRAINING predictions (the top fifth; no future
        distribution). Also reported: the last-surprise rule alone (top fifth of the previous SUE) and every event.
TRADE   buy B = 5 sessions before R: one call with delta 0.70-0.80, 20-75 days to expiry, expiring after the exit,
        buy/sell gap <= 5% of the mid; delta nearest 0.75, then the nearest expiry; bought at B's ask. Sell X = 1
        session after R at the bid (X+1 or X+2 if X has no quote; otherwise not counted). One trade per event.
COMPARE the stock over the same days (adjusted closes B -> X), and the stock scaled by the call's leverage at entry
        (delta x the unadjusted spot / the ask): does the call do better than the same exposure in the stock?

PASS (written before any result), on the model-selected trades: mean return per trade > 0, date-clustered t >= 2.8,
positive in at least half the calendar years, and the mean beats the leverage-matched stock. A pass is a candidate for
a paper fund only; live needs the account's options approval, capital for ~$2,000-6,000 contracts, and the owner.

    ./venv/bin/python earnings_call_test.py --register
    ./run_bounded.sh ./venv/bin/python earnings_call_test.py --run [--write]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

ROOT = Path(__file__).resolve().parent
EXPERIMENT = "earnings_itm_call_v1"
FUND = ["piotroski_f", "book_to_market", "gross_profitability", "accruals", "roa", "earnings_yield", "asset_growth"]
FEATURES = ["prev_sue", "prev2_sue"] + FUND + ["mom120"]
BUY_BEFORE, SELL_AFTER, MAX_RELEASE_LAG = 5, 1, 45
DELTA = (0.70, 0.80)
DTE = (20, 75)
MAX_GAP = 0.05
TOP = 0.80
T_NEED = 2.8
FIRST_TEST_YEAR = 2020
TRADES_CSV = ROOT / "data" / "earnings_call_trades.csv"


# --- events ------------------------------------------------------------------------------------
def surprise_events(conn) -> pd.DataFrame:
    """One row per quarterly surprise: ticker, sue_date (the first day it was known), sue, and the previous two."""
    d = pd.read_sql("SELECT ticker, date, sue, sue_age FROM daily_sue ORDER BY ticker, date", conn)
    new = (d["ticker"] != d["ticker"].shift()) | (d["sue"] != d["sue"].shift()) | (d["sue_age"] < d["sue_age"].shift())
    ev = d.loc[new, ["ticker", "date", "sue"]].rename(columns={"date": "sue_date"}).reset_index(drop=True)
    g = ev.groupby("ticker")
    ev["prev_sue"], ev["prev_date"] = g["sue"].shift(1), g["sue_date"].shift(1)
    ev["prev2_sue"], ev["prev2_date"] = g["sue"].shift(2), g["sue_date"].shift(2)
    return ev


def attach_release(ev: pd.DataFrame, rep: dict, sessions: np.ndarray) -> pd.DataFrame:
    """R (reaction-session index) = the latest 8-K 2.02 reaction session within MAX_RELEASE_LAG sessions before the
    surprise became known; -1 when there is none (the event is then never traded)."""
    j = np.searchsorted(sessions, ev["sue_date"].to_numpy().astype(str))
    out = np.full(len(ev), -1)
    for i, (t, jj) in enumerate(zip(ev["ticker"].to_numpy(), j)):
        r = rep.get(t)
        if r is None:
            continue
        k = np.searchsorted(r, jj, side="right") - 1
        if k >= 0 and jj - MAX_RELEASE_LAG <= r[k] <= jj:
            out[i] = r[k]
    ev = ev.copy()
    ev["R"] = out
    return ev


def as_of_dates(ev: pd.DataFrame, sessions: np.ndarray) -> pd.Series:
    """A = min(the buy date, 60 days before the surprise date); the buy date exists only when R does."""
    early = (pd.to_datetime(ev["sue_date"]) - pd.Timedelta(days=60)).dt.strftime("%Y-%m-%d")
    buy = [str(sessions[r - BUY_BEFORE]) if r >= BUY_BEFORE else None for r in ev["R"]]
    return pd.Series([min(e, b) if isinstance(b, str) else e for e, b in zip(early, buy)], index=ev.index)


def prev_known(ev: pd.DataFrame, A: pd.Series) -> tuple:
    """The previous two surprises, each only if it was filed by the as-of date (otherwise NaN: no look-ahead)."""
    return (np.where(ev["prev_date"].fillna("9999") <= A, ev["prev_sue"], np.nan),
            np.where(ev["prev2_date"].fillna("9999") <= A, ev["prev2_sue"], np.nan))


def features(conn, ev: pd.DataFrame, A: pd.Series) -> pd.DataFrame:
    """Point-in-time features as of A, one company at a time (loading every company's daily fundamentals and prices at
    once was killed at the 6 GB cap, 2026-10-22). A previous surprise counts only if it was known by A."""
    X = ev[["ticker"]].copy()
    X["A"] = A.values
    X["prev_sue"], X["prev2_sue"] = prev_known(ev, A)
    for col in FUND + ["mom120"]:
        X[col] = np.nan
    cols = ", ".join(FUND)
    for t, idx in X.groupby("ticker").groups.items():
        a = pd.DataFrame({"A": pd.to_datetime(X.loc[idx, "A"]), "_i": idx}).sort_values("A")
        f = pd.read_sql(f"SELECT date, {cols} FROM daily_fundamentals WHERE ticker=? ORDER BY date", conn, params=(t,))
        if len(f):
            f["date"] = pd.to_datetime(f["date"])
            m = pd.merge_asof(a, f, left_on="A", right_on="date", direction="backward")
            X.loc[m["_i"].to_numpy(), FUND] = m[FUND].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        p = pd.read_sql("SELECT date, close FROM prices WHERE ticker=? AND date >= '2010-01-01' ORDER BY date", conn,
                        params=(t,))
        if len(p) > 120:
            p["date"] = pd.to_datetime(p["date"])
            p["mom120"] = p["close"] / p["close"].shift(120) - 1
            m = pd.merge_asof(a, p[["date", "mom120"]], left_on="A", right_on="date", direction="backward")
            X.loc[m["_i"].to_numpy(), "mom120"] = pd.to_numeric(m["mom120"], errors="coerce").to_numpy(dtype=float)
    return X[["ticker", "A"] + FEATURES]


# --- prediction (walk-forward) -------------------------------------------------------------------
def walk_forward(ev: pd.DataFrame, X: pd.DataFrame) -> pd.DataFrame:
    """For each test year: fit on surprises filed before 1 January, score that year. Adds p_model, sel_model, sel_rule."""
    from sklearn.linear_model import LogisticRegression
    out = ev.copy()
    out["p_model"] = np.nan
    out["sel_model"] = False
    out["sel_rule"] = False
    year = out["sue_date"].str[:4].astype(int)
    y = (out["sue"] > 0).astype(int)
    for Y in sorted(set(year[year >= FIRST_TEST_YEAR])):
        tr, te = (year < Y).to_numpy(), (year == Y).to_numpy()
        Xtr, Xte = X.loc[tr, FEATURES], X.loc[te, FEATURES]
        med = Xtr.median()
        mu, sd = Xtr.fillna(med).mean(), Xtr.fillna(med).std().replace(0, 1)
        z = lambda M: ((M.fillna(med) - mu) / sd).clip(-5, 5).to_numpy()          # noqa: E731
        m = LogisticRegression(max_iter=500).fit(z(Xtr), y[tr])
        ptr, pte = m.predict_proba(z(Xtr))[:, 1], m.predict_proba(z(Xte))[:, 1]
        out.loc[te, "p_model"] = pte
        out.loc[te, "sel_model"] = pte >= np.quantile(ptr, TOP)
        cut = np.nanquantile(Xtr["prev_sue"], TOP)
        out.loc[te, "sel_rule"] = (Xte["prev_sue"] >= cut).to_numpy()
    return out


# --- the option trade ----------------------------------------------------------------------------
def pick_call(conn, sym: str, buy: str, exit_: str):
    """(expiration, strike, ask, delta) of the call to buy on `buy`, or None."""
    rows = conn.execute("SELECT expiration, strike, bid, ask, delta FROM option_quotes WHERE date=? AND symbol=? AND cp='C' "
                        "AND delta BETWEEN ? AND ? AND bid > 0 AND ask > bid", (buy, sym, *DELTA)).fetchall()
    b = date.fromisoformat(buy)
    ok = []
    for e, k, bid, ask, dl in rows:
        dte = (date.fromisoformat(e) - b).days
        if DTE[0] <= dte <= DTE[1] and e > exit_ and (ask - bid) / ((ask + bid) / 2) <= MAX_GAP:
            ok.append((abs(dl - 0.75), e, k, ask, dl))
    if not ok:
        return None
    _, e, k, ask, dl = min(ok)
    return e, k, ask, dl


def exit_bid(conn, sym: str, e: str, k: float, dates: list):
    for d in dates:
        r = conn.execute("SELECT bid FROM option_quotes WHERE date=? AND symbol=? AND expiration=? AND strike=? AND cp='C'",
                         (d, sym, e, k)).fetchone()
        if r and r[0] is not None and r[0] > 0:
            return d, float(r[0])
    return None


def local_spot(conn, sym: str, d: str) -> float | None:
    """The unadjusted spot on `d` from the STORED chain by put-call parity (S ~ K + C - P at the strike where call and
    put mids are closest), as options_lab.spot does — without its network fetch, so this test only reads."""
    by = {}
    for e, k, cp, b, a in conn.execute("SELECT expiration, strike, cp, bid, ask FROM option_quotes WHERE symbol=? AND date=? "
                                       "AND bid IS NOT NULL AND ask > 0", (sym, d)):
        by.setdefault((e, k), {})[cp] = (b + a) / 2
    pairs = [(k, v["C"] - v["P"]) for (e, k), v in by.items() if "C" in v and "P" in v]
    if not pairs:
        return None
    k, diff = min(pairs, key=lambda x: abs(x[1]))
    return k + diff


def trade(conn, sym: str, R: int, sessions: np.ndarray) -> dict | None:
    if R - BUY_BEFORE < 0 or R + SELL_AFTER + 2 >= len(sessions):
        return None
    buy, x = str(sessions[R - BUY_BEFORE]), str(sessions[R + SELL_AFTER])
    c = pick_call(conn, sym, buy, x)
    if not c:
        return None
    e, k, ask, dl = c
    ex = exit_bid(conn, sym, e, k, [str(sessions[R + SELL_AFTER + i]) for i in range(3)])
    if not ex:
        return {"symbol": sym, "buy": buy, "missing_exit": True}
    xd, bid = ex
    p0 = conn.execute("SELECT close FROM prices WHERE ticker=? AND date=?", (sym, buy)).fetchone()
    p1 = conn.execute("SELECT close FROM prices WHERE ticker=? AND date=?", (sym, xd)).fetchone()
    s_ret = (p1[0] / p0[0] - 1) if p0 and p1 and p0[0] else np.nan
    spot = local_spot(conn, sym, buy)
    lev = dl * spot / ask if spot else np.nan
    return {"symbol": sym, "buy": buy, "exit": xd, "report": str(sessions[R]), "expiration": e, "strike": k, "delta": dl,
            "ask": ask, "bid": bid, "contract_usd": ask * 100, "ret": bid / ask - 1, "stock_ret": s_ret, "leverage": lev,
            "stock_lev_ret": lev * s_ret if lev == lev and s_ret == s_ret else np.nan, "missing_exit": False}


# --- statistics and the verdict -------------------------------------------------------------------
def stats(t: pd.DataFrame) -> dict:
    import forward_stats as fs
    t = t[~t["missing_exit"]] if len(t) else t
    if len(t) < 10:
        return {"n": int(len(t)), "pass": False}
    r = t["ret"].to_numpy(float)
    cs = fs.cluster_stats(r, t["report"].astype(str).to_numpy())
    by = t.assign(y=t["report"].str[:4]).groupby("y")["ret"].mean()
    diff = (t["ret"] - t["stock_lev_ret"]).dropna()
    out = {"n": int(len(r)), "mean": float(r.mean()), "median": float(np.median(r)), "win": float((r > 0).mean()),
           "t": cs["t"], "dates": cs["clusters"], "by_year": {k: float(v) for k, v in by.items()},
           "years_positive": int((by > 0).sum()), "years": int(len(by)),
           "stock_mean": float(t["stock_ret"].mean()), "beat_rate": float(t["beat"].mean()) if "beat" in t else None,
           "vs_stock_lev": float(diff.mean()) if len(diff) else None,
           "median_contract_usd": float(t["contract_usd"].median()), "mean_usd": float((t["ret"] * t["contract_usd"]).mean())}
    out["pass"] = bool(out["mean"] > 0 and (out["t"] or 0) >= T_NEED and out["years_positive"] * 2 >= out["years"]
                       and (out["vs_stock_lev"] or -1) > 0)
    return out


def run(conn) -> dict:
    import earnings_study
    import risk_sweep as rsw
    sessions = np.array([str(r[0])[:10] for r in conn.execute("SELECT date FROM prices WHERE ticker='SPY' ORDER BY date")])
    ev = surprise_events(conn)
    rel = earnings_study.events(conn, "2010-01-01", date.today().isoformat())
    ev = attach_release(ev, rsw.report_sessions(rel, sessions), sessions)
    A = as_of_dates(ev, sessions)
    X = features(conn, ev, A)
    ev = walk_forward(ev, X)
    o0 = conn.execute("SELECT MIN(date) FROM option_quotes").fetchone()[0]
    cand = ev[(ev["R"] >= 0) & (ev["sue_date"].str[:4].astype(int) >= FIRST_TEST_YEAR)]
    cand = cand[[str(sessions[r - BUY_BEFORE]) >= o0 for r in cand["R"]]]
    rows = []
    for i, e in cand.iterrows():
        t = trade(conn, e["ticker"], int(e["R"]), sessions)
        if t:
            rows.append({**t, "beat": bool(e["sue"] > 0), "p_model": e["p_model"],
                         "sel_model": bool(e["sel_model"]), "sel_rule": bool(e["sel_rule"])})
    T = pd.DataFrame(rows)
    T.to_csv(TRADES_CSV, index=False)
    test = ev[ev["sue_date"].str[:4].astype(int) >= FIRST_TEST_YEAR]
    pred = {"events_scored": int(test["p_model"].notna().sum()),
            "beat_rate_all": float((test["sue"] > 0).mean()),
            "beat_rate_model_top": float((test.loc[test["sel_model"], "sue"] > 0).mean()),
            "beat_rate_rule_top": float((test.loc[test["sel_rule"], "sue"] > 0).mean())}
    res = {"prediction": pred, "events_with_release": int((ev["R"] >= 0).sum()), "candidates": int(len(cand)),
           "trades": int(len(T)), "missing_exits": int(T["missing_exit"].sum()) if len(T) else 0}
    if len(T):
        res["model"] = stats(T[T["sel_model"]])
        res["rule"] = stats(T[T["sel_rule"]])
        res["all"] = stats(T)
    return res


def render(res: dict) -> str:
    f = lambda x, s="{:+.1%}": "—" if x is None or x != x else s.format(x)       # noqa: E731
    p = res["prediction"]
    L = [f"# Earnings beat → in-the-money call — {date.today().isoformat()} (`{EXPERIMENT}`)", "",
         f"**Prediction, out of sample ({FIRST_TEST_YEAR} on, {p['events_scored']:,} reports):** beat rate {f(p['beat_rate_all'], '{:.0%}')} "
         f"overall, {f(p['beat_rate_model_top'], '{:.0%}')} in the model's top fifth, {f(p['beat_rate_rule_top'], '{:.0%}')} "
         "for the last-surprise rule alone.", "",
         f"Trades: {res['trades']:,} of {res['candidates']:,} reports with an SEC release date and option data "
         f"({res['missing_exits']} without an exit quote, not counted). One call, delta 0.70-0.80, gap <= 5%, bought 5 "
         "sessions before the report at the ask, sold 1 session after at the bid.", "",
         "| selection | trades | beat rate | mean per trade | median | win | t | years + | stock same days | vs leverage-matched stock | contract | $ per contract | pass |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for k, label in (("model", "model top fifth (decides)"), ("rule", "last-surprise rule"), ("all", "every report")):
        s = res.get(k) or {}
        L.append(f"| {label} | {s.get('n', 0)} | {f(s.get('beat_rate'), '{:.0%}')} | {f(s.get('mean'))} | {f(s.get('median'))} | "
                 f"{f(s.get('win'), '{:.0%}')} | {f(s.get('t'), '{:+.1f}')} | {s.get('years_positive', '—')}/{s.get('years', '—')} | "
                 f"{f(s.get('stock_mean'))} | {f(s.get('vs_stock_lev'))} | {f(s.get('median_contract_usd'), '${:,.0f}')} | "
                 f"{f(s.get('mean_usd'), '${:+,.0f}')} | {'PASS' if s.get('pass') else 'no'} |")
    m = res.get("model") or {}
    L += ["", f"**{'PASS' if m.get('pass') else 'FAIL'}** under the pre-registered rule (mean > 0, t >= {T_NEED}, positive "
          "in at least half the years, better than the leverage-matched stock).", "",
          "Caveats: a 'beat' is EPS against the same quarter a year earlier, not the analysts' consensus; trades need an "
          "SEC 8-K release date; option quotes are end-of-day; one test window (2020 on)."]
    return "\n".join(L) + "\n"


def spec() -> dict:
    return {"primary_metric": "mean return per trade of one ITM call (ask in, bid out) on the model's top fifth",
            "universe": "every daily_sue surprise with an 8-K 2.02 release date and option quotes, 2020 on",
            "entry_rule": {"features": FEATURES, "model": "logistic, walk-forward by year, trained before 1 January",
                           "select": f"p >= training {TOP:.0%} quantile", "buy": f"{BUY_BEFORE} sessions before the release",
                           "contract": {"delta": DELTA, "dte": DTE, "max_gap": MAX_GAP}},
            "exit_rule": f"{SELL_AFTER} session after the release at the bid (up to 2 more sessions for a quote)",
            "holding_period": "about 6 sessions", "cost_assumptions": "buy at the ask, sell at the bid",
            "evaluation_period": f"{FIRST_TEST_YEAR}-01-01 to the run date", "data_version": "market_data.db at the run",
            "stopping_rule": "one run", "sample_size": "every qualifying report",
            "holdout_policy": "walk-forward: each year scored by a model trained only on earlier years",
            "pass_rule": f"mean > 0, date-clustered t >= {T_NEED}, positive in >= half the years, beats the "
                         "leverage-matched stock"}


def register(conn) -> None:
    import experiment_registry as er
    try:
        er.get(conn, EXPERIMENT)
        return
    except er.RegistryError:
        pass
    er.create(conn, EXPERIMENT, "Stocks a point-in-time fundamentals model predicts will beat (EPS vs a year earlier) "
              "gain enough around the report that an in-the-money call bought 5 sessions before and sold 1 session "
              "after makes money, by more than noise and more than the same exposure in the stock. Fails otherwise.",
              "Claude (owner 'Ok build the test', 2026-10-22)", spec())
    er.register(conn, EXPERIMENT)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for x in ("register", "run", "write"):
        ap.add_argument(f"--{x}", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    if a.register:
        register(conn)
        print(f"{EXPERIMENT} registered")
    if a.run:
        import experiment_registry as er
        e = er.get(conn, EXPERIMENT)
        conn.row_factory = None
        res = run(conn)
        text = render(res)
        print(text)
        if a.write:
            (ROOT / "reports" / f"earnings_call_{date.today().isoformat()}.md").write_text(text)
        conn.row_factory = sqlite3.Row
        if e["status"] == er.REGISTERED:
            er.start(conn, EXPERIMENT)
            m = res.get("model") or {}
            er.complete(conn, EXPERIMENT, res, "PASS" if m.get("pass") else "FAIL: the model-selected calls do not pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
