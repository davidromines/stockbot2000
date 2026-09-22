"""
The persistent strategy scoreboard. Phase 7, item 17.

THE MOST IMPORTANT THING THIS MODULE DOES IS REFUSE TO RANK
------------------------------------------------------------
The 21 migrated funds hold a median of **7 equity marks**. A Sharpe ratio from 7
observations is not a weak estimate, it is noise with a decimal point, and a
leaderboard that prints it invites exactly the decision the league exists to
prevent: promoting whichever strategy got lucky in its first fortnight.

So a strategy below `league.min_rank_marks` is reported UNRANKED, with the date
it becomes rankable. It still accrues a record, it simply does not get a number.
This is the same fail-closed rule the risk engine and the quote checks already
use here — an unknown is never treated as an average.

THE FORMULA IS DELIBERATELY NOT DECIDED
----------------------------------------
Phase 7 says: *"Do not define the final weighting yet. Phase 7 should establish
the architecture for testing different scoring formulas."* So formulas are
registered in `FORMULAS`, every rank snapshot records which one produced it, and
`--formula` switches between them. Changing the weighting does not rewrite
history; it writes a new snapshot under a new formula name.

The three shipped formulas are starting points for that research, not
recommendations. `sharpe_only` exists mainly as a control: if a considered
formula cannot beat ranking on raw Sharpe, the consideration is not adding
anything.

WHAT IS MEASURED
----------------
From the forward record only — `paper_equity` and `paper_trades` for strategy
funds, `pair_fund_equity` for pair funds. Never from a backtest. A backtest
number has no place on a forward scoreboard, and keeping them in separate tables
is what stops one being read as the other.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

import league as lg
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scoreboard")

TRADING_DAYS = 252
UNRANKED = "UNRANKED"


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scoreboard_snapshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            at            TEXT NOT NULL,
            formula       TEXT NOT NULL,
            strategy_key  TEXT NOT NULL,
            version       INTEGER,
            rank          INTEGER,
            score         REAL,
            rankable      INTEGER NOT NULL,
            n_marks       INTEGER,
            metrics       TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sb_at ON scoreboard_snapshots(at)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sb_key "
                 "ON scoreboard_snapshots(strategy_key)")
    conn.commit()


# ---------------------------------------------------------------- metrics ---

def _equity_series(conn, kind: str, ref: str) -> tuple:
    if kind == "paper_runs":
        rows = conn.execute("SELECT date, equity_usd FROM paper_equity "
                            "WHERE run_id=? ORDER BY date", (ref,)).fetchall()
    elif kind == "pair_funds":
        rows = conn.execute("SELECT date, equity_usd FROM pair_fund_equity "
                            "WHERE name=? ORDER BY date", (ref,)).fetchall()
    else:
        return [], np.array([])
    return [r[0] for r in rows], np.array([r[1] for r in rows], dtype="float64")


def _drawdown(eq: np.ndarray) -> float:
    if eq.size < 2:
        return 0.0
    peak = np.maximum.accumulate(eq)
    return float(np.max((peak - eq) / np.where(peak > 0, peak, 1.0)))


def metrics(conn, strategy_key: str, kind: str, ref: str,
            capital: float | None = None) -> dict:
    """
    Every forward metric for one strategy.

    Returns them whether or not the sample supports them — deciding that is
    `rankable()`'s job, and a metric computed on thin data is still worth
    recording as long as nothing downstream mistakes it for a result.
    """
    dates, eq = _equity_series(conn, kind, ref)
    n = eq.size
    out = {"n_marks": int(n), "first_mark": dates[0] if dates else None,
           "last_mark": dates[-1] if dates else None}
    if n < 2:
        out.update({"cumulative_return": 0.0, "annualised_return": 0.0,
                    "sharpe": 0.0, "sortino": 0.0, "max_drawdown": 0.0,
                    "calmar": 0.0, "volatility": 0.0, "days": 0})
    else:
        start = capital if capital else eq[0]
        cum = float(eq[-1] / start - 1.0) if start else 0.0
        d0 = datetime.fromisoformat(dates[0]).date()
        d1 = datetime.fromisoformat(dates[-1]).date()
        days = max((d1 - d0).days, 1)
        rets = np.diff(eq) / np.where(eq[:-1] > 0, eq[:-1], 1.0)
        vol = float(rets.std(ddof=1)) if rets.size > 1 else 0.0
        ann_vol = vol * math.sqrt(TRADING_DAYS)
        mean_r = float(rets.mean()) if rets.size else 0.0
        downside = rets[rets < 0]
        dvol = float(downside.std(ddof=1)) * math.sqrt(TRADING_DAYS) \
            if downside.size > 1 else 0.0
        dd = _drawdown(eq)
        ann = float((1 + cum) ** (365.0 / days) - 1.0) if cum > -1 else -1.0
        out.update({
            "cumulative_return": cum,
            "annualised_return": ann,
            "volatility": ann_vol,
            "sharpe": (mean_r * TRADING_DAYS / ann_vol) if ann_vol > 0 else 0.0,
            "sortino": (mean_r * TRADING_DAYS / dvol) if dvol > 0 else 0.0,
            "max_drawdown": dd,
            "calmar": (ann / dd) if dd > 0 else 0.0,
            "days": days,
        })

    # Trade-level metrics exist only for strategy funds; pair funds switch
    # rather than trade a book, so their trade stats are reported as absent
    # rather than as zero. Zero would rank a pair fund as having lost every
    # trade it never made.
    if kind == "paper_runs":
        tr = conn.execute("""SELECT COUNT(*), COALESCE(SUM(net_pnl_usd),0),
            COALESCE(SUM(costs_usd),0), COALESCE(SUM(CASE WHEN net_pnl_usd>0
            THEN net_pnl_usd ELSE 0 END),0), COALESCE(SUM(CASE WHEN net_pnl_usd<0
            THEN -net_pnl_usd ELSE 0 END),0), COALESCE(SUM(CASE WHEN net_pnl_usd>0
            THEN 1 ELSE 0 END),0) FROM paper_trades WHERE run_id=?""",
            (ref,)).fetchone()
        n_tr, net, costs, gains, losses, wins = tr
        out.update({
            "n_trades": int(n_tr),
            "win_rate": (wins / n_tr) if n_tr else 0.0,
            "profit_factor": (gains / losses) if losses > 0 else None,
            "expectancy_usd": (net / n_tr) if n_tr else 0.0,
            "costs_usd": float(costs),
            "turnover_per_year": (n_tr * 365.0 / out["days"]) if out.get("days") else 0.0,
        })
    else:
        sw = conn.execute("SELECT COALESCE(MAX(switches),0) FROM pair_fund_equity "
                          "WHERE name=?", (ref,)).fetchone()[0]
        out.update({"n_trades": int(sw), "win_rate": None, "profit_factor": None,
                    "expectancy_usd": None, "costs_usd": None,
                    "turnover_per_year": (sw * 365.0 / out["days"])
                    if out.get("days") else 0.0})
    return out


def min_marks(cfg: dict) -> int:
    return int((cfg.get("league") or {}).get("min_rank_marks", 60))


def rankable(m: dict, floor: int) -> tuple:
    """(is_rankable, why_not). A thin sample is stated, never silently scored."""
    if m["n_marks"] < floor:
        need = floor - m["n_marks"]
        return False, (f"{m['n_marks']} of {floor} required marks "
                       f"— about {need} more sessions")
    if m.get("volatility", 0) <= 0:
        return False, "no variation in the equity curve yet"
    return True, ""


# --------------------------------------------------------------- formulas ---
#
# Registered, not hardcoded. Phase 7 asks for the architecture to TEST scoring
# formulas, so every snapshot records which one produced it and changing the
# weighting writes new history rather than rewriting old.

def _f_sharpe_only(m: dict) -> float:
    """The control. A considered formula that cannot beat this adds nothing."""
    return float(m.get("sharpe") or 0.0)


def _f_risk_adjusted(m: dict) -> float:
    """Sharpe, penalised for drawdown and for turnover it has to pay for."""
    s = float(m.get("sharpe") or 0.0)
    dd = float(m.get("max_drawdown") or 0.0)
    turn = float(m.get("turnover_per_year") or 0.0)
    return s * (1.0 - min(dd, 0.9)) - 0.0005 * turn


def _f_calmar(m: dict) -> float:
    """Return per unit of worst loss. Blind to volatility that recovers."""
    return float(m.get("calmar") or 0.0)


FORMULAS = {
    "sharpe_only": _f_sharpe_only,
    "risk_adjusted": _f_risk_adjusted,
    "calmar": _f_calmar,
}
DEFAULT_FORMULA = "risk_adjusted"


# ------------------------------------------------------------- scoreboard ---

def build(conn, cfg: dict, formula: str = DEFAULT_FORMULA) -> list:
    if formula not in FORMULAS:
        raise SystemExit(f"unknown formula {formula!r}; have {sorted(FORMULAS)}")
    init(conn)
    lg.init(conn)
    fn = FORMULAS[formula]
    floor = min_marks(cfg)

    rows = []
    for r in lg.roster(conn):
        if r["state"] == lg.RETIRED:
            continue
        m = metrics(conn, r["strategy_key"], r["source_kind"], r["source_ref"])
        ok, why = rankable(m, floor)
        rows.append({**r, "metrics": m, "rankable": ok, "why_not": why,
                     "score": fn(m) if ok else None})

    ranked = sorted([x for x in rows if x["rankable"]],
                    key=lambda x: -(x["score"] or 0))
    for i, x in enumerate(ranked, 1):
        x["rank"] = i
    for x in rows:
        x.setdefault("rank", None)
    return rows


def snapshot(conn, cfg: dict, formula: str = DEFAULT_FORMULA) -> int:
    """Record the scoreboard. Append-only — a rank is never revised."""
    rows = build(conn, cfg, formula)
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany("""INSERT INTO scoreboard_snapshots (at, formula,
        strategy_key, version, rank, score, rankable, n_marks, metrics)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        [(at, formula, x["strategy_key"], x["version"], x["rank"], x["score"],
          1 if x["rankable"] else 0, x["metrics"]["n_marks"],
          json.dumps(x["metrics"], sort_keys=True, default=str)) for x in rows])
    conn.commit()
    return len(rows)


