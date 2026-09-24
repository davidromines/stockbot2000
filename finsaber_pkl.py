"""
FINSABER aggregated pickles: a streaming, restricted importer.

The two `.pkl` files on Hugging Face (finsaber-team/FINSABER-reproduce) are one
Python dict each, keyed by `datetime.date`:

    {date: {"price":    {symbol: {open, high, low, close, adjusted_close, volume}},
            "news":     {symbol: [headline, ...]},
            "filing_k": {symbol: "10-K text"},
            "filing_q": {symbol: "10-Q text"}}}

The S&P 500 file is 27.3 GB (the README still says ~11 GB). It cannot be
loaded: this VM has 11.7 GB and jobs are capped at 6 GB. Nor can a stock
Unpickler stream it, because every object is MEMOIZEd and the memo keeps all
of them alive until the end.

So this module is a small pickle VM for the opcode subset pickle.dump emits for
plain data at protocol 3-5 (protocol 2 routes bytes through
`_codecs.encode`, which the whitelist refuses). Two properties are the point of it:

1. **Streaming.** Each top-level (date, value) pair is emitted as soon as it is
   complete and never inserted into the top dict; the memo entries it created
   are then dropped, except small scalars (dict keys, tickers, the date class)
   that later dates reference. A reference to a dropped entry raises rather
   than yielding a wrong object.
2. **Restricted.** Unpickling is code execution. The only global this VM will
   resolve is `datetime.date` / `datetime.datetime`, and REDUCE applies to
   nothing else. Any other global stops the import.

Like `finsaber.py`, everything lands in `data/finsaber.db`, never the primary
database. Pickle prices go to `finsaber_pkl_prices`, not `finsaber_prices`, so
the pickle and the CSV can be checked against each other rather than blended.

**Point-in-time status of news and filings is UNVERIFIED.** The date key is
FINSABER's; whether a headline or a filing dated D was public before D's open
is not established here (the SEC's 17:30 `filed` cutoff alone puts ~48% of
filings on a date they were not tradeable — see CLAUDE.md). Nothing may use
these tables as a signal until that is measured.

Resumable: progress is stored per dataset. A rerun re-parses from the start
(a pickle cannot be seeked) but skips writing dates already committed.
"""
import runtime  # noqa: F401  — entry point; must precede anything numeric.
import argparse
import datetime as _dt
import hashlib
import json
import logging
import os
import sqlite3
import struct
import sys
import zlib

import pandas as pd

import finsaber

log = logging.getLogger("finsaber_pkl")

_MARK = object()
_ALLOWED = {("datetime", "date"): _dt.date, ("datetime", "datetime"): _dt.datetime}


class PickleFormatError(Exception):
    pass


class _Reader:
    """Buffered byte reader; far cheaper than file.read(1) per opcode."""

    def __init__(self, f, chunk=1 << 24):
        self.f, self.chunk = f, chunk
        self.buf, self.pos, self.base = b"", 0, 0   # base = file offset of buf[0]

    def read(self, n):
        end = self.pos + n
        if end <= len(self.buf):
            out = self.buf[self.pos:end]
            self.pos = end
            return out
        parts = [self.buf[self.pos:]]
        self.base += self.pos
        have = len(parts[0])
        while have < n:
            data = self.f.read(max(self.chunk, n - have))
            if not data:
                raise PickleFormatError("unexpected end of file")
            parts.append(data)
            have += len(data)
        self.buf = b"".join(parts)
        self.pos = n
        return self.buf[:n]

    @property
    def offset(self):
        return self.base + self.pos


def _small(obj):
    """Memo entries kept across dates: cheap, and the kind later dates reuse."""
    if isinstance(obj, str):
        # Measured on the cherry-pick file: every cross-date reference is a
        # SHORT_BINUNICODE string (field names, tickers, and repeated headlines
        # such as "Benzinga's Top Initiations"); no container is ever shared.
        return len(obj) < 256
    return obj is None or isinstance(obj, (int, float, bool, bytes, _dt.date, type))


LONG_STRING_BUDGET = 1_500_000_000   # bytes of evicted-but-recallable long strings


