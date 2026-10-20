"""
Earnings-skip rule and stop widths, backtested (Stage AD3.5 / AD3.6). Two registered experiments, one run.
Research only: a passing result changes nothing live — a live stop or entry rule changes only through AD6's evidence
gate and the owner.

THE STRATEGIES (frozen into both specs at registration, genome and all, so a later slot or ranking change cannot change
what was tested): the medium-term slot holders with an entry rule, plus the ranking's top TOP strategies that pass its
gate, are not search strategies and have an entry rule — what can hold a slot at the monthly review.

DATA: the ranking's own basis — the factory backtest window (config factory.backtest_window), real panel plus the
synthetic dead companies (`as_is`, survivorship_backtest's loaders), next-open fills, costs.CostModel, exits priced off
unfiltered closes, at most CAP entries per strategy (uniform sample). Every signal is an independent trade in the
simulator, so a rule that only REMOVES entries is exactly the baseline's trade list minus those entries: the
comparison is paired by construction.

1. `earnings_skip_v1` (AD3.5). The study (earnings_study.py, 2026-10-19) found 5-session windows across an 8-K 2.02
   announcement have 1.64x the dispersion of control windows and no higher mean. Rule tested: skip an entry when the
   stock reports within N sessions of the fill (the fill session counts as the first; an announcement after 16:00 New
   York time belongs to the next session). Primary N = 5; N = 3 and 10 reported, not deciding. Strategies whose rule
   reads earnings columns (storage.SUE_COLS) are excluded — they are ABOUT the report.
   Report dates come from edgar_events (8-K item 2.02), which covers ~400-565 tickers a year in 2016-2019, so the test
   runs on COVERED ticker-years only (>= COVER_MIN reports that calendar year): elsewhere the rule could not bind and
   would only dilute the comparison. Robustness: a point-in-time PREDICTED date (the last known report + PRED_DAYS
   calendar days), since a live rule reads a calendar published in advance and the actual date is a mild look-ahead.
   PASS iff all four hold (written before any result):
     a. per-trade Sharpe (mean / sd of net return per trade, covered trades) is higher with the rule in a majority of
        the strategies that have >= MIN_REMOVED removed trades;
     b. the mean over those strategies of the removed trades' mean net return is <= that of the kept trades' (the
        rule does not throw away the better trades);
     c. pooled over those strategies, (a)'s mean Sharpe change is > 0 in a majority of calendar years;
     d. the predicted-date version also satisfies (a).
2. `stop_width_slots_v1` (AD3.6). Cells: stop_atr_multiple in STOPS, each strategy's own entry, hold, exit and
   take-profit unchanged. Per strategy and cell, paired by trade (same entries): ADOPTABLE iff the change in net return
   per trade is > 0 with a date-clustered t >= T_NEED (about a Bonferroni 5% across the five cells) AND > 0 in a
   majority of calendar years. The 2026-09-24 sweep (`stop_width`) found tighter stops did worse on rising_200, so
   "nothing adoptable" is a live possibility and is a result.

    ./venv/bin/python risk_sweep.py --register                     # freezes the strategies; prints them
    ./run_bounded.sh ./venv/bin/python risk_sweep.py --run         # resumable per strategy (data/risk_sweep.jsonl)
    ./venv/bin/python risk_sweep.py --report [--write]             # verdicts; completes both experiments when done
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import gc
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("risk_sweep")

ROOT = Path(__file__).resolve().parent
EXP_EARN = "earnings_skip_v1"
EXP_STOP = "stop_width_slots_v1"
STOPS = (1.5, 2.0, 3.0, 4.0, 6.0)
SKIP_N = (3, 5, 10)
PRIMARY_N = 5
TOP = 20
CAP = 20000
COVER_MIN = 3
PRED_DAYS = 91
MIN_REMOVED = 30
T_NEED = 2.58
SINK = ROOT / "data" / "risk_sweep.jsonl"


# --- the strategies ------------------------------------------------------------------

def candidates(conn, cfg, top: int = TOP) -> dict:
    """name -> {key, version, genome}: medium-term slot holders with an entry rule, then the ranking's top `top`."""
    import ranking
    import slots
    out = {}

    def add(key, ver):
        name = f"{key}@v{ver}"
        if name in out or ranking.from_search(conn, key):
            return False
        try:
            g = slots.genome_for(conn, key, ver)
        except Exception:                                          # noqa: BLE001
            return False
        if not g or not g.get("entry") or not isinstance(g.get("risk"), dict):
            return False
        out[name] = {"key": key, "version": int(ver), "genome": g}
        return True

    for _, h in sorted(slots.current(conn, cfg).items()):
        if h and not str(h["strategy_key"]).startswith("intraday:"):
            add(h["strategy_key"], h["version"])
    n = 0
    for r in ranking.rank(conn, cfg):
        if n >= top:
            break
        if r["passes_gate"] and add(r["strategy_key"], r["version"]):
            n += 1
    return out


