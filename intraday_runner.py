"""
Intraday Momentum Runner (Addendum G): the service that runs two of the five slots.

Everything that moves money goes through the EXISTING layers: ExecutionEngine -> RiskEngine -> kill switches ->
LiveBroker, the `slot_trades` ledger, `orders`, reconciliation, notify. This module adds the loop around them.

  stage      config.yaml `intraday.stage`:  OFF (does nothing) | SHADOW (scans and logs signals, no orders) | LIVE
             LIVE also needs config/risk.yaml `allow_intraday: true`, `execution_mode: LIVE`, and no kill switch.
  slots      config.yaml `intraday.slots` (also `slots.intraday_slots`, which hides them from the medium-term machinery
             and from slot_trader). `--assign` records the ASSIGN rows once; the medium-term holders there are released.
  each tick  (poll_every_s, default 15 s)
               1. manage open positions: fresh Robinhood quote -> intraday_manager.Manager.tick (stops, flatten, health)
               2. every scan_every_s inside the entry window: 1-minute bars for ~200 liquid names (yfinance, stored in
                  minute_bars), intraday_momentum.scan, log every qualifying signal, enter the best for a free slot
  limits     entries per session, simultaneous positions, daily loss (realised + unrealised), consecutive order failures,
             one position per symbol per session (the signal id is session-scoped), data freshness, reconciliation,
             kill switch. The existing account-wide limits stay authoritative in the risk engine.
  state      every position is persisted after every tick (`intraday_state`); a restart rebuilds it from the ledger and the
             stored minute bars and reconciles any working exit with the broker before sending another order.

    ./venv/bin/python intraday_runner.py --assign      record the slot assignments (idempotent)
    ./venv/bin/python intraday_runner.py --status
    ./venv/bin/python intraday_runner.py --serve       run until the close (cron starts it; flock keeps one instance)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
import time as _time
from datetime import datetime, time, timedelta, timezone

import pandas as pd

import intraday_manager as im
import intraday_momentum as mom
import intraday_stops as st
import quotes as qt
import signals as sg
from universe import load_config

log = logging.getLogger("intraday")
NY = st.NY
KEY = "intraday:momentum_runner"

DEFAULTS = {
    "stage": "OFF", "slots": [3, 5], "position_dollars": 20.0,
    "max_entries_per_session": 3, "max_simultaneous": 2,
    "max_daily_loss_dollars": 2.0, "max_loss_per_trade_dollars": 0.50,
    "entry_start": "09:50", "entry_end": "14:30", "scan_every_s": 60, "poll_every_s": 15,
    "max_price_drift": 0.005, "max_order_failures": 3,
    "universe_size": 200, "min_dollar_volume": 5e7, "min_market_cap": 2e9,
    "stop": {"mode": "pct", "initial_pct": 1.0, "trail_pct": 1.0, "max_hold_minutes": 60, "flatten_hhmm": "15:45"},
}


def settings(cfg: dict, block: str = "intraday") -> dict:
    s = {**DEFAULTS, **((cfg or {}).get(block) or {})}
    s["stop"] = {**DEFAULTS["stop"], **(((cfg or {}).get(block) or {}).get("stop") or {})}
    return s


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS intraday_runner_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, session TEXT NOT NULL, ticker TEXT NOT NULL,
        score REAL, features TEXT NOT NULL, action TEXT NOT NULL, note TEXT, calibrated INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS intraday_state (
        slot_id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, state TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS intraday_heartbeat (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, session TEXT NOT NULL, stage TEXT, scanned INTEGER,
        candidates INTEGER, open_positions INTEGER, entries_today INTEGER, note TEXT)""")
    conn.commit()


# --- reserved slots ------------------------------------------------------------------------------------------
def slots_of(cfg: dict, block: str = "intraday") -> list:
    return [int(x) for x in (settings(cfg, block).get("slots") or [])]


