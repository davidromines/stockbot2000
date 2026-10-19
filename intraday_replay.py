"""
Intraday replays (Stage AD7.1-7.3). Read-only research; places nothing, changes no rule.

1. **v0 Runner rules on free 1-minute history.** yfinance serves 1-minute bars for about the last 30 days (8 days per
   request). The replay runs the LIVE scanners unchanged (`intraday_momentum.scan`, `intraday_twin.scan_pairs`) every
   5 minutes through each session's entry window, takes each name's first qualifying signal per session (the signal
   POPULATION, not the cash-limited book), and exits it with the same stop library and minute-bar simulator the plan
   specified (`intraday_sim.simulate_trade`: next-bar latency, adverse-first, gap fills, flatten). Controls on the same
   days: the same name entered at a random time in the entry window with the same exit rule, and SPY over the same
   minutes.

2. **Market intraday momentum** (Gao, Han, Li and Zhou 2018, J. Financial Economics): the index's first half-hour return
   (previous close to 10:00) predicts its last half-hour return (15:30 to 16:00). Tested on 30-minute bars (~60 days)
   and, as an approximation, the first hour on hourly bars (~730 days), for SPY / QQQ / IWM, and implemented long-only
   through the bull or inverse ETF. Controls: always long the bull ETF in the last half-hour; no trade.
   NOTE: the twin-ETF Runner as configured cannot trade this effect: its entry window ends 14:30 ET and it flattens at
   15:45 ET.

3. **Prospective evaluation of the live Runners' logged signals** (`intraday_runner_signals` + `minute_bars`), against
   the pre-registered decision rule `intraday_runner_v0_prospective` (registered by `--register`).

    ./venv/bin/python intraday_replay.py --fetch        # download / refresh the cached 1-minute history (network)
    ./venv/bin/python intraday_replay.py --runners      # (1)  -> reports/intraday_replay_<date>.md
    ./venv/bin/python intraday_replay.py --mim          # (2)
    ./venv/bin/python intraday_replay.py --prospective  # (3)
    ./venv/bin/python intraday_replay.py --register     # pre-register (3)'s decision rule (once)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import costs as costs_mod
import forward_stats as fs
import intraday_momentum as mom
import intraday_runner as ir
import intraday_sim as sim
import intraday_stops as st
import intraday_twin as tw
from universe import load_config

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "intraday_replay"
NY = ir.NY
EXPERIMENT = "intraday_runner_v0_prospective"
STEP_MIN = 5
SEED = 20261019


# --- data ---------------------------------------------------------------------------------------------------
def fetch_1m(tickers: list, days: int = 28, download=None, now=None) -> pd.DataFrame:
    """Completed regular-session 1-minute bars for the last `days` calendar days, in 7-day requests."""
    import minute_bars as mb
    now = now or datetime.now(timezone.utc)
    if download is None:
        import yfinance as yf
        download = lambda tk, a, b: yf.download(tk, start=a, end=b, interval="1m", progress=False,   # noqa: E731
                                                auto_adjust=False, group_by="ticker", threads=True)
    parts, end = [], now
    start_all = now - timedelta(days=days)
    while end > start_all:
        a = max(start_all, end - timedelta(days=7))
        for i in range(0, len(tickers), 60):
            raw = download(tickers[i:i + 60], a.strftime("%Y-%m-%d"), (end + timedelta(days=1)).strftime("%Y-%m-%d"))
            parts.append(mb.normalize(raw, now=now))
        end = a
    if not parts:
        return pd.DataFrame(columns=["ticker", "ts", "open", "high", "low", "close", "volume"])
    out = pd.concat(parts, ignore_index=True).drop_duplicates(["ticker", "ts"]).sort_values(["ticker", "ts"])
    return out.reset_index(drop=True)


def cache_path(kind: str = "1m") -> Path:
    return CACHE / f"bars_{kind}.parquet"


def load_cache(kind: str = "1m") -> pd.DataFrame:
    p = cache_path(kind)
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def by_day(flat: pd.DataFrame) -> dict:
    """{day: {ticker: DataFrame with tz-aware NY ts}}."""
    out = {}
    if flat.empty:
        return out
    f = flat.copy()
    f["day"] = f["ts"].str[:10]
    for day, g in f.groupby("day"):
        per = {}
        for t, d in g.groupby("ticker"):
            d = d.drop(columns=["day"]).copy()
            d["ts"] = pd.to_datetime(d["ts"]).dt.tz_localize(NY)
            per[t] = d.reset_index(drop=True)
        out[day] = per
    return out


# --- (1) runner replays -------------------------------------------------------------------------------------
def _costs_for(feat: dict) -> sim.Costs:
    """The scanner's own round-trip estimate (spread tier + slippage) split into the simulator's per-side terms."""
    rt = float(feat.get("cost") or 0.0009)
    return sim.Costs(half_spread_bps=max(0.5, rt * 1e4 / 2 - 2.0), slippage_bps=2.0)


def _fixed(bars: pd.DataFrame, i: int, n: int) -> float:
    """Return over exactly n minutes from the open of bar i+2 (signal bar i, one bar of latency): open of bar j to the
    close of bar j+n-1. NaN if the session ends first."""
    j = i + 2
    if j + n - 1 >= len(bars):
        return np.nan
    return float(bars["close"].iloc[j + n - 1] / bars["open"].iloc[j] - 1)


def replay(days: dict, scan_fn, stop_for, s: dict, position_dollars: float = 5.0, seed: int = SEED) -> pd.DataFrame:
    """Every name's first qualifying signal per session, exited by the simulator; plus a random-time control."""
    rng = np.random.default_rng(seed)
    rows = []
    for day, per in sorted(days.items()):
        if "SPY" not in per or len(per["SPY"]) < 300:
            continue                                    # a half day or a missing index: skip the session
        d0 = datetime.fromisoformat(day).replace(tzinfo=NY)
        h0, m0 = map(int, s["entry_start"].split(":"))
        h1, m1 = map(int, s["entry_end"].split(":"))
        t, t_end = d0.replace(hour=h0, minute=m0), d0.replace(hour=h1, minute=m1)
        seen = set()
        while t <= t_end:
            cut = {k: b[b["ts"] < t] for k, b in per.items()}
            res = scan_fn(cut, cut.get("SPY"), t + timedelta(seconds=20))
            for c in res["candidates"]:
                k = c["ticker"]
                if k in seen or k not in per:
                    continue
                seen.add(k)
                full = per[k]
                i = len(cut[k]) - 1
                cfg = stop_for(k)
                tr = sim.simulate_trade(full, i, cfg, _costs_for(c), position_dollars=position_dollars)
                if tr is None:
                    continue
                # control: same name, same day, a random signal time in the window, same exit rule
                win = full[(full["ts"] >= d0.replace(hour=h0, minute=m0)) & (full["ts"] <= t_end)].index
                ci = int(rng.choice(win)) if len(win) else i
                ctr = sim.simulate_trade(full, ci, cfg, _costs_for(c), position_dollars=position_dollars)
                spy = per["SPY"]
                si = int((spy["ts"] < t).sum()) - 1
                rows.append({"day": day, "time": t.strftime("%H:%M"), "ticker": k, "direction": c.get("direction", "UP"),
                             "net": tr["net_pct"] / 100, "gross": tr["gross_pct"] / 100, "exit": tr["reason"],
                             "minutes": tr["hold_minutes"], "r15": _fixed(full, i, 15), "r30": _fixed(full, i, 30),
                             "r60": _fixed(full, i, 60), "spy30": _fixed(spy, si, 30),
                             "control_net": ctr["net_pct"] / 100 if ctr else np.nan})
            t += timedelta(minutes=STEP_MIN)
    d = pd.DataFrame(rows)
    if len(d):
        d["x30"] = d["r30"] - d["spy30"]
    return d


