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
PROMPT_VERSION = "1"

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

DATA WE HOLD
US stocks and ETFs, daily bars from 1962, SEC fundamentals. We do NOT hold forex, futures, commodities, crypto (for this factory), options, intraday bars, analyst estimates or news.
""" % (", ".join(FIELDS), ", ".join(FAMILIES), ", ".join(ALLOWED_COLS))


def build_prompt(entry):
    return _system_prompt(), original_definition(entry)


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


def translate(conn, provider, entry, rates=None):
    system, user = build_prompt(entry)
    resp = provider.complete(system, user, max_tokens=2000, temperature=0.0)
    parsed = parse_response(getattr(resp, "text", ""))
    entry_id = entry["entry_id"]
    model = getattr(resp, "model", None)
    conn.execute(
        "INSERT OR REPLACE INTO knowledge_translations VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (entry_id, datetime.now(timezone.utc).isoformat(), model,
         PROMPT_VERSION, original_definition(entry),
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
        except Exception:
            pass
    return parsed


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


def run(conn, provider, limit=50, sources=None, rates=None):
    counts = {"translated": 0, "yes": 0, "partial": 0, "no": 0, "errors": 0}
    for entry in pending(conn, limit=limit, sources=sources):
        try:
            parsed = translate(conn, provider, entry, rates=rates)
        except Exception as exc:
            counts["errors"] += 1
            print("  error %s: %s" % (entry["entry_id"], exc), file=sys.stderr)
            continue
        counts["translated"] += 1
        key = parsed["machine_translatable"].lower()
        if key in ("yes", "partial", "no"):
            counts[key] += 1
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
    args = ap.parse_args(argv)

    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        init(conn)
        if args.status:
            _status(conn)
        if args.run:
            provider = get_provider(cfg)
            counts = run(conn, provider, limit=args.limit,
                         sources=args.source, rates=cfg["ado"]["rates"])
            print(counts)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
