"""
The factory pipeline. Phase 13 steps H11-H13; Addendum B §B3, B17, B22.

    queue (discovery.py)
      -> SPECIFIED     the genome evaluates and carries a stop plan (§15, B13)
      -> BACKTESTED    enough trades on the backtest window
      -> VALIDATED     positive net on the backtest AND validation windows
      -> PROMISING     robustness.py does not call it FRAGILE
      -> PAPER         enrolled as a paper fund, stepped daily like every other
      -> QUALIFIED     its league says ELIGIBLE / ESTABLISHED on forward evidence
      -> LIVE_CANDIDATE  within the family concentration limit; the slot engine
                         (Addendum A) decides what actually trades

Backtests admit to paper; only forward evidence qualifies (B3). Benchmarks
and the null are informational, never gates (B20). Every step writes a §37
decision; every failure writes a failure record for discovery (B17). The
sealed holdout is never touched: windows come from `factory` in config.

Memory: one panel per (window, needs-fundamentals) per run, shared by every
strategy in the batch. Run it through run_bounded.sh.

    python factory_pipeline.py --run          one pass: test a budget, evaluate forward
    python factory_pipeline.py --evaluate     forward evaluation only
    python factory_pipeline.py --candidates   current live candidates
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import json
import logging
import sqlite3

import benchmark as bench
import costs as costs_mod
import discovery
import genome as gn
import league
import leagues
import paper_trading
import research_queue as rq
import reward
import robustness
import simulator
import storage
import strategy_factory as sf
import strategy_objects as so
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("factory_pipeline")
EXIT_MARGIN_DAYS = 120

_PANELS = {}


def panel(conn, cfg, window, fundamentals: bool):
    key = (tuple(window), fundamentals)
    if key in _PANELS:
        return _PANELS[key]
    _PANELS.clear()                       # one panel at a time keeps memory bounded
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True, include_open=True)
    if df.empty:
        _PANELS[key] = None
        return None
    if fundamentals:
        df = storage.attach_fundamentals(conn, df)
    end = (dt.date.fromisoformat(window[1]) + dt.timedelta(days=EXIT_MARGIN_DAYS)).isoformat()
    ex = storage.load_exit_prices(conn, df["ticker"].astype(str).unique(), window[0], end)
    _PANELS[key] = simulator.Panel(df, exit_prices=ex)
    return _PANELS[key]


def _needs_fund(m: dict) -> bool:
    return "daily_fundamentals" in (m.get("data_requirements") or [])


def _metrics(r: dict) -> dict:
    return {"gross_usd": float(r.get("gross_pnl_usd") or 0), "costs_usd": float(r.get("costs_usd") or 0),
            "net_usd": float(r.get("net_pnl_usd") or 0), "trades": int(r.get("n_trades") or 0),
            "win_rate": float(r.get("win_rate") or 0)}


def _null_excess(conn, cfg, window, r: dict, g: dict, size: float):
    """
    Excess over random entry at the same prices and holds. INFORMATIONAL (B20):
    reported beside every backtest so a bull market's drift is visible next to
    the strategy's P&L, never used as a gate.
    """
    try:
        surface = bench.null_surface(conn, cfg, tuple(window))
        f = reward.fitness(r, complexity=gn.complexity(g), position_size_usd=size,
                           benchmark_surface=surface, cfg=reward.params_from_config(cfg))
        return float(f.get("excess_pnl_usd")) if f.get("excess_pnl_usd") is not None else None
    except Exception as e:                                        # noqa: BLE001
        log.warning(f"null excess unavailable for {window}: {type(e).__name__}")
        return None


def _reject(conn, key, ver, stage, reason, window=None, regimes=None, evidence=None,
            decision="REJECT"):
    so.decide(conn, key, ver, decision, reason, to_state=league.REJECTED,
              classification="UNPROFITABLE" if stage in ("backtest", "validation") else None,
              evidence=evidence)
    discovery.record_failure(conn, key, ver, stage, reason, window=window, regimes=regimes,
                             suggests={"sample": "a looser threshold or a longer window",
                                       "validation": "the edge may be regime-specific; see regimes",
                                       "robustness": "a variant with a wider stop or longer hold",
                                       "backtest": "a trend or quality filter"}.get(stage))


def process(conn, cfg, key: str, ver: int) -> str:
    """Take one DISCOVERED strategy as far as the evidence allows. Returns its end state."""
    fcfg = cfg.get("factory") or {}
    m = so.meta(conn, key, ver)
    fam = sf.F.get(m.get("family"), {})
    if fam and not fam.get("data_available", True):
        so.decide(conn, key, ver, "DATA_PROBLEM", fam.get("missing") or "data unavailable")
        return league.DISCOVERED
    g = so.genome(conn, key, ver)
    stop = (g.get("risk") or {}).get("stop_atr_multiple")
    if not stop or float(stop) <= 0:
        _reject(conn, key, ver, "spec", "no stop plan: every live strategy needs one (§15, B13)")
        return league.REJECTED
    so.decide(conn, key, ver, "PROMOTE", "rules specified with a stop plan", to_state=league.SPECIFIED)

    size = float(cfg["risk"]["position_size_usd"])
    cm = costs_mod.CostModel(cfg)
    cap = int(fcfg.get("max_entries_per_backtest", 5000))
    bw, vw = tuple(fcfg["backtest_window"]), tuple(fcfg["validation_window"])
    need = _needs_fund(m)

    p = panel(conn, cfg, bw, need)
    if p is None:
        so.decide(conn, key, ver, "DATA_PROBLEM", f"empty panel for {bw}")
        return league.SPECIFIED
    try:
        r = simulator.simulate(g, p, cm, size, max_entries=cap)
    except Exception as e:                                    # noqa: BLE001
        _reject(conn, key, ver, "spec", f"genome failed to evaluate: {type(e).__name__}: {e}")
        return league.REJECTED
    bt = _metrics(r)
    # Survivorship: the primary database lacks ~7,000 delisted companies, so a
    # backtest here is SURVIVORSHIP_LIMITED until dataset_compare cross-validates
    # it on a delisted-inclusive dataset (§11).
    so.record_metrics(conn, key, ver, "backtest", window=json.dumps(bw), **bt,
                      excess_vs_null_usd=_null_excess(conn, cfg, bw, r, g, size),
                      survivorship_status="SURVIVORSHIP_LIMITED",
                      detail={"n_signals": r.get("n_signals"), "gap_loss_usd": r.get("gap_loss_usd"),
                              "entries_capped": r.get("entries_capped")})
    if bt["trades"] < int(fcfg.get("min_backtest_trades", 30)):
        _reject(conn, key, ver, "sample", f"{bt['trades']} trades on {bw} (< min)", window=bw,
                decision="INSUFFICIENT_SAMPLE")
        return league.REJECTED
    so.decide(conn, key, ver, "PROMOTE", f"backtested: {bt['trades']} trades, net ${bt['net_usd']:+.2f}",
              to_state=league.BACKTESTED, evidence=bt)
    if bt["net_usd"] <= 0:
        _reject(conn, key, ver, "backtest", f"net ${bt['net_usd']:+.2f} on {bw}", window=bw, evidence=bt)
        return league.REJECTED

    # Robustness on the backtest panel, while it is loaded.
    rob = robustness.analyse(conn, g, p, cm, size, cap, r, cfg, window=bw)
    so.record_metrics(conn, key, ver, "robustness", window=json.dumps(bw),
                      detail={"verdict": rob["verdict"], "failures": rob["failures"],
                              "regimes": rob["tests"].get("regimes")})

    pv = panel(conn, cfg, vw, need)
    rv = simulator.simulate(g, pv, cm, size, max_entries=cap) if pv is not None else {}
    va = _metrics(rv)
    so.record_metrics(conn, key, ver, "validation", window=json.dumps(vw), **va,
                      excess_vs_null_usd=_null_excess(conn, cfg, vw, rv, g, size) if rv else None,
                      survivorship_status="SURVIVORSHIP_LIMITED")
    if va["net_usd"] <= 0 or va["trades"] == 0:
        _reject(conn, key, ver, "validation", f"validation net ${va['net_usd']:+.2f} over {va['trades']} trades",
                window=vw, regimes=rob["tests"].get("regimes"), evidence={"backtest": bt, "validation": va})
        return league.REJECTED
    so.decide(conn, key, ver, "PROMOTE", f"validated out of sample: net ${va['net_usd']:+.2f}",
              to_state=league.VALIDATED, classification="PROFITABLE", evidence=va)

    if rob["verdict"] != "ROBUST":
        _reject(conn, key, ver, "robustness", f"FRAGILE: {', '.join(rob['failures'])}",
                window=bw, regimes=rob["tests"].get("regimes"), evidence=rob)
        return league.REJECTED
    so.decide(conn, key, ver, "PROMOTE", "robust under the §28 perturbations",
              to_state=league.PROMISING, classification="PROMISING", evidence={"failures": rob["failures"]})
    enroll(conn, cfg, key, ver, m, g)
    return league.PAPER


def enroll(conn, cfg, key: str, ver: int, m: dict, g: dict) -> str:
    """§26 automatic paper enrolment through the existing paper engine."""
    leagues.init(conn)
    have = conn.execute("SELECT run_id FROM factory_paper_link WHERE strategy_key=? AND version=?",
                        (key, ver)).fetchone()
    if have:
        return have[0]
    paper_trading.init(conn)
    run_id = paper_trading.start(conn, cfg, name=f"{key} v{ver}", strategy=json.dumps(g, sort_keys=True))
    conn.execute("UPDATE paper_runs SET label=?, family=? WHERE run_id=?",
                 (m.get("family", key)[:40] + f" v{ver}", m.get("family"), run_id))
    conn.execute("INSERT INTO factory_paper_link VALUES (?,?,?,?)",
                 (key, ver, run_id, dt.date.today().isoformat()))
    conn.commit()
    so.decide(conn, key, ver, "PROMOTE", f"enrolled in paper trading as run {run_id}",
              to_state=league.PAPER)
    return run_id


def evaluate_forward(conn, cfg) -> dict:
    """H12: forward evidence moves strategies between PAPER, QUALIFIED and LIVE_CANDIDATE."""
    st = leagues.standings(conn, cfg, record=True)
    moved = {"qualified": 0, "demoted": 0, "candidates": 0, "unchanged": 0}
    for rows in st.values():
        for r in rows:
            key, ver, cur = r["strategy_key"], r["version"], league.canonical(r["state"])
            tier = r["tier"]
            good = tier in ("ELIGIBLE", "ESTABLISHED")
            if cur == league.PAPER and good:
                so.decide(conn, key, ver, "PROMOTE", f"forward evidence: {tier} in {r['league']}",
                          to_state=league.QUALIFIED, classification="QUALIFIED",
                          evidence={k: r.get(k) for k in ("net_usd", "sessions", "closed_trades",
                                                          "max_drawdown_pct")})
                moved["qualified"] += 1
            elif cur in (league.QUALIFIED, league.LIVE_CANDIDATE) and tier == "NOT_ELIGIBLE":
                so.decide(conn, key, ver, "DEMOTE", f"forward evidence fell to NOT_ELIGIBLE in {r['league']}",
                          to_state=league.DEMOTED, evidence={"net_usd": r.get("net_usd")})
                moved["demoted"] += 1
            else:
                moved["unchanged"] += 1
    moved["candidates"] = len(promote_candidates(conn, cfg))
    return moved


def promote_candidates(conn, cfg) -> list:
    """QUALIFIED -> LIVE_CANDIDATE, one per concentration family (§18, B7)."""
    st = leagues.standings(conn, cfg)
    pool = [r for rows in st.values() for r in rows
            if league.canonical(r["state"]) in (league.QUALIFIED, league.LIVE_CANDIDATE)
            and r["tier"] in ("ELIGIBLE", "ESTABLISHED")]
    pool.sort(key=lambda r: -(r.get("net_usd") or 0))
    seen, out = set(), []
    for r in pool:
        if r["family"] in seen:
            continue
        seen.add(r["family"])
        if league.canonical(r["state"]) == league.QUALIFIED:
            so.decide(conn, r["strategy_key"], r["version"], "PROMOTE",
                      f"best QUALIFIED strategy in family {r['family']}", to_state=league.LIVE_CANDIDATE)
        out.append(r)
    return out


def live_candidates(conn, cfg) -> list:
    """What the slot engine may choose from: LIVE_CANDIDATE and LIVE strategies with their evidence."""
    st = leagues.standings(conn, cfg)
    return [r for rows in st.values() for r in rows
            if league.canonical(r["state"]) in (league.LIVE_CANDIDATE, league.LIVE)]


def run(conn, cfg, budget: int | None = None) -> dict:
    so.init(conn)
    discovery.init(conn)
    summary = {"plan": discovery.plan(conn, cfg), "processed": {}, "recycled": []}
    for item in discovery.take(conn, cfg, budget):
        key, ver = item["strategy_key"], item["version"]
        try:
            end = process(conn, cfg, key, ver)
        except Exception as e:                                   # noqa: BLE001
            log.exception(f"{key} v{ver} failed in the pipeline")
            so.decide(conn, key, ver, "RESEARCH_MORE", f"pipeline error: {type(e).__name__}: {e}")
            end = "ERROR"
        rq.set_status(conn, item["id"], "done", end)
        summary["processed"][f"{key} v{ver}"] = end
        log.info(f"{key} v{ver} -> {end}")
    _PANELS.clear()
    summary["recycled"] = discovery.recycle(conn, cfg)
    summary["forward"] = evaluate_forward(conn, cfg)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--budget", type=int)
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--candidates", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    if a.run:
        s = run(conn, cfg, a.budget)
        ends = {}
        for v in s["processed"].values():
            ends[v] = ends.get(v, 0) + 1
        print(f"  processed {len(s['processed'])}: {ends}")
        print(f"  recycled {len(s['recycled'])}; forward {s['forward']}")
    if a.evaluate:
        print(f"  forward {evaluate_forward(conn, cfg)}")
    if a.candidates or not (a.run or a.evaluate):
        c = live_candidates(conn, cfg)
        print(f"  {len(c)} live candidate(s)")
        for r in c:
            print(f"    {r['name']:<30} {r['league']:<14} net {r.get('net_usd') or 0:+.2f}  {r['tier']}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
