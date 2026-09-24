"""
Baseline portfolios for every forward fund. Phase 6 §16.

A forward result means nothing on its own: a momentum fund up 2% in a month
the market rose 3% is a loser, and a small-cap fund compared only with SPY is
compared with a market it never had access to. Each fund is set beside five
baselines over ITS OWN window, on ITS OWN capital, from the first open after it
started (the same next-open convention as every fill in this project):

    cash             0
    SPY              buy at the first open, hold to the last close
    index ETF        pair fund: its own signal index (SPY / QQQ / IWM / XLE).
                     Stock fund: `baselines.small_cap_etf` (IWM) when the median
                     market cap of the names it traded is under
                     `baselines.large_cap_usd`, else SPY. Fixed rule, set in
                     config before any result.
    matched null     equal weight in EVERY name the fund could have bought on
                     its start date: common stock, clean data, over the price
                     and liquidity floors. The universe it actually had.
    random control   1,000 random portfolios of the fund's own size drawn from
                     that universe (stock funds), or random switching at the
                     fund's own switch count (pair funds); the fund's percentile

The fund's own figure is the authoritative restated net (fund_accounting,
accounting.py), falling back to its equity curve only where no accounting row
exists — and says which. Baselines are charged a modeled round trip.

Weeks of forward data make every one of these noisy. The table is a record,
not a verdict; the scoreboard's sample floors still decide what is rankable.

    python baselines.py                all forward funds
    python baselines.py --json out.json
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys

import numpy as np
import pandas as pd

import costs as costs_mod

log = logging.getLogger("baselines")

DEFAULTS = {"small_cap_etf": "IWM", "large_cap_etf": "SPY", "large_cap_usd": 10e9,
            "random_trials": 1000, "seed": 20260924}


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("baselines") or {})}


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _first_session_after(conn, day: str) -> str | None:
    r = conn.execute("SELECT MIN(date) FROM prices WHERE ticker='SPY' AND date > ?", (day,)).fetchone()
    return r[0] if r else None


def hold_return(conn, ticker: str, start: str, end: str) -> float | None:
    """Open of `start` to the last close on or before `end`. None when either is missing."""
    o = conn.execute("SELECT open FROM prices WHERE ticker=? AND date=? AND open>0", (ticker, start)).fetchone()
    c = conn.execute("SELECT close FROM prices WHERE ticker=? AND date<=? AND close>0 ORDER BY date DESC LIMIT 1",
                     (ticker, end)).fetchone()
    return (c[0] / o[0] - 1) if o and c else None


def matched_universe(conn, cfg: dict, as_of: str) -> list:
    """Tickers the fund could buy after `as_of`'s close: common stock, clean, over the price and liquidity floors."""
    risk = cfg.get("risk") or {}
    types = (cfg.get("universe") or {}).get("tradeable_types") or ["common_stock"]
    ph = ",".join("?" * len(types))
    day = conn.execute("SELECT MAX(date) FROM features WHERE ticker='SPY' AND date<=?", (as_of,)).fetchone()[0]
    if not day:
        return []
    rows = conn.execute(
        f"SELECT f.ticker FROM features f JOIN prices p ON p.ticker=f.ticker AND p.date=f.date "
        f"JOIN symbols s ON s.ticker=f.ticker WHERE f.date=? AND p.close>=? AND f.dollar_volume_20>=? "
        f"AND s.security_type IN ({ph}) AND COALESCE(s.data_quality,'')=''",
        (day, float(risk.get("min_price") or 0), float(risk.get("min_dollar_volume") or 0), *types)).fetchall()
    return sorted(t for (t,) in rows)


def universe_returns(conn, tickers: list, start: str, end: str) -> pd.Series:
    """Per-ticker open(start) -> last close <= end. A name that stops trading keeps its last close (it is not dropped)."""
    if not tickers:
        return pd.Series(dtype=float)
    out = {}
    for i in range(0, len(tickers), 500):
        ch = tickers[i:i + 500]
        ph = ",".join("?" * len(ch))
        o = dict(conn.execute(f"SELECT ticker, open FROM prices WHERE date=? AND open>0 AND ticker IN ({ph})",
                              (start, *ch)).fetchall())
        c = {}
        for t, _d, cl in conn.execute(f"SELECT ticker, date, close FROM prices WHERE date>=? AND date<=? AND close>0 "
                                      f"AND ticker IN ({ph}) ORDER BY date", (start, end, *ch)):
            c[t] = cl
        out.update({t: c[t] / o[t] - 1 for t in o if t in c})
    return pd.Series(out, dtype=float)


def _cost_frac(cm, dv=1e9) -> float:
    return float(cm.round_trip(100.0, dollar_volume=dv)) / 100.0