def summarize(d: pd.DataFrame) -> dict:
    if d.empty:
        return {"signals": 0}
    cs = fs.cluster_stats(d["net"].to_numpy(), d["day"].to_numpy())
    diff = (d["net"] - d["control_net"]).dropna()
    cd = fs.cluster_stats(diff.to_numpy(), d.loc[diff.index, "day"].to_numpy()) if len(diff) else {}
    return {"signals": int(len(d)), "sessions": int(d["day"].nunique()), "mean_net": float(d["net"].mean()),
            "median_net": float(d["net"].median()), "win": float((d["net"] > 0).mean()),
            "t_day": cs.get("t"), "mean_x30": float(d["x30"].mean()), "mean_control_net": float(d["control_net"].mean()),
            "vs_control": float(diff.mean()) if len(diff) else np.nan, "t_vs_control": cd.get("t"),
            "exits": d["exit"].str.replace(r" \(gap\)", "", regex=True).value_counts().to_dict()}


def runners(cfg: dict, conn) -> dict:
    flat = load_cache("1m")
    days = by_day(flat)
    tickers = sorted({t for per in days.values() for t in per})
    meta = ir.meta_for(conn, tickers)
    s = ir.settings(cfg)
    stock_stop = st.StopConfig(mode="pct", initial_pct=s["stop"]["initial_pct"], trail_pct=s["stop"]["trail_pct"],
                               max_hold_minutes=s["stop"]["max_hold_minutes"], flatten_hhmm=s["stop"]["flatten_hhmm"])
    legs = {t for b, r, _ in tw.pairs_of(cfg) for t in (b, r)}
    stock_scan = lambda cut, spy, now: mom.scan({t: b for t, b in cut.items() if t != "SPY" and t not in legs},  # noqa: E731
                                                spy, meta, now=now, cfg=s)
    stock = replay(days, stock_scan, lambda k: stock_stop, s, s["position_dollars"])
    ts_ = tw.settings(cfg)
    lev = tw.leverage_map(cfg)
    twin_stop = lambda k: st.StopConfig(mode="pct", initial_pct=ts_["stop"]["initial_pct"] * lev.get(k, 1),  # noqa: E731
                                        trail_pct=ts_["stop"]["trail_pct"] * lev.get(k, 1),
                                        max_hold_minutes=ts_["stop"]["max_hold_minutes"], flatten_hhmm=ts_["stop"]["flatten_hhmm"])
    twin_scan = lambda cut, spy, now: tw.scan_pairs({t: b for t, b in cut.items() if t in legs}, meta, now, cfg)  # noqa: E731
    twin = replay(days, twin_scan, twin_stop, {**s, "entry_start": ts_["entry_start"], "entry_end": ts_["entry_end"]},
                  ts_["position_dollars"])
    return {"stock": stock, "twin": twin, "sessions": len(days), "tickers": len(tickers)}


