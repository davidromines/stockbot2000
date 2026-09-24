"""
The authoritative P&L. Phase 13 step H2; Addendum B §B18.

ONE DEFINITION, EVERY FUND
--------------------------
    equity  =  capital  +  gross P&L  -  costs
    costs   =  costs already paid  +  the round trip every open position
               would pay to close at its latest mark

Liquidation basis. A fund's equity is what it would hold if it closed
everything at the mark, so no fund looks richer for not having traded yet.

WHY THIS EXISTS
---------------
On 2026-09-24 the forward funds were found to disagree about when a trade is
charged:

- paper funds charged the whole round trip only when a position CLOSED, so
  ~100 open positions carried no cost at all;
- pair funds charged a switch but never the opening buy, so a fund that had
  not yet switched reported gross == net;
- the Value Fund charged nothing.

Every one of those inflates equity, and inconsistently, so a ranking across
them would have ranked the accounting rather than the strategies.

NOTHING IS OVERWRITTEN
----------------------
The engines' own curves (`paper_equity`, `pair_fund_equity`,
`value_fund_equity`, `crypto_fund_equity`) are left exactly as recorded and
are reported here as `equity_original`. The restated figure sits beside it in
`fund_accounting`, tagged with `ACCOUNTING_VERSION`. A future change to the
model mints a new version rather than rewriting old rows.

RECONCILIATION
--------------
For each fund the engine's own equity must equal
`capital + gross - costs_realized`: the original curve and this module's
gross must agree on everything the engine did charge. A difference is split
into its known causes, and only what remains is an ACCOUNTING_PROBLEM:

- cash drift: engine cash vs its own ledger (capital - open cost basis + net
  of closed trades). Caused by a repeated step whose INSERT OR REPLACE
  overwrote a held position (fixed in paper_trading.py 2026-09-24).
- mark difference: engine position value vs shares x last real close. Caused
  by marking positions with no bar that day at ENTRY price (fixed the same
  day; they now mark at their last real close).

EXPLAINED means the original curve is wrong for identified reasons; the
restated figure, built from the ledger and real closes, is authoritative.

Usage:
    python accounting.py --restate          # compute and store today's statement
    python accounting.py --report           # print the latest statement
    python accounting.py --snapshot PATH    # also write the statement as JSON
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone

import costs as costs_mod
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("accounting")

ACCOUNTING_VERSION = 1
TOLERANCE_USD = 0.05          # engines mark at slightly different closes; cents, not dollars


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fund_accounting (
            as_of            TEXT NOT NULL,
            fund_kind        TEXT NOT NULL,
            fund_id          TEXT NOT NULL,
            label            TEXT,
            capital_usd      REAL NOT NULL,
            gross_usd        REAL NOT NULL,
            costs_realized   REAL NOT NULL,
            costs_open       REAL NOT NULL,
            costs_usd        REAL NOT NULL,
            net_usd          REAL NOT NULL,
            equity_original  REAL,
            equity_restated  REAL NOT NULL,
            open_positions   INTEGER,
            closed_trades    INTEGER,
            cost_basis       TEXT NOT NULL,        -- 'modeled' | 'measured' | 'mixed'
            reconciled       INTEGER NOT NULL,     -- 1 = original curve agrees
            recon_diff_usd   REAL,
            recon_status     TEXT,                 -- RECONCILED | EXPLAINED | ACCOUNTING_PROBLEM
            cash_drift_usd   REAL,                 -- engine cash vs its own trade ledger
            mark_diff_usd    REAL,                 -- engine marks vs last real closes
            unexplained_usd  REAL,
            note             TEXT,
            accounting_version INTEGER NOT NULL,
            computed_at      TEXT NOT NULL,
            PRIMARY KEY (as_of, fund_kind, fund_id, accounting_version)
        )""")
    conn.commit()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _mark(conn, ticker: str, as_of: str):
    """Close and 20-day dollar volume at or before as_of. None if unpriced."""
    p = conn.execute("SELECT close FROM prices WHERE ticker=? AND date<=? "
                     "ORDER BY date DESC LIMIT 1", (ticker, as_of)).fetchone()
    f = conn.execute("SELECT dollar_volume_20 FROM features WHERE ticker=? AND date<=? "
                     "ORDER BY date DESC LIMIT 1", (ticker, as_of)).fetchone()
    return (p[0] if p else None), (f[0] if f else None)