def assign(conn, cfg: dict, actor: str = "owner 2026-10-15", block: str = "intraday", key: str = KEY) -> list:
    """Hand the configured slots to a Runner. Idempotent. The previous holders there are RELEASED; slot_trader's
    next pass sells their positions ('slot released or reassigned') exactly as it does for any reassignment."""
    import slots
    slots.init(conn)
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur, done = slots.current(conn, cfg), []
    for sl in slots_of(cfg, block):
        h = cur.get(sl)
        if h and h["strategy_key"] == key:
            continue
        if h:
            conn.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, reason) "
                         "VALUES (?,?,?,?,?,?,?,?)", (at, sl, "RELEASE", h["strategy_key"], h["version"], None, "LIVE",
                                                      f"reserved for {key} ({actor})"))
        conn.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, reason, evidence) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", (at, sl, "ASSIGN", key, 1, settings(cfg, block)["position_dollars"], "LIVE",
                                                    f"{key} v0 ({actor})", json.dumps({"stage": settings(cfg, block)["stage"]})))
        done.append(sl)
    conn.commit()
    return done


# --- gates (pure) --------------------------------------------------------------------------------------------
def in_window(ny: datetime, s: dict) -> bool:
    h0, m0 = (int(x) for x in s["entry_start"].split(":"))
    h1, m1 = (int(x) for x in s["entry_end"].split(":"))
    t = ny.time()
    return time(h0, m0) <= t <= time(h1, m1)


def entry_gate(s: dict, ny: datetime, entries_today: int, open_n: int, daily_pnl: float, failures: int,
               stage_live: bool, kill: str | None, halted: str | None) -> tuple:
    """(allowed, reason). Every limit the plan lists for NEW entries; exits are never gated by these."""
    if not stage_live:
        return False, "stage is not LIVE"
    if kill:
        return False, f"kill switch: {kill}"
    if halted:
        return False, halted
    if not in_window(ny, s):
        return False, "outside the entry window"
    if entries_today >= s["max_entries_per_session"]:
        return False, f"{entries_today} entries already today (cap {s['max_entries_per_session']})"
    if open_n >= s["max_simultaneous"]:
        return False, f"{open_n} intraday positions open (cap {s['max_simultaneous']})"
    if daily_pnl <= -abs(s["max_daily_loss_dollars"]):
        return False, f"intraday daily loss ${daily_pnl:.2f} at the ${s['max_daily_loss_dollars']:.2f} limit"
    if failures >= s["max_order_failures"]:
        return False, f"{failures} consecutive order failures"
    return True, ""


# --- the ledger ----------------------------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ledger_rows_today(conn, slots_: list, day: str, mode: str = "LIVE") -> list:
    if not slots_:
        return []
    q = ",".join("?" * len(slots_))
    cur = conn.execute(f"SELECT * FROM slot_trades WHERE mode=? AND slot_id IN ({q}) ORDER BY id", [mode, *slots_])
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return [r for r in rows if datetime.fromisoformat(r["at"]).astimezone(NY).date().isoformat() == day]


def realised_today(rows: list) -> tuple:
    """(realised dollars, entries today, symbols traded today) from the day's OPEN/CLOSE rows."""
    opens, pnl, entries, syms = {}, 0.0, 0, set()
    for r in rows:
        if r["action"] == "OPEN":
            opens[r["slot_id"]] = r
            entries += 1
            syms.add(r["symbol"])
        elif r["action"] == "CLOSE" and r["slot_id"] in opens:
            o = opens.pop(r["slot_id"])
            pnl += (float(r["price"]) - float(o["price"])) * float(r["quantity"])
    return pnl, entries, syms


