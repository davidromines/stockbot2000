"""Regression tests for knowledge_extract (TASK-050). No network, no model."""
import runtime  # noqa: F401

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import knowledge_extract as ke

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


VALID = {"entry": {"op": "gt", "args": [{"op": "rank", "args": [{"col": "roc_10"}]},
                                        {"const": 0.9}]},
         "exit": {"op": "lt", "args": [{"col": "close"}, {"const": 0}]},
         "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20}}


def fenced(payload):
    return "Here you go:\n```json\n%s\n```\n" % json.dumps(payload)


def good_payload(**over):
    payload = {"fields": {f: "stated by source" for f in ke.FIELDS},
               "genome": VALID, "assumptions": ["assumed 20d hold"],
               "ambiguities": [], "missing_information": [],
               "translation_confidence": 0.7, "family": "MOMENTUM",
               "data_available": "YES"}
    payload.update(over)
    return payload


class FakeProvider:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def complete(self, system, user, max_tokens=2000, temperature=0.0):
        self.calls += 1
        text = self.texts.pop(0) if self.texts else ""

        class R:
            pass
        r = R()
        r.text = text
        r.model = "fake-model"
        r.prompt_tokens = 1
        r.completion_tokens = 1
        return r


class RaisingProvider:
    def __init__(self, fail_on):
        self.fail_on = fail_on
        self.calls = 0

    def complete(self, system, user, max_tokens=2000, temperature=0.0):
        self.calls += 1
        if self.fail_on in user:
            raise RuntimeError("boom")

        class R:
            pass
        r = R()
        r.text = fenced(good_payload())
        r.model = "fake-model"
        r.prompt_tokens = 1
        r.completion_tokens = 1
        return r


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE knowledge_entries(
        entry_id TEXT PRIMARY KEY, source TEXT, strategy_name TEXT,
        strategy_family TEXT, source_type TEXT, source_title TEXT,
        source_author TEXT, source_url TEXT, original_claim TEXT,
        original_market TEXT, original_asset_class TEXT,
        original_frequency TEXT, long_short TEXT, entry_rules TEXT,
        exit_rules TEXT, position_sizing TEXT, stop_loss TEXT,
        take_profit TEXT, holding_period TEXT, rebalance_frequency TEXT,
        required_data TEXT, translation_notes TEXT)""")
    conn.execute("INSERT INTO knowledge_entries(entry_id, source, source_title, "
                 "entry_rules, exit_rules, holding_period) VALUES "
                 "('e1','pwb_papers','A Paper','buy when rsi_14 < 30',"
                 "'sell after 5 days','5 days')")
    conn.execute("INSERT INTO knowledge_entries(entry_id, source, source_title) "
                 "VALUES ('e2','pwb_papers','Title Only')")
    conn.execute("INSERT INTO knowledge_entries(entry_id, source, source_title, "
                 "entry_rules) VALUES ('e3','other','Third','buy the dip')")
    conn.commit()
    ke.init(conn)
    return conn


def main():
    # --- validate_genome -------------------------------------------------
    check("valid genome accepted", ke.validate_genome(VALID) == [],
          ke.validate_genome(VALID))
    bad_col = json.loads(json.dumps(VALID))
    bad_col["entry"]["args"][0]["args"][0]["col"] = "not_a_column"
    check("unknown column rejected", ke.validate_genome(bad_col) != [])
    bad_op = json.loads(json.dumps(VALID))
    bad_op["entry"]["op"] = "frobnicate"
    check("unknown op rejected", ke.validate_genome(bad_op) != [])
    no_n = json.loads(json.dumps(VALID))
    no_n["entry"] = {"op": "pct_change", "args": [{"col": "close"}]}
    check("pct_change without n rejected", ke.validate_genome(no_n) != [])
    zero_hold = json.loads(json.dumps(VALID))
    zero_hold["risk"]["max_hold_days"] = 0
    check("max_hold_days 0 rejected", ke.validate_genome(zero_hold) != [])
    check("missing risk rejected", ke.validate_genome(
        {"entry": VALID["entry"], "exit": VALID["exit"]}) != [])

    # --- parse_response --------------------------------------------------
    good = ke.parse_response(fenced(good_payload()))
    check("good answer is YES", good["machine_translatable"] == "YES",
          good["machine_translatable"])
    partial_payload = good_payload()
    partial_payload["fields"] = dict(partial_payload["fields"])
    partial_payload["fields"]["holding_period"] = "requires_interpretation"
    partial = ke.parse_response(fenced(partial_payload))
    check("requires_interpretation is PARTIAL",
          partial["machine_translatable"] == "PARTIAL",
          partial["machine_translatable"])
    missing_payload = good_payload()
    missing_payload["fields"] = dict(missing_payload["fields"])
    del missing_payload["fields"]["liquidity"]
    missing = ke.parse_response(fenced(missing_payload))
    check("missing field filled with unspecified",
          missing["fields"]["liquidity"] == "unspecified",
          missing["fields"]["liquidity"])
    null_genome = ke.parse_response(fenced(good_payload(genome=None)))
    check("null genome is NO", null_genome["machine_translatable"] == "NO",
          null_genome["machine_translatable"])
    invalid = ke.parse_response(fenced(good_payload(genome=bad_col)))
    check("invalid genome is NO with error",
          invalid["machine_translatable"] == "NO" and invalid["errors"],
          invalid["errors"])
    garbage = ke.parse_response("no json here at all")
    check("garbage is unparseable NO",
          garbage["machine_translatable"] == "NO"
          and "unparseable response" in garbage["errors"],
          garbage["errors"])
    check("bad family becomes OTHER",
          ke.parse_response(fenced(good_payload(family="NOPE")))["family"]
          == "OTHER")

    # --- original_definition / build_prompt ------------------------------
    conn = make_db()
    entry = dict(conn.execute(
        "SELECT * FROM knowledge_entries WHERE entry_id='e1'").fetchone())
    od = ke.original_definition(entry)
    check("original_definition starts with title",
          od.splitlines()[0] == "title: A Paper", od.splitlines()[0])
    check("original_definition carries rule text",
          "entry_rules: buy when rsi_14 < 30" in od)
    system, user = ke.build_prompt(entry)
    check("prompt includes grammar and columns",
          "crosses_above" in system and "piotroski_f" in system
          and "MOMENTUM" in system)
    check("user message is the original definition", user == od)

    # --- translate -------------------------------------------------------
    provider = FakeProvider([fenced(good_payload())])
    parsed = ke.translate(conn, provider, entry)
    row = conn.execute("SELECT * FROM knowledge_translations WHERE entry_id='e1'"
                       ).fetchone()
    check("translate stored a row", row is not None)
    check("stored original_definition matches",
          row["original_definition"] == od)
    check("stored genome JSON round-trips",
          json.loads(row["genome"]) == VALID)
    check("translate returns parsed dict",
          parsed["machine_translatable"] == "YES")

    # --- pending ---------------------------------------------------------
    pend = ke.pending(conn)
    ids = [e["entry_id"] for e in pend]
    check("pending excludes translated entry", "e1" not in ids, ids)
    check("pending puts rule text first", ids[0] == "e3", ids)
    check("pending source filter works",
          [e["entry_id"] for e in ke.pending(conn, sources=["other"])] == ["e3"])

    # --- run -------------------------------------------------------------
    conn2 = make_db()
    raiser = RaisingProvider("Third")
    counts = ke.run(conn2, raiser)
    check("run counts the raising entry as an error", counts["errors"] == 1,
          counts)
    check("run translated the others", counts["translated"] == 2, counts)
    check("run counted YES", counts["yes"] == 2, counts)

    if FAILED:
        print("\n%d FAILED" % len(FAILED))
        sys.exit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
