"""
Exit-rule sweep: do profit targets or trailing stops improve the strategies
that hold slots? Registered experiment `exit_rules` (owner, 2026-09-24:
"we have stop loss rules but do we have 'we made some money, let's sell it'
rules?").

THE QUESTION
------------
Each slot strategy exits on its ATR stop, its time limit or its own exit rule.
None locks in a gain. Two candidate profit exits, each already enforceable
live by stop_plans.py:

    take-profit     sell once price >= entry x (1 + p)       p in 5 / 10 / 20 %
    trailing stop   sell once price <= highest close since
                    entry - k x ATR at entry                 k in 2 / 3

The grid is every combination plus "none", run against each strategy AS IT
IS (`as_is`, its own genes untouched). Entry, stop and hold stay the
strategy's own, so the only thing that varies is the profit exit.

WHAT WOULD COUNT AS THE HYPOTHESIS FAILING
-----------------------------------------
A cell is ADOPTABLE for a strategy only if its net P&L per trade beats that
strategy's `as_is` over the whole window AND in a majority of the two-year
blocks. Anything else is noise from one era. Written before any result.

A profit exit does not create an edge: it trades occasional large wins for
more small ones. The stop-width sweep found tighter exits did WORSE on these
entries, so "no cell adoptable" is a live possibility and is a result.

The strategies are the slot holders at registration, frozen into the spec
(genome and all), so a later slot change cannot change what was tested.
Pair and value holders have no genome entry and are skipped.

Same blocks, resume file and memory discipline as stop_sweep.py.

Usage (VM):
    ./run_bounded.sh ./venv/bin/python exit_sweep.py --run
    ./venv/bin/python exit_sweep.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as _dt
import json
import logging
from pathlib import Path

import benchmark as bench
import costs as costs_mod
import reward
import simulator
import storage
from stop_sweep import EXIT_MARGIN_DAYS, _blocks
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("exit_sweep")

EXPERIMENT = "exit_rules"
TAKE_PROFITS = (None, 5.0, 10.0, 20.0)
TRAILS = (None, 2.0, 3.0)
AS_IS = "as_is"


def cells() -> list:
    """(label, overrides). `as_is` first; None removes a gene."""
    out = [(AS_IS, None)]
    for tp in TAKE_PROFITS:
        for tr in TRAILS:
            out.append((f"tp={tp or '-'} trail={tr or '-'}",
                        {"take_profit_pct": tp, "trailing_atr_multiple": tr}))
    return out


def apply(genome: dict, overrides: dict | None) -> dict:
    g = json.loads(json.dumps(genome))
    if overrides:
        risk = g.setdefault("risk", {})
        for k, v in overrides.items():
            if v is None:
                risk.pop(k, None)
            else:
                risk[k] = v
    return g


def slot_strategies(conn, cfg) -> dict:
    """name -> genome for every slot holder with an entry rule."""
    import slots
    out = {}
    for slot, h in sorted(slots.current(conn, cfg).items()):
        if not h:
            continue
        g = slots.genome_for(conn, h["strategy_key"], h["version"])
        if g and g.get("entry"):
            out[f"{h['strategy_key']}@v{h['version']}"] = g
    return out


def spec_for(strategies: dict, window) -> dict:
    return {
        "primary_metric": "net P&L per trade, $ (gross, costs, net and excess over the null reported beside it)",
        "universe": "config universe.tradeable_types with risk.min_price and risk.min_dollar_volume floors",
        "entry_rule": strategies,
        "exit_rule": {"cells": [c[0] for c in cells()],
                      "take_profit_pct": list(TAKE_PROFITS), "trailing_atr_multiple": list(TRAILS),
                      "fixed": "each strategy's own stop, hold and exit rule"},
        "holding_period": "each strategy's own max_hold_days",
        "cost_assumptions": "costs.CostModel(config); next-open fills; exits priced off unfiltered closes",
        "evaluation_period": list(window),
        "data_version": "market_data.db prices/features at run time",
        "stopping_rule": "every (block, strategy, cell) computed once",
        "sample_size": "all signals, capped at 20,000 entries per block (simulator max_entries)",
        "holdout_policy": "search window only; the sealed holdout is not touched",
        "adoption_rule": "beats as_is net per trade over the window AND in a majority of blocks",
    }


def ensure_registered(conn, cfg, window) -> dict:
    """Register on first run with the slot holders frozen in; afterwards read them back."""
    import experiment_registry as er
    try:
        e = er.get(conn, EXPERIMENT)
    except er.RegistryError:
        strategies = slot_strategies(conn, cfg)
        if not strategies:
            raise SystemExit("no slot holder with an entry rule to test")
        er.create(conn, EXPERIMENT,
                  "Adding a take-profit and/or trailing stop to a slot strategy raises its net P&L "
                  "per trade over the search window and in a majority of two-year blocks. Fails if "
                  "no cell beats the strategy as it is on both counts.",
                  "claude", spec_for(strategies, window))
        er.register(conn, EXPERIMENT)
        er.start(conn, EXPERIMENT)
        e = er.get(conn, EXPERIMENT)
    return json.loads(e["spec"])


def _done(path: Path) -> set:
    if not path.exists():
        return set()
    return {(r["block"], r["strategy"], r["cell"]) for r in
            (json.loads(line) for line in path.read_text().splitlines() if line.strip())}


def sweep(conn, cfg, window, strategies: dict, sink: Path, skip: set) -> None:
    size = float(cfg["risk"]["position_size_usd"])
    cm = costs_mod.CostModel(cfg)
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True, include_open=True)
    block = f"{window[0]}..{window[1]}"
    if df.empty:
        return
    exit_end = (_dt.date.fromisoformat(window[1]) + _dt.timedelta(days=EXIT_MARGIN_DAYS)).isoformat()
    exitpx = storage.load_exit_prices(conn, df["ticker"].astype(str).unique(), window[0], exit_end)
    panel = simulator.Panel(df, exit_prices=exitpx)
    surface = bench.null_surface(conn, cfg, window)
    rp = reward.params_from_config(cfg)
    for name, genome in strategies.items():
        for label, over in cells():
            if (block, name, label) in skip:
                continue
            g = apply(genome, over)
            r = simulator.simulate(g, panel, cm, size, max_entries=20000)
            row = {"block": block, "strategy": name, "cell": label, "trades": r["n_trades"]}
            if r["n_trades"]:
                f = reward.fitness(r, complexity=3, position_size_usd=size, benchmark_surface=surface, cfg=rp)
                row.update({"gross": r["gross_pnl_usd"], "costs": r["costs_usd"], "net": r["net_pnl_usd"],
                            "excess": f["excess_pnl_usd"], "win": r["win_rate"],
                            "hold": r["avg_hold_days"], "n_tp": r.get("n_take_profit", 0),
                            "n_trail": r.get("n_trailed", 0), "n_stop": r.get("n_stopped", 0)})
            with sink.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            log.info(f"{block} {name} {label}: {r['n_trades']:,} trades net ${r['net_pnl_usd']:,.0f}")


def combine(rows: list) -> dict:
    """(strategy, cell) -> totals over blocks, plus per-block net per trade."""
    agg = {}
    for r in rows:
        if not r.get("trades"):
            continue
        a = agg.setdefault((r["strategy"], r["cell"]), {
            "strategy": r["strategy"], "cell": r["cell"], "trades": 0, "gross": 0.0, "costs": 0.0,
            "net": 0.0, "excess": 0.0, "wins": 0.0, "n_tp": 0, "n_trail": 0, "n_stop": 0, "blocks": {}})
        for k in ("trades", "gross", "costs", "net", "excess", "n_tp", "n_trail", "n_stop"):
            a[k] += r[k]
        a["wins"] += r["win"] * r["trades"]
        a["blocks"][r["block"]] = r["net"] / r["trades"]
    for a in agg.values():
        a["win"] = a.pop("wins") / a["trades"]
        a["net_per_trade"] = a["net"] / a["trades"]
    return agg


def verdicts(agg: dict) -> dict:
    """The pre-registered adoption rule, per strategy and cell."""
    out = {}
    for (s, c), a in agg.items():
        base = agg.get((s, AS_IS))
        if c == AS_IS or not base:
            continue
        common = set(a["blocks"]) & set(base["blocks"])
        wins = sum(1 for b in common if a["blocks"][b] > base["blocks"][b])
        out[(s, c)] = {"beats_window": a["net_per_trade"] > base["net_per_trade"],
                       "blocks_won": wins, "blocks": len(common),
                       "adoptable": a["net_per_trade"] > base["net_per_trade"] and wins * 2 > len(common)}
    return out


def render(agg: dict, v: dict) -> str:
    L = []
    for s in sorted({k[0] for k in agg}):
        L += ["", f"  {s}   gross / costs / NET per trade ($), excess over the null ($)",
              f"  {'cell':<22}{'trades':>8}{'gross':>9}{'costs':>9}{'net':>9}{'excess':>10}"
              f"{'win':>7}{'tp':>6}{'trail':>6}  verdict"]
        rows = sorted((a for k, a in agg.items() if k[0] == s), key=lambda a: (a["cell"] != AS_IS, -a["net_per_trade"]))
        for a in rows:
            n = a["trades"]
            vv = v.get((s, a["cell"]))
            verdict = "baseline" if a["cell"] == AS_IS else (
                f"ADOPTABLE ({vv['blocks_won']}/{vv['blocks']} blocks)" if vv and vv["adoptable"]
                else f"no ({vv['blocks_won']}/{vv['blocks']} blocks)" if vv else "no baseline")
            L.append(f"  {a['cell']:<22}{n:>8,}{a['gross'] / n:>9.3f}{-a['costs'] / n:>9.3f}"
                     f"{a['net_per_trade']:>9.3f}{a['excess']:>10,.0f}{a['win'] * 100:>6.1f}%"
                     f"{a['n_tp']:>6}{a['n_trail']:>6}  {verdict}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Exit-rule sweep (experiment exit_rules).")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--block-years", type=int, default=2)
    ap.add_argument("--out", default="data/exit_sweep.json")
    a = ap.parse_args(argv)
    cfg = load_config()
    runtime.be_nice()
    window = (cfg["lab"]["search_start"], cfg["lab"]["search_end"])
    out = Path(a.out)
    sink = out.with_suffix(".jsonl")
    blocks = _blocks(window, a.block_years)
    conn = storage.connect(cfg["database"]["market_data_path"])
    spec = ensure_registered(conn, cfg, window)
    strategies = spec["entry_rule"]
    if a.run:
        storage.init_db(conn)
        bench.init(conn)
        for b in blocks:
            done = _done(sink)
            left = [(s, c) for s in strategies for c, _ in cells() if (f"{b[0]}..{b[1]}", s, c) not in done]
            if not left:
                log.info(f"block {b[0]}..{b[1]} already complete")
                continue
            sweep(conn, cfg, b, strategies, sink, done)
            import gc
            gc.collect()
    rows = [json.loads(line) for line in sink.read_text().splitlines() if line.strip()] if sink.exists() else []
    want = {f"{b[0]}..{b[1]}" for b in blocks}
    complete = len(_done(sink)) >= len(blocks) * len(strategies) * len(cells())
    agg = combine([r for r in rows if r["block"] in want])
    v = verdicts(agg)
    print(render(agg, v))
    adoptable = [f"{s}: {c}" for (s, c), x in v.items() if x["adoptable"]]
    print(f"\n  {'COMPLETE' if complete else 'PARTIAL'}: {len(rows)} rows. "
          f"Adoptable: {', '.join(adoptable) if adoptable else 'none'}")
    out.write_text(json.dumps({"window": window, "complete": complete, "strategies": list(strategies),
                               "combined": [{**x, "blocks": x["blocks"]} for x in agg.values()],
                               "verdicts": [{"strategy": s, "cell": c, **x} for (s, c), x in v.items()]},
                              indent=1))
    if complete:
        import experiment_registry as er
        if er.get(conn, EXPERIMENT)["status"] == er.RUNNING:
            er.complete(conn, EXPERIMENT, {"adoptable": adoptable, "file": str(out)},
                        "adoptable cells: " + (", ".join(adoptable) if adoptable else "none — profit exits "
                                               "did not beat the strategies as they are"))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
