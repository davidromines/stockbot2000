"""Knowledge Factory machine translation layer (Addendum E rev 2 §8, N3).

Turns a documented strategy's own words into explicit fields plus a Stockbot
genome interpretation. The source's text is stored verbatim; anything the
source does not state is marked UNSTATED rather than guessed, because this
project's failure mode is a plausible-looking number that was never in the
source.
"""
import runtime  # noqa: F401  (thread limits must be set before numeric imports)

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone

from llm import get_provider
from llm import provider as prov

FIELDS = ("universe", "entry", "exit", "ranking", "lookback", "holding_period",
          "rebalance", "position_sizing", "long_short", "stop", "take_profit",
          "risk_rules", "required_data", "regime_filter", "liquidity")
UNSTATED = ("unspecified", "unknown", "requires_interpretation")
FAMILIES = ("MOMENTUM", "TREND", "MEAN_REVERSION", "VALUE", "QUALITY",
            "LOW_VOLATILITY", "SIZE", "REVERSAL", "EARNINGS_SURPRISE",
            "ANALYST_REVISION", "SEASONALITY", "BREAKOUT", "VOLATILITY",
            "LIQUIDITY", "PAIRS", "RELATIVE_VALUE", "FACTOR", "REGIME",
            "EVENT", "FUNDAMENTAL", "HYBRID", "OTHER")
ALLOWED_COLS = (
    "close", "volume", "returns", "dollar_volume_20",
    "sma_50", "sma_200", "rsi_14", "roc_10", "adx_14", "macd", "macd_signal",
    "macd_hist", "bb_pct", "vol_ratio", "price_above_sma50",
    "price_above_sma200", "golden_cross", "atr_14", "stoch_k", "stoch_d",
    "obv_rising", "cci_20", "willr_14", "chaikin_osc", "pct_of_52w_high",
    "pct_off_52w_low", "drawdown_200", "log_dollar_volume",
    "piotroski_f", "book_to_market", "gross_profitability", "chs_distress",
    "asset_growth", "accruals", "roa", "earnings_yield", "net_share_issuance",
    "debt_to_equity", "cash_to_assets", "altman_z", "fcf_to_price",
    "rd_to_assets", "market_cap", "sue", "sue_age", "alpha_252",
    "short_volume_ratio_20", "analog_p_up", "analog_mean", "analog_q10",
    "composite", "insider_buy_usd_90", "insider_buyers_90", "opp_buyers_90",
    "cal_month", "cal_dom", "cal_tdom", "cal_tdom_rev", "cal_pre_holiday",
    "cal_post_holiday",
)
PROMPT_VERSION = "5"   # 5: paper pages for title-only entries; 4: column glossary, long leg of long-short; 2: cached source text in the prompt; 3: verification pass

# The source's own words, in the order they should be read. Title first.
SOURCE_COLS = (
    ("source_title", "title"),
    ("source", "source"),
    ("source_type", "source_type"),
    ("source_author", "author"),
    ("source_url", "url"),
    ("strategy_name", "strategy_name"),
    ("strategy_family", "source_family"),
    ("original_claim", "claim"),
    ("original_market", "market"),
    ("original_asset_class", "asset_class"),
    ("original_frequency", "frequency"),
    ("long_short", "long_short"),
    ("entry_rules", "entry_rules"),
    ("exit_rules", "exit_rules"),
    ("position_sizing", "position_sizing"),
    ("stop_loss", "stop_loss"),
    ("take_profit", "take_profit"),
    ("holding_period", "holding_period"),
    ("rebalance_frequency", "rebalance_frequency"),
    ("required_data", "required_data"),
    ("translation_notes", "translation_notes"),
)

_TS_OPS = ("lag", "delta", "zscore", "pct_change")
_CMP_OPS = ("gt", "lt", "crosses_above", "crosses_below")
_LOGIC_OPS = ("and", "or", "not")
_CS_OPS = ("rank",)
_ARITY = {"gt": 2, "lt": 2, "crosses_above": 2, "crosses_below": 2,
          "and": 2, "or": 2, "not": 1, "rank": 1}
_KNOWN_OPS = tuple(_ARITY) + _TS_OPS