class SellAdapter:
    """Implements intraday_manager's broker interface on top of ExecutionEngine. Each attempt uses a distinct strategy
    suffix so a retry is a new decision (the signal id is session-scoped), while order_status() always asks the orders
    table what happened to the previous attempt."""

    def __init__(self, conn, engine, slot: int, reconciled_fn, mode: str = "LIVE", key: str = KEY):
        self.conn, self.engine, self.slot, self.reconciled, self.mode, self.key = conn, engine, slot, reconciled_fn, mode, key

    def _strategy(self, n: int) -> str:
        return f"slot{self.slot}:{self.key}" + (f":x{n}" if n > 1 else "")

    @staticmethod
    def _parse(ref_id: str) -> tuple:
        """x-<symbol>-<fill time iso>-<attempt>  ->  (symbol, attempt). Symbols may contain '-'."""
        import re
        m = re.match(r"^x-(.+)-(\d{4}-\d{2}-\d{2}T.*)-(\d+)$", ref_id)
        return m.group(1), int(m.group(3))

    @classmethod
    def _attempt(cls, ref_id: str) -> int:
        return cls._parse(ref_id)[1]

    def _map(self, state: str, filled: float, px) -> dict:
        s = {"FILLED": "FILLED", "PARTIALLY_FILLED": "PARTIAL", "SUBMITTED": "PENDING", "VALIDATING": "PENDING",
             "APPROVED": "PENDING", "UNKNOWN": "PENDING", "NEW": "PENDING"}.get(state, state)
        return {"status": s, "filled_qty": float(filled or 0.0), "avg_price": float(px) if px else None, "reason": state}

    def submit_sell(self, symbol: str, qty: float, ref_id: str) -> dict:
        n = self._attempt(ref_id)
        sig = sg.Signal(symbol=symbol, action="SELL", strategy=self._strategy(n), reason=f"intraday exit {ref_id}",
                        quantity=float(qty), session=self.engine.session)
        res = self.engine.execute(sig, reconciled=self.reconciled())
        o = res.get("order")
        status = res.get("status", "")
        if o is not None and getattr(o, "state", None) in ("FILLED", "PARTIALLY_FILLED"):
            return self._map(o.state, o.filled_quantity, o.avg_fill_price)
        if status in ("submitted", "unknown", "validating", "approved"):
            return {"status": "PENDING", "filled_qty": 0.0, "avg_price": None, "reason": status}
        if status == "duplicate" and isinstance(o, dict):
            return self._map(o.get("state", ""), o.get("filled_quantity"), o.get("avg_fill_price"))
        return {"status": "REJECTED", "filled_qty": 0.0, "avg_price": None,
                "reason": "; ".join(res.get("reasons") or []) or status}

    def order_status(self, ref_id: str) -> dict | None:
        import execution as ex
        n = self._attempt(ref_id)
        symbol = self._parse(ref_id)[0]
        sig = sg.Signal(symbol=symbol, action="SELL", strategy=self._strategy(n), reason="", session=self.engine.session)
        row = ex.already_submitted(self.conn, sig.signal_id, self.mode)
        if not row:
            return None
        return self._map(row["state"], row.get("filled_quantity"), row.get("avg_fill_price"))


# --- data ----------------------------------------------------------------------------------------------------
def universe(conn, s: dict) -> list:
    """Liquid US common stocks: top by 20-day dollar volume, price >= $5, market cap >= floor (known only)."""
    day = conn.execute("SELECT MAX(date) FROM features WHERE dollar_volume_20 IS NOT NULL").fetchone()[0]
    rows = conn.execute(
        "SELECT f.ticker FROM features f JOIN symbols s ON s.ticker=f.ticker WHERE f.date=? AND s.security_type='common_stock' "
        "AND s.is_active=1 AND f.dollar_volume_20 >= ? ORDER BY f.dollar_volume_20 DESC LIMIT ?",
        (day, s["min_dollar_volume"], s["universe_size"] * 3)).fetchall()
    import market_caps
    out = []
    for (t,) in rows:
        cap, _src = market_caps.lookup(conn, t)
        px = conn.execute("SELECT close FROM prices WHERE ticker=? ORDER BY date DESC LIMIT 1", (t,)).fetchone()
        if cap and cap >= s["min_market_cap"] and px and px[0] >= 5:
            out.append(t)
        if len(out) >= s["universe_size"]:
            break
    return out


