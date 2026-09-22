"""
Sweep stop width against entry rule. Tests the one live lead this project has.

THE OBSERVATION
---------------
Six paper funds share the entry rule `pct_change(sma_200, 3) > ~0.02` and differ
mainly in stop width. They split cleanly by that one parameter:

    stop 2.50 / 2.55 / 3.26   ->  +0.55%  +0.34%  +1.72%
    stop 4.98 / 4.98 / 4.98   ->  -0.78%  -3.95%  -8.30%

Tight stops positive, wide stops negative, identical entry. That is the most
specific thing eleven days of forward trading has produced, and waiting for
evolution to stumble onto it again is a poor use of a search that has already
run 328,105 evaluations without finding it.

WHY A SWEEP AND NOT A SEARCH
-----------------------------
Evolution optimises many parameters at once and reports a winner. It cannot tell
you *why* the winner won, and with this many trials the winner is usually noise.
A sweep holds the entry rule fixed and varies one axis, so the output is a shape
rather than a champion — and a shape either holds across entry rules and windows
or it does not. That is a claim which can be falsified, which a champion is not.

**The forward observation is 11 days on 6 funds.** It could easily be noise.
This sweep is what decides that, over 14 years and every entry rule given to it.

Usage:
    python stop_sweep.py --run
    python stop_sweep.py --run --window 2020-01-01 2022-12-31
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging

import numpy as np

import benchmark as bench
import costs as costs_mod
import genome as gn
import reward
import simulator
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sweep")

# Entry rules held fixed while the stop varies. The first is the one the paper
# funds actually run; the rest are there so any pattern has to hold beyond the
# single rule that suggested it.
ENTRIES = {
    "rising_200": {"op": "gt", "args": [
        {"op": "pct_change", "args": [{"col": "sma_200"}], "n": 3}, {"const": 0.0199}]},
    "rising_50": {"op": "gt", "args": [
        {"op": "pct_change", "args": [{"col": "sma_50"}], "n": 3}, {"const": 0.03}]},
    "macd_pullback": {"op": "and", "args": [
        {"op": "gt", "args": [{"op": "rank", "args": [{"col": "macd"}]}, {"const": 0.7}]},
        {"op": "lt", "args": [{"col": "rsi_14"}, {"const": 40.0}]}]},
    "rsi_oversold": {"op": "lt", "args": [{"col": "rsi_14"}, {"const": 30.0}]},
}

STOPS = (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0)
HOLDS = (10, 20, 40)


def sweep(conn, cfg, window, entries=None) -> list:
    size = float(cfg["risk"]["position_size_usd"])
    cm = costs_mod.CostModel(cfg)
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True, include_open=True)
    if df.empty:
        return []
    exitpx = storage.load_exit_prices(conn, df["ticker"].astype(str).unique(),
                                      window[0], "2099-12-31")
    panel = simulator.Panel(df, exit_prices=exitpx)
    surface = bench.null_surface(conn, cfg, window)
    rp = reward.params_from_config(cfg)
    log.info(f"panel {panel.n:,} rows, {window[0]} -> {window[1]}")

    out = []
    for ename, entry in (entries or ENTRIES).items():
        for hold in HOLDS:
            for stop in STOPS:
                g = {"entry": entry,
                     "exit": {"op": "lt", "args": [{"col": "close"}, {"const": 0.0}]},
                     "risk": {"max_hold_days": hold, "stop_atr_multiple": stop}}
                r = simulator.simulate(g, panel, cm, size, max_entries=20000)
                if not r["n_trades"]:
                    continue
                f = reward.fitness(r, complexity=3, position_size_usd=size,
                                   benchmark_surface=surface, cfg=rp)
                out.append({"entry": ename, "hold": hold, "stop": stop,
                            "trades": r["n_trades"], "net": r["net_pnl_usd"],
                            "excess": f["excess_pnl_usd"], "fitness": f["fitness"],
                            "win": r["win_rate"], "gap_loss": r.get("gap_loss_usd", 0.0),
                            "stopped": r.get("n_stopped", 0)})
    return out


def report(rows: list) -> None:
    by_entry = {}
    for r in rows:
        by_entry.setdefault(r["entry"], []).append(r)
    for ename, rs in by_entry.items():
        print(f"\n  {ename.upper()}   excess over the null, by stop width")
        print("  " + "-" * 62)
        holds = sorted({r["hold"] for r in rs})
        print(f"  {'stop':>6}" + "".join(f"{'hold ' + str(h):>16}" for h in holds))
        for stop in sorted({r["stop"] for r in rs}):
            line = f"  {stop:>6.1f}"
            for h in holds:
                m = [r for r in rs if r["stop"] == stop and r["hold"] == h]
                line += f"{m[0]['excess']:>15,.0f} " if m else f"{'-':>16}"
            print(line)
        best = max(rs, key=lambda r: r["excess"])
        print(f"    best: stop {best['stop']} hold {best['hold']}  "
              f"excess ${best['excess']:,.0f}  net ${best['net']:,.0f}  "
              f"{best['trades']:,} trades  win {best['win']*100:.1f}%")
        # The claim under test, stated so the data can refute it.
        tight = [r["excess"] for r in rs if r["stop"] <= 3.0]
        wide = [r["excess"] for r in rs if r["stop"] >= 5.0]
        if tight and wide:
            t, w = float(np.mean(tight)), float(np.mean(wide))
            verdict = "HOLDS" if t > w else "does NOT hold"
            print(f"    tight (<=3.0) mean ${t:,.0f} vs wide (>=5.0) mean ${w:,.0f}"
                  f"   -> tight-beats-wide {verdict}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--window", nargs=2, default=None)
    ap.add_argument("--out", default="data/stop_sweep.json")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); bench.init(conn)
    win = tuple(a.window) if a.window else (cfg["lab"]["search_start"],
                                            cfg["lab"]["search_end"])
    rows = sweep(conn, cfg, win)
    report(rows)
    from pathlib import Path
    Path(a.out).write_text(json.dumps({"window": win, "rows": rows}, indent=2))
    print(f"\n  written to {a.out}")
    conn.close()


if __name__ == "__main__":
    main()
