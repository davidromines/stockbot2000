"""
Paper-track the wider-stop variants that passed the registered sweep (Stage AD3.6; owner 2026-10-21, option (a)).

`stop_width_slots_v1` (risk_sweep.py) froze 23 strategies and tested ATR stop multiples against each as it was. For
every strategy whose 6x cell is ADOPTABLE under the pre-registered rule (paired gain per trade, date-clustered t >=
2.58, a gain in most years) this opens a NEW strategy — never an edit of the old one:

  - the genome exactly as the experiment froze it, with `risk.stop_atr_multiple` = 6.0 (risk_sweep.with_stop)
  - its own paper fund (next-open fills), so it builds its own forward record
  - registered in the league at PAPER with parent_key = the original, source_ref = stop_width_slots_v1, and its own
    family label (<parent family>_stop6x) so its evidence never mixes with the parent's

Research only: slots.assess refuses every strategy registered from `slots.research_only_sources` (this experiment),
so none can take a slot or a stand-in until the owner decides on its record. The parents and their stops are
untouched.

    ./venv/bin/python stop_adopt.py            # what would be opened
    ./venv/bin/python stop_adopt.py --apply    # open the funds and register them
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys

import risk_sweep as rsw
from universe import load_config

ACTOR = "stop_adopt"
SOURCE = rsw.EXP_STOP
MULT = 6.0


def winners(rows: list, mult: float = MULT) -> dict:
    """strategy -> its adoptable cell summary at `mult` (risk_sweep's pre-registered rule)."""
    out = {}
    for r in rows:
        s = (r.get("stops") or {}).get(str(mult))
        if s and rsw.stop_verdict(s):
            out[r["strategy"]] = {**s, "own_stop": r.get("stop"), "base_mean": r.get("base_mean")}
    return out


def existing(conn, parent: str) -> str | None:
    r = conn.execute("SELECT strategy_key FROM league_strategies WHERE parent_key=? AND source_ref=?",
                     (parent, SOURCE)).fetchone()
    return r[0] if r else None


def adopt(conn, cfg, spec: dict, rows: list, apply_: bool) -> list:
    import league
    import leagues
    import migrate_league
    import paper_trading
    done = []
    for strat, w in sorted(winners(rows).items()):
        parent, ver = strat.split("@v")
        name = (conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? AND version=?",
                             (parent, int(ver))).fetchone() or [parent])[0]
        new_name = f"{name} · stop {MULT:g}x ATR"
        item = {"parent": strat, "name": new_name, "own_stop": w["own_stop"], "d_mean": w["d_mean"], "t": w["t"]}
        have = existing(conn, parent)
        if have:
            done.append({**item, "strategy_key": have, "status": "already open"})
            continue
        if not apply_:
            done.append({**item, "status": "would open"})
            continue
        genome = rsw.with_stop(spec["entry_rule"][strat], MULT)
        family = f"{leagues.family_of(conn, parent, int(ver)) or 'unknown'}_stop{MULT:g}x"
        paper_trading.init(conn)
        run_id = paper_trading.start(conn, cfg, name=new_name, strategy=json.dumps(genome, sort_keys=True))
        conn.execute("UPDATE paper_runs SET label=?, family=? WHERE run_id=?", (new_name[:60], family, run_id))
        conn.commit()
        key = f"paper:{run_id}"
        run = dict(zip(("strategy", "family", "capital_usd"),
                       conn.execute("SELECT strategy, family, capital_usd FROM paper_runs WHERE run_id=?",
                                    (run_id,)).fetchone()))
        hyp = (f"{SOURCE} [{MULT:g}x ATR stop, was {w['own_stop']:g}x]: {w['d_mean']:+.3%} per trade vs the parent "
               f"(date-clustered t {w['t']:+.1f}), 2016-2019 with dead companies; research only until its own record")
        league.register(conn, key, new_name, migrate_league._paper_spec(run), author=ACTOR,
                        source_kind="experiment", source_ref=SOURCE, parent_key=parent,
                        ancestry=[parent], hypothesis=hyp)
        league.transition(conn, key, "PAPER", f"opened from experiment {SOURCE}: {hyp}", actor=ACTOR)
        done.append({**item, "strategy_key": key, "status": "opened"})
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    import experiment_registry as er
    e = er.get(conn, SOURCE)
    if e["status"] != er.COMPLETE:
        raise SystemExit(f"{SOURCE} is {e['status']}, not COMPLETE: nothing to adopt yet")
    spec = json.loads(e["spec"])
    for d in adopt(conn, cfg, spec, rsw.rows(), a.apply):
        print(f"  {d['status']:<13} {d['name'][:70]:<70} {d['d_mean']:+.3%}/trade (t {d['t']:+.1f})"
              + (f"  {d['strategy_key']}" if d.get("strategy_key") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