def about_earnings(genome: dict) -> bool:
    import storage
    return bool(storage.columns_read([genome]) & set(storage.SUE_COLS))


def with_stop(genome: dict, mult: float) -> dict:
    g = json.loads(json.dumps(genome))
    g.setdefault("risk", {})["stop_atr_multiple"] = float(mult)
    return g


# --- report dates ----------------------------------------------------------------------

def report_sessions(events: pd.DataFrame, sessions: np.ndarray) -> dict:
    """ticker -> sorted session indices of each report's reaction session (earnings_study's convention)."""
    out = {}
    for t, g in events.groupby("ticker"):
        idx = np.searchsorted(sessions, g["day"].to_numpy().astype(str))
        same = (idx < len(sessions)) & (sessions[np.minimum(idx, len(sessions) - 1)] == g["day"].to_numpy().astype(str))
        idx = idx + (g["after_close"].to_numpy().astype(bool) & same)
        idx = idx[idx < len(sessions)]
        if idx.size:
            out[str(t)] = np.unique(idx)
    return out


def covered(events: pd.DataFrame, min_reports: int = COVER_MIN) -> set:
    """{(ticker, year)} with at least `min_reports` reports that calendar year."""
    y = events.assign(year=events["day"].astype(str).str[:4])
    n = y.groupby(["ticker", "year"]).size()
    return {(str(t), str(yr)) for (t, yr), k in n.items() if k >= min_reports}


def skip_mask(tickers, sig, rep: dict, n: int) -> np.ndarray:
    """True where a report session R satisfies sig+1 <= R <= sig+n (the fill session is the first of n)."""
    out = np.zeros(len(sig), dtype=bool)
    for i, (t, s) in enumerate(zip(tickers, sig)):
        r = rep.get(t)
        if r is None or s < 0:
            continue
        j = np.searchsorted(r, s + 1)
        out[i] = j < len(r) and r[j] <= s + n
    return out


def predicted_mask(tickers, sig, rep: dict, sessions: np.ndarray, n: int, days: int = PRED_DAYS) -> np.ndarray:
    """The point-in-time version: the next report is predicted as the last report on or before the signal + `days`."""
    out = np.zeros(len(sig), dtype=bool)
    for i, (t, s) in enumerate(zip(tickers, sig)):
        r = rep.get(t)
        if r is None or s < 0:
            continue
        j = np.searchsorted(r, s, side="right") - 1
        if j < 0:
            continue
        p_day = (date.fromisoformat(str(sessions[r[j]])[:10]) + timedelta(days=days)).isoformat()
        p = int(np.searchsorted(sessions, p_day))
        out[i] = s + 1 <= p <= s + n
    return out


# --- statistics (pure; tested) ----------------------------------------------------------

def sharpe(x) -> float:
    x = np.asarray(x, dtype=float)
    if len(x) < 3:
        return float("nan")
    sd = float(x.std(ddof=1))
    return float(x.mean() / sd) if sd > 0 else float("nan")