def _row(**kw) -> dict:
    kw["costs_usd"] = kw["costs_realized"] + kw["costs_open"]
    kw["net_usd"] = kw["gross_usd"] - kw["costs_usd"]
    kw["equity_restated"] = kw["capital_usd"] + kw["net_usd"]
    orig = kw.get("equity_original")
    kw.setdefault("cash_drift_usd", 0.0)
    kw.setdefault("mark_diff_usd", 0.0)
    if orig is None:
        kw["reconciled"], kw["recon_diff_usd"], kw["unexplained_usd"] = 1, None, 0.0
        kw["recon_status"] = "RECONCILED"
        return kw
    diff = orig - (kw["capital_usd"] + kw["gross_usd"] - kw["costs_realized"])
    kw["recon_diff_usd"] = diff
    kw["unexplained_usd"] = diff - kw["cash_drift_usd"] - kw["mark_diff_usd"]
    kw["reconciled"] = 1 if abs(diff) <= TOLERANCE_USD else 0
    if kw["reconciled"]:
        kw["recon_status"] = "RECONCILED"
    elif abs(kw["unexplained_usd"]) <= TOLERANCE_USD:
        # The original curve is wrong for identified reasons. The restated
        # figure is built from the trade ledger and today's closes, so it is
        # the authoritative one; the original stays on record as it was.
        kw["recon_status"] = "EXPLAINED"
    else:
        kw["recon_status"] = "ACCOUNTING_PROBLEM"
    return kw


# --------------------------------------------------------------------------- #
# per fund kind
# --------------------------------------------------------------------------- #
def paper_funds(conn, cm) -> list:
    out = []
    for r in conn.execute("SELECT * FROM paper_runs WHERE status='open'"):
        e = conn.execute("SELECT date, equity_usd, cash_usd, positions_usd FROM paper_equity "
                         "WHERE run_id=? ORDER BY date DESC LIMIT 1", (r["run_id"],)).fetchone()
        if not e:
            continue
        as_of = e["date"]
        t = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(gross_pnl_usd),0) g, "
                         "COALESCE(SUM(costs_usd),0) k FROM paper_trades WHERE run_id=?",
                         (r["run_id"],)).fetchone()
        gross_open = costs_open = basis_open = mtm_open = 0.0
        n_open = unpriced = 0
        net_closed = conn.execute("SELECT COALESCE(SUM(net_pnl_usd),0) FROM paper_trades "
                                  "WHERE run_id=?", (r["run_id"],)).fetchone()[0]
        for p in conn.execute("SELECT ticker, entry_price, shares FROM paper_positions "
                              "WHERE run_id=?", (r["run_id"],)):
            n_open += 1
            basis_open += p["shares"] * p["entry_price"]
            px, dv = _mark(conn, p["ticker"], as_of)
            if px is None:
                unpriced += 1
                px = p["entry_price"]          # stated in the note, never silent
            gross_open += p["shares"] * (px - p["entry_price"])
            mtm_open += p["shares"] * px
            costs_open += float(cm.round_trip(p["shares"] * px, dv, p["shares"]))
        # Decompose any disagreement with the engine's own curve. Cash drift:
        # engine cash vs capital - open cost basis + net of closed trades.
        # Mark difference: engine's position value vs shares x last real close.
        cash_drift = float(e["cash_usd"]) - (float(r["capital_usd"]) - basis_open + net_closed)
        mark_diff = float(e["positions_usd"]) - mtm_open
        out.append(_row(
            cash_drift_usd=cash_drift, mark_diff_usd=mark_diff,
            as_of=as_of, fund_kind="paper", fund_id=r["run_id"],
            label=r["label"] or r["name"], capital_usd=float(r["capital_usd"]),
            gross_usd=float(t["g"]) + gross_open, costs_realized=float(t["k"]),
            costs_open=costs_open, equity_original=float(e["equity_usd"]),
            open_positions=n_open, closed_trades=int(t["n"]), cost_basis="modeled",
            note=(f"{unpriced} open position(s) unpriced, marked at entry"
                  if unpriced else None)))
    return out


class _NoCost:
    enabled = False

    def round_trip(self, *a, **k):
        return 0.0