def meta_for(conn, tickers: list) -> dict:
    out = {}
    for t in tickers:
        r = conn.execute("SELECT f.atr_14, f.dollar_volume_20, (SELECT close FROM prices p WHERE p.ticker=f.ticker "
                         "ORDER BY date DESC LIMIT 1) FROM features f WHERE f.ticker=? AND f.atr_14 IS NOT NULL "
                         "ORDER BY date DESC LIMIT 1", (t,)).fetchone()
        if r and r[0] and r[2]:
            out[t] = {"daily_atr_pct": float(r[0]) / float(r[2]), "dollar_volume_20": float(r[1] or 0)}
    return out


def fetch_bars(tickers: list, now: datetime) -> dict:
    """{ticker: DataFrame(ts tz-aware NY, open, high, low, close, volume)} of TODAY's completed 1-minute bars."""
    import yfinance as yf
    import minute_bars as mb
    raw = yf.download(tickers, period="1d", interval="1m", progress=False, auto_adjust=False, group_by="ticker", threads=True)
    flat = mb.normalize(raw, now=now)
    out = {}
    today = now.astimezone(NY).date().isoformat()
    for t, g in flat.groupby("ticker"):
        g = g[g["ts"].str[:10] == today]
        if len(g):
            d = g.copy()
            d["ts"] = pd.to_datetime(d["ts"]).dt.tz_localize(NY)
            out[t] = d.reset_index(drop=True)
    return out


