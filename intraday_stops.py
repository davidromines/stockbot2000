"""
Intraday Momentum Runner (Addendum G), M2: the stop and exit rules as pure functions.

No broker, no database, no clock: everything here takes prices and timestamps and returns decisions, so the same
code drives the minute-bar simulator (intraday_sim.py) and the live position manager (intraday_manager.py).

    initial stop     below the entry price, a percentage or a multiple of the 1-minute ATR, optionally capped so the
                     intended loss on the position does not exceed a dollar limit
    trailing stop    highest ELIGIBLE price since the fill x (1 - trail), or highest - k x ATR; it never moves down
    eligible price   a price observed at or after the fill. The bar in which the fill happened mid-bar, and every bar
                     before it, can never lift the stop (a high that occurred before the entry is not a high since entry)
    exits            initial stop, trailing stop, maximum holding time, the end-of-session flatten (US market calendar,
                     America/New_York, early closes, daylight saving), and caller-supplied signal exits

A stop price is a TRIGGER. Nothing here says what a sale will fetch; the simulator and the manager record the
trigger and the execution price separately.

Worked example (plan section 3.5): entry $100, highest $103, 1 % trail -> trigger $101.97.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class StopConfig:
    mode: str = "pct"                    # "pct" | "atr"
    initial_pct: float = 1.0             # initial stop distance below entry, percent
    trail_pct: float = 1.0               # trailing distance below the highest eligible price, percent
    atr: float | None = None             # 1-minute ATR in price units (mode "atr")
    initial_atr_mult: float = 2.0
    trail_atr_mult: float = 2.0
    max_hold_minutes: int | None = 60    # None = no time limit (the flatten still applies)
    flatten_hhmm: str = "15:45"          # New York time; never later than 15 minutes before the close

    def __post_init__(self):
        if self.mode not in ("pct", "atr"):
            raise ValueError(f"unknown stop mode {self.mode!r}")
        if self.mode == "atr" and not (self.atr and self.atr > 0):
            raise ValueError("atr mode needs a positive atr")
        if self.mode == "pct" and not (0 < self.initial_pct < 100 and 0 < self.trail_pct < 100):
            raise ValueError("percentage stops must be between 0 and 100")


def cap_initial_pct(cfg: StopConfig, position_dollars: float, max_loss_dollars: float | None) -> StopConfig:
    """Tighten the initial stop so the INTENDED loss on the position stays within the dollar limit.
    Intended, not guaranteed: a gap or slippage can make the realised loss larger (reported separately)."""
    if cfg.mode != "pct" or not max_loss_dollars or position_dollars <= 0:
        return cfg
    return replace(cfg, initial_pct=min(cfg.initial_pct, 100.0 * max_loss_dollars / position_dollars))


class TrailingStop:
    """Initial + trailing stop for ONE long position. `observe*` may be called with any price series; only prices at
    or after the fill time are eligible to raise the highest price, and the stop never decreases."""

    def __init__(self, entry_price: float, fill_time: datetime, cfg: StopConfig):
        if entry_price <= 0:
            raise ValueError("entry price must be positive")
        self.entry, self.fill_time, self.cfg = float(entry_price), fill_time, cfg
        self.highest = float(entry_price)
        self.initial = self._initial_level()
        self._stop = self.initial

    def _initial_level(self) -> float:
        c = self.cfg
        return self.entry * (1 - c.initial_pct / 100) if c.mode == "pct" else self.entry - c.initial_atr_mult * c.atr

    def _trail_level(self) -> float:
        c = self.cfg
        return self.highest * (1 - c.trail_pct / 100) if c.mode == "pct" else self.highest - c.trail_atr_mult * c.atr

    @property
    def stop_price(self) -> float:
        return self._stop

    def observe(self, price: float, ts: datetime) -> bool:
        """A price seen at `ts`. Returns True when it raised the stop. Prices before the fill are ignored."""
        if ts < self.fill_time or price is None:
            return False
        if price > self.highest:
            self.highest = float(price)
            level = self._trail_level()
            if level > self._stop:
                self._stop = level
                return True
        return False

    def observe_bar_high(self, bar_start: datetime, high: float) -> bool:
        """A bar's high counts only if the bar STARTED at or after the fill: a bar that began earlier may have made
        its high before the entry, and a candle's range does not say in what order its prices occurred."""
        return self.observe(high, bar_start) if bar_start >= self.fill_time else False

    def breached(self, price: float) -> bool:
        return price is not None and price <= self._stop

    def reason(self) -> str:
        return "trailing stop" if self._stop > self.initial else "initial stop"

    def state(self) -> dict:
        return {"entry": self.entry, "fill_time": self.fill_time.isoformat(), "highest": self.highest,
                "stop": self._stop, "initial": self.initial}


def rebuild(entry_price: float, fill_time: datetime, cfg: StopConfig, bars) -> TrailingStop:
    """Restart recovery: re-derive the trailing state from the stored bars since the fill. `bars` yields
    (bar_start, high). Because the stop is a monotone function of the eligible highs, the result is identical to the
    state the live service had before it stopped."""
    ts = TrailingStop(entry_price, fill_time, cfg)
    for start, high in bars:
        ts.observe_bar_high(start, high)
    return ts


# --- session calendar (US equities, New York time) ---------------------------------------------------------------
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def session_close(d: date) -> time:
    """Regular close 16:00 ET; 13:00 ET on the day after Thanksgiving and on Dec 24 when it is a weekday.
    (A small rule table; the project's trading_calendar is authoritative once this is wired in.)"""
    if d == _nth_weekday(d.year, 11, 3, 4) + timedelta(days=1):
        return time(13, 0)
    if d.month == 12 and d.day == 24 and d.weekday() < 5:
        return time(13, 0)
    return time(16, 0)


def flatten_at(d: date, cfg: StopConfig) -> datetime:
    """The moment (tz-aware, New York) from which an intraday position must be exited on session `d`."""
    h, m = (int(x) for x in cfg.flatten_hhmm.split(":"))
    want = datetime.combine(d, time(h, m), tzinfo=NY)
    close = datetime.combine(d, session_close(d), tzinfo=NY)
    return min(want, close - timedelta(minutes=15))


def to_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC)
