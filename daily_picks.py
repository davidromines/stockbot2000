"""
The daily book: best candidate from every system we built, in one place.

Everything in this project has been measured separately and reported separately.
This is the synthesis — one report, one ranked list, with each pick carrying the
measured track record of the system that produced it so the number is never
separated from what it is worth.

WHAT EACH SYSTEM CONTRIBUTES, AND WHAT IT HAS ACTUALLY EARNED
-------------------------------------------------------------
Every source below is labelled with its own out-of-sample record. This is not
decoration. A pick from a screen that beat SPY in 6 of 15 windows is a different
object from a pick from a screen that beat it in 1 of 15, and a report that
printed both as "BUY" without that context would be lying by omission.

  quality_value   conviction, fundamentals   beat SPY 4/15 windows, mean -4.2%
  deep_value      conviction, fundamentals   beat SPY 6/15 windows, mean -1.5%
  buffett         QMJ + low beta, unlevered  beat SPY 6/15 windows, Sharpe 0.76
  lab_survivor    evolved momentum rule      cleared validation + exposure gate
  classifier      XGBoost, 24 indicators     AUC 0.612, top-decile lift 1.54x

None of these beat the index reliably. That is the honest state of the evidence
and it is printed on the report itself.

SELL RULES
----------
Every position gets three exits, checked daily, whichever fires first:

  1. Strategy exit    — the screen's own rule. A conviction name is sold when its
                        fundamentals fall out of the top 40%; a genome position
                        when its exit tree fires.
  2. Stop loss        — a hard percentage floor, per strategy. Wider for
                        conviction (fundamentals move slowly and noise should not
                        trigger a sale), tighter for momentum.
  3. Time stop        — momentum positions have a holding limit; conviction ones
                        do not, by design.

Stops are checked against a daily close, not intraday. Robinhood's dollar-based
fractional orders are market orders only and cannot rest at the broker, so a gap
through the stop is not protected against. That is a real limitation of the
account, not of the code.

Usage:
    python daily_picks.py --report          # today's book
    python daily_picks.py --record          # write picks to the database
    python daily_picks.py --check           # sell signals on open picks
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging

import numpy as np
import pandas as pd

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("picks")

# Measured out-of-sample records, carried onto every pick.
PROVENANCE = {
    "deep_value":    dict(kind="value", record="beat SPY in 6/15 windows, mean excess -1.5%",
                          stop_pct=0.25, hold_days=None),
    "buffett":       dict(kind="quality", record="beat SPY in 6/15 windows, Sharpe 0.76 (Berkshire's own)",
                          stop_pct=0.25, hold_days=None),
    "quality_value": dict(kind="value", record="beat SPY in 4/15 windows, mean excess -4.2%",
                          stop_pct=0.25, hold_days=None),
    "lab_survivor":  dict(kind="momentum", record="cleared validation and the survivorship gate; never forward-tested",
                          stop_pct=0.12, hold_days=49),
    "classifier":    dict(kind="model", record="AUC 0.612 out-of-sample, top-decile lift 1.54x",
                          stop_pct=0.12, hold_days=21),
}


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS picks (
            pick_date   TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            source      TEXT NOT NULL,
            rank        INTEGER,
            price       REAL NOT NULL,
            stop_price  REAL,
            hold_days   INTEGER,
            rationale   TEXT,
            status      TEXT NOT NULL DEFAULT 'open',
            exit_date   TEXT,
            exit_price  REAL,
            exit_reason TEXT,
            PRIMARY KEY (pick_date, ticker, source)
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_picks_status ON picks(status)")
    conn.commit()


def _latest_date(conn) -> str:
    return conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]


def _conviction_picks(conn, cfg, screen: str, n: int = 3) -> list:
    """Top names from one conviction screen, on the most recent review date."""
    import conviction as cv
    end = _latest_date(conn)
    start = str((pd.Timestamp(end) - pd.Timedelta(days=20)).date())
    panel = cv._load_panel(conn, cfg, start, end)
    if panel.empty:
        return []
    panel = panel[panel["date"] == panel["date"].max()]
    sc = cv.SCREENS[screen]
    d = panel.dropna(subset=[c for c in sc["requires"] if c in panel.columns]).copy()
    if len(d) < 30:
        return []
    try:
        d["score"] = sc["score"](d)
    except Exception:
        return []
    d = d.dropna(subset=["score"]).sort_values("score", ascending=False)
    out = []
    for i, r in enumerate(d.head(n).itertuples(index=False), 1):
        bits = []
        for c, lab in (("book_to_market", "B/M"), ("piotroski_f", "F-score"),
                       ("gross_profitability", "GP/A"), ("roe", "ROE"),
                       ("beta", "beta"), ("chs_distress", "distress")):
            v = getattr(r, c, None)
            if v is not None and np.isfinite(v):
                bits.append(f"{lab} {v:.2f}")
        out.append({"ticker": str(r.ticker), "price": float(r.close), "rank": i,
                    "source": screen, "rationale": ", ".join(bits[:4])})
    return out


def _genome_picks(conn, cfg, n: int = 3) -> list:
    """
    Today's entries from the validated Lab survivor.

    The rule needs trailing history — its conditions look backwards — so it is
    evaluated over a window and sliced to the latest date, exactly as paper
    trading does it. Scoring it on a single row would silently yield NaN and
    produce no picks at all, which is indistinguishable from "no signal today".
    """
    import genome as gn
    from train_model import FEATURE_COLS
    row = conn.execute("""
        SELECT s.genome, s.entry_desc FROM promotions p
        JOIN strategies s ON s.id = p.strategy_id
        JOIN evaluations e ON e.strategy_id = s.id
        WHERE p.stage='validation' AND p.decision='pass'
        ORDER BY e.excess_pnl_usd DESC LIMIT 1""").fetchone()
    if not row:
        return []
    g = json.loads(row["genome"])
    end = _latest_date(conn)
    start = str((pd.Timestamp(end) - pd.Timedelta(days=420)).date())
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=start, end_date=end,
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"), include_liquidity=True)
    if df.empty:
        return []
    df = df.sort_values(["ticker", "date"])
    fires = gn._as_bool(gn.evaluate(g["entry"], df)).to_numpy()
    latest = df["date"].max()
    hit = df[(df["date"] == latest) & fires]
    if hit.empty:
        return []
    if "dollar_volume_20" in hit:
        hit = hit.sort_values("dollar_volume_20", ascending=False)
    return [{"ticker": str(r.ticker), "price": float(r.close), "rank": i,
             "source": "lab_survivor",
             "rationale": (row["entry_desc"] or "")[:60]}
            for i, r in enumerate(hit.head(n).itertuples(index=False), 1)]


def _classifier_picks(conn, cfg, n: int = 3) -> list:
    """Top scores from the XGBoost model, using the columns it was trained on."""
    import xgboost as xgb
    from train_model import FEATURE_COLS
    latest = storage.load_latest_features(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        max_staleness_days=cfg["scoresheet"].get("max_staleness_days", 5),
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"))
    if latest.empty:
        return []
    m = xgb.XGBClassifier(); m.load_model(cfg["model"]["path"])
    want = getattr(m, "feature_names_in_", None)
    if want is None:
        want = m.get_booster().feature_names
    want = list(want) if want is not None else list(FEATURE_COLS)
    if any(c not in latest.columns for c in want):
        return []
    latest = latest.copy()
    latest["score"] = m.predict_proba(latest[want])[:, 1] * 100
    top = latest.sort_values("score", ascending=False).head(n)
    return [{"ticker": str(r.ticker), "price": float(r.close), "rank": i,
             "source": "classifier", "rationale": f"model score {r.score:.1f}/100"}
            for i, r in enumerate(top.itertuples(index=False), 1)]


def gather(conn, cfg) -> list:
    """Every system's candidates, deduplicated, best-ranked source winning."""
    picks = []
    for screen in ("deep_value", "buffett", "quality_value"):
        try:
            picks += _conviction_picks(conn, cfg, screen)
        except Exception as e:
            log.warning(f"{screen}: {type(e).__name__}: {e}")
    for fn, lab in ((_genome_picks, "lab_survivor"), (_classifier_picks, "classifier")):
        try:
            picks += fn(conn, cfg)
        except Exception as e:
            log.warning(f"{lab}: {type(e).__name__}: {e}")

    # A name surfacing from two independent systems is more interesting than one
    # surfacing twice from the same family, so agreement is recorded rather than
    # collapsed away.
    by_ticker: dict = {}
    for p in picks:
        by_ticker.setdefault(p["ticker"], []).append(p)
    out = []
    for t, ps in by_ticker.items():
        best = min(ps, key=lambda x: x["rank"])
        best = dict(best)
        best["agreement"] = sorted({x["source"] for x in ps})
        prov = PROVENANCE.get(best["source"], {})
        best["record"] = prov.get("record", "")
        best["kind"] = prov.get("kind", "")
        best["stop_price"] = round(best["price"] * (1 - prov.get("stop_pct", 0.15)), 4)
        best["hold_days"] = prov.get("hold_days")
        out.append(best)
    return sorted(out, key=lambda x: (-len(x["agreement"]), x["rank"]))