# --- the runner ----------------------------------------------------------------------------------------------
class Runner:
    BLOCK = "intraday"          # which config.yaml block configures this runner
    KEY = KEY                   # the strategy key its slots carry

    def __init__(self, conn, cfg, engine, quote_fn, bars_fn, notify_fn=None, reconcile_fn=None, stage_ok_fn=None,
                 kill_fn=None, universe_fn=None, meta_fn=None, mode: str = "LIVE"):
        # ExecutionEngine reads rows by column name (row["n"]); a plain connection made every entry fail with
        # "tuple indices must be integers" on 2026-10-15 (the fake-engine tests could not see it). Always Row.
        conn.row_factory = sqlite3.Row
        self.mode = mode
        self.conn, self.cfg, self.s = conn, cfg, settings(cfg, self.BLOCK)
        self.engine, self.quote, self.bars_fn = engine, quote_fn, bars_fn
        self.notify = notify_fn or (lambda t, m: None)
        self.reconcile = reconcile_fn or (lambda: True)
        self.stage_ok = stage_ok_fn or (lambda: self.s["stage"] == "LIVE")
        self.kill = kill_fn or (lambda: None)
        self.universe = (universe_fn or (lambda: universe(conn, self.s)))()
        self.meta = (meta_fn or (lambda ts: meta_for(conn, ts)))(self.universe)
        cfg_stop = self.s["stop"]
        self.stop_cfg = st.StopConfig(mode=cfg_stop["mode"], initial_pct=cfg_stop["initial_pct"], trail_pct=cfg_stop["trail_pct"],
                                      max_hold_minutes=cfg_stop["max_hold_minutes"], flatten_hhmm=cfg_stop["flatten_hhmm"])
        self.stop_cfg = st.cap_initial_pct(self.stop_cfg, self.s["position_dollars"], self.s["max_loss_per_trade_dollars"])
        self.positions: dict = {}            # slot -> im.Position
        self.holders: dict = {}              # slot -> holder dict
        self.failures = 0
        self.halted = None
        self.last_scan = None
        self.last_ts: dict = {}
        self.logged: set = set()
        self.last_reconcile = (None, True)
        self.errors = 0
        init(conn)
        self.recover()

    # --- restart recovery ---------------------------------------------------------------------------------
    def recover(self) -> None:
        import slot_trader as stx
        cur = stx.slots.current(self.conn, self.cfg)
        self.holders = {sl: h for sl, h in cur.items() if sl in slots_of(self.cfg, self.BLOCK) and h and h["strategy_key"] == self.KEY}
        opens = stx.open_positions(self.conn, self.mode)
        for sl, p in opens.items():
            if sl not in self.holders or p["strategy_key"] != self.KEY:
                continue
            r = self.conn.execute("SELECT state FROM intraday_state WHERE slot_id=?", (sl,)).fetchone()
            mgr = self._mgr(sl, p["symbol"])
            if r:
                pos = mgr.restore(json.loads(r[0]))
            else:
                pos = mgr.open(p["symbol"], float(p["quantity"]), float(p["price"]), datetime.fromisoformat(p["at"]))
            bars = self.conn.execute("SELECT ts, high FROM minute_bars WHERE ticker=? AND ts >= ?",
                                     (p["symbol"], datetime.fromisoformat(p["at"]).astimezone(NY).strftime("%Y-%m-%d %H:%M"))).fetchall()
            mgr.rebuild(pos, [(pd.Timestamp(t).tz_localize(NY).to_pydatetime(), float(h)) for t, h in bars])
            self.positions[sl] = pos
            log.info(f"recovered slot {sl}: {pos.symbol} status {pos.status}")

    def stop_for(self, symbol: str | None) -> st.StopConfig:
        """The stop rules for a symbol. The stock Runner uses one configuration; the twin-ETF Runner scales by leverage."""
        return self.stop_cfg

    def scan(self, bars: dict, spy, now) -> dict:
        """The entry model. The stock Runner uses intraday_momentum.scan; the twin-ETF Runner overrides this."""
        return mom.scan({t: b for t, b in bars.items() if t != "SPY"}, spy, self.meta, now=now, cfg=self.s)

    def _mgr(self, slot: int, symbol: str | None = None) -> im.Manager:
        return im.Manager(SellAdapter(self.conn, self.engine, slot, lambda: self.last_reconcile[1], self.mode, self.KEY),
                          self.stop_for(symbol), alert=lambda m: self.notify("Intraday runner", m))

    # --- helpers ------------------------------------------------------------------------------------------
    def today(self, now) -> str:
        return now.astimezone(NY).date().isoformat()

    def daily_pnl(self, now) -> tuple:
        rows = ledger_rows_today(self.conn, slots_of(self.cfg, self.BLOCK), self.today(now), self.mode)
        realised, entries, syms = realised_today(rows)
        unreal = 0.0
        for sl, pos in self.positions.items():
            if pos.status != im.CLOSED:
                try:
                    q = self.quote(pos.symbol)
                except Exception:                                   # noqa: BLE001
                    q = None
                if q:
                    unreal += (q[0] - pos.entry_price) * pos.remaining
        return realised + unreal, entries, syms

    def persist(self, slot: int, pos: im.Position) -> None:
        self.conn.execute("INSERT OR REPLACE INTO intraday_state (slot_id, symbol, state, updated_at) VALUES (?,?,?,?)",
                          (slot, pos.symbol, json.dumps(im.Manager.snapshot(pos)), _now_iso()))
        self.conn.commit()

    def reconcile_ok(self, now) -> bool:
        last, ok = self.last_reconcile
        if last is None or (now - last).total_seconds() > 120:
            try:
                ok = bool(self.reconcile())
            except Exception as e:                                  # noqa: BLE001
                log.error(f"reconcile failed: {type(e).__name__}: {e}")
                ok = False
            self.last_reconcile = (now, ok)
        return self.last_reconcile[1]

    # --- 1. manage open positions ---------------------------------------------------------------------------
    def manage(self, now) -> None:
        for sl, pos in list(self.positions.items()):
            if pos.status == im.CLOSED:
                continue
            q = None
            try:
                q = self.quote(pos.symbol)
            except Exception as e:                                  # noqa: BLE001
                log.error(f"quote {pos.symbol}: {type(e).__name__}: {e}")
            price, qts = (q[0], q[1]) if q else (None, None)
            kill = self.kill()
            mgr = self._mgr(sl, pos.symbol)
            if kill and pos.status == im.OPEN:
                mgr._exit(pos, f"kill switch: {kill}")
            else:
                mgr.tick(pos, price, qts, now)
            self.persist(sl, pos)
            if pos.status == im.CLOSED:
                self.finalize(sl, pos, now)
            elif pos.status == im.ESCALATED:
                self.halted = "an exit could not be completed"

    def finalize(self, slot: int, pos: im.Position, now) -> None:
        avg = pos.proceeds / pos.exited_qty if pos.exited_qty else pos.entry_price
        h = self.holders[slot]
        self.conn.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, "
                          "atr, stop_plan, reason, signal_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (now.astimezone(timezone.utc).isoformat(timespec="seconds"), self.mode, slot, self.KEY, h["version"], pos.symbol, "CLOSE", pos.exited_qty, avg, None, None,
                           f"intraday: {pos.exit_reason}", pos.exit_ref))
        self.conn.commit()
        pnl = (avg - pos.entry_price) * pos.exited_qty
        self.notify("Intraday exit", f"slot {slot} SELL {pos.symbol} {pos.exited_qty:.6f} @ ${avg:.2f} "
                                     f"({pos.exit_reason}); {pnl:+.2f} vs entry ${pos.entry_price:.2f}")
        self.conn.execute("DELETE FROM intraday_state WHERE slot_id=?", (slot,))
        self.conn.commit()
        del self.positions[slot]

    # --- 2. scan and enter ----------------------------------------------------------------------------------
    def scan_and_enter(self, now) -> dict:
        ny = now.astimezone(NY)
        pnl, entries, syms = self.daily_pnl(now)
        live = self.stage_ok()
        ok, why = entry_gate(self.s, ny, entries, len(self.positions), pnl, self.failures, live, self.kill(), self.halted)
        if pnl <= -abs(self.s["max_daily_loss_dollars"]) and self.positions:
            self.halted = self.halted or "intraday daily loss limit"
            for sl, pos in list(self.positions.items()):
                if pos.status == im.OPEN:
                    self._mgr(sl, pos.symbol)._exit(pos, "intraday daily loss limit")
                    self.persist(sl, pos)
        if self.s["stage"] == "OFF" or not (time(9, 35) <= ny.time() <= time(16, 0)):
            return {"scanned": 0, "note": why or "idle"}
        tickers = list(dict.fromkeys(self.universe + ["SPY"]))
        bars = self.bars_fn(tickers, now)
        self.store(bars)                                   # the whole session is kept: the history the evaluation needs
        if not in_window(ny, self.s):
            return {"scanned": len(bars), "candidates": 0, "note": why or "outside the entry window"}
        spy = bars.get("SPY")
        res = self.scan(bars, spy, now)
        cands = res["candidates"]
        for c in cands:
            key = (self.today(now), c["ticker"])
            if key not in self.logged:
                self.logged.add(key)
                self.conn.execute("INSERT INTO intraday_runner_signals (at, session, ticker, score, features, action, note, calibrated) "
                                  "VALUES (?,?,?,?,?,?,?,0)", (_now_iso(), self.today(now), c["ticker"], c["score"],
                                                              json.dumps({k: (str(v) if k == "last_bar" else v) for k, v in c.items()}),
                                                              "QUALIFIED", why or "eligible"))
        self.conn.commit()
        entered = []
        if ok and cands and self.reconcile_ok(now):
            free = [sl for sl in self.holders if sl not in self.positions]
            for c in cands:
                if not free or c["ticker"] in syms:
                    continue
                ok2, why2 = entry_gate(self.s, ny, entries + len(entered), len(self.positions), pnl, self.failures,
                                       live, self.kill(), self.halted)
                if not ok2:
                    break
                if self.enter(free[0], c, now):
                    entered.append(c["ticker"])
                    syms.add(c["ticker"])
                    free.pop(0)
        return {"scanned": res["scanned"], "candidates": len(cands), "entered": entered, "rejected": res["rejected"], "note": why}

    def store(self, bars: dict) -> None:
        rows = []
        for t, b in bars.items():
            last = self.last_ts.get(t)
            new = b if last is None else b[b["ts"] > last]
            if len(new):
                self.last_ts[t] = new["ts"].max()
                rows += [(t, r.ts.strftime("%Y-%m-%d %H:%M"), r.open, r.high, r.low, r.close, r.volume) for r in new.itertuples()]
        if rows:
            self.conn.executemany("INSERT OR IGNORE INTO minute_bars (ticker, ts, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)", rows)
            self.conn.commit()

    def enter(self, slot: int, c: dict, now) -> bool:
        sym = c["ticker"]
        q = self.quote(sym)
        if not q:
            self._log_skip(now, c, "no fresh Robinhood quote")
            return False
        if abs(q[0] / c["price"] - 1) > self.s["max_price_drift"]:
            self._log_skip(now, c, f"quote ${q[0]:.2f} drifted from the signal price ${c['price']:.2f}")
            return False
        sig = sg.Signal(symbol=sym, action="BUY", strategy=f"slot{slot}:{self.KEY}",
                        reason=f"intraday momentum v0 (uncalibrated) score {c['score']:.2f}",
                        notional_value=float(self.s["position_dollars"]), session=self.engine.session)
        res = self.engine.execute(sig, reconciled=self.last_reconcile[1])
        o = res.get("order")
        if res.get("status") in ("filled", "partially_filled") and o is not None and o.filled_quantity:
            h = self.holders[slot]
            sc = self.stop_for(sym)
            plan = [{"type": "trailing_pct", "pct": sc.trail_pct}, {"type": "fixed_pct", "pct": sc.initial_pct}]
            self.conn.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, "
                              "atr, stop_plan, reason, signal_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (now.astimezone(timezone.utc).isoformat(timespec="seconds"), self.mode, slot, self.KEY, h["version"], sym, "OPEN", float(o.filled_quantity),
                               float(o.avg_fill_price), None, json.dumps(plan), sig.reason, res["signal_id"]))
            self.conn.commit()
            pos = self._mgr(slot, sym).open(sym, float(o.filled_quantity), float(o.avg_fill_price), now)
            self.positions[slot] = pos
            self.persist(slot, pos)
            self.failures = 0
            self.notify("Intraday entry", f"slot {slot} BUY {sym} {o.filled_quantity:.6f} @ ${float(o.avg_fill_price):.2f}; "
                                          f"stop ${pos.stop:.2f} (trailing {sc.trail_pct}%)")
            self.conn.execute("UPDATE intraday_runner_signals SET action='TRADED' WHERE session=? AND ticker=?", (self.today(now), sym))
            self.conn.commit()
            return True
        if res.get("status") in ("failed", "halted"):
            self.failures += 1
            if self.failures >= self.s["max_order_failures"]:
                self.notify("Intraday runner", f"{self.failures} consecutive order failures - new entries halted")
        self._log_skip(now, c, f"{res.get('status')}: {'; '.join(res.get('reasons') or [])[:120]}")
        return False

    def _log_skip(self, now, c, note) -> None:
        self.conn.execute("UPDATE intraday_runner_signals SET note=? WHERE session=? AND ticker=?", (note, self.today(now), c["ticker"]))
        self.conn.commit()

    # --- one tick -------------------------------------------------------------------------------------------
    def tick(self, now) -> dict:
        out = {}
        try:
            self.manage(now)
            due = self.last_scan is None or (now - self.last_scan).total_seconds() >= self.s["scan_every_s"]
            if due and (self.s["stage"] != "OFF"):
                self.last_scan = now
                out = self.scan_and_enter(now)
            self.errors = 0
        except Exception as e:                                      # noqa: BLE001
            self.errors += 1
            log.exception("tick failed")
            if self.errors == 5:
                self.halted = f"{self.errors} consecutive errors"
                self.notify("Intraday runner", f"errors: {type(e).__name__}: {e} - new entries halted")
        self.conn.execute("INSERT INTO intraday_heartbeat (at, session, stage, scanned, candidates, open_positions, entries_today, note) "
                          "VALUES (?,?,?,?,?,?,?,?)", (_now_iso(), self.today(now), self.s["stage"], out.get("scanned"),
                                                       out.get("candidates"), len(self.positions), None, out.get("note")))
        self.conn.commit()
        return out