# --- (2) market intraday momentum ------------------------------------------------------------------------------
def mim_table(bars: pd.DataFrame, first_end: str, last_start: str, pairs: list, spread: dict) -> pd.DataFrame:
    """Per index and day: first-period return (previous close -> `first_end` bar close), the last-period return of the
    index, and the long-only implementation: bull ETF if the first return > 0, inverse ETF if < 0, net of costs."""
    b = bars.copy()
    b["day"], b["hm"] = b["ts"].str[:10], b["ts"].str[11:16]
    out = []
    for bull, bear, _lev in pairs:
        ix = b[b.ticker == bull]
        if ix.empty:
            continue
        days = sorted(ix["day"].unique())
        for k in range(1, len(days)):
            prev, d = ix[ix.day == days[k - 1]], ix[ix.day == days[k]]
            fe, ls = d[d.hm == first_end], d[d.hm == last_start]
            if prev.empty or fe.empty or ls.empty:
                continue
            r1 = float(fe["close"].iloc[0] / prev["close"].iloc[-1] - 1)
            rl = float(ls["close"].iloc[0] / ls["open"].iloc[0] - 1)
            leg = bull if r1 > 0 else bear
            lg = b[(b.ticker == leg) & (b.day == days[k]) & (b.hm == last_start)]
            if lg.empty:
                continue
            rr = float(lg["close"].iloc[0] / lg["open"].iloc[0] - 1)
            bl = b[(b.ticker == bull) & (b.day == days[k]) & (b.hm == last_start)]
            out.append({"index": bull, "day": days[k], "r_first": r1, "r_last": rl, "leg": leg,
                        "timed_net": rr - spread.get(leg, 0.0004), "long_net": float(bl["close"].iloc[0] / bl["open"].iloc[0] - 1)
                        - spread.get(bull, 0.0004)})
    return pd.DataFrame(out)