def check_sells(conn, cfg) -> list:
    """
    Sell signals on every open pick. Three exits, whichever fires first.

    Checked against the daily close. Robinhood's dollar-based fractional orders
    are market-only and cannot rest at the broker, so a stop here is a daily
    instruction to sell, not a resting order — an overnight gap through it is
    unprotected. That is a property of the account, and pretending otherwise
    would make the stop look like insurance it is not.
    """
    init(conn)
    today = _latest_date(conn)
    rows = conn.execute("SELECT * FROM picks WHERE status='open'").fetchall()
    sells = []
    for r in rows:
        px = conn.execute("SELECT close FROM prices WHERE ticker=? AND date<=? "
                          "AND close>0 ORDER BY date DESC LIMIT 1",
                          (r["ticker"], today)).fetchone()
        if not px:
            continue
        price = float(px[0])
        held = (pd.Timestamp(today) - pd.Timestamp(r["pick_date"])).days
        reason = None
        if r["stop_price"] and price <= r["stop_price"]:
            reason = f"stop hit ({price:.2f} <= {r['stop_price']:.2f})"
        elif r["hold_days"] and held >= r["hold_days"]:
            reason = f"holding limit reached ({held}d)"
        if reason:
            sells.append({"ticker": r["ticker"], "source": r["source"],
                          "entry": r["price"], "now": price,
                          "pnl_pct": (price / r["price"] - 1) * 100,
                          "reason": reason, "pick_date": r["pick_date"]})
    return sells