def stock_fund(conn, cfg, cm, fund: dict) -> dict:
    s = settings(cfg)
    start = _first_session_after(conn, fund["started_on"])
    end = fund["end"]
    cap = fund["capital"]
    out = {"cash": 0.0}
    for name, etf in (("spy", "SPY"), ("index_etf", _index_etf(conn, cfg, fund))):
        r = hold_return(conn, etf, start, end) if start else None
        out[name] = None if r is None else round(cap * (r - _cost_frac(cm)), 2)
        if name == "index_etf":
            out["index_etf_symbol"] = etf
    uni = matched_universe(conn, cfg, fund["started_on"])
    rets = universe_returns(conn, uni, start, end) if start else pd.Series(dtype=float)
    if len(rets):
        dv = _universe_dv(conn, list(rets.index), fund["started_on"])
        cost = np.array([_cost_frac(cm, dv.get(t, 0.0)) for t in rets.index])
        net = rets.to_numpy() - cost
        out["matched_null"] = round(cap * float(net.mean()), 2)
        out["matched_universe_n"] = int(len(net))
        k = max(1, int(fund.get("positions") or 1))
        rng = np.random.default_rng(s["seed"])
        draws = np.array([net[rng.choice(len(net), size=min(k, len(net)), replace=False)].mean()
                          for _ in range(int(s["random_trials"]))]) * cap
        out.update(_random_summary(draws, fund["net"], k))
    else:
        out["matched_null"] = None
    return out


def _universe_dv(conn, tickers: list, as_of: str) -> dict:
    day = conn.execute("SELECT MAX(date) FROM features WHERE ticker='SPY' AND date<=?", (as_of,)).fetchone()[0]
    out = {}
    for i in range(0, len(tickers), 500):
        ch = tickers[i:i + 500]
        ph = ",".join("?" * len(ch))
        out.update(dict(conn.execute(f"SELECT ticker, dollar_volume_20 FROM features WHERE date=? AND ticker IN ({ph})",
                                     (day, *ch)).fetchall()))
    return {k: float(v or 0) for k, v in out.items()}


def _index_etf(conn, cfg, fund: dict) -> str:
    """Fixed rule: IWM when the fund's traded names have a median cap under the line, else SPY."""
    s = settings(cfg)
    if fund.get("index_etf"):
        return fund["index_etf"]
    import market_caps
    caps = [market_caps.lookup(conn, t)[0] for t in fund.get("tickers") or []]
    caps = [c for c in caps if c]
    if not caps:
        return s["small_cap_etf"]            # unknown sizes lean small in this data; stated, not hidden
    return s["large_cap_etf"] if float(np.median(caps)) >= float(s["large_cap_usd"]) else s["small_cap_etf"]


def _random_summary(draws: np.ndarray, fund_net, k: int) -> dict:
    out = {"random_p5": round(float(np.percentile(draws, 5)), 2),
           "random_p50": round(float(np.percentile(draws, 50)), 2),
           "random_p95": round(float(np.percentile(draws, 95)), 2),
           "random_k": int(k)}
    if fund_net is not None:
        out["fund_percentile"] = round(float((draws < fund_net).mean() * 100), 1)
    return out


def pair_fund(conn, cfg, cm, fund: dict) -> dict:
    """Pair funds: SPY and their own index held; matched null = 50/50 in the two legs; random switching at their count."""
    import pair_funds
    from erx_momentum import run_switch
    from pair_momentum import load_pair
    s = settings(cfg)
    r = fund["row"]
    start = _first_session_after(conn, fund["started_on"])
    end, cap = fund["end"], fund["capital"]
    out = {"cash": 0.0}
    for name, etf in (("spy", "SPY"), ("index_etf", r["signal"])):
        x = hold_return(conn, etf, start, end) if start else None
        out[name] = None if x is None else round(cap * (x - _cost_frac(cm)), 2)
    out["index_etf_symbol"] = r["signal"]
    legs = [hold_return(conn, t, start, end) if start else None for t in (r["bull"], r["bear"])]
    out["matched_null"] = (round(cap * (float(np.mean(legs)) - _cost_frac(cm)), 2)
                           if all(v is not None for v in legs) else None)
    w = load_pair(conn, r["bull"], r["bear"], r["signal"], r["started_on"], end)
    res = pair_funds.replay(conn, cfg, r, end)
    if len(w) >= 2 and res:
        rng = np.random.default_rng(s["seed"])
        n, finals = len(w), []
        for _ in range(int(s["random_trials"])):
            flips = np.zeros(n, dtype=bool)
            if res["n_switches"]:
                flips[rng.choice(np.arange(1, n), size=min(int(res["n_switches"]), n - 1), replace=False)] = True
            state, want = rng.random() < 0.5, np.empty(n, dtype=bool)
            for i in range(n):
                state = (not state) if flips[i] else state
                want[i] = state
            finals.append(run_switch(w, pd.Series(want, index=w.index), cm, capital=cap)["final"] - cap)
        out.update(_random_summary(np.array(finals), fund["net"], 1))
    return out


