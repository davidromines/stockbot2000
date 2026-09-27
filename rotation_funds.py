"""
ETF rotation as strategies in the tournament (owner, 2026-09-27: sector / ETF rotation).

A DECLARED grid, fixed here before any result: universe {sectors, assets} x lookback
{63, 126, 252 sessions} x top_k {1, 3}, always with the absolute-momentum filter (step
into SHY when momentum is not positive) — 12 variants. Each is a strategy object like
every other and goes through the same gates, measured by rotation.backtest (next-open
fills, 5 bp a side):

    backtest   2006-2019    net per trade > 0, else REJECTED
    validation 2020-2022    net per trade > 0, else REJECTED
    unseen     2023 -> today  one look, stored in holdout_results (the ranking gates on it)

Survivors are enrolled in paper trading (a paper fund whose strategy is the rotation
rule — paper_trading._rotation_step) and ranked by ranking.py from these results; a slot
holding one trades the fund's top ETF (slot_trader._rotation_signals). The factory
pipeline's §28 perturbation suite does not apply to a monthly ETF rule; the lookback
grid is its parameter check, and every variant's result is kept.

    ./venv/bin/python rotation_funds.py --run
    ./venv/bin/python rotation_funds.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import itertools
import json
import logging
import sqlite3
import sys

import league
import strategy_objects as so

log = logging.getLogger("rotation_funds")
ACTOR = "rotation_funds"
GRID = {"universe": ["sectors", "assets"], "lookback": [63, 126, 252], "top_k": [1, 3]}
WINDOWS = {"backtest": ("2006-01-01", "2019-12-31"), "validation": ("2020-01-01", "2022-12-31")}
UNSEEN = "2023-01-01"
SIZE = 20.0


def variants() -> list:
    return [{"universe": u, "lookback": lb, "top_k": k, "abs_filter": True}
            for u, lb, k in itertools.product(GRID["universe"], GRID["lookback"], GRID["top_k"])]


def genome(p: dict) -> dict:
    # A 3 x ATR price stop for the live plan (a plan needs one); no time exit that would
    # close a position the fund still holds — max hold far beyond a month's rebalance.
    return {"rotation": p, "risk": {"stop_atr_multiple": 3.0, "max_hold_days": 252}}


def name(p: dict) -> str:
    return (f"ETF Rotation {p['universe']} {p['lookback']}d top{p['top_k']}"
            + (" +cash" if p["abs_filter"] else ""))


def _metrics(bt: dict) -> dict:
    n = bt["n_trades"]
    return {"trades": n, "net_usd": bt["mean_net"] * n * SIZE, "gross_usd": bt["mean_gross"] * n * SIZE,
            "costs_usd": (bt["mean_gross"] - bt["mean_net"]) * n * SIZE, "win_rate": bt["win_rate"],
            "return_pct": bt["cagr"] * 100, "max_drawdown_pct": bt["max_drawdown"] * 100}


def evaluate(conn, cfg, p: dict, close, open_, end: str) -> dict:
    """Register one variant and take it through backtest -> validation -> unseen -> paper."""
    import holdout
    import rotation
    key = so.key_for("etf_rotation", p)
    obj = {"strategy_key": key, "name": name(p), "family": f"etf_rotation_{p['universe']}",
           "league": "etf_macro", "genome": genome(p), "parameters": p, "source": "etf_rotation",
           "source_ref": "rotation_funds", "data_requirements": ["prices"],
           "hypothesis": "Relative + absolute momentum across ETFs (Faber 2007; Antonacci 2014)."}
    reg = so.register(conn, obj, author=ACTOR)
    ver = reg["version"]
    st = league.canonical(league.state(conn, key, ver))
    out = {"key": key, "name": name(p)}
    if st != league.DISCOVERED:
        out["state"] = st
        return out
    so.decide(conn, key, ver, "PROMOTE", "rotation rule specified with a 3 x ATR stop", to_state=league.SPECIFIED)
    res = {}
    for phase, (a, b) in WINDOWS.items():
        bt = rotation.backtest(close, open_, p, a, b)
        m = _metrics(bt)
        so.record_metrics(conn, key, ver, phase, window=json.dumps([a, b]), **m,
                          detail={"cagr": bt["cagr"], "benchmark_cagr": bt["benchmark_cagr"]})
        res[phase] = bt
        out[phase] = bt["mean_net"]
    so.decide(conn, key, ver, "PROMOTE", f"backtested: {res['backtest']['n_trades']} trades",
              to_state=league.BACKTESTED, evidence=_metrics(res["backtest"]))
    if res["backtest"]["mean_net"] <= 0:
        so.decide(conn, key, ver, "REJECT", f"backtest net {res['backtest']['mean_net']:+.3%}/trade",
                  to_state=league.REJECTED)
        out["state"] = "REJECTED"
        return out
    if res["validation"]["mean_net"] <= 0 or not res["validation"]["n_trades"]:
        so.decide(conn, key, ver, "REJECT", f"validation net {res['validation']['mean_net']:+.3%}/trade",
                  to_state=league.REJECTED)
        out["state"] = "REJECTED"
        return out
    so.decide(conn, key, ver, "PROMOTE", "validated out of sample", to_state=league.VALIDATED,
              classification="PROFITABLE", evidence=_metrics(res["validation"]))
    # One look at the unseen window, stored exactly as holdout.py stores it.
    holdout.init(conn)
    if not holdout.result(conn, key, ver):
        u = rotation.backtest(close, open_, p, UNSEEN, end)
        n = u["n_trades"]
        spy = close["SPY"].dropna()
        spy = spy[(spy.index >= UNSEEN) & (spy.index <= end)]
        conn.execute("INSERT INTO holdout_results (strategy_key, version, window_start, window_end, trades, gross_usd, "
                     "costs_usd, net_usd, per_trade, win_rate, excess_vs_null_usd, gap_loss_usd, evaluated_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (key, ver, UNSEEN, end, n, u["mean_gross"] * n * SIZE,
                      (u["mean_gross"] - u["mean_net"]) * n * SIZE, u["mean_net"] * n * SIZE,
                      u["mean_net"] if n else None, u["win_rate"], None, 0.0,
                      dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        out["unseen"] = u["mean_net"]
        out["unseen_cagr"], out["spy_cagr"] = u["cagr"], u["benchmark_cagr"]
    so.decide(conn, key, ver, "PROMOTE", "monthly ETF rule: the lookback grid is its parameter check",
              to_state=league.PROMISING, classification="PROMISING")
    import factory_pipeline as fp
    fp.enroll(conn, cfg, key, ver, so.meta(conn, key, ver) or {}, genome(p))
    out["state"] = "PAPER"
    return out


def run(conn, cfg) -> list:
    import rotation
    end = conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()[0]
    tickers = sorted(set(sum(rotation.UNIVERSES.values(), [])))
    close, open_ = rotation.load(conn, tickers, "2004-01-01", end)
    out = [evaluate(conn, cfg, p, close, open_, end) for p in variants()]
    conn.commit()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    if a.run:
        for r in run(conn, cfg):
            print(f"  {r['name']:<42} {r.get('state', ''):<10} "
                  + " ".join(f"{k} {r[k]:+.2%}" for k in ("backtest", "validation", "unseen") if r.get(k) is not None)
                  + (f"  (unseen CAGR {r['unseen_cagr']:+.1%} vs SPY {r['spy_cagr']:+.1%})" if "unseen_cagr" in r else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
