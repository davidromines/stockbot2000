"""
Options without the $100 cap, and with a tight buy/sell gap (owner 2026-10-22: "remove the $100 cap and test again").
Registered experiment `options_liquid_v1`. Writes BACKTEST rows under variant names only; the strategies' own
backtests are untouched.

Why: at or under $100 a contract's median buy/sell gap was 72% of its price (2026-10-20 quotes); in the existing
backtests, single long call/put trades entered with a gap <= 5% averaged +2.1% against -18% to -34% for gaps above 10%
(the retail-options studies name the gap as the main reason buyers lose). So:

    A  the 10 tradeable specs (one long call or put) with no price cap — the gap limit as before (50% of the mid)
    B  the same with no cap and the gap limited to 5% of the mid at entry       <- the test that decides

Window: every option date in the store (2020-01-06 ..). Fills as options_lab always does: buy at the ask, sell at the
bid. Stock-signal specs read the top 5 ranked stock strategies AT REGISTRATION (frozen in the spec).

PASS for a strategy under B (written before any result): mean return per trade > 0, date-clustered t >= 2.8 (about a
Bonferroni 5% across the 10), and a positive mean in at least 4 of the 7 calendar years. A pass is a candidate for a
paper fund; live needs the account's options approval, live sizing for real contract prices, and the owner.

    ./venv/bin/python options_liquid_test.py --register
    ./run_bounded.sh ./venv/bin/python options_liquid_test.py --run      # resumable per variant
    ./venv/bin/python options_liquid_test.py --report [--write]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import copy
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

ROOT = Path(__file__).resolve().parent
EXPERIMENT = "options_liquid_v1"
SINK = ROOT / "data" / "options_liquid.jsonl"
SETTINGS = {"A": {"max_contract_cost_usd": None}, "B": {"max_contract_cost_usd": None, "max_spread_frac": 0.05}}
T_NEED = 2.8
MIN_YEARS = 4


def strategies() -> list:
    import options_lab as ol
    return sorted(n for n, p in ol.STRATEGIES.items() if ol.tradeable(p))


def variant(name: str, key: str) -> str:
    return f"{name}__liq{key}"


def cfg_for(cfg: dict, key: str) -> dict:
    c = copy.deepcopy(cfg)
    c.setdefault("options", {}).update(SETTINGS[key])
    return c


def stats(rows: pd.DataFrame) -> dict:
    import forward_stats as fs
    if len(rows) < 10:
        return {"n": int(len(rows)), "pass": False}
    r = rows["ret"].to_numpy(float)
    cs = fs.cluster_stats(r, rows["opened"].astype(str).to_numpy())
    by = rows.assign(y=rows["opened"].str[:4]).groupby("y")["ret"].mean()
    usd = (rows["ret"] * rows["cost"] * 100).to_numpy(float)              # one contract: (value - cost) x 100
    out = {"n": int(len(r)), "mean": float(r.mean()), "median": float(np.median(r)), "win": float((r > 0).mean()),
           "t": cs["t"], "dates": cs["clusters"], "by_year": {k: float(v) for k, v in by.items()},
           "years_positive": int((by > 0).sum()), "years": int(len(by)),
           "median_contract_usd": float(np.median(rows["cost"]) * 100), "mean_usd_per_contract": float(usd.mean())}
    out["pass"] = bool(out["mean"] > 0 and (out["t"] or 0) >= T_NEED and out["years_positive"] >= MIN_YEARS)
    return out


def spec(conn, cfg) -> dict:
    import ranking
    top = [r["strategy_key"] for r in ranking.rank(conn, cfg) if r["passes_gate"] and not r.get("from_search")
           and not str(r["strategy_key"]).startswith(("crypto:", "option:", "pair:", "value:"))][:5]
    return {"primary_metric": "mean return per trade of one long call or put, bought at the ask and sold at the bid",
            "universe": "options_lab's specs that may trade (one long call or put): " + ", ".join(strategies()),
            "entry_rule": {"settings": SETTINGS, "stock_signal_top5_at_registration": top},
            "exit_rule": "each spec's own exits (holding limit, expiry-near, earnings), as options_lab",
            "holding_period": "each spec's own", "cost_assumptions": "buy at the ask, sell at the bid (no other cost)",
            "evaluation_period": "every option date in the store at the run (2020-01-06 ..)",
            "data_version": "option_quotes / option_vol (DoltHub) at the run", "stopping_rule": "one run of each variant",
            "sample_size": "every signal the spec takes", "holdout_policy": "none; a pass goes to paper first",
            "pass_rule": f"under B: mean > 0, date-clustered t >= {T_NEED}, positive in >= {MIN_YEARS} of 7 years"}


def register(conn, cfg) -> dict:
    import experiment_registry as er
    try:
        return json.loads(er.get(conn, EXPERIMENT)["spec"])
    except er.RegistryError:
        pass
    sp = spec(conn, cfg)
    er.create(conn, EXPERIMENT, "With no per-contract price cap and the entry gap limited to 5% of the mid, at least one "
              "long call/put strategy makes money per trade by more than noise across 10 strategies and in most years. "
              "Fails if none passes under B.", "Claude (owner 'remove the $100 cap and test again', 2026-10-22)", sp)
    er.register(conn, EXPERIMENT)
    return json.loads(er.get(conn, EXPERIMENT)["spec"])


def lean_signals(conn, cfg, start: str, end: str, keys: list) -> dict:
    """options_lab.stock_signals for the frozen five: date -> [(ticker, strategy name)], most liquid first, loading
    only the columns their rules read. The full loader (every feature and every fundamental, 2020 onward) was killed
    at the 6 GB cap on 2026-10-22."""
    import genome as gn
    import storage
    import strategy_objects as so
    from train_model import FEATURE_COLS
    gs = []
    for k in keys:
        ver = conn.execute("SELECT MAX(version) FROM league_strategies WHERE strategy_key=?", (k,)).fetchone()[0] or 1
        g = so.genome(conn, k, ver)
        nm = conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? AND version=?", (k, ver)).fetchone()
        if g and g.get("entry"):
            gs.append((nm[0] if nm else k, g))
    need = storage.columns_read([g for _, g in gs])
    df = storage.load_training_frame(conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"], start_date=start,
                                     end_date=end, min_price=cfg["risk"].get("min_price"),
                                     min_dollar_volume=cfg["risk"].get("min_dollar_volume"), include_liquidity=True)
    df = df[[c for c in df.columns if c in {"ticker", "date", "close", "dollar_volume_20"} | need]]
    if any(storage.needs_panel(g) for _, g in gs):
        df = storage.attach_fundamentals(conn, df, extras=need)
    df = df.sort_values(["ticker", "date"])
    out = {}
    for name, g in gs:
        hit = df[gn._as_bool(gn.evaluate(g["entry"], df)).to_numpy()]
        for d, grp in hit.sort_values("dollar_volume_20", ascending=False).groupby("date"):
            out.setdefault(str(d)[:10], []).extend((t, name) for t in grp["ticker"].astype(str))
    return out


def _done(sink: Path = SINK) -> set:
    return {json.loads(x)["variant"] for x in sink.read_text().splitlines() if x.strip()} if sink.exists() else set()


def run(conn, cfg, sp: dict) -> int:
    import experiment_registry as er
    import options_lab as ol
    if er.get(conn, EXPERIMENT)["status"] == er.REGISTERED:
        er.start(conn, EXPERIMENT)
    ol.init(conn)
    dates = ol.option_dates(conn, "2020-01-01", None)
    done, wrote, sig = _done(), 0, None
    for key in SETTINGS:
        for name in strategies():
            v = variant(name, key)
            if v in done:
                continue
            p = ol.STRATEGIES[name]
            if p["rule"] in ("stock_signal", "signal_cheap_iv") and sig is None:
                sig = lean_signals(conn, cfg, dates[0], dates[-1], sp["entry_rule"]["stock_signal_top5_at_registration"])
                print(f"stock signals: {sum(len(v) for v in sig.values()):,} on {len(sig):,} dates", flush=True)
            conn.execute("DELETE FROM option_trades WHERE mode='BACKTEST' AND strategy=?", (v,))
            ol.run(conn, cfg_for(cfg, key), v, dates, "BACKTEST",
                   sig if p["rule"] in ("stock_signal", "signal_cheap_iv") else None, spec=p)
            rows = pd.read_sql("SELECT opened, cost, ret FROM option_trades WHERE mode='BACKTEST' AND strategy=? "
                               "AND ret IS NOT NULL", conn, params=(v,))
            with SINK.open("a") as fh:
                fh.write(json.dumps({"variant": v, "strategy": name, "setting": key, **stats(rows)}, default=float) + "\n")
            wrote += 1
            print(f"{v}: {len(rows)} trades", flush=True)
    return wrote


def results() -> list:
    return [json.loads(x) for x in SINK.read_text().splitlines() if x.strip()] if SINK.exists() else []


def render(res: list) -> str:
    import options_lab as ol
    by = {(r["strategy"], r["setting"]): r for r in res}
    f = lambda x, s="{:+.1%}": "—" if x is None else s.format(x)       # noqa: E731
    L = [f"# Options without the $100 cap — {date.today().isoformat()} (`{EXPERIMENT}`)", "",
         "One long call or put per trade, bought at the ask and sold at the bid, 2020 onward. A = no price cap; "
         "B = no cap and an entry gap of at most 5% of the mid (the test that decides).", "",
         "| strategy | A: trades | A: mean | B: trades | B: mean | B: median | B: win | B: t | B: years + | B: contract (median) | B: $ per contract | pass |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for name in strategies():
        a, b = by.get((name, "A"), {}), by.get((name, "B"), {})
        L.append(f"| {ol.STRATEGIES[name]['name']} | {a.get('n', '—')} | {f(a.get('mean'))} | {b.get('n', '—')} | "
                 f"{f(b.get('mean'))} | {f(b.get('median'))} | {f(b.get('win'), '{:.0%}')} | {f(b.get('t'), '{:+.1f}')} | "
                 f"{b.get('years_positive', '—')}/{b.get('years', '—')} | "
                 f"{f(b.get('median_contract_usd'), '${:,.0f}')} | {f(b.get('mean_usd_per_contract'), '${:+,.0f}')} | "
                 f"{'PASS' if b.get('pass') else 'no'} |")
    passed = [ol.STRATEGIES[r["strategy"]]["name"] for r in res if r["setting"] == "B" and r.get("pass")]
    L += ["", f"**Under B: {len(passed)} of {len(strategies())} pass.** " + (", ".join(passed) if passed else
          "No long call/put strategy makes money by more than noise even when only tight-gap contracts are bought.")]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for x in ("register", "run", "report", "write"):
        ap.add_argument(f"--{x}", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    sp = register(conn, cfg)
    if a.register:
        print(f"{EXPERIMENT} registered; stock-signal top 5: {sp['entry_rule']['stock_signal_top5_at_registration']}")
    conn.row_factory = None
    if a.run:
        conn.row_factory = sqlite3.Row
        print(f"computed {run(conn, cfg, sp)} variants")
    if a.report or a.write:
        res = results()
        text = render(res)
        print(text)
        if a.write:
            (ROOT / "reports" / f"options_liquid_{date.today().isoformat()}.md").write_text(text)
        n = 2 * len(strategies())
        if len(res) >= n:
            import experiment_registry as er
            conn.row_factory = sqlite3.Row
            if er.get(conn, EXPERIMENT)["status"] == er.RUNNING:
                passed = [r["strategy"] for r in res if r["setting"] == "B" and r.get("pass")]
                er.complete(conn, EXPERIMENT, {"passed": passed, "variants": res},
                            "PASS: " + ", ".join(passed) if passed else "FAIL: no strategy passes under B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
