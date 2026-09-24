"""
Research library -> strategy objects. Phase 13 §7, §32; step H4.

Every library entry is a hypothesis, never evidence (§7). This bridge:

1. carries the §7 fields the library does not already hold, in
   `library_meta` (rationale, exact rules, entry/exit, sizing, risk, holding
   period, URL, publication date, and the three statuses: backtest,
   replication, forward test);
2. maps each entry to the factory families that express it and links the
   resulting strategy objects (`library_strategy_link`), so one entry becomes
   one or more strategy objects (§32);
3. queues them for the pipeline; nobody tests entries one by one by hand;
4. accepts a new human hypothesis from the command line and turns it into a
   library entry with the provenance fields the library requires.

An entry with no expressible template (options flow, LLM setups, event
studies needing an event pipeline) is linked to nothing and marked blocked
with the reason — visible, not dropped.

    python library_bridge.py --sync
    python library_bridge.py --add --name "..." --family momentum \
        --hypothesis "..." --rationale "..." --biases "..." --limitations "..." \
        --template xs_momentum
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone

import research_queue as rq
import storage
import strategy_factory as sf
import strategy_library as lib
import strategy_objects as so
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("library_bridge")

# Entry -> factory families that express it. Explicit, reviewable, and the
# reason for every unmapped entry is stated below it.
MAPPING = {
    "family:momentum": ["xs_momentum", "ts_momentum", "relative_strength"],
    "family:value": ["value_book", "earnings_yield"],
    "family:quality": ["profitability", "quality_roa", "quality_piotroski"],
    "family:value_momentum": ["value_momentum"],
    "family:value_quality": ["value_quality"],
    "family:fundamental_momentum": ["fundamental_momentum", "fundamental_price_momentum"],
    "family:defensive": ["balance_sheet", "low_volatility"],
    "conviction:deep_value": ["value_book"],
    "conviction:quality_value": ["value_quality"],
    "conviction:piotroski_value": ["quality_piotroski"],
    "conviction:magic_formula": ["roic_valuation"],
    "conviction:buffett": ["value_quality_momentum", "quality_low_volatility"],
    "conviction:conservative": ["balance_sheet", "low_volatility"],
    "seed:rsi_oversold": ["rsi_reversion"],
    "seed:rsi_oversold_uptrend": ["rsi_reversion"],
    "seed:golden_cross": ["ma_cross"],
    "seed:macd_crossover": ["macd_cross"],
    "seed:macd_trend_confirmed": ["macd_cross"],
    "seed:bollinger_reversion": ["bollinger_reversion"],
    "seed:bollinger_breakout": ["volatility_breakout"],
    "seed:cross_sectional_momentum": ["xs_momentum"],
    "seed:dual_momentum": ["ts_momentum"],
    "seed:donchian_breakout": ["breakout_52w"],
    "seed:trend_following_adx": ["trend_following"],
    "seed:obv_accumulation": ["momentum_volume"],
    "seed:mean_reversion_to_sma": ["bollinger_reversion"],
    "seed:short_term_reversal": ["rsi_reversion"],
}
BLOCKED = {
    "seed:momentum_pullback": "the seed whose constant contaminated 231 survivors; not regenerated (seed_mode NONE)",
    "event:pead": "needs the earnings-surprise event pipeline in the event league (pead.py), not a daily template",
    "social:smart_money_copy": "needs filings-to-trade event data not in this database",
    "social:options_flow": "no options data",
    "social:leaps_small_account": "no options data",
    "social:llm_setup_generator": "ML league generator not built; no historical LLM outputs to test",
    "social:sets_machine": "crypto; covered by crypto_grid.py in the crypto league",
    "model:xgboost": "already forward-tested as the XGBoost paper fund (ML league)",
    "seed:stochastic_crossover": "stoch features available but no factory template yet",
    "seed:williams_r_oversold": "no factory template yet",
    "seed:cci_extreme": "no factory template yet",
    "seed:turtle_with_volume": "no factory template yet",
    "seed:chaikin_oscillator": "no factory template yet",
}
META = ("economic_rationale", "exact_rules", "holding_period", "entry_conditions",
        "exit_conditions", "position_sizing", "risk_management", "url",
        "publication_date", "implementation_notes", "backtest_status",
        "replication_status", "forward_test_status")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init(conn) -> None:
    lib.init(conn)
    rq.init(conn)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS library_meta (
            entry_id TEXT PRIMARY KEY,
            {', '.join(f'{m} TEXT' for m in META)},
            updated_at TEXT NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS library_strategy_link (
            entry_id TEXT NOT NULL, strategy_key TEXT NOT NULL, version INTEGER NOT NULL,
            family TEXT NOT NULL, linked_at TEXT NOT NULL,
            PRIMARY KEY (entry_id, strategy_key, version))""")
    conn.commit()