def earn_summary(ret, years, cov, masks: dict) -> dict:
    """Per strategy: covered trades' baseline vs each rule (`masks`: label -> removed mask)."""
    ret, years, cov = np.asarray(ret, float), np.asarray(years).astype(str), np.asarray(cov, bool)
    out = {"covered": int(cov.sum()), "base_mean": float(ret[cov].mean()) if cov.any() else None,
           "base_sharpe": sharpe(ret[cov]), "rules": {}}
    for label, m in masks.items():
        rem, kept = cov & np.asarray(m, bool), cov & ~np.asarray(m, bool)
        by_year = {}
        for y in sorted(set(years[cov])):
            b, k = cov & (years == y), kept & (years == y)
            by_year[y] = sharpe(ret[k]) - sharpe(ret[b])
        out["rules"][label] = {"removed": int(rem.sum()), "kept": int(kept.sum()),
                               "removed_mean": float(ret[rem].mean()) if rem.any() else None,
                               "kept_mean": float(ret[kept].mean()) if kept.any() else None,
                               "removed_sd": float(ret[rem].std(ddof=1)) if rem.sum() > 2 else None,
                               "kept_sd": float(ret[kept].std(ddof=1)) if kept.sum() > 2 else None,
                               "d_sharpe": sharpe(ret[kept]) - sharpe(ret[cov]), "d_sharpe_by_year": by_year}
    return out


def stop_summary(base_ret, cell_ret, dates, years) -> dict:
    """A stop cell against the strategy as it is, paired by trade."""
    import forward_stats as fs
    d = np.asarray(cell_ret, float) - np.asarray(base_ret, float)
    years = np.asarray(years).astype(str)
    cs = fs.cluster_stats(d, pd.Series(dates).astype(str).to_numpy()) if len(d) > 2 else {"t": float("nan")}
    by_year = {y: float(d[years == y].mean()) for y in sorted(set(years))}
    return {"n": int(len(d)), "mean": float(np.mean(cell_ret)) if len(d) else None, "d_mean": float(d.mean()) if len(d) else None,
            "t": cs.get("t"), "dates": cs.get("clusters"), "d_by_year": by_year,
            "sharpe": sharpe(cell_ret), "d_sharpe": sharpe(cell_ret) - sharpe(base_ret)}


def earn_verdict(rows: list, primary: str = f"skip{PRIMARY_N}", pred: str = f"pred{PRIMARY_N}") -> dict:
    """The pre-registered PASS rule over the per-strategy earnings summaries."""
    use = [r for r in rows if r["rules"].get(primary, {}).get("removed", 0) >= MIN_REMOVED]
    if not use:
        return {"strategies": 0, "call": "NO DATA", "a": False, "b": False, "c": False, "d": False}
    ds = [r["rules"][primary]["d_sharpe"] for r in use]
    a = sum(1 for x in ds if x == x and x > 0) * 2 > len(use)
    rm = [r["rules"][primary]["removed_mean"] for r in use]
    km = [r["rules"][primary]["kept_mean"] for r in use]
    b = float(np.mean(rm)) <= float(np.mean(km))
    years = sorted({y for r in use for y in r["rules"][primary]["d_sharpe_by_year"]})
    yv = {y: np.nanmean([r["rules"][primary]["d_sharpe_by_year"].get(y, np.nan) for r in use]) for y in years}
    c = sum(1 for v in yv.values() if v == v and v > 0) * 2 > len(yv) if yv else False
    pu = [r for r in use if pred in r["rules"]]
    pd_ = [r["rules"][pred]["d_sharpe"] for r in pu]
    d = bool(pu) and sum(1 for x in pd_ if x == x and x > 0) * 2 > len(pu)
    return {"strategies": len(use), "a": a, "b": b, "c": c, "d": d,
            "mean_d_sharpe": float(np.nanmean(ds)), "removed_mean": float(np.mean(rm)), "kept_mean": float(np.mean(km)),
            "year_d_sharpe": {y: float(v) for y, v in yv.items()},
            "call": "PASS: worth a paper rule for non-earnings strategies" if (a and b and c and d) else "FAIL"}


def stop_verdict(s: dict) -> bool:
    by = [v for v in s["d_by_year"].values() if v == v]
    return (s["d_mean"] or 0) > 0 and (s["t"] or 0) >= T_NEED and sum(1 for v in by if v > 0) * 2 > len(by)


# --- the run --------------------------------------------------------------------------------

