"""
The promotion ladder. Phase 10.

Moves a strategy from "scored well in the search" to "worth real money", one
gate at a time. Most candidates dying at the validation stage is the system
working correctly, not a failure.

    01  search           2006-2019, walk-forward      ~200k/night
    02  shortlist        deduplicated survivors       ~200
    03  validation       2020-2022                    ~10
    04  sealed holdout   2023-present, deflated       ~2-3
    05  paper trading    forward, no bias             1-2
    06  funded           small stake, kill rule

**The sealed period is sealed.** Each strategy may be evaluated against it exactly
once, ever. That rule is enforced here in code rather than left to discipline: a
second attempt is refused and the refusal is recorded. Every peek costs
statistical validity and there is no way to un-peek, so the enforcement has to be
mechanical.

**Deflated Sharpe.** The winner of 200,000 trials has a far better Sharpe than the
winner of 200 purely through multiple testing. The ledger stores the true trial
count, and stage 04 applies the correction before deciding anything. A strategy
that only looks good because a great many were tried is exactly what this catches.

Usage:
    python promote.py --shortlist <run_id>       # stage 02
    python promote.py --validate <run_id>        # stage 03
    python promote.py --seal <strategy_id>       # stage 04, ONCE per strategy
    python promote.py --status
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import math

import numpy as np

import costs as costs_mod
import genome as gn
import ledger
import reward
import simulator
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("promote")

STAGES = ("shortlist", "validation", "sealed", "paper", "funded")


def deflated_sharpe(observed: float, n_trials: int, n_obs: int,
                    skew: float = 0.0, kurt: float = 3.0) -> float:
    """
    Probability that the observed Sharpe is genuinely above zero, given how many
    strategies were tried.

    Bailey and López de Prado's deflated Sharpe, simplified. The intuition is the
    part that matters: the maximum of many random Sharpes is well above zero by
    construction, so the bar a winner must clear rises with the number of
    candidates tested. Testing 200,000 strategies and keeping the best is not
    evidence of skill unless the best is far better than the best of 200,000
    coin flips.

    **Known calibration issue — not yet fixed.** `reward.sharpe` returns an
    annualised figure while `n_obs` here is a trade count, and the formula assumes
    both are at the same frequency. The structure of the correction is right and
    it moves in the right direction with trial count, but the absolute threshold
    is currently too strict: a Sharpe of 1.5 over 500 observations scores 0.126 at
    10 trials, which is far harsher than it should be. Recorded in BACKLOG.md.
    Until it is fixed, read stage 04 as directional rather than as a calibrated
    probability.
    """
    if n_trials < 2 or n_obs < 2:
        return 0.0
    euler = 0.5772156649
    # Expected maximum Sharpe from n_trials draws of pure noise.
    e_max = ((1 - euler) * _z(1 - 1.0 / n_trials)
             + euler * _z(1 - 1.0 / (n_trials * math.e)))
    denom = math.sqrt(max(1e-12,
                          (1 - skew * observed + (kurt - 1) / 4 * observed ** 2) / (n_obs - 1)))
    return float(_norm_cdf((observed - e_max) / denom))


def _z(p: float) -> float:
    """Inverse normal CDF, Acklam's approximation. Avoids a scipy dependency."""
    p = min(max(p, 1e-12), 1 - 1e-12)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q, r = p - 0.5, (p - 0.5) ** 2
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _decide(conn, sid: str, stage: str, passed: bool, evidence: dict) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO promotions (strategy_id, stage, decision, evidence, decided_at)
        VALUES (?, ?, ?, ?, ?)
    """, (sid, stage, "pass" if passed else "fail", json.dumps(evidence), storage._now()))
    conn.commit()


def _already(conn, sid: str, stage: str):
    return conn.execute("SELECT * FROM promotions WHERE strategy_id=? AND stage=?",
                        (sid, stage)).fetchone()


def _evaluate_window(conn, cfg, genome_dict, window):
    """Simulate one genome over an arbitrary window. Used by every gate."""
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True)
    if df.empty:
        return None
    panel = simulator.Panel(df)
    cm = costs_mod.CostModel(cfg)
    size = cfg["risk"]["position_size_usd"]
    capital = size * cfg["risk"]["max_open_positions"]
    res = simulator.simulate(genome_dict, panel, cm, size,
                             max_entries=cfg["lab"].get("max_entries_per_eval", 20000))
    scored = reward.fitness(res, gn.complexity(genome_dict), capital_usd=capital)
    scored["pnl_series"] = res.get("pnl_series")
    return scored


def shortlist(conn, cfg, run_id: str, keep: int = 200) -> list[str]:
    """
    Stage 02. Take the best by net P&L, deduplicated by rule text.

    Deduplication matters more than it sounds: elitism and mutation produce many
    near-identical copies of whatever is currently winning, and carrying twenty
    clones into validation would waste the budget and overstate how many distinct
    ideas survived.
    """
    rows = ledger.top_by_pnl(conn, run_id, limit=keep * 5)
    seen, out = set(), []
    for r in rows:
        if r["net_pnl_usd"] <= 0:
            continue
        key = (r["entry_desc"], r["exit_desc"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r["id"])
        _decide(conn, r["id"], "shortlist", True,
                {"net_pnl_usd": r["net_pnl_usd"], "trial_index": r["trial_index"]})
        if len(out) >= keep:
            break
    log.info(f"Shortlisted {len(out)} distinct profitable strategies from {len(rows)} scored")
    return out


def validate(conn, cfg, run_id: str) -> list[str]:
    """Stage 03. Re-run the shortlist on 2020-2022 — data the search never saw."""
    lab = cfg["lab"]
    window = (lab["validation_start"], lab["validation_end"])
    ids = [r["strategy_id"] for r in conn.execute("""
        SELECT p.strategy_id FROM promotions p JOIN strategies s ON s.id = p.strategy_id
        WHERE p.stage='shortlist' AND p.decision='pass' AND s.run_id = ?
    """, (run_id,)).fetchall()]
    if not ids:
        log.warning("Nothing shortlisted — run --shortlist first.")
        return []

    log.info(f"Validating {len(ids)} strategies on {window[0]} -> {window[1]}")
    survivors = []
    for i, sid in enumerate(ids, start=1):
        row = conn.execute("SELECT genome FROM strategies WHERE id=?", (sid,)).fetchone()
        scored = _evaluate_window(conn, cfg, json.loads(row["genome"]), window)
        if scored is None:
            continue
        passed = scored["net_pnl_usd"] > 0 and scored["n_trades"] >= 20
        _decide(conn, sid, "validation", passed,
                {"net_pnl_usd": scored["net_pnl_usd"], "sharpe": scored["sharpe"],
                 "n_trades": scored["n_trades"], "window": window})
        if passed:
            survivors.append(sid)
        if i % 25 == 0:
            log.info(f"  {i}/{len(ids)} — {len(survivors)} still standing")

    log.info(f"{len(survivors)} of {len(ids)} survived validation. "
             f"Most candidates dying here is the system working.")
    return survivors


def seal(conn, cfg, sid: str) -> None:
    """
    Stage 04. The sealed holdout — 2023 to now. **Once per strategy, ever.**

    Refusing a second attempt is the whole point. Re-testing until a strategy
    passes is the most natural way to destroy a holdout, and discipline is not a
    reliable defence against it at two in the morning.
    """
    prior = _already(conn, sid, "sealed")
    if prior:
        log.error(f"REFUSED. {sid} was already opened against the sealed period on "
                  f"{prior['decided_at']} — decision was '{prior['decision']}'.")
        log.error("The sealed period may be used exactly once per strategy. "
                  "There is no way to un-peek.")
        return

    row = conn.execute("""
        SELECT s.genome, e.trial_index FROM strategies s
        JOIN evaluations e ON e.strategy_id = s.id WHERE s.id = ?
    """, (sid,)).fetchone()
    if not row:
        log.error(f"No such strategy: {sid}")
        return
    if not _already(conn, sid, "validation"):
        log.error("Not validated yet. The ladder exists to be climbed in order.")
        return

    lab = cfg["lab"]
    window = (lab["sealed_start"], "2099-12-31")
    log.warning(f"Opening the sealed period for {sid}. This can only happen once.")
    scored = _evaluate_window(conn, cfg, json.loads(row["genome"]), window)
    if scored is None:
        log.error("No data in the sealed window.")
        return

    trials = int(row["trial_index"] or 1)
    dsr = deflated_sharpe(scored["sharpe"], trials, max(scored["n_trades"], 2))
    passed = scored["net_pnl_usd"] > 0 and dsr > 0.95

    _decide(conn, sid, "sealed", passed, {
        "net_pnl_usd": scored["net_pnl_usd"], "sharpe": scored["sharpe"],
        "n_trades": scored["n_trades"], "trials_when_found": trials,
        "deflated_sharpe_prob": dsr, "window": window})

    log.info(f"  NET P&L          ${scored['net_pnl_usd']:+,.2f}")
    log.info(f"  raw Sharpe       {scored['sharpe']:.3f}")
    log.info(f"  trials to find   {trials:,}")
    log.info(f"  deflated Sharpe  {dsr:.3f}  (needs > 0.95)")
    log.info(f"  VERDICT          {'PASS' if passed else 'FAIL'}")
    if not passed and scored["net_pnl_usd"] > 0:
        log.info("  Profitable but not distinguishable from the best of "
                 f"{trials:,} random tries.")


def status(conn) -> None:
    print(f"{'stage':>12} {'pass':>7} {'fail':>7}")
    print("-" * 28)
    for stage in STAGES:
        r = conn.execute("""
            SELECT SUM(decision='pass') p, SUM(decision='fail') f
            FROM promotions WHERE stage = ?
        """, (stage,)).fetchone()
        print(f"{stage:>12} {r['p'] or 0:>7} {r['f'] or 0:>7}")

    rows = conn.execute("""
        SELECT p.strategy_id, p.evidence, s.entry_desc FROM promotions p
        JOIN strategies s ON s.id = p.strategy_id
        WHERE p.stage='sealed' AND p.decision='pass'
    """).fetchall()
    if rows:
        print("\n  cleared the sealed holdout:")
        for r in rows:
            ev = json.loads(r["evidence"])
            print(f"    {r['strategy_id']}  ${ev['net_pnl_usd']:+,.2f}  "
                  f"dsr {ev['deflated_sharpe_prob']:.3f}  {(r['entry_desc'] or '')[:40]}")
    else:
        print("\n  nothing has cleared the sealed holdout.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shortlist", metavar="RUN_ID")
    parser.add_argument("--validate", metavar="RUN_ID")
    parser.add_argument("--seal", metavar="STRATEGY_ID")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    ledger.init(conn)

    if args.shortlist:
        shortlist(conn, cfg, args.shortlist)
    elif args.validate:
        validate(conn, cfg, args.validate)
    elif args.seal:
        seal(conn, cfg, args.seal)
    else:
        status(conn)
    conn.close()


if __name__ == "__main__":
    main()