def mim_summary(t: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ix, g in t.groupby("index"):
        x, y = g["r_first"].to_numpy(), g["r_last"].to_numpy()
        slope = np.polyfit(x, y, 1)[0] if len(g) > 2 else np.nan
        corr = float(np.corrcoef(x, y)[0, 1]) if len(g) > 2 else np.nan
        rows.append({"index": ix, "days": len(g), "corr": corr, "slope": slope,
                     "t_corr": corr * np.sqrt((len(g) - 2) / max(1e-12, 1 - corr ** 2)) if len(g) > 2 else np.nan,
                     "timed_mean": g["timed_net"].mean(), "timed_t": fs.iid_stats(g["timed_net"].to_numpy()).get("t"),
                     "long_mean": g["long_net"].mean(), "hit": float((np.sign(x) == np.sign(y)).mean())})
    return pd.DataFrame(rows)


def mim(cfg: dict, conn, download=None) -> dict:
    pairs = tw.pairs_of(cfg)
    legs = sorted({t for b, r, _ in pairs for t in (b, r)})
    meta = ir.meta_for(conn, legs)
    spread = {t: float(costs_mod.estimate_spread_pct(m["dollar_volume_20"])) + 0.0004 for t, m in meta.items()}
    if download is None:
        import yfinance as yf
        download = lambda interval, period: yf.download(legs, period=period, interval=interval, progress=False,  # noqa: E731
                                                        auto_adjust=False, group_by="ticker", threads=True)
    res = {}
    for interval, period, first_end, last_start in (("30m", "60d", "09:30", "15:30"), ("60m", "730d", "09:30", "15:30")):
        raw = download(interval, period)
        flat = _flatten_any(raw)
        res[interval] = mim_table(flat, first_end, last_start, pairs, spread)
    return res


def _flatten_any(raw) -> pd.DataFrame:
    """yfinance multi-ticker frame -> ticker, ts (NY, bar start), open, high, low, close."""
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=["ticker", "ts", "open", "high", "low", "close"])
    parts = []
    tick = raw.columns.get_level_values(0).unique() if isinstance(raw.columns, pd.MultiIndex) else [None]
    for t in tick:
        d = raw[t] if t is not None else raw
        d = d.dropna(subset=["Close"])
        idx = d.index.tz_convert(NY) if d.index.tz is not None else d.index.tz_localize("UTC").tz_convert(NY)
        parts.append(pd.DataFrame({"ticker": t, "ts": idx.strftime("%Y-%m-%d %H:%M"), "open": d["Open"].to_numpy(float),
                                   "high": d["High"].to_numpy(float), "low": d["Low"].to_numpy(float),
                                   "close": d["Close"].to_numpy(float)}))
    return pd.concat(parts, ignore_index=True)


# --- (3) prospective evaluation of the live Runners' logged signals ------------------------------------------------
DECISION = {"min_sessions": 30, "min_signals": 300, "t_needed": 2.0}


def spec() -> dict:
    return {
        "primary_metric": "mean net return per qualifying signal (entry at the bar after the signal bar's next open, exits by "
                          "the configured stop / 60-minute limit / 15:45 flatten, modelled spread + 2 bps slippage per side), "
                          "date-clustered t; secondary: the same minus a random-time control on the same name and day",
        "universe": "every row of intraday_runner_signals with action QUALIFIED or TRADED (both Runners), from 2026-10-20",
        "entry_rule": "intraday_momentum v0 and intraday_twin v0 exactly as configured on 2026-10-19; thresholds frozen",
        "exit_rule": "intraday_stops as configured on 2026-10-19 (stock 1%/1%, twin 0.35% x leverage), 60 minutes, 15:45 ET",
        "holding_period": "same day; at most 60 minutes",
        "cost_assumptions": "the scanner's own round-trip estimate split into half spread + 2 bps slippage per side",
        "evaluation_period": f"from 2026-10-20 until both >= {DECISION['min_sessions']} sessions and >= {DECISION['min_signals']} signals",
        "data_version": "minute_bars as collected by the Runner (yfinance 1-minute, New York time)",
        "stopping_rule": "one evaluation at the fixed sample: mean net > 0 with date-clustered t >= 2 -> paper, then micro-live "
                         "with stop conditions; mean net <= 0 -> retire v0; otherwise continue to twice the sample once",
        "sample_size": f"{DECISION['min_signals']} signals over {DECISION['min_sessions']} sessions, per Runner",
        "holdout_policy": "no threshold is tuned on these signals; any v1 rule is a new experiment on new dates",
    }


