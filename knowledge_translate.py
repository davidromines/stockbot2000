"""
Stage O3/O4, first pass — which documented strategies can Stockbot test, and
with what.

For every knowledge entry that carries a rule description (the 60 PWB coded
strategies and the 84 QuantConnect Strategy Library entries):

1. DATA. Our database holds US equities and ETFs, daily bars, SEC
   fundamentals. A strategy on forex, futures, options, crypto, bonds or
   intraday bars cannot be tested here — recorded as data_available = NO with
   the reason. That is not a refutation and is never reported as one.
2. FAMILY. Where the source's rule is the same economic idea as one of the 40
   strategy_factory families, the entry is linked to that family's tested
   strategy objects as a SOURCE_DERIVED_VARIANT — never a reproduction: the
   sources describe long-short, monthly-rebalanced portfolios of hundreds of
   stocks; our slots hold single long positions with a stop. The difference is
   written into translation_notes (§7-8: never invent, always label).
3. Everything testable that matches no family is listed as NEEDS_TEMPLATE —
   the build list for the next templates.

Keyword rules, not judgement calls, so the result is reproducible and every
decision carries the rule that made it.

    ./venv/bin/python knowledge_translate.py --run
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import knowledge_library as kl

NO_DATA = [  # (reason, patterns) — first match wins
    ("options / implied volatility", r"\boption|implied vol|\bvix\b|variance risk premium|dispersion trading|straddle|volatility risk premium"),
    ("forex", r"\bforex\b|\bfx\b|currenc|carry trade|exchange rate|\bppp\b"),
    ("futures / commodities", r"futures|commodit|crude oil|\boil\b|\bgold\b|wti|brent|natural gas|term structure"),
    ("crypto", r"bitcoin|crypto|ethereum"),
    ("bonds", r"\bbond|treasur|yield curve|credit spread"),
    ("intraday bars", r"intraday|minute|hourly|overnight|opening range|\bgap\b"),
    ("non-US equities", r"\beurope|\bchina|\bjapan|frontier|emerging market|country (?:equity )?ind|international"),
    ("text / alternative data", r"sentiment|lexical|twitter|news|esg|google|lunar|weather"),
]
FAMILY_MAP = [  # (factory family, patterns)
    ("breakout_52w", r"52[- ]?weeks? high"),
    ("low_accruals", r"accrual"),
    # NOT "investment" alone: nearly every description opens "The investment universe consists of..."
    ("low_investment", r"asset growth|low investment|investment effect|capital expenditure|capex"),
    ("quality_piotroski", r"f-?score|piotroski"),
    ("profitability", r"gross profitab|profitability"),
    ("value_book", r"book[- ]to[- ]market|value effect|value factor|\bb/m\b"),
    ("earnings_yield", r"earnings yield|\be/p\b|price[- ]to[- ]earnings"),
    ("buyback", r"repurchase|buyback"),
    ("dividend", r"dividend"),
    ("earnings_revision", r"earnings announcement|post-earnings|earnings surprise|\bsue\b|analyst"),
    ("low_volatility", r"low[- ]volatility|betting against beta|low beta|idiosyncratic vol"),
    ("ts_momentum", r"time[- ]series momentum|trend[- ]following|asset class trend"),
    ("xs_momentum", r"momentum"),
    ("rsi_reversion", r"short[- ]term reversal|reversal|mean reversion|contrarian"),
    ("ma_cross", r"moving average|golden cross"),
]


def _text(conn, e) -> str:
    """Source text for one entry: the cached description (never stored in the DB for PWB)."""
    src, raw = e["source"], e["raw_cache"]
    if src == "pwb_coded" and raw and Path(raw).exists():
        _, desc = kl._header_comment(Path(raw).read_text(errors="replace"))
        return f"{e['strategy_name']} {desc}"
    if src == "qc_library":
        return f"{e['strategy_name']} {e['entry_rules'] or ''}"
    return e["strategy_name"]


def ensure_columns(conn) -> None:
    have = {r[1] for r in conn.execute("PRAGMA table_info(knowledge_entries)")}
    for col in ("data_available", "data_reason", "factory_family", "translation_state"):
        if col not in have:
            conn.execute(f"ALTER TABLE knowledge_entries ADD COLUMN {col} TEXT")
    conn.commit()


def run(conn) -> dict:
    conn.row_factory = sqlite3.Row
    ensure_columns(conn)
    rows = conn.execute("SELECT * FROM knowledge_entries WHERE source IN ('pwb_coded','qc_library')").fetchall()
    fam_keys = {}
    # Factory objects are registered in the league under fx_<family>_<hash>, family in league_strategies.
    for (k, v, fam) in conn.execute("SELECT strategy_key, version, family FROM league_strategies "
                                    "WHERE strategy_key LIKE 'fx_%'").fetchall():
        fam_keys.setdefault(fam, []).append((k, v))
    out = {"no_data": {}, "linked": {}, "needs_template": []}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for e in rows:
        t = _text(conn, e).lower()
        reason = next((r for r, pat in NO_DATA if re.search(pat, t)), None)
        fam = next((f for f, pat in FAMILY_MAP if re.search(pat, t)), None)
        if reason:
            conn.execute("UPDATE knowledge_entries SET data_available='NO', data_reason=?, translation_state="
                         "'DATA_UNAVAILABLE', translation_notes=? WHERE entry_id=?",
                         (reason, f"not testable on Stockbot's data ({reason}); not a refutation", e["entry_id"]))
            out["no_data"][reason] = out["no_data"].get(reason, 0) + 1
        elif fam:
            note = (f"SOURCE_DERIVED_VARIANT via factory family {fam}: same economic idea; differs from the source "
                    f"in construction — long-only single positions with a stop and a max hold, US common stock "
                    f"above $5 and $1M/day, next-open fills and costs, vs the source's portfolio (often long-short, "
                    f"monthly rebalanced). A result here tests our encoding, not the source (§8).")
            conn.execute("UPDATE knowledge_entries SET data_available='YES', factory_family=?, machine_translatable="
                         "'YES', translation_state='SOURCE_DERIVED_VARIANT', translation_notes=? WHERE entry_id=?",
                         (fam, note, e["entry_id"]))
            for k, v in fam_keys.get(fam, []):
                conn.execute("INSERT OR IGNORE INTO knowledge_links VALUES (?,?,?,?,?)",
                             (e["entry_id"], k, v, "SOURCE_DERIVED_VARIANT", now))
            out["linked"][fam] = out["linked"].get(fam, 0) + 1
        else:
            conn.execute("UPDATE knowledge_entries SET data_available='YES', translation_state='NEEDS_TEMPLATE', "
                         "translation_notes='testable on our data; no existing family encodes it — a new template "
                         "is needed (O3)' WHERE entry_id=?", (e["entry_id"],))
            out["needs_template"].append(e["strategy_name"])
    conn.commit()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="First translation pass over the Knowledge Library (Stage O3/O4).")
    ap.add_argument("--run", action="store_true")
    ap.parse_args(argv)
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    kl.init(conn)
    o = run(conn)
    n = sum(o["no_data"].values()) + sum(o["linked"].values()) + len(o["needs_template"])
    print(f"\n  TRANSLATION, FIRST PASS — {n} strategies with rule descriptions")
    print(f"\n  not testable on our data: {sum(o['no_data'].values())}")
    for r, k in sorted(o["no_data"].items(), key=lambda x: -x[1]):
        print(f"    {r:<30} {k}")
    print(f"\n  linked to an existing family (SOURCE_DERIVED_VARIANT): {sum(o['linked'].values())}")
    for f, k in sorted(o["linked"].items(), key=lambda x: -x[1]):
        print(f"    {f:<30} {k}")
    print(f"\n  testable, needs a new template: {len(o['needs_template'])}")
    for nme in sorted(o["needs_template"]):
        print(f"    {nme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