def pair_funds(conn, cm) -> list:
    """Gross by replaying the curve with costs off; the opening buy is charged."""
    import pair_funds as pf
    from erx_momentum import METHODS, run_switch
    out = []
    for r in conn.execute("SELECT * FROM pair_funds WHERE status='open'"):
        e = conn.execute("SELECT date, equity_usd, switches FROM pair_fund_equity "
                         "WHERE name=? ORDER BY date DESC LIMIT 1", (r["name"],)).fetchone()
        if not e:
            continue
        w = pf.load_pair(conn, r["bull"], r["bear"], r["signal"], r["started_on"], e["date"])
        warm = pf.load_pair(conn, r["bull"], r["bear"], r["signal"], "2005-01-01", e["date"])
        fn, _ = METHODS[r["method"]]
        sig = fn(warm["close_XLE"], r["param"]).reindex(w.index)
        cap = float(r["capital_usd"])
        g = run_switch(w, sig, _NoCost(), capital=cap, min_hold=int(r["min_hold"]))
        n = run_switch(w, sig, cm, capital=cap, min_hold=int(r["min_hold"]))
        gross = float(g["final"]) - cap
        switch_costs = float(g["final"]) - float(n["final"])   # what the engine charged
        # The opening buy and the eventual exit of the current holding: one
        # round trip on today's equity. ETFs this liquid carry the same
        # dollar-volume assumption the engine uses for a switch.
        open_cost = float(cm.round_trip(float(g["final"]), dollar_volume=20_000_000))
        out.append(_row(
            as_of=e["date"], fund_kind="pair", fund_id=r["name"], label=r["label"],
            capital_usd=cap, gross_usd=gross, costs_realized=switch_costs,
            costs_open=open_cost, equity_original=float(e["equity_usd"]),
            open_positions=1, closed_trades=int(e["switches"]), cost_basis="modeled"))
    return out


def value_fund(conn, cm) -> list:
    v = conn.execute("SELECT * FROM value_fund").fetchone()
    if not v:
        return []
    e = conn.execute("SELECT date, equity_usd FROM value_fund_equity WHERE name=? "
                     "ORDER BY date DESC LIMIT 1", (v["name"],)).fetchone()
    as_of = e["date"] if e else v["started_on"]
    closed = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(net_pnl_usd),0) g "
                          "FROM value_fund_trades WHERE name=?", (v["name"],)).fetchone()
    gross_open = costs_open = 0.0
    n_open = 0
    for p in conn.execute("SELECT ticker, entry_price, shares FROM value_fund_positions "
                          "WHERE name=?", (v["name"],)):
        n_open += 1
        px, dv = _mark(conn, p["ticker"], as_of)
        px = px if px is not None else p["entry_price"]
        gross_open += p["shares"] * (px - p["entry_price"])
        costs_open += float(cm.round_trip(p["shares"] * px, dv, p["shares"]))
    # The Value Fund's closed trades were booked with no costs, so their
    # recorded P&L is gross; their costs are charged here, on entry notional.
    closed_costs = 0.0
    for t in conn.execute("SELECT ticker, entry_price, shares, opened_on FROM "
                          "value_fund_trades WHERE name=?", (v["name"],)):
        _, dv = _mark(conn, t["ticker"], t["opened_on"])
        closed_costs += float(cm.round_trip(t["shares"] * t["entry_price"], dv, t["shares"]))
    return [_row(
        as_of=as_of, fund_kind="value", fund_id=v["name"], label="Value Fund",
        capital_usd=float(v["capital_usd"]), gross_usd=float(closed["g"]) + gross_open,
        costs_realized=closed_costs, costs_open=costs_open,
        equity_original=(float(e["equity_usd"]) + closed_costs) if e else None,
        open_positions=n_open, closed_trades=int(closed["n"]), cost_basis="modeled",
        note="engine charges no costs; all costs here are added by this model")]


def crypto_fund(conn) -> list:
    out = []
    for f in conn.execute("SELECT * FROM crypto_fund"):
        t = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(gross_usd),0) g, "
                         "COALESCE(SUM(fees_usd),0) k FROM crypto_fund_trades WHERE name=?",
                         (f["name"],)).fetchone()
        e = conn.execute("SELECT * FROM crypto_fund_equity WHERE name=? "
                         "ORDER BY date DESC LIMIT 1", (f["name"],)).fetchone()
        unreal = float(e["unrealised_usd"]) if e else 0.0
        n_open = int(e["open_positions"]) if e else 0
        # Open grid positions: the crypto engine charges the entry fee when a
        # level fills, so only the exit fee is outstanding.
        import crypto_grid
        open_fee = crypto_grid.TAKER_FEE * max(unreal, 0.0) if n_open else 0.0
        out.append(_row(
            as_of=e["date"] if e else "", fund_kind="crypto", fund_id=f["name"],
            label="Crypto Grid", capital_usd=float(f["capital_usd"]),
            gross_usd=float(t["g"]) + unreal, costs_realized=float(t["k"]),
            costs_open=open_fee, equity_original=float(e["equity_usd"]) if e else None,
            open_positions=n_open, closed_trades=int(t["n"]), cost_basis="modeled",
            note=("open-position exit fee approximated on unrealised value"
                  if n_open else None)))
    return out