def register(conn) -> dict:
    import experiment_registry as er
    try:
        return er.get(conn, EXPERIMENT)
    except er.RegistryError:
        er.create(conn, EXPERIMENT,
                  "The v0 Intraday Runner rules (stock momentum and twin-ETF index direction) earn a positive net return per "
                  "qualifying signal over the following minutes. Fails if the mean net return per signal is <= 0 at the fixed "
                  "sample.", "Claude (Stage AD7.4, owner-approved plan 2026-10-19)", spec())
        return er.register(conn, EXPERIMENT)


def prospective(conn, cfg: dict, since: str = "2026-10-20") -> pd.DataFrame:
    """The logged signals since `since`, each simulated on the stored minute bars."""
    sig = pd.read_sql("SELECT at, session, ticker, action, features FROM intraday_runner_signals WHERE "
                      "action IN ('QUALIFIED','TRADED') AND session >= ? ORDER BY id", conn, params=(since,))
    s, ts_ = ir.settings(cfg), tw.settings(cfg)
    lev = tw.leverage_map(cfg)
    rows = []
    for r in sig.itertuples():
        bars = pd.read_sql("SELECT ts, open, high, low, close, volume FROM minute_bars WHERE ticker=? AND substr(ts,1,10)=? "
                           "ORDER BY ts", conn, params=(r.ticker, r.session))
        if bars.empty:
            continue
        bars["ts"] = pd.to_datetime(bars["ts"]).dt.tz_localize(NY)
        at = pd.Timestamp(r.at).tz_convert(NY)
        i = int((bars["ts"] < at.floor("min")).sum()) - 1
        if i < 0:
            continue
        twin = r.ticker in lev
        c = ts_["stop"] if twin else s["stop"]
        m = lev.get(r.ticker, 1) if twin else 1
        cfg_ = st.StopConfig(mode="pct", initial_pct=c["initial_pct"] * m, trail_pct=c["trail_pct"] * m,
                             max_hold_minutes=c["max_hold_minutes"], flatten_hhmm=c["flatten_hhmm"])
        import json
        feat = json.loads(r.features or "{}")
        tr = sim.simulate_trade(bars, i, cfg_, _costs_for(feat))
        if tr:
            rows.append({"day": r.session, "ticker": r.ticker, "runner": "twin" if twin else "stock", "action": r.action,
                         "net": tr["net_pct"] / 100, "exit": tr["reason"]})
    return pd.DataFrame(rows)


def verdict(d: pd.DataFrame) -> dict:
    out = {}
    for runner, g in (d.groupby("runner") if len(d) else []):
        cs = fs.cluster_stats(g["net"].to_numpy(), g["day"].to_numpy())
        ready = g["day"].nunique() >= DECISION["min_sessions"] and len(g) >= DECISION["min_signals"]
        mean = float(g["net"].mean())
        call = ("INTERIM" if not ready else "PASS: to paper" if (mean > 0 and (cs.get("t") or 0) >= DECISION["t_needed"])
                else "RETIRE v0" if mean <= 0 else "CONTINUE to twice the sample")
        out[runner] = {"signals": len(g), "sessions": int(g["day"].nunique()), "mean_net": mean, "t_day": cs.get("t"),
                       "call": call}
    return out


# --- report ---------------------------------------------------------------------------------------------------------
def _pct(v, s="{:+.3%}"):
    return "n/a" if v is None or v != v else s.format(v)


