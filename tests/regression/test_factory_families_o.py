"""Regression: Stage O families register correctly and stay isolated."""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import strategy_factory as sf
import factory_families_o as fo

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)


def _nodes(n):
    yield n
    for a in n.get("args", []):
        yield from _nodes(a)


def _find_op(genome, op):
    return [n for n in _nodes(genome["entry"]) if n.get("op") == op]


def main():
    for name in fo.NEW_FAMILIES:
        check(f"registered:{name}", name in sf.F, "missing from strategy_factory.F")

    check("ten_families", len(fo.NEW_FAMILIES) == 10, str(len(fo.NEW_FAMILIES)))

    # turn_of_month: first grid point, entry references the calendar and liquidity
    fam = sf.F["turn_of_month"]
    pts = sf.grid_points(fam, 8)
    check("turn_of_month_grid", len(pts) >= 1, "no grid points")
    g = fam["build"](pts[0])
    entry_json = json.dumps(g["entry"])
    check("turn_of_month_entry_cal", "cal_tdom_rev" in entry_json, entry_json)
    check("turn_of_month_entry_liq", "log_dollar_volume" in entry_json, entry_json)
    check("turn_of_month_hold", g["risk"]["max_hold_days"] == 5,
          str(g["risk"]["max_hold_days"]))

    # seasonality_12m: lag(231) wrapping pct_change(21)
    fam = sf.F["seasonality_12m"]
    g = fam["build"](sf.grid_points(fam, 8)[0])
    lags = _find_op(g, "lag")
    check("seasonality_lag", len(lags) == 1 and lags[0]["n"] == 231,
          json.dumps(lags))
    inner = lags[0]["args"][0] if lags else {}
    check("seasonality_pct", inner.get("op") == "pct_change" and inner.get("n") == 21,
          json.dumps(inner))

    # These four lacked data until 2026-09-27; each now reads a column the shared loader
    # attaches (storage.attach_fundamentals), so each must be available and read it.
    import inspect
    import storage
    attached = set(storage.FUNDAMENTAL_PANEL_COLS) | {"alpha_252", "short_volume_ratio_20"}
    for name, col in (("small_cap", "market_cap"), ("rd_intensity", "rd_to_assets"),
                      ("short_interest", "short_volume_ratio_20"), ("capm_alpha", "alpha_252")):
        f = sf.F[name]
        check(f"available:{name}", f["data_available"] is True, str(f["data_available"]))
        g = f["build"]({k: v[0] for k, v in f["grid"].items()})
        check(f"reads {col}:{name}", col in json.dumps(g["entry"]) and col in attached, json.dumps(g["entry"]))
    src = inspect.getsource(storage.attach_fundamentals)
    check("the loader attaches short volume and alpha", "short_volume.attach" in src and "_attach_alpha" in src)

    for name in ("turn_of_month", "pre_holiday", "payday", "january_illiquid",
                 "seasonality_12m", "liquidity_premium"):
        check(f"available:{name}", sf.F[name]["data_available"] is True,
              str(sf.F[name]["data_available"]))

    for name in fo.NEW_FAMILIES:
        check(f"knowledge:{name}", name in fo.KNOWLEDGE and bool(fo.KNOWLEDGE[name]),
              "no knowledge entry")

    for name in fo.NEW_FAMILIES:
        check(f"grid_points:{name}", len(sf.grid_points(sf.F[name], 8)) >= 1,
              "no grid points")

    # freeze boundary: no evolutionary machinery referenced
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "factory_families_o.py")).read()
    check("no_evolve_import", "import evolve" not in src and "from evolve" not in src, "")
    check("no_seeds_import", "import seeds" not in src and "from seeds" not in src, "")

    if FAILED:
        print(f"\n  {len(FAILED)} FAILED")
        return 1
    print("\n  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