def _entries(conn) -> list:
    cur = conn.execute("SELECT * FROM strategy_library")
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def sync(conn, cfg) -> dict:
    """Link every entry to strategy objects, fill §7 metadata, queue the work."""
    init(conn)
    per_family = int((cfg.get("factory") or {}).get("max_variants_per_family", 8))
    stats = {"entries": 0, "linked": 0, "strategies": 0, "blocked": 0, "queued": 0}
    for e in _entries(conn):
        stats["entries"] += 1
        eid = e["entry_id"]
        fams = MAPPING.get(eid, [])
        rules = {f: sf.F[f]["build"](sf.grid_points(sf.F[f], 1)[0]) for f in fams}
        meta = {
            "economic_rationale": "; ".join(sf.F[f]["rationale"] for f in fams) or e.get("interpretation"),
            "exact_rules": json.dumps(rules, sort_keys=True) if rules else None,
            "holding_period": ", ".join(str(sf.F[f]["grid"].get("hold", "")) for f in fams) or None,
            "entry_conditions": "; ".join(f"{f}: see exact_rules" for f in fams) or None,
            "exit_conditions": "strategy exit rule, ATR stop and maximum hold (genome risk)" if fams else None,
            "position_sizing": "one live slot's capital per position (config: slots)",
            "risk_management": "ATR stop and maximum holding period per genome; central risk engine",
            "url": None, "publication_date": None,
            "implementation_notes": (BLOCKED.get(eid) if not fams else
                                     f"expressed by factory families {', '.join(fams)}"),
            "backtest_status": e.get("validation_status"),
            "replication_status": "FAITHFUL" if eid not in lib.NOT_FAITHFUL else "NOT FAITHFUL",
            "forward_test_status": "paper fund running" if eid in (
                "model:xgboost", "conviction:deep_value", "conviction:quality_value") else "none",
        }
        conn.execute(f"INSERT OR REPLACE INTO library_meta (entry_id, {', '.join(META)}, updated_at) "
                     f"VALUES ({', '.join('?' * (len(META) + 2))})",
                     (eid, *[meta[m] for m in META], _now()))
        if not fams:
            rq.enqueue(conn, "library", eid, family=e.get("family"),
                       reason=BLOCKED.get(eid, "no template expresses this entry yet"))
            item = conn.execute("SELECT id FROM research_queue WHERE source='library' AND ref=? "
                                "AND strategy_key=''", (eid,)).fetchone()
            rq.set_status(conn, item[0], "blocked", BLOCKED.get(eid, "no template yet"))
            stats["blocked"] += 1
            continue
        stats["linked"] += 1
        for f in fams:
            for obj in sf.build_objects(f, per_family):
                r = so.register(conn, obj)
                conn.execute("INSERT OR IGNORE INTO library_strategy_link VALUES (?,?,?,?,?)",
                             (eid, r["strategy_key"], r["version"], f, _now()))
                stats["strategies"] += 1
                if rq.enqueue(conn, "library", eid, family=f, strategy_key=r["strategy_key"],
                              version=r["version"], reason=f"library entry {eid}"):
                    stats["queued"] += 1
    conn.commit()
    return stats


def add_hypothesis(conn, a) -> str:
    """A human hypothesis becomes a library entry, then strategy objects if a template fits."""
    init(conn)
    eid = f"human:{a.name.lower().replace(' ', '_')[:40]}"
    lib.upsert(conn, {"entry_id": eid, "name": a.name, "family": a.family,
                      "original_author": "user", "source": "human hypothesis",
                      "original_hypothesis": a.hypothesis, "interpretation": a.rationale,
                      "implementation": a.template or "NOT YET IMPLEMENTED",
                      "known_biases": a.biases, "limitations": a.limitations,
                      "validation_status": "HYPOTHESIS",
                      "status_reason": "entered by a person; untested"})
    if a.template:
        MAPPING[eid] = [a.template]
    sync(conn, load_config())
    return eid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--add", action="store_true")
    for f in ("name", "family", "hypothesis", "rationale", "biases", "limitations", "template"):
        ap.add_argument(f"--{f}")
    a = ap.parse_args()
    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    conn.row_factory = sqlite3.Row
    if a.add:
        print(f"  added {add_hypothesis(conn, a)}")
    if a.sync or not a.add:
        print(f"  {sync(conn, cfg)}")
        print(f"  queue: {rq.counts(conn)}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
