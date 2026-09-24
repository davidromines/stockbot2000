"""
The template path must not feed the frozen evolutionary search (B16).

Template families are governed separately from evolve.py; that separation is
only real while no factory output can reach the evolutionary population. This
test fails if any search-side file starts referencing a factory module or
table. Crossing that boundary is allowed only with the freeze applied there.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SEARCH_SIDE = ["evolve.py", "genome.py", "seeds.py", "lab_loop.sh", "promote.py"]
FACTORY = ["strategy_factory", "factory_pipeline", "library_bridge", "research_queue",
           "strategy_meta", "strategy_objects", "discovery"]


def main():
    failed = []
    for name in SEARCH_SIDE:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        text = open(path).read()
        hits = [f for f in FACTORY if re.search(rf"\b{f}\b", text)]
        if hits:
            print(f"  FAIL  {name} references {hits}")
            failed.append(name)
        else:
            print(f"  PASS  {name} does not reference the factory")
    print()
    if failed:
        print(f"  {len(failed)} FAILED: {', '.join(failed)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