def spec(strategies: dict, window, which: str) -> dict:
    common = {
        "universe": "config universe.tradeable_types with risk.min_price and risk.min_dollar_volume floors, plus the "
                    "synthetic dead companies (as_is) — the ranking's basis",
        "entry_rule": {k: v["genome"] for k, v in strategies.items()},
        "holding_period": "each strategy's own max_hold_days",
        "cost_assumptions": "costs.CostModel(config); next-open fills; exits priced off unfiltered closes",
        "evaluation_period": list(window),
        "data_version": "market_data.db at run time; current synthetic build (survivorship_backtest.generator)",
        "stopping_rule": "each strategy computed once; one evaluation when all are done",
        "sample_size": f"all signals, at most {CAP:,} entries per strategy (uniform sample)",
        "holdout_policy": "factory backtest window only; the 2023-today unseen window and the sealed holdout untouched",
    }
    if which == "earn":
        return {**common, "primary_metric": "change in per-trade Sharpe (mean/sd of net return) on covered ticker-years "
                                            f"when entries within {PRIMARY_N} sessions of an 8-K 2.02 report are skipped",
                "exit_rule": {"skip_n": list(SKIP_N), "primary_n": PRIMARY_N, "covered_min_reports": COVER_MIN,
                              "predicted_days": PRED_DAYS, "min_removed": MIN_REMOVED,
                              "fixed": "each strategy's own exits; strategies reading SUE columns excluded"},
                "pass_rule": "a: Sharpe up in a majority of strategies; b: removed trades' mean <= kept; c: pooled change "
                             "> 0 in a majority of years; d: the predicted-date version satisfies a"}
    return {**common, "primary_metric": "change in net return per trade against the strategy as it is, paired by trade",
            "exit_rule": {"stop_atr_multiple": list(STOPS), "fixed": "each strategy's own entry, hold, exit, take-profit"},
            "adoption_rule": f"d_mean > 0 with date-clustered t >= {T_NEED} AND > 0 in a majority of years"}


def register(conn, cfg) -> dict:
    """Both experiments with the same frozen strategies; afterwards read them back."""
    import experiment_registry as er
    import survivorship_backtest as sb
    window = sb.window_of(cfg)
    try:
        return json.loads(er.get(conn, EXP_STOP)["spec"])["entry_rule"]
    except er.RegistryError:
        pass
    strategies = candidates(conn, cfg)
    if not strategies:
        raise SystemExit("no strategy with an entry rule to test")
    er.create(conn, EXP_EARN, "Skipping entries within 5 sessions of an earnings report raises non-earnings strategies' "
              "per-trade Sharpe without dropping their better trades, in most strategies and most years, with actual and "
              "predicted report dates. Fails if any of the four conditions fails.", "Claude (owner 'keep building', "
              "2026-10-20)", spec(strategies, window, "earn"))
    er.register(conn, EXP_EARN)
    er.create(conn, EXP_STOP, "A different ATR stop multiple raises a slot candidate's net return per trade, by more than "
              "noise across five cells and in most years. Fails for a strategy if no cell does.", "Claude (owner 'keep "
              "building', 2026-10-20)", spec(strategies, window, "stop"))
    er.register(conn, EXP_STOP)
    return {k: v["genome"] for k, v in strategies.items()}


def _done(sink: Path = SINK) -> set:
    if not sink.exists():
        return set()
    return {json.loads(x)["strategy"] for x in sink.read_text().splitlines() if x.strip()}