# --- wiring --------------------------------------------------------------------------------------------------
def build_live(conn, cfg, cls=None, block: str = "intraday") -> Runner:
    import killswitch as ks
    import risk_engine
    import robinhood_live
    import slot_trader as stx

    class FreshQuotes(robinhood_live.RobinhoodQuotes):
        def get(self, symbol):
            self._cache.pop(symbol, None)
            return super().get(symbol)

    provider = FreshQuotes(conn, max_age_seconds=20)
    broker, engine = stx._build(conn, cfg, "LIVE", provider)

    def quote_fn(sym):
        q = provider.get(sym)
        if not q:
            return None
        ts = q.get("as_of")
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00")) if ts else datetime.now(timezone.utc)
        return float(q["price"]), t

    def stage_ok():
        lim = risk_engine.load_limits()
        return (str((cfg.get(block) or {}).get("stage", "OFF")).upper() == "LIVE" and bool(lim.get("allow_intraday")) and
                str(lim.get("execution_mode", "")).upper() == "LIVE")

    def notify_fn(title, msg):
        try:
            import notify
            notify.notify(f"Stockbot2000 {title}", msg)
        except Exception as e:                                      # noqa: BLE001
            log.warning(f"alert failed: {type(e).__name__}")

    return (cls or Runner)(conn, cfg, engine, quote_fn, fetch_bars, notify_fn=notify_fn,
                           reconcile_fn=lambda: stx.reconcile(conn, broker, "LIVE")[0], stage_ok_fn=stage_ok,
                           kill_fn=lambda: ks.global_engaged())