def stream(f, long_budget=LONG_STRING_BUDGET):
    """
    Yield (key, value) for each top-level item of a pickled dict, one at a time.

    Raises PickleFormatError on anything outside the supported subset, on a
    disallowed global, or on a reference to a memo entry already dropped.
    """
    r = _Reader(f)
    stack, metastack = [], []
    memo, next_memo = {}, 0
    since_emit = []          # memo indices created since the last emission
    # Long strings are rarely shared across dates, but nothing guarantees it: a
    # forward-filled filing would be one object referenced from many dates. So
    # they leave the memo into a byte-bounded LRU rather than disappearing.
    from collections import OrderedDict
    lru, lru_bytes = OrderedDict(), 0
    top = None               # the top-level dict (first object pushed)

    def at_top_frame():
        return len(metastack) == 1 and len(metastack[0]) == 1 and metastack[0][0] is top

    def evict():
        nonlocal lru_bytes
        for i in since_emit:
            obj = memo.get(i)
            if obj is None or obj is _EVICTED or _small(obj):
                continue
            memo[i] = _EVICTED
            if isinstance(obj, str):
                lru[i] = obj
                lru_bytes += len(obj)
        since_emit.clear()
        while lru_bytes > long_budget and lru:
            _, old = lru.popitem(last=False)
            lru_bytes -= len(old)

    def push(obj):
        stack.append(obj)
        # A third element in the top frame means the (key, value) before it is
        # complete: nothing at this level can add to a value once another push
        # has happened here (inner batches open their own MARK frame).
        if top is not None and at_top_frame() and len(stack) == 3:
            k, v = stack[0], stack[1]
            del stack[:2]
            return (k, v)
        return None

    def pop_mark():
        nonlocal stack
        items = stack
        stack = metastack.pop()
        return items

    while True:
        op = r.read(1)
        out = None
        if op == b"\x80":                       # PROTO
            r.read(1)
        elif op == b"\x95":                     # FRAME — frames are advisory
            r.read(8)
        elif op == b".":                        # STOP
            if stack and stack[-1] is top:
                return
            raise PickleFormatError("STOP with unexpected stack")
        elif op == b"(":                        # MARK
            metastack.append(stack)
            stack = []
        elif op == b"}":                        # EMPTY_DICT
            d = {}
            if top is None:
                top = d
            out = push(d)
        elif op == b"]":                        # EMPTY_LIST
            out = push([])
        elif op == b")":                        # EMPTY_TUPLE
            out = push(())
        elif op == b"\x94":                     # MEMOIZE
            memo[next_memo] = stack[-1]
            since_emit.append(next_memo)
            next_memo += 1
        elif op in (b"h", b"j"):                # BINGET / LONG_BINGET
            i = r.read(1)[0] if op == b"h" else struct.unpack("<I", r.read(4))[0]
            obj = memo.get(i, _MISSING)
            if obj is _EVICTED and i in lru:
                lru.move_to_end(i)
                obj = lru[i]
            if obj is _MISSING or obj is _EVICTED:
                raise PickleFormatError(f"reference to dropped memo entry {i} at byte {r.offset}")
            out = push(obj)
        elif op == b"\x8c":                     # SHORT_BINUNICODE
            out = push(r.read(r.read(1)[0]).decode("utf-8", "surrogatepass"))
        elif op == b"X":                        # BINUNICODE
            out = push(r.read(struct.unpack("<I", r.read(4))[0]).decode("utf-8", "surrogatepass"))
        elif op == b"\x8d":                     # BINUNICODE8
            out = push(r.read(struct.unpack("<Q", r.read(8))[0]).decode("utf-8", "surrogatepass"))
        elif op == b"C":                        # SHORT_BINBYTES
            out = push(r.read(r.read(1)[0]))
        elif op == b"B":                        # BINBYTES
            out = push(r.read(struct.unpack("<I", r.read(4))[0]))
        elif op == b"\x93":                     # STACK_GLOBAL
            name = stack.pop()
            module = stack.pop()
            cls = _ALLOWED.get((module, name))
            if cls is None:
                raise PickleFormatError(f"global {module}.{name} is not allowed")
            out = push(cls)
        elif op == b"c":                        # GLOBAL (protocol <4)
            module = r_line(r)
            name = r_line(r)
            cls = _ALLOWED.get((module, name))
            if cls is None:
                raise PickleFormatError(f"global {module}.{name} is not allowed")
            out = push(cls)
        elif op in (b"\x85", b"\x86", b"\x87"):  # TUPLE1/2/3
            n = {b"\x85": 1, b"\x86": 2, b"\x87": 3}[op]
            t = tuple(stack[-n:])
            del stack[-n:]
            out = push(t)
        elif op == b"t":                        # TUPLE
            out = push(tuple(pop_mark()))
        elif op == b"R":                        # REDUCE — date constructors only
            args = stack.pop()
            fn = stack.pop()
            if fn not in _ALLOWED.values():
                raise PickleFormatError(f"REDUCE on {fn!r} is not allowed")
            out = push(fn(*args))
        elif op == b"s":                        # SETITEM
            v = stack.pop()
            k = stack.pop()
            stack[-1][k] = v
        elif op == b"u":                        # SETITEMS
            items = pop_mark()
            target = stack[-1]
            if target is top:
                # Emitted, not stored: this is what keeps memory flat.
                for i in range(0, len(items), 2):
                    yield items[i], items[i + 1]
                    evict()
            else:
                for i in range(0, len(items), 2):
                    target[items[i]] = items[i + 1]
        elif op == b"a":                        # APPEND
            v = stack.pop()
            stack[-1].append(v)
        elif op == b"e":                        # APPENDS
            items = pop_mark()
            stack[-1].extend(items)
        elif op == b"J":                        # BININT
            out = push(struct.unpack("<i", r.read(4))[0])
        elif op == b"K":                        # BININT1
            out = push(r.read(1)[0])
        elif op == b"M":                        # BININT2
            out = push(struct.unpack("<H", r.read(2))[0])
        elif op == b"\x8a":                     # LONG1
            n = r.read(1)[0]
            out = push(int.from_bytes(r.read(n), "little", signed=True))
        elif op == b"G":                        # BINFLOAT
            out = push(struct.unpack(">d", r.read(8))[0])
        elif op == b"N":
            out = push(None)
        elif op == b"\x88":
            out = push(True)
        elif op == b"\x89":
            out = push(False)
        elif op == b"q":                        # BINPUT (protocol 2/3)
            i = r.read(1)[0]
            memo[i] = stack[-1]
            since_emit.append(i)
        elif op == b"r":                        # LONG_BINPUT
            i = struct.unpack("<I", r.read(4))[0]
            memo[i] = stack[-1]
            since_emit.append(i)
        else:
            raise PickleFormatError(f"unsupported opcode {op!r} at byte {r.offset - 1}")

        if out is not None:
            yield out
            evict()


