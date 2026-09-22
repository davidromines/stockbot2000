"""
What does random look like after passing through THIS pipeline? Phase 6 section 17.

THE QUESTION THIS ANSWERS
--------------------------
`control.py` asks a yes/no question — does the validation gate filter noise? —
and answers it with a pass rate. That is necessary and not sufficient. The
question that actually governs how a result should be read is:

    How impressive can a random strategy look after passing through this exact
    research pipeline?

Not the average random strategy. The *best* one. A search reports its winner,
so the honest comparison is against the best of an equally large collection of
things known to be worthless. Every published number in this project should be
placed against that distribution before anyone decides it means something.

WHY IT PERSISTS
---------------
The table is append-only and accumulates across runs, for the same reason the
trial ledger is: a distribution built from 200 samples and thrown away is a
worse calibration than one built from 200 a night over months. Nothing here is
ever deleted or recomputed — a control run that produced an inconvenient
distribution is exactly the one worth keeping.

WHAT IS MEASURED
----------------
Returns, Sharpe, drawdown, win rate and turnover, each on the validation window
through the identical panel, cost model, null surface and fitness function a
real candidate faces. If any of those change, the old rows describe a pipeline
that no longer exists — so each row records the config fingerprint it was
produced under, and `report()` refuses to pool rows across fingerprints.

Usage:
    python random_control.py --run 200        # add 200 random genomes
    python random_control.py --report         # the distribution so far
    python random_control.py --place sharpe 1.8   # where does 1.8 sit in noise?
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone

import numpy as np

import benchmark as bench
import costs as costs_mod
import control
import genome as gn
import reward
import simulator
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rcontrol")

METRICS = ("net_pnl_usd", "excess_pnl_usd", "sharpe", "max_drawdown",
           "win_rate", "turnover")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS random_control (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            at              TEXT NOT NULL,
            fingerprint     TEXT NOT NULL,
            window          TEXT NOT NULL,
            genome          TEXT,
            n_trades        INTEGER,
            n_signals       INTEGER,
            entries_capped  INTEGER,
            net_pnl_usd     REAL,
            excess_pnl_usd  REAL,
            sharpe          REAL,
            max_drawdown    REAL,
            win_rate        REAL,
            turnover        REAL,
            passed_gate     INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_rc_fp ON random_control(fingerprint)")
    conn.commit()


def fingerprint(cfg: dict) -> str:
    """
    Identifies the pipeline that produced a row.

    Only the parts that move the distribution are included. Pooling rows from
    before and after a fitness change would build a calibration for a pipeline
    that never existed, and the mistake would be invisible — the numbers would
    still look like a distribution.
    """
    lab, risk = cfg["lab"], cfg["risk"]
    material = {
        "window": [lab["validation_start"], lab["validation_end"]],
        "gates": lab.get("gates", {}),
        "max_depth": lab.get("max_depth"),
        "max_entries": lab.get("max_entries_per_eval"),
        "position_size_usd": risk["position_size_usd"],
        "max_open_positions": risk["max_open_positions"],
        "min_price": risk.get("min_price"),
        "min_dollar_volume": risk.get("min_dollar_volume"),
        "reward": cfg.get("reward", {}),
        "costs": cfg.get("costs", {}),
        "price_band_edges": cfg.get("benchmark", {}).get("price_band_edges"),
    }
    blob = json.dumps(material, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _turnover(res: dict, years: float) -> float:
    """
    Signals per year, from the count BEFORE uniform subsampling.

    `n_trades` saturates at `max_entries_per_eval`, so using it here made the
    first control run report p95, p99 and max all equal to 20000/3 — the
    sampling cap, identical for every busy strategy, presented as a
    distribution. Turnover is the one metric of the five that the cap destroys.
    """
    # Not res.get("n_signals", res["n_trades"]): a dict default is evaluated
    # eagerly, so that form raises on a result carrying only the new key.
    n = res["n_signals"] if "n_signals" in res else res.get("n_trades", 0)
    if years <= 0 or not n:
        return 0.0
    return float(n) / years


def run(cfg: dict, n: int, seed: int | None = None) -> dict:
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    init(conn)
    lab = cfg["lab"]
    valid_w = (lab["validation_start"], lab["validation_end"])
    fp = fingerprint(cfg)

    # A fresh seed per run by default. A fixed seed would make every run redraw
    # the same genomes, so the table would grow without the distribution
    # gaining any information — the failure mode is silent because the row
    # count still rises.
    if seed is None:
        seed = int(datetime.now(timezone.utc).timestamp()) & 0x7FFFFFFF

    log.info(f"loading validation panel {valid_w[0]}..{valid_w[1]}")
    panel, df = control._panel(conn, cfg, valid_w)
    surf = bench.null_surface(conn, cfg, valid_w)

    years = max((np.datetime64(valid_w[1]) - np.datetime64(valid_w[0]))
                / np.timedelta64(365, "D"), 1e-9)
    stats = gn.column_stats(df, FEATURE_COLS + gn.BASE_PRIMITIVES)
    grammar = gn.Grammar(FEATURE_COLS, stats, max_depth=lab.get("max_depth", 4),
                         seed=seed)
    cm = costs_mod.CostModel(cfg)
    rp = reward.params_from_config(cfg)
    size = cfg["risk"]["position_size_usd"]
    capital = size * cfg["risk"]["max_open_positions"]
    max_entries = lab.get("max_entries_per_eval", 20000)
    gates = lab.get("gates", {})

    rows, passed = [], 0
    for i in range(n):
        g = grammar.random_genome()
        res = simulator.simulate(g, panel, cm, size, max_entries=max_entries)
        fit = reward.fitness(res, gn.complexity(g), capital_usd=capital,
                             benchmark_surface=surf, position_size_usd=size, cfg=rp)
        ok = (fit.get("excess_pnl_usd", 0) >= gates.get("min_excess_pnl_usd", 0)
              and fit.get("sharpe", 0) >= gates.get("min_sharpe", 0)
              and res["n_trades"] >= gates.get("min_trades", 20))
        passed += ok
        rows.append((
            datetime.now(timezone.utc).isoformat(timespec="seconds"), fp,
            # A genome is already a plain dict, so it round-trips through JSON.
            # str(g) would store a Python repr that no later run could reload —
            # and the point of keeping the genome is that an outlier in this
            # table can be re-simulated rather than merely wondered about.
            f"{valid_w[0]}..{valid_w[1]}", json.dumps(g, sort_keys=True),
            res["n_trades"], int(res.get("n_signals", res["n_trades"])),
            1 if res.get("entries_capped") else 0,
            float(fit.get("net_pnl_usd", 0.0)),
            float(fit.get("excess_pnl_usd", 0.0)), float(fit.get("sharpe", 0.0)),
            float(fit.get("max_drawdown", 0.0)), float(res["win_rate"]),
            _turnover(res, years), 1 if ok else 0))
        if (i + 1) % 25 == 0:
            log.info(f"  {i+1}/{n} — {passed} passing the gate")

    conn.executemany("""INSERT INTO random_control (at, fingerprint, window,
        genome, n_trades, n_signals, entries_capped, net_pnl_usd, excess_pnl_usd,
        sharpe, max_drawdown, win_rate, turnover, passed_gate)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM random_control WHERE fingerprint=?",
                         (fp,)).fetchone()[0]
    conn.close()
    log.info(f"recorded {n} rows; {total:,} now under fingerprint {fp}")
    return {"added": n, "passed": passed, "total": total, "fingerprint": fp}


