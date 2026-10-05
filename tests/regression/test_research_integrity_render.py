"""Regression test: research_integrity.render must tolerate a forward fund with no label.

The Kalman fund (kf_kalman_e) was opened without a label; the unlabelled name
reached ', '.join(...) and failed the daily [9/10] stage with a TypeError.
Everything runs on a hand-built dict; no database is touched.
"""

import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import research_integrity as ri

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


def fund(run_id, label, equity, date="2026-10-02"):
    return {"run_id": run_id, "label": label, "family": None, "capital_usd": 100.0,
            "started_on": "2026-10-01", "equity_usd": equity, "date": date}


def dossier(forward):
    return {
        "generated": "2026-10-05T00:00:00+00:00",
        "trials": {"evaluations": 1, "promotions": 1, "backtests": 1, "total_trials": 3,
                   "unique_structures": 1, "effective_trials": 1},
        "noise_bar": 5.0, "delisted": 10, "delisted_priced": 1, "ancestry": {"INDEPENDENT": 1},
        "control": {}, "search_mode": "FROZEN", "forward": forward, "pair": [],
        "paper_trades": 0,
    }


def main() -> int:
    try:
        text = ri.render(dossier([
            fund("kf_kalman_e", None, None, date=None),      # never marked, no label
            fund("run_a", "Deep Value screen", 101.0),
            fund("run_b", None, 99.0),                        # marked, no label
        ]))
        ok = True
    except TypeError as e:
        text, ok = str(e), False
    check("render accepts funds with no label", ok, text)
    check("an unlabelled stalled fund is named by its run id", "kf_kalman_e" in text, text[-300:])
    check("an unlabelled live fund is named by its run id", "| run_b |" in text, text[-300:])
    check("a labelled fund keeps its label", "| Deep Value screen |" in text)

    print()
    if FAILED:
        print("  %d FAILED" % len(FAILED))
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
