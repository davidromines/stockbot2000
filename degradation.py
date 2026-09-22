"""
How predictive are this project's own backtests? Phase 7, item 15.

THE QUESTION
------------
Phase 7 asks for `backtest -> out-of-sample -> paper -> live` tracked as one
chain, with degradation measured at each hop, *"to allow Stockbot to learn how
predictive its own backtests are."*

For this project that is not a nice-to-have. Every apparent edge here has so far
turned out to be a measurement artifact — the price filter, the exit-pricing
bug, close fills, the seed convergence. Each was caught by a specific
investigation. This measures the general case: across every strategy that has
both a backtest and a forward record, how much of the backtest survived contact
with forward time?

WHY THE LINK IS FRAGILE, AND WHY IT IS NOT FIXED HERE
-------------------------------------------------------
`paper_runs` stores each genome inline as JSON rather than referencing
`strategies.id`. That denormalisation is deliberate and load-bearing — it is why
every forward test survived the corruption that cost 5,767 strategy rows — so it
stays. The cost is that linking a fund back to its backtest means matching on
genome text, which works for 13 of 16 funds. The classifier and the two
conviction screens have no genome at all and are reported as unlinkable rather
than quietly dropped.

WHAT THIS CANNOT YET SAY
-------------------------
The forward records are a median of 7 marks long. A degradation ratio computed
over 7 sessions is not an estimate of degradation, and the module refuses to
report a verdict below `league.min_rank_marks`. It shows the pairing and the
raw numbers, marked provisional, so the measurement is in place and accruing —
the answer arrives with calendar time, and nothing else makes it arrive sooner.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone

import league as lg
import scoreboard as sb
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("degradation")

STAGES = ("backtest", "validation", "paper", "live")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS degradation (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            at                TEXT NOT NULL,
            strategy_key      TEXT NOT NULL,
            version           INTEGER,
            linked_strategy   TEXT,
            link_method       TEXT NOT NULL,
            backtest_return   REAL,
            validation_return REAL,
            paper_return      REAL,
            live_return       REAL,
            paper_vs_backtest REAL,
            n_marks           INTEGER,
            provisional       INTEGER NOT NULL,
            note              TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_deg_key ON degradation(strategy_key)")
    conn.commit()


def _link(conn, run_id: str) -> tuple:
    """
    Find the Lab strategy behind a paper fund. Returns (strategy_id, method).

    Matched on genome text because `paper_runs` stores the genome inline rather
    than referencing `strategies.id`. That denormalisation is why the forward
    record survived the 2026-09-12 corruption, so it is not being undone to make
    this join easier.
    """
    raw = conn.execute("SELECT strategy FROM paper_runs WHERE run_id=?",
                       (run_id,)).fetchone()
    if not raw or not raw[0]:
        return None, "no strategy recorded"
    raw = raw[0]
    if raw == "model":
        return None, "classifier — no genome to link"
    try:
        g = json.loads(raw)
    except (ValueError, TypeError):
        return None, "unreadable strategy field"
    if not isinstance(g, dict) or "entry" not in g:
        if isinstance(g, dict) and g.get("conviction"):
            return None, "conviction screen — no Lab backtest exists"
        return None, "not a genome"

    for text, how in ((raw, "genome text"),
                      (json.dumps(g, sort_keys=True), "genome normalised")):
        r = conn.execute("SELECT id FROM strategies WHERE genome=? LIMIT 1",
                         (text,)).fetchone()
        if r:
            return r[0], how
    return None, "genome not found in the Lab ledger"


def _return_on_window(conn, strategy_id: str, start: str, end: str,
                      position_size: float):
    """
    A Lab strategy's MEAN PER-TRADE return over one window.

    Not net P&L over capital. The Lab's `net_pnl_usd` is the sum across up to
    20,000 independent $20 trades spanning fourteen years; a forward fund's
    return is a portfolio compounding $100 over weeks. Dividing the first by
    $100 produced backtest figures of 3,428% to 26,065% against forward figures
    of a few percent, and every "survived" ratio came out near zero — a number
    that looked like a devastating finding and was purely a unit error.

    Mean per-trade return is the one quantity both sides actually have. It is
    still not a perfect comparison — the forward side compounds and holds a
    concentrated book — but it is a comparison of like with like.

    Selected by WINDOW rather than row order: `evaluations` is WITHOUT ROWID,
    and "the first row" is not a definition of anything.
    """
    r = conn.execute("""SELECT net_pnl_usd, n_trades FROM evaluations
        WHERE strategy_id=? AND window_start=? AND window_end=? LIMIT 1""",
        (strategy_id, start, end)).fetchone()
    if not r or r[0] is None or not r[1] or not position_size:
        return None
    return (float(r[0]) / int(r[1])) / position_size


def _backtest_return(conn, strategy_id: str, position_size: float,
                     lab: dict) -> tuple:
    """(backtest, validation) mean per-trade returns for a Lab strategy."""
    bt = _return_on_window(conn, strategy_id, lab["search_start"],
                           lab["search_end"], position_size)
    val = _return_on_window(conn, strategy_id, lab["validation_start"],
                            lab["validation_end"], position_size)
    return bt, val


def _forward_per_trade(conn, run_id: str):
    """
    The forward fund's mean per-trade return, from its own closed trades.

    `paper_trades.pnl_pct` is recorded per trade, so this needs no assumption
    about sizing — which is the whole reason the comparison is done here rather
    than on the equity curve.
    """
    r = conn.execute("""SELECT COUNT(*), AVG(pnl_pct) FROM paper_trades
        WHERE run_id=? AND exit_date IS NOT NULL""", (run_id,)).fetchone()
    if not r or not r[0] or r[1] is None:
        return None, 0
    v = float(r[1])
    # pnl_pct is stored as a percentage in this schema; normalise to a fraction.
    return (v / 100.0 if abs(v) > 1.0 else v), int(r[0])


def measure(conn, cfg: dict) -> list:
    init(conn)
    floor = sb.min_marks(cfg)
    lab = cfg["lab"]
    out = []
    for r in lg.roster(conn):
        if r["source_kind"] != "paper_runs":
            out.append({**r, "link_method": "pair fund — no Lab backtest",
                        "linked": None, "backtest_return": None,
                        "paper_return": None, "provisional": True,
                        "n_marks": 0, "paper_vs_backtest": None,
                        "equity_return": None, "n_fwd_trades": 0})
            continue
        size = float(cfg["risk"]["position_size_usd"])
        sid, how = _link(conn, r["source_ref"])
        m = sb.metrics(conn, r["strategy_key"], "paper_runs", r["source_ref"])
        bt = val = None
        if sid:
            bt, val = _backtest_return(conn, sid, size, lab)
        fwd, n_fwd = _forward_per_trade(conn, r["source_ref"])
        deg = None
        if bt not in (None, 0) and fwd is not None:
            # Share of the backtest's per-trade edge that survived into forward
            # time. 1.0 reproduced it; 0.0 none of it; negative means forward
            # went the other way.
            deg = fwd / bt
        if sid and bt is None:
            how = "linked, but no evaluation on the search window"
        out.append({**r, "link_method": how, "linked": sid,
                    "backtest_return": bt, "validation_return": val,
                    "paper_return": fwd, "equity_return": m["cumulative_return"],
                    "paper_vs_backtest": deg,
                    "n_marks": m["n_marks"], "n_fwd_trades": n_fwd,
                    "provisional": (m["n_marks"] < floor or n_fwd < 20)})
    return out


def record(conn, cfg: dict) -> int:
    rows = measure(conn, cfg)
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany("""INSERT INTO degradation (at, strategy_key, version,
        linked_strategy, link_method, backtest_return, validation_return,
        paper_return, live_return, paper_vs_backtest, n_marks, provisional, note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(at, x["strategy_key"], x["version"], x["linked"], x["link_method"],
          x["backtest_return"], x.get("validation_return"), x["paper_return"],
          None, x["paper_vs_backtest"], x["n_marks"],
          1 if x["provisional"] else 0, None) for x in rows])
    conn.commit()
    return len(rows)