def serve(poll_s: int | None = None) -> int:
    import robinhood_mcp as rh
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    import intraday_twin as tw
    blocks = [("intraday", Runner), (tw.BLOCK, tw.TwinRunner)]
    active = [(b, c) for b, c in blocks if str((cfg.get(b) or {}).get("stage", "OFF")).upper() != "OFF"]
    if not active:
        log.info("every intraday stage is OFF: nothing to do")
        return 0
    runners: dict = {}
    poll = poll_s or settings(cfg)["poll_every_s"]
    while True:
        now = datetime.now(timezone.utc)
        ny = now.astimezone(NY)
        if ny.time() >= time(16, 5):
            break
        if ny.weekday() < 5 and ny.time() >= time(9, 25):
            try:
                with rh.session():
                    for block, cls in active:
                        try:
                            if block not in runners:
                                runners[block] = build_live(conn, cfg, cls, block)
                            runners[block].tick(now)
                        except Exception as e:                      # noqa: BLE001  — one runner's failure never stops the other
                            log.error(f"{block} failed: {type(e).__name__}: {e}")
            except Exception as e:                                  # noqa: BLE001
                log.error(f"loop error: {type(e).__name__}: {e}")
        _time.sleep(poll)
    for block, r in runners.items():
        if r.positions:
            r.notify("Intraday runner", f"{block}: session over with {len(r.positions)} intraday position(s) not closed - check the account")
    return 0


def status() -> int:
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    init(conn)
    s = settings(cfg)
    import slots
    cur = slots.current(conn, cfg)
    print(f"stage {s['stage']}  slots {s['slots']}")
    for sl in slots_of(cfg):
        h = cur.get(sl)
        print(f"  slot {sl}: {h['strategy_key'] if h else 'cash'}")
    for r in conn.execute("SELECT slot_id, symbol, updated_at FROM intraday_state"):
        print("  open", r)
    for r in conn.execute("SELECT at, session, scanned, candidates, open_positions, note FROM intraday_heartbeat ORDER BY id DESC LIMIT 3"):
        print("  beat", r)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--assign", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    if a.assign:
        cfg = load_config()
        conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
        import intraday_twin as tw
        print("assigned slots:", assign(conn, cfg) or "already assigned")
        if str((cfg.get(tw.BLOCK) or {}).get("stage", "OFF")).upper() != "OFF":
            print("twin-ETF slots:", assign(conn, cfg, block=tw.BLOCK, key=tw.KEY_TWIN) or "already assigned")
        return 0
    if a.status:
        return status()
    if a.serve:
        return serve()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