def run(conn, cfg, strategies: dict, sink: Path = SINK) -> int:
    import costs as costs_mod
    import earnings_study
    import experiment_registry as er
    import simulator
    import storage
    import survivorship_backtest as sb
    for e in (EXP_EARN, EXP_STOP):
        if er.get(conn, e)["status"] == er.REGISTERED:
            er.start(conn, e)
    window = sb.window_of(cfg)
    done = _done(sink)
    todo = {k: g for k, g in strategies.items() if k not in done}
    if not todo:
        return 0
    size = float(cfg["risk"]["position_size_usd"])
    cm = costs_mod.CostModel(cfg)
    sessions = np.array([str(r[0])[:10] for r in conn.execute("SELECT date FROM prices WHERE ticker='SPY' ORDER BY date")])
    ev = earnings_study.events(conn, str(int(window[0][:4]) - 1) + "-01-01", str(int(window[1][:4]) + 1) + "-12-31")
    rep = report_sessions(ev, sessions)
    cov = covered(ev)
    wrote = 0
    for fund in (False, True):                           # one real panel at a time keeps memory bounded
        group = {k: g for k, g in todo.items() if storage.needs_panel(g) == fund}
        if not group:
            continue
        need = storage.columns_read(list(group.values()))
        real, real_ex = sb._real(conn, cfg, window, fund, need if fund else None, sb.SIM_COLS | need)
        srows, sex = sb.synthetic_frames(conn, cfg, window, "as_is", fundamentals=fund)
        df, ex = sb._combine(real, sb._trim(srows, sb.SIM_COLS | need)), sb._combine(real_ex, sex)
        del real, real_ex, srows, sex
        gc.collect()
        panel = simulator.Panel(df, exit_prices=ex)
        del df, ex
        gc.collect()
        tick_all = panel.df["ticker"].astype(str).to_numpy()
        for name, g in group.items():
            base = simulator.simulate(g, panel, cm, size, max_entries=CAP)
            n = int(base["n_trades"])
            row = {"strategy": name, "trades": n, "signals": int(base.get("n_signals") or 0),
                   "stop": float(g["risk"].get("stop_atr_multiple", 2.0)), "about_earnings": about_earnings(g)}
            if n:
                idx = np.asarray(base["entry_rows"], dtype=int)
                ret = np.asarray(base["pnl_series"], float) / size
                dts = np.asarray(pd.to_datetime(panel.dates[idx]).strftime("%Y-%m-%d"), dtype=str)
                yrs = np.array([d[:4] for d in dts])
                tk = tick_all[idx]
                row.update({"base_mean": float(ret.mean()), "base_sharpe": sharpe(ret)})
                if not row["about_earnings"]:
                    sig = np.searchsorted(sessions, dts)
                    sig = np.where((sig < len(sessions)) & (sessions[np.minimum(sig, len(sessions) - 1)] == dts), sig, -1)
                    cv = np.array([(t, y) in cov for t, y in zip(tk, yrs)])
                    masks = {f"skip{k}": skip_mask(tk, sig, rep, k) for k in SKIP_N}
                    masks[f"pred{PRIMARY_N}"] = predicted_mask(tk, sig, rep, sessions, PRIMARY_N)
                    row["earn"] = earn_summary(ret, yrs, cv, masks)
                row["stops"] = {}
                for m in STOPS:
                    r = simulator.simulate(with_stop(g, m), panel, cm, size, max_entries=CAP)
                    if not np.array_equal(np.asarray(r["entry_rows"], dtype=int), idx):
                        log.warning(f"{name} stop {m}: entries differ from the baseline; cell skipped")
                        continue
                    row["stops"][str(m)] = stop_summary(ret, np.asarray(r["pnl_series"], float) / size, dts, yrs)
            with sink.open("a") as fh:
                fh.write(json.dumps(row, default=float) + "\n")
            wrote += 1
            log.info(f"{name}: {n:,} trades; base {row.get('base_mean', 0):+.3%}/trade")
        del panel, tick_all
        gc.collect()
    return wrote


def rows(sink: Path = SINK) -> list:
    return [json.loads(x) for x in sink.read_text().splitlines() if x.strip()] if sink.exists() else []