# --------------------------------------------------------------------------- #
def statement(conn, cfg) -> list:
    cm = costs_mod.CostModel(cfg)
    rows = paper_funds(conn, cm) + pair_funds(conn, cm) + value_fund(conn, cm) + crypto_fund(conn)
    return rows


def store(conn, rows: list) -> int:
    init(conn)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cols = ("as_of fund_kind fund_id label capital_usd gross_usd costs_realized "
            "costs_open costs_usd net_usd equity_original equity_restated "
            "open_positions closed_trades cost_basis reconciled recon_diff_usd "
            "recon_status cash_drift_usd mark_diff_usd unexplained_usd note").split()
    for r in rows:
        vals = [r.get(c) for c in cols] + [ACCOUNTING_VERSION, now]
        conn.execute(f"INSERT OR REPLACE INTO fund_accounting ({','.join(cols)},"
                     f"accounting_version, computed_at) VALUES ({','.join('?' * (len(cols) + 2))})",
                     vals)
    conn.commit()
    return len(rows)


def totals(rows: list) -> dict:
    out = {}
    for key in sorted({r["fund_kind"] for r in rows}) + ["ALL"]:
        rs = rows if key == "ALL" else [r for r in rows if r["fund_kind"] == key]
        out[key] = {k: round(sum(r[k] for r in rs), 2)
                    for k in ("capital_usd", "gross_usd", "costs_usd", "net_usd")}
        out[key]["funds"] = len(rs)
    return out


def render(rows: list) -> str:
    L = ["", "  FUND ACCOUNTING  (liquidation basis — accounting v%d)" % ACCOUNTING_VERSION,
         "  equity = capital + gross - costs;  costs = paid + round trip on open positions",
         "  " + "-" * 78,
         f"  {'fund':<28}{'kind':<7}{'gross':>9}{'costs':>9}{'net':>9}"
         f"{'orig eq':>10}{'restated':>10}  recon"]
    for r in sorted(rows, key=lambda r: (r["fund_kind"], -r["net_usd"])):
        L.append(f"  {r['label'][:27]:<28}{r['fund_kind']:<7}{r['gross_usd']:>+9.2f}"
                 f"{-r['costs_usd']:>+9.2f}{r['net_usd']:>+9.2f}"
                 f"{(r['equity_original'] or 0):>10.2f}{r['equity_restated']:>10.2f}  "
                 + ("ok" if r["reconciled"] else
                    f"{r['recon_status'][:9]} cash {r['cash_drift_usd']:+.2f} mark {r['mark_diff_usd']:+.2f}"
                    + (f" ?? {r['unexplained_usd']:+.2f}" if r["recon_status"] == "ACCOUNTING_PROBLEM" else "")))
    L.append("  " + "-" * 78)
    for k, t in totals(rows).items():
        L.append(f"  {k.upper():<28}{t['funds']:>3} funds  gross {t['gross_usd']:+.2f}  "
                 f"costs {-t['costs_usd']:+.2f}  net {t['net_usd']:+.2f}")
    ex = [r for r in rows if r["recon_status"] == "EXPLAINED"]
    bad = [r for r in rows if r["recon_status"] == "ACCOUNTING_PROBLEM"]
    L.append("")
    L.append(f"  RECONCILIATION: {len(rows) - len(ex) - len(bad)} agree, "
             f"{len(ex)} differ for identified reasons (original curve kept, restated "
             f"figure authoritative), {len(bad)} ACCOUNTING_PROBLEM")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--restate", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--snapshot")
    a = ap.parse_args()
    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    conn.row_factory = sqlite3.Row
    rows = statement(conn, cfg)
    if a.restate:
        store(conn, rows)
    print(render(rows))
    if a.snapshot:
        with open(a.snapshot, "w") as fh:
            json.dump({"accounting_version": ACCOUNTING_VERSION, "rows": rows,
                       "totals": totals(rows)}, fh, indent=1, default=str)
    conn.close()
    return 0 if not any(r["recon_status"] == "ACCOUNTING_PROBLEM" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