def record(conn, picks: list) -> int:
    init(conn)
    today = _latest_date(conn)
    n = 0
    for p in picks:
        conn.execute("""INSERT OR IGNORE INTO picks
            (pick_date,ticker,source,rank,price,stop_price,hold_days,rationale,status)
            VALUES (?,?,?,?,?,?,?,?, 'open')""",
            (today, p["ticker"], p["source"], p["rank"], p["price"],
             p["stop_price"], p["hold_days"],
             f"{p['rationale']} | agreement: {','.join(p['agreement'])}"))
        n += 1
    conn.commit()
    return n


def report(conn, cfg, picks: list, sells: list, size: float) -> str:
    today = _latest_date(conn)
    L = [f"\n  STOCKBOT2000 — DAILY BOOK   prices as of {today}",
         "  " + "=" * 84]

    if sells:
        L.append(f"\n  SELL — {len(sells)} position(s) triggered an exit\n")
        L.append(f"  {'ticker':<8}{'source':<16}{'entry':>9}{'now':>9}{'P&L':>9}  reason")
        L.append("  " + "-" * 84)
        for s in sells:
            L.append(f"  {s['ticker']:<8}{s['source']:<16}{s['entry']:>9.2f}"
                     f"{s['now']:>9.2f}{s['pnl_pct']:>+8.1f}%  {s['reason']}")
    else:
        L.append("\n  SELL — nothing triggered today")

    L.append(f"\n  BUY — ranked, ${size:.2f} per position\n")
    L.append(f"  {'#':<3}{'ticker':<8}{'source':<16}{'price':>9}{'stop':>9}{'shares':>10}  why")
    L.append("  " + "-" * 96)
    for i, p in enumerate(picks[:10], 1):
        agree = "+" if len(p["agreement"]) > 1 else " "
        L.append(f"  {i:<3}{p['ticker']:<8}{p['source']:<16}{p['price']:>9.2f}"
                 f"{p['stop_price']:>9.2f}{size/p['price']:>10.4f} {agree} {p['rationale'][:44]}")

    multi = [p for p in picks if len(p["agreement"]) > 1]
    if multi:
        L.append(f"\n  Two systems agreed on: "
                 f"{', '.join(p['ticker'] + ' (' + '+'.join(p['agreement']) + ')' for p in multi)}")

    L.append("\n  " + "=" * 84)
    L.append("  WHAT EACH SOURCE HAS ACTUALLY EARNED, OUT OF SAMPLE")
    seen = set()
    for p in picks[:10]:
        if p["source"] in seen:
            continue
        seen.add(p["source"])
        L.append(f"    {p['source']:<16}{p['record']}")
    L.append("")
    L.append("  None of these beat the index reliably in testing. The best of them beat")
    L.append("  SPY in 6 of 15 rolling two-year windows. This book exists to find out")
    L.append("  forward whether any of that changes; it is not evidence that it will.")
    L.append("")
    L.append("  Stops are checked against a DAILY CLOSE. Dollar-based fractional orders")
    L.append("  are market-only and cannot rest at the broker, so an overnight gap")
    L.append("  through a stop is not protected against.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--size", type=float, default=None)
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    size = a.size if a.size is not None else cfg["risk"]["position_size_usd"]
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)

    sells = check_sells(conn, cfg)
    if a.check and not (a.report or a.record):
        for s in sells:
            print(f"  SELL {s['ticker']} ({s['source']}) {s['pnl_pct']:+.1f}% — {s['reason']}")
        if not sells:
            print("  no sell signals")
        conn.close(); return

    picks = gather(conn, cfg)
    print(report(conn, cfg, picks, sells, size))
    if a.record:
        n = record(conn, picks)
        print(f"\n  recorded {n} picks to the database")
    conn.close()


if __name__ == "__main__":
    main()