def render(rr: dict | None, mm: dict | None, pv: dict | None) -> str:
    L = [f"# Intraday replays — {date.today().isoformat()}", "",
         "Read-only research (Stage AD7). Nothing here changes a rule or places an order.", ""]
    if rr:
        L += [f"## 1. v0 Runner rules on free 1-minute history ({rr['sessions']} sessions, {rr['tickers']} names)", "",
              "| Runner | signals | sessions | mean net | median | win | t (by day) | random-time control | vs control (t) | 30-min vs SPY |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for name in ("stock", "twin"):
            sm = summarize(rr[name])
            if not sm.get("signals"):
                L.append(f"| {name} | 0 | | | | | | | | |")
                continue
            L.append(f"| {name} | {sm['signals']} | {sm['sessions']} | {_pct(sm['mean_net'])} | {_pct(sm['median_net'])} | "
                     f"{sm['win']:.0%} | {_pct(sm['t_day'], '{:+.2f}')} | {_pct(sm['mean_control_net'])} | "
                     f"{_pct(sm['vs_control'])} ({_pct(sm['t_vs_control'], '{:+.2f}')}) | {_pct(sm['mean_x30'])} |")
        L += ["", "Net = after the scanner's spread estimate and 2 bps slippage per side, exits by the configured stop, "
              "60-minute limit or 15:45 flatten, one bar of latency. Each name's first signal per session; the population, "
              "not the cash-limited book. A replay on ~20 sessions is weak evidence either way.", ""]
        for name in ("stock", "twin"):
            sm = summarize(rr[name])
            if sm.get("signals"):
                L.append(f"- {name} exits: " + ", ".join(f"{k} {v}" for k, v in sm["exits"].items()))
        L.append("")
    if mm:
        L += ["## 2. Market intraday momentum (first period -> last half-hour)", "",
              "| bars | index | days | corr | t | hit rate | timed long-only net / day | t | always-long net / day |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
        for interval, t in mm.items():
            if t.empty:
                continue
            for r in mim_summary(t).itertuples():
                L.append(f"| {interval} | {r.index} | {r.days} | {r.corr:+.3f} | {r.t_corr:+.2f} | {r.hit:.0%} | "
                         f"{_pct(r.timed_mean)} | {_pct(r.timed_t, '{:+.2f}')} | {_pct(r.long_mean)} |")
        L += ["", "30m: first half-hour (previous close -> 10:00) vs 15:30-16:00. 60m: first hour (previous close -> 10:30) "
              "vs the 15:30-16:00 bar. Timed = buy the bull ETF at 15:30 if the first return is up, the inverse ETF if down, "
              "sell at the close, net of modelled spread + slippage. The configured twin Runner cannot take this trade "
              "(entries end 14:30, flat by 15:45).", ""]
    if pv is not None:
        L += [f"## 3. Prospective: the live Runners' logged signals (pre-registered `{EXPERIMENT}`)", ""]
        if not pv:
            L.append("No signals since 2026-10-20 yet.")
        for k, v in (pv or {}).items():
            L.append(f"- {k}: {v['signals']} signals over {v['sessions']} sessions, mean net {_pct(v['mean_net'])}, "
                     f"t {_pct(v['t_day'], '{:+.2f}')} — **{v['call']}** (decides at >= {DECISION['min_sessions']} sessions "
                     f"and >= {DECISION['min_signals']} signals)")
        L.append("")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--runners", action="store_true")
    ap.add_argument("--mim", action="store_true")
    ap.add_argument("--prospective", action="store_true")
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    db = cfg["database"]["market_data_path"]
    if a.register:
        conn = sqlite3.connect(db, timeout=60)
        conn.row_factory = sqlite3.Row
        e = register(conn)
        print(f"{EXPERIMENT} v{e['version']} {e['status']}")
        return 0
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    if a.fetch:
        s = ir.settings(cfg)
        names = ir.universe(conn, s)
        legs = sorted({t for b, r, _ in tw.pairs_of(cfg) for t in (b, r)})
        flat = fetch_1m(sorted(set(names) | set(legs) | {"SPY"}))
        CACHE.mkdir(parents=True, exist_ok=True)
        flat.to_parquet(cache_path("1m"))
        print(f"cached {len(flat):,} bars, {flat['ticker'].nunique()} names, {flat['ts'].str[:10].nunique()} sessions")
    rr = runners(cfg, conn) if a.runners else None
    mm = mim(cfg, conn) if a.mim else None
    pv = verdict(prospective(conn, cfg)) if a.prospective else None
    if rr or mm or pv is not None:
        text = render(rr, mm, pv)
        print(text)
        if a.write:
            stem = "intraday_prospective" if (pv is not None and not rr and not mm) else "intraday_replay"
            p = ROOT / "reports" / f"{stem}_{date.today().isoformat()}.md"
            p.write_text(text)
            print(f"written {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