def funds(conn) -> list:
    """Every open forward fund: kind, id, label, window, capital, net and its source."""
    out = []
    acct = {}
    if _has(conn, "fund_accounting"):
        for kind, fid, net, as_of in conn.execute(
                "SELECT fund_kind, fund_id, net_usd, as_of FROM fund_accounting a WHERE as_of = "
                "(SELECT MAX(as_of) FROM fund_accounting b WHERE b.fund_kind=a.fund_kind AND b.fund_id=a.fund_id) "
                "ORDER BY accounting_version"):
            acct[(kind, fid)] = (net, as_of)
    if _has(conn, "paper_runs") and _has(conn, "paper_equity"):
        cur = conn.execute("SELECT * FROM paper_runs WHERE status='open'")
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            r = dict(zip(cols, row))
            eq = conn.execute("SELECT MAX(date), MAX(open_positions) FROM paper_equity WHERE run_id=?",
                              (r["run_id"],)).fetchone()
            last = conn.execute("SELECT equity_usd FROM paper_equity WHERE run_id=? ORDER BY date DESC LIMIT 1",
                                (r["run_id"],)).fetchone()
            if not eq or not eq[0]:
                continue
            net, src = _net(acct, "paper", r["run_id"], last, r["capital_usd"])
            tick = [t for (t,) in conn.execute("SELECT DISTINCT ticker FROM paper_trades WHERE run_id=? UNION "
                                               "SELECT ticker FROM paper_positions WHERE run_id=?",
                                               (r["run_id"], r["run_id"]))] if _has(conn, "paper_trades") else []
            out.append({"kind": "paper", "id": r["run_id"], "label": r.get("label") or r["name"],
                        "started_on": r["started_on"], "end": eq[0], "capital": float(r["capital_usd"]),
                        "positions": eq[1], "tickers": tick, "net": net, "net_source": src})
    if _has(conn, "pair_funds") and _has(conn, "pair_fund_equity"):
        cur = conn.execute("SELECT * FROM pair_funds WHERE status='open'")
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            r = dict(zip(cols, row))
            e = conn.execute("SELECT date, equity_usd FROM pair_fund_equity WHERE name=? ORDER BY date DESC LIMIT 1",
                             (r["name"],)).fetchone()
            if not e:
                continue
            net, src = _net(acct, "pair", r["name"], (e[1],), r["capital_usd"])
            out.append({"kind": "pair", "id": r["name"], "label": r["label"], "started_on": r["started_on"],
                        "end": e[0], "capital": float(r["capital_usd"]), "row": r, "net": net, "net_source": src})
    return out


def _net(acct, kind, fid, last, capital):
    if (kind, fid) in acct:
        return round(float(acct[(kind, fid)][0]), 2), f"accounting {acct[(kind, fid)][1]}"
    if last and last[0] is not None:
        return round(float(last[0]) - float(capital), 2), "equity curve (no accounting row)"
    return None, "none"


def run(conn, cfg: dict) -> list:
    cm = costs_mod.CostModel(cfg)
    rows = []
    for f in funds(conn):
        try:
            b = pair_fund(conn, cfg, cm, f) if f["kind"] == "pair" else stock_fund(conn, cfg, cm, f)
        except Exception as e:                               # noqa: BLE001 — one fund must not sink the table
            log.warning(f"{f['kind']}:{f['id']}: {type(e).__name__}: {e}")
            b = {"error": f"{type(e).__name__}: {e}"}
        rows.append({k: v for k, v in f.items() if k not in ("row", "tickers")} | b)
    return rows


def _m(v):
    return f"{v:>+8.2f}" if isinstance(v, (int, float)) else f"{'—':>8}"


def render(rows: list) -> str:
    L = ["", "  BASELINES PER FORWARD FUND (Phase 6 §16) — USD on each fund's own capital and window",
         f"  {'fund':<28}{'days':>11}{'fund':>9}{'SPY':>9}{'ETF':>13}{'matched':>9}{'rand p50':>9}"
         f"{'p5..p95':>17}{'pctile':>7}"]
    for r in sorted(rows, key=lambda x: (x["kind"], str(x["label"]))):
        etf = f"{_m(r.get('index_etf'))} {r.get('index_etf_symbol') or '':<4}"
        rng = (f"{r['random_p5']:+.2f}..{r['random_p95']:+.2f}" if "random_p5" in r else "—")
        L.append(f"  {str(r['label'])[:28]:<28}{r['started_on'][5:]:>5}-{r['end'][5:]:<5}{_m(r['net'])}"
                 f"{_m(r.get('spy'))}{etf:>13}{_m(r.get('matched_null'))}{_m(r.get('random_p50'))}"
                 f"{rng:>17}{(str(r['fund_percentile']) if 'fund_percentile' in r else '—'):>7}")
    L += ["  cash = 0 for every fund. matched = equal weight in everything the fund could buy on its start",
          "  date; random = same-size random portfolios from that universe (pair funds: random switching",
          "  at the fund's switch count). Baselines net of a modeled round trip. Weeks of data: a record,",
          "  not a verdict.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Baseline portfolios per forward fund (Phase 6 §16).")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    rows = run(conn, cfg)
    print(render(rows))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(rows, fh, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
