"""
The crypto order slate. Phase 12, item 42.

What the crypto paper fund's strategy says to do NOW, as orders a person can
place — each one passed through the existing kill switches and risk engine
first, exactly as the equity slate is.

WHERE THE ORDERS COME FROM
---------------------------
The same engine and the same state as the paper fund. A person mirroring this
slate reproduces the fund; a slate derived by a second route would be a second
strategy that merely shares a name. So:

  * an OPEN grid in the fund produces its resting orders — the next grid level
    to buy, the take-profit, and the stop — at the prices `simulate()` would
    use for them;
  * a pair with NO open grid, whose latest CLOSED bar meets the entry rule,
    produces a BUY of the first grid level at the next bar's open.

The second case is checked separately because `simulate()` cannot see it: a
signal on the newest closed bar has no following bar yet to fill on.

ROUTING
-------
Kill switches first — checking them last is how a halted system still builds a
slate someone might act on. Then each order goes to `RiskEngine.validate`,
which carries crypto-specific floors (see the `crypto:` block in
`config/risk.yaml`) and the `allow_crypto` operator switch. The verdict is
written next to every order, approved or not, so a rejection says which gate
stopped it rather than producing a silently shorter list.

Output: `data/crypto_slate.txt` for a person, `data/crypto_slate.json` for
reconciliation.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import broker as bk
import crypto_fund as cf
import crypto_grid as cg
import killswitch
import risk_engine as re_
import signals as sg
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("corders")

SLATE_TXT = Path("data/crypto_slate.txt")
SLATE_JSON = Path("data/crypto_slate.json")
STRATEGY = "crypto_grid:social:sets_machine"


def _bars(conn, symbol: str, interval: str):
    rows = conn.execute(
        "SELECT open_time, open, high, low, close FROM crypto_prices "
        "WHERE symbol=? AND interval=? ORDER BY open_time",
        (symbol, interval)).fetchall()
    if not rows:
        return None
    return (np.array([r[0] for r in rows], dtype="int64"),
            np.array([[r[1], r[2], r[3], r[4]] for r in rows], dtype="float64"))


def candidates(conn) -> list:
    """Orders the fund's strategy implies right now. Reads only."""
    s = cf.status(conn)
    if not s.get("exists"):
        return []
    f = s["fund"]
    g = json.loads(f["strategy"])
    symbols = json.loads(f["symbols"])
    budget = f["capital_usd"] / len(symbols)
    unit = budget / sum(g["size_mult"] ** k for k in range(g["levels"]))
    open_by_sym = {o["symbol"]: json.loads(o["state"]) for o in s["open"]}
    out = []

    for sym in symbols:
        st = open_by_sym.get(sym)
        if st:
            fills = st["fills"]
            base = fills[0][0]
            k = len(fills)
            deepest = base * (1 - g["spacing"] * g["levels"])
            if k < g["levels"]:
                lvl = base * (1 - g["spacing"] * k)
                out.append({"symbol": sym, "action": "BUY",
                            "notional": unit * g["size_mult"] ** k,
                            "limit_price": lvl, "kind": f"grid level {k + 1}",
                            "reason": f"open grid: next level at {lvl:,.4f}"})
            out.append({"symbol": sym, "action": "SELL",
                        "quantity": st["qty"],
                        "limit_price": st["avg"] * (1 + g["take_profit"]),
                        "kind": "take-profit",
                        "reason": f"take-profit {g['take_profit']:.0%} over "
                                  f"average fill {st['avg']:,.4f}"})
            out.append({"symbol": sym, "action": "SELL",
                        "quantity": st["qty"],
                        "limit_price": deepest * (1 - g["stop"]),
                        "kind": "stop",
                        "reason": f"stop {g['stop']:.0%} below the deepest level"})
            continue

        b = _bars(conn, sym, f["interval"])
        if b is None:
            continue
        ts, a = b
        c = a[:, 3]
        ref = cg._ref(c, g["lookback"])
        i = len(c) - 1
        if i < g["lookback"] or not np.isfinite(ref[i]):
            continue
        # Only a bar that closed after the fund opened may signal — the same
        # forward-only rule the fund's own replay applies.
        if int(ts[i]) < int(f["started_ts"]):
            continue
        if c[i] <= ref[i] * (1 - g["entry_drop"]):
            out.append({"symbol": sym, "action": "BUY", "notional": unit,
                        "limit_price": None, "kind": "grid entry",
                        "reason": f"close {c[i]:,.4f} is {1 - c[i] / ref[i]:.2%} "
                                  f"below its {g['lookback']}-bar mean "
                                  f"(entry at {g['entry_drop']:.0%})"})
    return out