def render(rows: list, floor: int) -> str:
    linked = [x for x in rows if x["paper_vs_backtest"] is not None]
    unlinked = [x for x in rows if x["paper_vs_backtest"] is None]
    firm = [x for x in linked if not x["provisional"]]

    L = ["", "  BACKTEST -> FORWARD DEGRADATION",
         f"  {len(linked)} of {len(rows)} strategies have both a backtest and a "
         f"forward record", "  " + "-" * 86,
         "  Mean return PER TRADE on both sides — the only quantity the",
         "  backtest and the forward record both actually have.",
         "  " + "-" * 86,
         f"  {'name':<24}{'backtest':>11}{'forward':>11}{'survived':>11}"
         f"{'trades':>8}  status"]
    for x in sorted(linked, key=lambda y: -(y["paper_vs_backtest"] or 0)):
        L.append(f"  {x['name'][:23]:<24}{x['backtest_return']:>10.3%}"
                 f"{x['paper_return']:>11.3%}{x['paper_vs_backtest']:>10.1%}"
                 f"{x['n_fwd_trades']:>8}  "
                 f"{'PROVISIONAL' if x['provisional'] else 'firm'}")
    L += ["  " + "-" * 86]

    if firm:
        vals = sorted(x["paper_vs_backtest"] for x in firm)
        med = vals[len(vals) // 2]
        L += ["", f"  Median share of backtest return surviving into forward "
                  f"time: {med:.1%}", f"  across {len(firm)} strategies with a "
                  f"sufficient forward record."]
    else:
        L += ["", "  NO VERDICT YET. Every pairing above is provisional: the",
              f"  forward records are shorter than the {floor} marks required",
              "  for a number to mean anything. A degradation ratio computed",
              "  over seven sessions measures the seven sessions, not the",
              "  degradation. The measurement is in place and accruing; the",
              "  answer arrives with calendar time and nothing makes it",
              "  arrive sooner."]
    if unlinked:
        L += ["", "  NOT LINKABLE", "  " + "-" * 86]
        for x in sorted(unlinked, key=lambda y: y["name"]):
            L.append(f"  {x['name'][:25]:<26}{x['link_method']}")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn); lg.init(conn)
    rows = measure(conn, cfg)
    print(render(rows, sb.min_marks(cfg)))
    if a.record:
        print(f"  recorded {record(conn, cfg)} rows\n")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