def init(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_translations(
            entry_id TEXT PRIMARY KEY,
            translated_at TEXT,
            model TEXT,
            prompt_version TEXT,
            original_definition TEXT,
            fields TEXT,
            genome TEXT,
            assumptions TEXT,
            ambiguities TEXT,
            missing_information TEXT,
            translation_confidence REAL,
            machine_translatable TEXT,
            family TEXT,
            data_available TEXT,
            errors TEXT
        )""")
    conn.commit()


def original_definition(entry):
    """The source's own words, verbatim. Never rewritten, never summarised."""
    lines = []
    for col, label in SOURCE_COLS:
        try:
            val = entry[col]
        except (KeyError, IndexError):
            val = None
        if val is None:
            continue
        val = str(val).strip()
        if val:
            lines.append("%s: %s" % (label, val))
    return "\n".join(lines)


def _system_prompt():
    return """You translate a documented trading strategy into explicit fields and, separately, into a Stockbot genome.

RULES
1. Extract ONLY what the source states. For every field, use the source's own wording.
2. If the source does not state a field, set it to exactly one of: "unspecified", "unknown", "requires_interpretation". Never invent a number, a threshold, a lookback or a universe the source does not give.
3. The genome is a Stockbot INTERPRETATION, not a quotation. It may fill gaps, but every gap it fills must be listed in "assumptions".
4. If the strategy needs data Stockbot does not hold, set genome to null and data_available to "NO: <reason>".
5. Answer with ONE JSON object inside a ```json fenced block, with exactly these keys:
   fields, genome, assumptions, ambiguities, missing_information, translation_confidence, family, data_available.

"fields" is an object with exactly these keys: %s
"translation_confidence" is a number in 0..1.
"family" is exactly one of: %s
"data_available" is "YES" or "NO: <reason>".

GENOME GRAMMAR
A genome is {"entry": NODE, "exit": NODE, "risk": {"stop_atr_multiple": float, "max_hold_days": int}}.
A NODE is one of {"col": NAME}, {"const": number}, {"op": OP, "args": [NODE, ...]}, and for time-series ops also "n": int.
OPs: comparisons gt, lt, crosses_above, crosses_below (2 args); logic and, or (2 args), not (1 arg); time-series within a ticker lag, delta, zscore, pct_change (1 arg plus "n"); cross-sectional rank (1 arg, percentile 0-1 across stocks that day).
Positions are long only, one stock per position, $20 each. "Buy the top decile of X" is {"op":"gt","args":[{"op":"rank","args":[{"col":"X"}]},{"const":0.9}]}.
An exit that never fires is {"op":"lt","args":[{"col":"close"},{"const":0}]} (exit by stop or holding period only).
stop_atr_multiple must be in 0.5..10; max_hold_days must be in 1..504.

ALLOWED COLUMN NAMES
%s

COLUMN MEANINGS (use the inverse when the source ranks on the reciprocal)
book_to_market = book equity / market cap (the inverse of P/B: "low P/B" = high book_to_market);
earnings_yield = earnings / price (inverse of P/E); fcf_to_price = (operating cash flow - capex) / market cap;
gross_profitability = gross profit / assets; roa = net income / assets; market_cap in dollars (size);
asset_growth, accruals, net_share_issuance, debt_to_equity, piotroski_f (0-9), altman_z, chs_distress (higher = more distress);
sue = standardised unexpected earnings (earnings surprise); returns = one-day return; roc_10 = 10-day rate of change ONLY;
a return over N months is {"op":"pct_change","args":[{"col":"close"}],"n":21*N} (12-1 momentum: lag that by 21);
volatility has no column: use atr_14 relative to close, or zscore; rsi_14, bb_pct, stoch_k, willr_14, cci_20 are the usual oscillators;
pct_of_52w_high = close / 52-week high; drawdown_200 = distance below the 200-day high.
LONG-SHORT SOURCES: encode the LONG leg only and say so in assumptions — that is a valid translation, not a reason for data_available NO.

DATA WE HOLD
US stocks and ETFs, daily bars from 1962, SEC fundamentals. We do NOT hold forex, futures, commodities, crypto (for this factory), options, intraday bars, analyst estimates or news.
""" % (", ".join(FIELDS), ", ".join(FAMILIES), ", ".join(ALLOWED_COLS))


CACHE_CHARS = 12000


def _cached_source(entry):
    """The locally cached source text (code or description), for the prompt only.

    Its licence is often unstated, so it is never copied into the database; the
    stored record names the file and its hash instead (knowledge_library's rule)."""
    import hashlib
    from pathlib import Path
    try:
        path = entry["raw_cache"]
    except (KeyError, IndexError):
        return None, None
    if not path or not Path(path).is_file():
        return None, None
    raw = Path(path).read_bytes()
    return raw.decode("utf-8", "replace")[:CACHE_CHARS], f"{path} sha256:{hashlib.sha256(raw).hexdigest()[:16]}"


def build_prompt(entry):
    user = original_definition(entry)
    text, ref = _cached_source(entry)
    if text:
        user += f"\n\nCACHED SOURCE TEXT ({ref}; the source's own code or description):\n{text}"
    return _system_prompt(), user


def _validate_node(node, path, errors):
    if not isinstance(node, dict):
        errors.append("%s: node is not an object" % path)
        return
    if "col" in node:
        col = node["col"]
        if col not in ALLOWED_COLS:
            errors.append("%s: unknown column %r" % (path, col))
        return
    if "const" in node:
        val = node["const"]
        # bool is an int subclass; a boolean constant is a type error here.
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            errors.append("%s: const is not a number" % path)
        elif val != val or val in (float("inf"), float("-inf")):
            errors.append("%s: const is not finite" % path)
        return
    if "op" not in node:
        errors.append("%s: node has neither col, const nor op" % path)
        return
    op = node["op"]
    if op not in _KNOWN_OPS:
        errors.append("%s: unknown op %r" % (path, op))
        return
    args = node.get("args")
    if not isinstance(args, list):
        errors.append("%s: op %r has no args list" % (path, op))
        return
    if op in _ARITY:
        if len(args) != _ARITY[op]:
            errors.append("%s: op %r takes %d args, got %d"
                          % (path, op, _ARITY[op], len(args)))
    elif len(args) != 1:
        errors.append("%s: op %r takes 1 arg, got %d" % (path, op, len(args)))
    if op in _TS_OPS:
        n = node.get("n")
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 504:
            errors.append("%s: op %r needs integer n in 1..504" % (path, op))
    for i, arg in enumerate(args):
        _validate_node(arg, "%s.args[%d]" % (path, i), errors)


def validate_genome(g):
    errors = []
    if not isinstance(g, dict):
        return ["genome is not an object"]
    for key in ("entry", "exit", "risk"):
        if key not in g:
            errors.append("missing %s" % key)
    if "entry" in g:
        _validate_node(g["entry"], "entry", errors)
    if "exit" in g:
        _validate_node(g["exit"], "exit", errors)
    risk = g.get("risk")
    if risk is not None:
        if not isinstance(risk, dict):
            errors.append("risk is not an object")
        else:
            stop = risk.get("stop_atr_multiple")
            if isinstance(stop, bool) or not isinstance(stop, (int, float)):
                errors.append("risk.stop_atr_multiple is not a number")
            elif stop != stop or not 0.5 <= stop <= 10:
                errors.append("risk.stop_atr_multiple outside 0.5..10")
            hold = risk.get("max_hold_days")
            if isinstance(hold, bool) or not isinstance(hold, int):
                errors.append("risk.max_hold_days is not an integer")
            elif not 1 <= hold <= 504:
                errors.append("risk.max_hold_days outside 1..504")
    return errors


def _extract_json_block(text):
    if not text:
        return None
    match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


def _unparseable():
    return {"fields": {f: "unspecified" for f in FIELDS}, "genome": None,
            "assumptions": [], "ambiguities": [], "missing_information": [],
            "translation_confidence": 0.0, "family": "OTHER",
            "data_available": "NO: unparseable response",
            "errors": ["unparseable response"], "machine_translatable": "NO"}


def parse_response(text):
    raw = _extract_json_block(text)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return _unparseable()
    if not isinstance(data, dict):
        return _unparseable()

    fields = data.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    # A field the model omitted is unstated, not empty: an empty string would
    # read downstream as "the source says nothing here", which is a different
    # claim from "we did not extract it".
    out_fields = {}
    for f in FIELDS:
        val = fields.get(f)
        out_fields[f] = val if val not in (None, "") else "unspecified"

    genome = data.get("genome")
    if genome is not None and not isinstance(genome, dict):
        genome = None

    family = data.get("family")
    if family not in FAMILIES:
        family = "OTHER"

    conf = data.get("translation_confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        conf = 0.0
    if conf != conf:
        conf = 0.0
    conf = max(0.0, min(1.0, float(conf)))

    errors = validate_genome(genome) if genome is not None else []

    if genome is None or errors:
        machine = "NO"
    elif any(out_fields[f] in UNSTATED
             for f in ("entry", "exit", "holding_period", "universe")):
        machine = "PARTIAL"
    else:
        machine = "YES"

    data_available = data.get("data_available")
    if not isinstance(data_available, str) or not data_available.strip():
        data_available = "NO: not stated by the model"

    return {"fields": out_fields, "genome": genome,
            "assumptions": data.get("assumptions") or [],
            "ambiguities": data.get("ambiguities") or [],
            "missing_information": data.get("missing_information") or [],
            "translation_confidence": conf, "family": family,
            "data_available": data_available, "errors": errors,
            "machine_translatable": machine}


VERIFY_SYSTEM = """You check a translation of a documented trading strategy into a genome.
For EVERY condition in the genome check, against the source text and the stated assumptions:
the direction (gt vs lt; a high-value leg is rank > q, a low-value leg is rank < q), the column
(does it measure what the source ranks on?), the threshold and the holding period.
Answer with ONE JSON object in a ```json fenced block: {"ok": true|false, "problems": [strings],
"genome": the corrected genome (or the same genome when ok)}. Change only what is wrong; never add
conditions the source does not state."""


def verify(provider, entry, parsed):
    """Second pass: the genome checked against the source and its own assumptions (a first
    trial translated 'buy high book-to-market' as rank(book_to_market) < 0.2). Returns
    (genome, problems, response)."""
    if parsed.get("genome") is None:
        return None, [], None
    _, user = build_prompt(entry)
    user += ("\n\nPROPOSED GENOME:\n" + json.dumps(parsed["genome"]) +
             "\n\nSTATED ASSUMPTIONS:\n" + json.dumps(parsed.get("assumptions") or []))
    resp = provider.complete(VERIFY_SYSTEM, user, max_tokens=1500, temperature=0.0)
    raw = _extract_json_block(getattr(resp, "text", ""))
    try:
        v = json.loads(raw)
    except (ValueError, TypeError):
        return parsed["genome"], ["verification unparseable"], resp
    if not isinstance(v, dict):
        return parsed["genome"], ["verification unparseable"], resp
    probs = [str(x) for x in (v.get("problems") or [])]
    g = v.get("genome") if isinstance(v.get("genome"), dict) else parsed["genome"]
    if validate_genome(g):
        return parsed["genome"], probs + ["verified genome invalid; first genome kept"], resp
    return g, probs, resp


def compute(provider, entry):
    """The model work for one entry — prompt, answer, parse, verification — with no database
    access, so several can run in parallel threads. Returns (parsed, resp, vresp)."""
    system, user = build_prompt(entry)
    resp = provider.complete(system, user, max_tokens=2000, temperature=0.0)
    parsed = parse_response(getattr(resp, "text", ""))
    vresp = None
    if parsed.get("genome") is not None and not parsed.get("errors"):
        g, probs, vresp = verify(provider, entry, parsed)
        if probs:
            parsed["ambiguities"] = list(parsed["ambiguities"]) + [f"verification: {p}" for p in probs]
        if g != parsed["genome"]:
            parsed["assumptions"] = list(parsed["assumptions"]) + [
                "genome corrected by the verification pass; first version: " + json.dumps(parsed["genome"])]
            parsed["genome"] = g
    return parsed, resp, vresp


def store(conn, entry, parsed, resp, vresp=None, rates=None):
    entry_id = entry["entry_id"]
    model = getattr(resp, "model", None)
    conn.execute(
        "INSERT OR REPLACE INTO knowledge_translations VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (entry_id, datetime.now(timezone.utc).isoformat(), model,
         PROMPT_VERSION, original_definition(entry) + (
             f"\ncached source: {_cached_source(entry)[1]}" if _cached_source(entry)[1] else ""),
         json.dumps(parsed["fields"]),
         json.dumps(parsed["genome"]) if parsed["genome"] is not None else None,
         json.dumps(parsed["assumptions"]),
         json.dumps(parsed["ambiguities"]),
         json.dumps(parsed["missing_information"]),
         parsed["translation_confidence"], parsed["machine_translatable"],
         parsed["family"], parsed["data_available"],
         json.dumps(parsed["errors"])))
    conn.commit()
    if rates:
        # Fake providers in tests have no real model; recording is best-effort.
        try:
            prov.record(conn, resp, "knowledge_extract", entry_id, rates)
            if vresp is not None:
                prov.record(conn, vresp, "knowledge_verify", entry_id, rates)
        except Exception:
            pass
    return parsed


def translate(conn, provider, entry, rates=None):
    parsed, resp, vresp = compute(provider, entry)
    return store(conn, entry, parsed, resp, vresp, rates)


def pending(conn, limit=50, sources=None):
    sql = ("SELECT e.* FROM knowledge_entries e "
           "LEFT JOIN knowledge_translations t ON t.entry_id = e.entry_id "
           "WHERE t.entry_id IS NULL")
    params = []
    if sources:
        sql += " AND e.source IN (%s)" % ",".join("?" * len(sources))
        params.extend(sources)
    # Entries with rule text carry the most extractable signal, so they go
    # first; the ordering is deterministic so reruns are reproducible.
    sql += (" ORDER BY CASE WHEN e.entry_rules IS NULL OR TRIM(e.entry_rules)='' "
            "THEN 1 ELSE 0 END, e.entry_id LIMIT ?")
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# Measured 2026-09-28: 2,185 extractions + 183 verifications cost $2.49 -> ~$0.0012 per entry.
COST_PER_ENTRY_USD = 0.0012


def pending_count(conn) -> int:
    """Library entries not yet translated. Pure SQL — no model call."""
    return conn.execute("SELECT COUNT(*) FROM knowledge_entries e "
                        "LEFT JOIN knowledge_translations t ON t.entry_id = e.entry_id "
                        "WHERE t.entry_id IS NULL").fetchone()[0]


def pending_alert(conn, send=True) -> str | None:
    """Owner, 2026-09-28: translation is a by-hand DeepSeek job, so the daily run
    only tells the owner when entries are waiting. Returns the message (None if 0)."""
    n = pending_count(conn)
    if not n:
        return None
    msg = (f"{n} new strategy-library entries are waiting to be translated "
           f"(DeepSeek, est. ${n * COST_PER_ENTRY_USD:.2f}). Ask Claude: "
           f"\"translate the pending library entries\".")
    if send:
        import notify
        notify.notify("Stockbot2000: library entries waiting", msg)
    return msg


def run(conn, provider, limit=50, sources=None, rates=None, workers=1):
    """Translate pending entries. With workers > 1 the model calls run in parallel threads;
    every database write stays on this thread (sqlite writers must not overlap)."""
    counts = {"translated": 0, "yes": 0, "partial": 0, "no": 0, "errors": 0}
    todo = pending(conn, limit=limit, sources=sources)

    def done(entry, parsed, resp, vresp):
        store(conn, entry, parsed, resp, vresp, rates)
        counts["translated"] += 1
        key = parsed["machine_translatable"].lower()
        if key in ("yes", "partial", "no"):
            counts[key] += 1

    if workers <= 1:
        for entry in todo:
            try:
                done(entry, *compute(provider, entry))
            except Exception as exc:
                counts["errors"] += 1
                print("  error %s: %s" % (entry["entry_id"], exc), file=sys.stderr)
        return counts
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(compute, provider, e): e for e in todo}
        for f in as_completed(futs):
            entry = futs[f]
            try:
                done(entry, *f.result())
            except Exception as exc:
                counts["errors"] += 1
                print("  error %s: %s" % (entry["entry_id"], exc), file=sys.stderr)
    return counts


def _status(conn):
    rows = conn.execute(
        "SELECT machine_translatable, COUNT(*) FROM knowledge_translations "
        "GROUP BY machine_translatable").fetchall()
    print("machine_translatable:")
    for val, n in rows:
        print("  %-8s %d" % (val, n))
    rows = conn.execute(
        "SELECT family, COUNT(*) FROM knowledge_translations "
        "GROUP BY family ORDER BY COUNT(*) DESC").fetchall()
    print("family:")
    for val, n in rows:
        print("  %-20s %d" % (val, n))


def main(argv=None):
    from universe import load_config
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--source", action="append", default=None)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--pending-alert", action="store_true",
                    help="count untranslated entries and notify the owner (no model call)")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        init(conn)
        if args.status:
            _status(conn)
        if args.pending_alert:
            print(pending_alert(conn) or "no library entries waiting")
        if args.run:
            provider = get_provider(cfg)
            counts = run(conn, provider, limit=args.limit,
                         sources=args.source, rates=cfg["ado"]["rates"], workers=args.workers)
            print(counts)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