def route(conn, cands: list) -> dict:
    """Kill switches, then the risk engine. Every verdict is kept."""
    killswitch.init(conn)
    sim = bk.CryptoSimulatedBroker(conn=conn, cash=100.0)
    s = cf.status(conn)
    equity = s.get("equity", 100.0) if s.get("exists") else 100.0
    # The portfolio in the shape RiskEngine reads. The first version passed
    # `cash` where the sizer reads `buying_power`, so every order was sized to
    # $0.00 and rejected as too small — a wrong key that looked like a limit.
    # Buying power is equity less what open grids already have deployed.
    positions, deployed = {}, 0.0
    for o in s.get("open", []):
        st = json.loads(o["state"])
        positions[o["symbol"]] = {"quantity": st["qty"],
                                  "value": st["qty"] * st["last_close"]}
        deployed += st["deployed_usd"]
    portfolio = {"equity": equity, "buying_power": max(equity - deployed, 0.0),
                 "positions": positions, "daily_pnl": 0.0}
    engine = re_.RiskEngine()
    # Reconciled means the book matches its source of truth. For a paper fund
    # the book IS the fund's own replay, so it counts as reconciled only when
    # it was stepped this session — a fund not stepped today is exactly the
    # stale book the switch exists to halt on. Passing nothing would halt
    # every run forever; passing True unconditionally would defeat the switch.
    last = (s.get("fund") or {}).get("last_step") or ""
    reconciled = last[:10] == datetime.now(timezone.utc).date().isoformat()
    verdict = killswitch.check(conn, portfolio, engine.L, reconciled=reconciled)
    halted = not getattr(verdict, "trading_allowed", False)
    session = datetime.now(timezone.utc).date().isoformat()

    routed = []
    for cnd in cands:
        sig = sg.Signal(symbol=cnd["symbol"], action=cnd["action"],
                        strategy=STRATEGY, reason=cnd["reason"],
                        asset_type="crypto", session=session,
                        notional_value=cnd.get("notional"),
                        quantity=cnd.get("quantity"))
        q = sim.get_quote(cnd["symbol"])
        if halted:
            ok, why = False, ["kill switch: " + "; ".join(getattr(verdict, "reasons", []))]
        else:
            rr = engine.validate(sig, portfolio, q, {})
            ok = bool(rr.approved)
            why = list(getattr(rr, "reasons", []) or [])
        routed.append({**cnd, "signal_id": sig.signal_id, "approved": ok,
                       "why": why, "price": (q or {}).get("price")})
    return {"session": session, "halted": halted, "orders": routed}


def write(result: dict) -> tuple:
    SLATE_TXT.parent.mkdir(parents=True, exist_ok=True)
    SLATE_JSON.write_text(json.dumps(result, indent=2, default=str))
    L = [f"CRYPTO SLATE  {result['session']}", "=" * 60, ""]
    if not result["orders"]:
        L += ["No orders. No open grid needs attention and no pair's latest",
              "closed bar met the entry rule."]
    for o in result["orders"]:
        size = (f"${o['notional']:,.2f}" if o.get("notional")
                else f"{o['quantity']:.8f} units")
        px = (f" @ {o['limit_price']:,.4f}" if o.get("limit_price")
              else " at market, next bar")
        mark = "APPROVED" if o["approved"] else "REJECTED"
        L.append(f"{mark:<9}{o['action']:<5}{o['symbol']:<10}{size:>18}{px}")
        L.append(f"         {o['kind']}: {o['reason']}")
        for w in o["why"]:
            L.append(f"         - {w}")
        L.append("")
    L += ["=" * 60,
          "Place approved orders yourself; fills are reconciled on the next run."]
    SLATE_TXT.write_text("\n".join(L) + "\n")
    return SLATE_TXT, SLATE_JSON


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    cf.init(conn)
    r = route(conn, candidates(conn))
    txt, js = write(r)
    print("\n" + txt.read_text())
    print(f"  written to {txt} and {js}\n")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