def render(rs: list, n_strategies: int) -> str:
    L = [f"# Earnings skip and stop widths — {date.today().isoformat()} (Stage AD3.5 / AD3.6)", "",
         f"{len(rs)} of {n_strategies} strategies computed. Backtest window, real plus synthetic dead companies (as_is), "
         "next-open fills, net of costs. Research only: nothing live changes from this.", ""]
    er_ = [r["earn"] for r in rs if r.get("earn")]
    v = earn_verdict(er_)
    L += [f"## {EXP_EARN}: skip entries within {PRIMARY_N} sessions of a report — **{v['call']}**", "",
          f"Strategies with >= {MIN_REMOVED} removed trades: {v['strategies']}. Conditions: "
          f"a {'yes' if v['a'] else 'no'} · b {'yes' if v['b'] else 'no'} · c {'yes' if v['c'] else 'no'} · "
          f"d {'yes' if v['d'] else 'no'}.", ""]
    if v["strategies"]:
        L += [f"Mean Sharpe change {v['mean_d_sharpe']:+.4f}; removed trades {v['removed_mean']:+.3%} vs kept "
              f"{v['kept_mean']:+.3%} per trade; by year: " + ", ".join(f"{y} {x:+.4f}" for y, x in v["year_d_sharpe"].items()), ""]
    L += ["| strategy | covered | " + " | ".join(f"{k} removed / dSharpe" for k in [f"skip{n}" for n in SKIP_N] + [f"pred{PRIMARY_N}"])
          + " |", "|---|---:|" + "---:|" * (len(SKIP_N) + 1)]
    for r in rs:
        e = r.get("earn")
        if not e:
            continue
        cells = [f"{e['rules'][k]['removed']} / {e['rules'][k]['d_sharpe']:+.4f}" for k in
                 [f"skip{n}" for n in SKIP_N] + [f"pred{PRIMARY_N}"]]
        L.append(f"| {r['strategy']} | {e['covered']} | " + " | ".join(cells) + " |")
    L += ["", f"## {EXP_STOP}: ATR stop multiple", "",
          f"Cell = change in net return per trade against the strategy as it is (paired, date-clustered t); adoptable "
          f"needs t >= {T_NEED} and a gain in most years.", "",
          "| strategy | own stop | base/trade | " + " | ".join(f"{m}x" for m in STOPS) + " | adoptable |",
          "|---|---:|---:|" + "---:|" * len(STOPS) + "---|"]
    adopt = []
    for r in rs:
        if not r.get("stops"):
            continue
        cells, ok = [], []
        for m in STOPS:
            s = r["stops"].get(str(m))
            cells.append(f"{s['d_mean']:+.3%} (t {s['t']:+.1f})" if s and s.get("t") == s.get("t") else "—")
            if s and stop_verdict(s):
                ok.append(f"{m}x")
        if ok:
            adopt.append(f"{r['strategy']}: {', '.join(ok)}")
        L.append(f"| {r['strategy']} | {r['stop']:g} | {r.get('base_mean', 0):+.3%} | " + " | ".join(cells)
                 + f" | {', '.join(ok) or 'none'} |")
    L += ["", "Adoptable: " + ("; ".join(adopt) if adopt else "none"), "",
          "Caveats: one window (2016-2019) with synthetic dead companies; report dates exist for a minority of tickers, so "
          "the earnings test covers those ticker-years only; a stop change is a different strategy and would need its own "
          "paper record before any live use."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for f in ("register", "run", "report", "write"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    runtime.be_nice()
    import sqlite3
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    strategies = register(conn, cfg)
    if a.register:
        print(f"{len(strategies)} strategies frozen:")
        for k in strategies:
            print("  " + k)
    if a.run:
        print(f"computed {run(conn, cfg, strategies)} strategies")
    if a.report or a.write or not (a.register or a.run):
        rs = [r for r in rows() if r["strategy"] in strategies]
        text = render(rs, len(strategies))
        print(text)
        if a.write:
            (ROOT / "reports" / f"risk_sweep_{date.today().isoformat()}.md").write_text(text)
        if len(rs) == len(strategies):
            import experiment_registry as er
            v = earn_verdict([r["earn"] for r in rs if r.get("earn")])
            adopt = [f"{r['strategy']}: {m}x" for r in rs for m in STOPS
                     if (r.get("stops") or {}).get(str(m)) and stop_verdict(r["stops"][str(m)])]
            for e, res, concl in ((EXP_EARN, v, v["call"]),
                                  (EXP_STOP, {"adoptable": adopt}, "adoptable: " + (", ".join(adopt) or "none"))):
                if er.get(conn, e)["status"] == er.RUNNING:
                    er.complete(conn, e, res, concl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