def load(conn, fp: str) -> dict:
    init(conn)
    out = {}
    for m in METRICS:
        vals = [r[0] for r in conn.execute(
            f"SELECT {m} FROM random_control WHERE fingerprint=? AND {m} IS NOT NULL",
            (fp,))]
        out[m] = np.array(vals, dtype="float64")
    return out


def place(conn, fp: str, metric: str, value: float) -> dict:
    """
    Where does `value` sit in the noise distribution?

    This is the calibration tool section 17 asks for. The number that matters is
    `beaten_by_noise`: the share of random strategies that did at least as well.
    A result beaten by 8% of noise is not a finding, however good it looks
    beside zero.
    """
    if metric not in METRICS:
        raise SystemExit(f"unknown metric {metric!r}; have {list(METRICS)}")
    arr = load(conn, fp)[metric]
    if arr.size < 30:
        raise SystemExit(f"only {arr.size} control samples under fingerprint {fp} — "
                         f"too few to place a result against. Run --run first.")
    # Drawdown is the one metric where smaller is better.
    better = (arr <= value) if metric == "max_drawdown" else (arr >= value)
    n_better = int(better.sum())
    share = n_better / arr.size
    return {"metric": metric, "value": value, "n": int(arr.size),
            "n_better": n_better,
            "beaten_by_noise": share, "percentile": float((1 - share) * 100),
            # The finest share this many samples can distinguish from zero.
            # Reporting "0.0%" off 300 draws claims a precision the sample does
            # not have, and it is the number a reader would most like to believe.
            "resolution": 1.0 / arr.size,
            "noise_max": float(arr.max()), "noise_min": float(arr.min()),
            "noise_median": float(np.median(arr))}


