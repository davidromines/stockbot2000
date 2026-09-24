"""
RETIRED 2026-09-24 (owner's decision). The Phase 10 promotion path —
promotion_policy.py, roster.py, allocation.py, live_pipeline.py — is replaced
by ONE system: ranking.py scores every strategy and slots.py fills the five
slots from it. Kept, with its tests, as the record of what applied before;
daily.sh no longer runs it, and nothing trades from it.

Capital allocation across the live roster. Phase 10, item 32.

How much each roster slot gets, against the account cap. Sizing comes from
config — $20 x 5 today — and the allocator never invents capital: the sum of
allocations can be below the cap but never above it.

Three schemes, registered rather than hardcoded, because which one is right is
an empirical question nobody here has answered yet:

    equal        every slot the same. The control.
    score        proportional to scoreboard score.
    risk_parity  inverse to realised volatility, so a wild strategy gets less.

`allocate()` returns dollars per strategy and refuses to exceed the cap.
Nothing here places an order.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone

import eligibility
import league as lg
import scoreboard as sb
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("allocation")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS allocations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            at            TEXT NOT NULL,
            scheme        TEXT NOT NULL,
            strategy_key  TEXT NOT NULL,
            dollars       REAL NOT NULL,
            share         REAL NOT NULL,
            capital_usd   REAL NOT NULL,
            note          TEXT
        )
    """)
    conn.commit()


def _equal(rows):
    n = len(rows)
    return {r["strategy_key"]: 1.0 / n for r in rows} if n else {}


def _score(rows):
    tot = sum(max(r.get("score") or 0.0, 0.0) for r in rows)
    if tot <= 0:
        return _equal(rows)
    return {r["strategy_key"]: max(r.get("score") or 0.0, 0.0) / tot for r in rows}


def _risk_parity(rows):
    """Inverse volatility. A strategy with no measured vol falls back to equal."""
    inv = {}
    for r in rows:
        v = (r.get("metrics") or {}).get("volatility") or 0.0
        inv[r["strategy_key"]] = (1.0 / v) if v > 0 else 0.0
    tot = sum(inv.values())
    if tot <= 0:
        return _equal(rows)
    return {k: v / tot for k, v in inv.items()}


SCHEMES = {"equal": _equal, "score": _score, "risk_parity": _risk_parity}
DEFAULT_SCHEME = "equal"


def capital(cfg: dict) -> float:
    r = cfg["risk"]
    return float(r["position_size_usd"]) * int(r["max_open_positions"])


def allocate(conn, cfg: dict, scheme: str = DEFAULT_SCHEME,
             formula: str = sb.DEFAULT_FORMULA) -> dict:
    if scheme not in SCHEMES:
        raise SystemExit(f"unknown scheme {scheme!r}; have {sorted(SCHEMES)}")
    init(conn)
    cap = capital(cfg)
    proposal = eligibility.propose(conn, cfg, formula)
    roster = proposal["roster"]
    if not roster:
        return {"scheme": scheme, "capital": cap, "allocations": [],
                "unallocated": cap, "roster_empty": True,
                "reason": "no strategy is eligible, so there is nothing to fund"}

    shares = SCHEMES[scheme](roster)
    per_position_cap = float(cfg["risk"]["position_size_usd"])
    out, spent = [], 0.0
    for r in roster:
        share = shares.get(r["strategy_key"], 0.0)
        dollars = min(cap * share, per_position_cap)
        spent += dollars
        out.append({"strategy_key": r["strategy_key"], "name": r["name"],
                    "share": share, "dollars": dollars,
                    "score": r.get("score")})
    return {"scheme": scheme, "capital": cap, "allocations": out,
            "allocated": spent, "unallocated": cap - spent,
            "roster_empty": False}


def record(conn, cfg: dict, result: dict, note: str = "") -> int:
    init(conn)
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [(at, result["scheme"], a["strategy_key"], a["dollars"], a["share"],
             result["capital"], note) for a in result["allocations"]]
    conn.executemany("""INSERT INTO allocations (at, scheme, strategy_key,
        dollars, share, capital_usd, note) VALUES (?,?,?,?,?,?,?)""", rows)
    conn.commit()
    return len(rows)


def render(r: dict) -> str:
    L = ["", f"  CAPITAL ALLOCATION — scheme '{r['scheme']}'",
         f"  account cap ${r['capital']:,.2f}", "  " + "-" * 62]
    if r.get("roster_empty"):
        L += [f"  {r['reason']}.",
              "  The allocator funds the roster; it does not choose one.", ""]
        return "\n".join(L)
    L.append(f"  {'strategy':<30}{'share':>9}{'dollars':>12}")
    for a in r["allocations"]:
        L.append(f"  {a['name'][:29]:<30}{a['share']:>9.1%}{a['dollars']:>12,.2f}")
    L += ["  " + "-" * 62,
          f"  allocated ${r['allocated']:,.2f}   unallocated "
          f"${r['unallocated']:,.2f}",
          "", "  Nothing here places an order.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scheme", default=DEFAULT_SCHEME)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--schemes", action="store_true")
    a = ap.parse_args()
    if a.schemes:
        print("\n  ALLOCATION SCHEMES")
        for k, f in sorted(SCHEMES.items()):
            print(f"    {k:<14}{(f.__doc__ or 'equal weight').strip().splitlines()[0]}")
        return 0
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    r = allocate(conn, cfg, a.scheme)
    print(render(r))
    if a.record and not r.get("roster_empty"):
        print(f"  recorded {record(conn, cfg, r)} allocations\n")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