def render(rows: list, formula: str, floor: int) -> str:
    ranked = [x for x in rows if x["rankable"]]
    un = [x for x in rows if not x["rankable"]]
    L = ["", f"  STRATEGY SCOREBOARD — formula '{formula}'",
         f"  {len(ranked)} ranked, {len(un)} not yet rankable "
         f"(needs {floor} equity marks)", "  " + "-" * 88]
    if ranked:
        L.append(f"  {'#':>2}  {'name':<24}{'score':>9}{'return':>10}"
                 f"{'sharpe':>9}{'maxDD':>8}{'trades':>8}{'marks':>7}")
        for x in ranked:
            m = x["metrics"]
            L.append(f"  {x['rank']:>2}  {x['name'][:23]:<24}{x['score']:>9.3f}"
                     f"{m['cumulative_return']:>9.2%}{m['sharpe']:>9.2f}"
                     f"{m['max_drawdown']:>8.1%}{m.get('n_trades') or 0:>8}"
                     f"{m['n_marks']:>7}")
    else:
        L += ["  NOTHING IS RANKED YET, and that is the correct answer.",
              "",
              "  Every strategy here holds far too short a forward record for a",
              "  Sharpe ratio to mean anything. Ranking them would produce a",
              "  leaderboard of whoever got lucky in their first fortnight, which",
              "  is the decision this league exists to prevent."]
    if un:
        L += ["", "  NOT YET RANKABLE", "  " + "-" * 88,
              f"  {'name':<26}{'return so far':>15}{'marks':>8}   why not"]
        for x in sorted(un, key=lambda y: -y["metrics"]["n_marks"]):
            m = x["metrics"]
            L.append(f"  {x['name'][:25]:<26}{m['cumulative_return']:>14.2%}"
                     f"{m['n_marks']:>8}   {x['why_not']}")
    L += ["", "  Returns shown for unranked strategies are a record, not a score.",
          "  They are far too short to distinguish skill from noise.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--formula", default=DEFAULT_FORMULA,
                    help=f"one of {sorted(FORMULAS)}")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--formulas", action="store_true")
    ap.add_argument("--history", metavar="STRATEGY_KEY")
    a = ap.parse_args()

    if a.formulas:
        print("\n  SCORING FORMULAS (none is final — Phase 7 builds the")
        print("  architecture for testing them, not the answer)")
        for k, f in sorted(FORMULAS.items()):
            mark = "  <- default" if k == DEFAULT_FORMULA else ""
            print(f"    {k:<16}{(f.__doc__ or '').strip().splitlines()[0]}{mark}")
        return 0

    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)

    if a.history:
        print(f"\n  RANK HISTORY — {a.history}")
        for r in conn.execute("""SELECT at, formula, rank, score, rankable, n_marks
            FROM scoreboard_snapshots WHERE strategy_key=? ORDER BY id""",
            (a.history,)):
            print(f"  {r['at']}  {r['formula']:<14}"
                  f"{'rank ' + str(r['rank']) if r['rankable'] else UNRANKED:<12}"
                  f"{r['n_marks']:>4} marks")
        conn.close(); return 0

    rows = build(conn, cfg, a.formula)
    print(render(rows, a.formula, min_marks(cfg)))
    if a.snapshot:
        n = snapshot(conn, cfg, a.formula)
        print(f"  recorded {n} rows to the scoreboard history\n")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