_MISSING = object()
_EVICTED = object()


def r_line(r):
    chars = []
    while True:
        c = r.read(1)
        if c == b"\n":
            return b"".join(chars).decode("ascii")
        chars.append(c)


# --------------------------------------------------------------------------- store

def init(conn):
    finsaber.init(conn)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS finsaber_pkl_prices (
            dataset   TEXT NOT NULL,
            symbol    TEXT NOT NULL,
            date      TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL,
            PRIMARY KEY (dataset, symbol, date)
        ) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS finsaber_news (
            dataset  TEXT NOT NULL,
            symbol   TEXT NOT NULL,
            date     TEXT NOT NULL,
            seq      INTEGER NOT NULL,
            headline TEXT NOT NULL,
            PRIMARY KEY (dataset, symbol, date, seq)
        ) WITHOUT ROWID;
        -- Filing text is zlib-compressed; `chars` is the uncompressed length.
        CREATE TABLE IF NOT EXISTS finsaber_filings (
            dataset TEXT NOT NULL,
            symbol  TEXT NOT NULL,
            date    TEXT NOT NULL,
            form    TEXT NOT NULL,
            chars   INTEGER NOT NULL,
            sha256  TEXT NOT NULL,
            text_z  BLOB NOT NULL,
            PRIMARY KEY (dataset, symbol, date, form)
        ) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS finsaber_pkl_progress (
            dataset     TEXT PRIMARY KEY,
            source_path TEXT,
            last_date   TEXT,
            dates       INTEGER,
            complete    INTEGER NOT NULL DEFAULT 0,
            sha256      TEXT,
            updated_at  TEXT
        );
    """)
    conn.commit()


_FORMS = {"filing_k": "10-K", "filing_q": "10-Q"}


def _rows_for(dataset, day, value, counts):
    d = day.isoformat()
    prices, news, filings = [], [], []
    for sym, bar in (value.get("price") or {}).items():
        o, h, l, c = (bar.get(k) for k in ("open", "high", "low", "close"))
        ok = all(isinstance(x, (int, float)) and x > 0 for x in (o, h, l, c)) and h >= l
        if not ok:
            counts["rejected_bars"] += 1   # rejected, never repaired (finsaber._valid)
            continue
        prices.append((dataset, sym, d, o, h, l, c, bar.get("adjusted_close"), bar.get("volume")))
    for sym, heads in (value.get("news") or {}).items():
        for i, text in enumerate(heads or []):
            if text:
                news.append((dataset, sym, d, i, str(text)))
    for key, form in _FORMS.items():
        for sym, text in (value.get(key) or {}).items():
            if text:
                raw = str(text).encode("utf-8", "surrogatepass")
                filings.append((dataset, sym, d, form, len(text),
                                hashlib.sha256(raw).hexdigest(), zlib.compress(raw, 6)))
    unknown = set(value) - {"price", "news", *_FORMS}
    if unknown:
        counts["unknown_sections"] |= unknown
    return prices, news, filings


def import_pkl(conn, path, dataset, commit_every=20):
    """Stream one FINSABER pickle into the store. Returns counts."""
    init(conn)
    prog = conn.execute("SELECT last_date, complete FROM finsaber_pkl_progress WHERE dataset=?",
                        (dataset,)).fetchone()
    if prog and prog["complete"]:
        log.info(f"{dataset}: already complete through {prog['last_date']}")
        return {"dataset": dataset, "skipped": "complete"}
    resume_after = prog["last_date"] if prog else None

    counts = {"dates": 0, "skipped_dates": 0, "bars": 0, "headlines": 0, "filings": 0,
              "rejected_bars": 0, "unknown_sections": set()}
    last = None
    pending = 0
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        for day, value in stream(f):
            if not isinstance(day, _dt.date) or not isinstance(value, dict):
                raise PickleFormatError(f"top-level item is {type(day).__name__} -> "
                                        f"{type(value).__name__}, not date -> dict")
            d = day.isoformat()
            if resume_after and d <= resume_after:
                counts["skipped_dates"] += 1
                continue
            p, n, fl = _rows_for(dataset, day, value, counts)
            conn.executemany("INSERT OR REPLACE INTO finsaber_pkl_prices VALUES (?,?,?,?,?,?,?,?,?)", p)
            conn.executemany("INSERT OR REPLACE INTO finsaber_news VALUES (?,?,?,?,?)", n)
            conn.executemany("INSERT OR REPLACE INTO finsaber_filings VALUES (?,?,?,?,?,?,?)", fl)
            counts["dates"] += 1
            counts["bars"] += len(p)
            counts["headlines"] += len(n)
            counts["filings"] += len(fl)
            last = d if last is None or d > last else last
            pending += 1
            if pending >= commit_every:
                _progress(conn, dataset, path, last, counts, complete=False)
                pending = 0
                log.info(f"{dataset}: through {d} ({f.tell() / size:.1%}) "
                         f"bars {counts['bars']:,} news {counts['headlines']:,} filings {counts['filings']:,}")
    digest = finsaber._sha256(path)
    _progress(conn, dataset, path, last or resume_after, counts, complete=True, sha256=digest)
    counts["unknown_sections"] = sorted(counts["unknown_sections"])
    counts["sha256"] = digest
    return counts


def _progress(conn, dataset, path, last, counts, complete, sha256=None):
    conn.execute("""
        INSERT INTO finsaber_pkl_progress (dataset, source_path, last_date, dates, complete, sha256, updated_at)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(dataset) DO UPDATE SET source_path=excluded.source_path,
            last_date=excluded.last_date,
            dates=excluded.dates,
            complete=excluded.complete, sha256=COALESCE(excluded.sha256, finsaber_pkl_progress.sha256),
            updated_at=excluded.updated_at
    """, (dataset, os.path.abspath(path), last, counts["dates"] + counts["skipped_dates"],
          int(complete), sha256, finsaber._now()))
    conn.commit()


def pit_check(fconn, conn, dataset: str = "sp500") -> dict:
    """
    Are FINSABER's filing dates point-in-time? Each 10-K/10-Q is matched to the
    same ticker's SEC filing within 45 days, and its date compared with the
    SEC `filed` date and with `first_tradeable` — the first session the filing
    could actually be traded on (pit_facts.py).

    Measured 2026-09-24: FINSABER dates a filing ON its SEC filed date (78%) or
    the day before, so 89.7% of them fall BEFORE the first tradeable session.
    The rule that follows: never use a FINSABER filing as of its own date —
    join to sec_filings.first_tradeable and use that.
    """
    import numpy as np
    fs = pd.read_sql_query("SELECT symbol, date, form FROM finsaber_filings WHERE dataset=?", fconn,
                           params=(dataset,))
    sec = pd.read_sql_query("SELECT ticker AS symbol, form, filed, first_tradeable FROM sec_filings "
                            "WHERE form IN ('10-K','10-Q') AND first_tradeable IS NOT NULL", conn)
    fs["d"] = pd.to_datetime(fs["date"])
    sec["fd"], sec["ft"] = pd.to_datetime(sec["filed"]), pd.to_datetime(sec["first_tradeable"])
    out = []
    for (sym, form), g in fs.groupby(["symbol", "form"]):
        s = sec[(sec["symbol"] == sym) & (sec["form"] == form)].sort_values("fd")
        if s.empty:
            continue
        m = pd.merge_asof(g.sort_values("d"), s[["fd", "ft"]], left_on="d", right_on="fd",
                          direction="nearest", tolerance=pd.Timedelta(days=45))
        out.append(m.dropna(subset=["fd"]))
    m = pd.concat(out) if out else pd.DataFrame(columns=["d", "fd", "ft"])
    vs_filed = (m["d"] - m["fd"]).dt.days
    vs_trade = (m["d"] - m["ft"]).dt.days
    return {"dataset": dataset, "filings": int(len(fs)), "matched_to_sec": int(len(m)),
            "dated_on_filed_day": round(float((vs_filed == 0).mean()), 4) if len(m) else None,
            "before_first_tradeable": round(float((vs_trade < 0).mean()), 4) if len(m) else None,
            "median_days_vs_filed": float(np.median(vs_filed)) if len(m) else None,
            "rule": "never use a FINSABER filing as of its own date; use sec_filings.first_tradeable",
            "news": "UNVERIFIED — no reference timestamp exists for headlines; not usable as a signal"}


def status(conn):
    init(conn)
    out = []
    for r in conn.execute("SELECT * FROM finsaber_pkl_progress ORDER BY dataset"):
        ds = r["dataset"]
        n = {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE dataset=?", (ds,)).fetchone()[0]
             for t in ("finsaber_pkl_prices", "finsaber_news", "finsaber_filings")}
        out.append({**dict(r), **n})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stream a FINSABER aggregated pickle into data/finsaber.db")
    ap.add_argument("--import", dest="path", help=".pkl file")
    ap.add_argument("--dataset", help="dataset name (default: derived from the file name)")
    ap.add_argument("--db", default=finsaber.DEFAULT_DB)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--pit-check", action="store_true", help="measure filing dates against SEC tradeable dates")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    conn = finsaber.connect(args.db)
    if args.path:
        name = args.dataset or ("cherrypick" if "cherrypick" in args.path else
                                "sp500" if "sp500" in args.path else
                                os.path.splitext(os.path.basename(args.path))[0])
        print(import_pkl(conn, args.path, name))
    if args.pit_check:
        from universe import load_config
        main_db = sqlite3.connect(f"file:{load_config()['database']['market_data_path']}?mode=ro", uri=True)
        rep = pit_check(conn, main_db)
        json.dump(rep, open("data/finsaber_pit_report.json", "w"), indent=1)
        print(json.dumps(rep, indent=1))
        return 0
    for row in status(conn):
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