def report(conn) -> None:
    init(conn)
    fps = conn.execute("""SELECT fingerprint, COUNT(*) n, MIN(at) f, MAX(at) l
                          FROM random_control GROUP BY fingerprint
                          ORDER BY n DESC""").fetchall()
    if not fps:
        print("\n  no random-control samples yet — run: random_control.py --run 200")
        return
    print(f"\n  RANDOM-STRATEGY CONTROL — {len(fps)} pipeline fingerprint(s)")
    print("  Rows are never pooled across fingerprints: a fitness or cost change")
    print("  makes older rows describe a pipeline that no longer exists.\n")

    for row in fps:
        fp, n = row["fingerprint"], row["n"]
        d = load(conn, fp)
        pg = conn.execute("SELECT SUM(passed_gate) FROM random_control "
                          "WHERE fingerprint=?", (fp,)).fetchone()[0] or 0
        print(f"  fingerprint {fp}   {n:,} random genomes   "
              f"{row['f'][:10]}..{row['l'][:10]}")
        print(f"  {'metric':<16}{'min':>13}{'p50':>13}{'p95':>13}{'p99':>13}{'MAX':>14}")
        print("  " + "-" * 82)
        for m in METRICS:
            a = d[m]
            if not a.size:
                continue
            # Ratios need decimals; dollars and signal counts run to six figures
            # and ran into each other at three. Width per metric, not one format
            # for all — the first report printed "84751.500603362.517" as a cell.
            f = ".3f" if m in ("sharpe", "max_drawdown", "win_rate") else ",.0f"
            print(f"  {m:<16}{a.min():>13{f}}{np.percentile(a,50):>13{f}}"
                  f"{np.percentile(a,95):>13{f}}{np.percentile(a,99):>13{f}}"
                  f"{a.max():>14{f}}")
        cap = conn.execute("SELECT SUM(entries_capped) FROM random_control "
                           "WHERE fingerprint=?", (fp,)).fetchone()[0] or 0
        if cap:
            print(f"\n  {cap}/{n} hit the entry cap. Their TRADE counts are")
            print(f"  identical by construction; turnover above uses the true")
            print(f"  signal count, which the cap does not touch.")
        print(f"\n  passed the validation gate: {pg}/{n} ({pg/n:.1%})"
              f"   {'GOOD' if pg/n < 0.05 else 'TOO LOOSE — target is under 5%'}")

        sh = d["sharpe"]
        if sh.size:
            print(f"\n  The best of these {n:,} worthless strategies scored a Sharpe of "
                  f"{sh.max():.2f}")
            print(f"  and made ${d['net_pnl_usd'].max():,.2f}. Any real candidate must")
            print(f"  clear that before its number means anything.")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", type=int, metavar="N")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--place", nargs=2, metavar=("METRIC", "VALUE"))
    ap.add_argument("--seed", type=int)
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()

    if a.run:
        r = run(cfg, a.run, seed=a.seed)
        print(f"\n  added {r['added']} random genomes "
              f"({r['passed']} passed the gate)")
        print(f"  {r['total']:,} total under fingerprint {r['fingerprint']}")
        return 0

    conn = storage.connect(cfg["database"]["market_data_path"])
    if a.place:
        res = place(conn, fingerprint(cfg), a.place[0], float(a.place[1]))
        print(f"\n  PLACING {res['metric']} = {res['value']:g} AGAINST "
              f"{res['n']:,} RANDOM STRATEGIES")
        print("  " + "-" * 62)
        print(f"  noise min / median / max : {res['noise_min']:.3f} / "
              f"{res['noise_median']:.3f} / {res['noise_max']:.3f}")
        if res["n_better"]:
            print(f"  beaten or matched by     : {res['n_better']}/{res['n']} "
                  f"= {res['beaten_by_noise']:.1%} of noise")
        else:
            # Never "0.0%". The sample cannot see below one in n.
            print(f"  beaten or matched by     : 0 of {res['n']} "
                  f"— below this sample's resolution of {res['resolution']:.2%}")
        print(f"  percentile               : {res['percentile']:.1f}"
              f"  (+/- {res['resolution']:.1%})")
        print()
        if res["beaten_by_noise"] > 0.05:
            print("  NOT A FINDING. More than 5% of strategies known to be")
            print("  worthless did at least this well.")
        else:
            print("  Clears the noise distribution of THIS many random draws.")
            print("  That is necessary and a long way from sufficient. The")
            print("  search evaluated far more candidates than this control")
            print("  contains, and the best of a million draws beats the best")
            print("  of a few hundred — run `multiple_testing.py --report` for")
            print("  the bar that actually applies, and note this says nothing")
            print("  about the future either way.")
        conn.close(); return 0

    report(conn)
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
