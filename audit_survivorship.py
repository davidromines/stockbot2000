"""
Addendum F, Phase D1 — how much do the conclusions depend on the synthetic dead companies? (read-only)

Three ways to treat the ~7,600 dead companies we hold no prices for:
    exclude   not at all (survivors only)
    as_is     the generator's paths (delisting returns from the literature, real failure shapes for failures)
    zero      every unpriced death a total loss (the worst case)
and several generator CONFIGURATIONS were tried on the same real failures before the current one was chosen
(v4, v5, v5c with fundamentals and volume). This report asks, for the whole ranked set, the five slot holders and
the forward-positive families: how many verdicts change with the mode, how many with the generator, and what
cannot be identified from the data we have.  It invents no prices.

    ./venv/bin/python audit_survivorship.py      # prints and writes reports/audit_survivorship_<date>.md
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

FAMILIES = ["lab_search", "momentum", "kf_seasonality", "st_uptrend_pullback", "bollinger_reversion",
            "kf_mean_reversion", "st_momentum_1d", "turn_of_month"]


def load(conn) -> pd.DataFrame:
    d = pd.read_sql_query("SELECT strategy_key, version, mode, generator, trades, synthetic_trades, per_trade, share_deep, computed_at FROM survivorship_backtests", conn)
    return d


def latest_by_mode(d: pd.DataFrame) -> pd.DataFrame:
    gen = d.sort_values("computed_at").iloc[-1]["generator"]
    x = d[d["generator"] == gen]
    w = x.pivot_table(index=["strategy_key", "version"], columns="mode", values="per_trade")
    w["trades"] = x[x["mode"] == "as_is"].set_index(["strategy_key", "version"])["trades"]
    w["synthetic_trades"] = x[x["mode"] == "as_is"].set_index(["strategy_key", "version"])["synthetic_trades"]
    w["synth_share"] = w["synthetic_trades"] / w["trades"].replace(0, np.nan)
    return w.reset_index(), gen


def gen_label(g: str) -> str:
    base = g.split(":")[0].replace(".parquet", "")
    extra = ("+fundamentals+volume" if "fund:" in g else "")
    h = g.split(":")[1].split("|")[0] if ":" in g else ""
    return f"{base}#{h[-4:]}{extra}"


def generator_sensitivity(d: pd.DataFrame) -> dict:
    a = d[d["mode"] == "as_is"].copy()
    a["gen"] = a["generator"].map(gen_label)
    order = a.groupby("gen")["computed_at"].min().sort_values().index.tolist()
    w = a.pivot_table(index=["strategy_key", "version"], columns="gen", values="per_trade")[order]
    multi = w[w.notna().sum(axis=1) >= 2]
    spread = multi.max(axis=1) - multi.min(axis=1)
    flips = ((multi > 0).any(axis=1) & (multi <= 0).any(axis=1))
    first, last = multi.apply(lambda r: r.dropna().iloc[0], axis=1), multi.apply(lambda r: r.dropna().iloc[-1], axis=1)
    return {"generators": order, "n_multi": len(multi), "median_spread": float(spread.median()), "p90_spread": float(spread.quantile(.9)),
            "flip_share": float(flips.mean()), "flips": int(flips.sum()), "rho_first_last": float(first.rank().corr(last.rank())),
            "counts": {g: int(w[g].notna().sum()) for g in order}}


def verdict_changes(w: pd.DataFrame) -> dict:
    ok = w.dropna(subset=["exclude", "as_is", "zero"])
    pos = {m: (ok[m] > 0) for m in ("exclude", "as_is", "zero")}
    top = lambda m, k: set(ok.sort_values(m, ascending=False).head(k).index)
    return {"n": len(ok), "pos": {m: int(v.sum()) for m, v in pos.items()},
            "as_is_pos_zero_neg": int((pos["as_is"] & ~pos["zero"]).sum()),
            "exclude_pos_as_is_neg": int((pos["exclude"] & ~pos["as_is"]).sum()),
            "rho_as_is_zero": float(ok["as_is"].rank().corr(ok["zero"].rank())),
            "rho_exclude_as_is": float(ok["exclude"].rank().corr(ok["as_is"].rank())),
            "top50_overlap_as_is_zero": len(top("as_is", 50) & top("zero", 50)),
            "top50_overlap_exclude_as_is": len(top("exclude", 50) & top("as_is", 50)),
            "synth_share_median": float(ok["synth_share"].median()), "synth_share_p90": float(ok["synth_share"].quantile(.9)),
            "mean_gap_exclude_minus_asis": float((ok["exclude"] - ok["as_is"]).mean() * 100),
            "mean_gap_asis_minus_zero": float((ok["as_is"] - ok["zero"]).mean() * 100)}


def by_family(conn, w: pd.DataFrame) -> pd.DataFrame:
    fam = pd.read_sql_query("SELECT strategy_key, version, family FROM league_strategies", conn)
    x = w.merge(fam, on=["strategy_key", "version"], how="left").dropna(subset=["as_is"])
    g = x.groupby("family").agg(strategies=("as_is", "size"), exclude=("exclude", "median"), as_is=("as_is", "median"), zero=("zero", "median"),
                                 pos_asis=("as_is", lambda s: float((s > 0).mean())), pos_zero=("zero", lambda s: float((s > 0).mean())),
                                 synth=("synth_share", "median"))
    return g.sort_values("strategies", ascending=False)


def holders(conn, cfg, w: pd.DataFrame) -> pd.DataFrame:
    import slots
    rows = []
    for sl, h in slots.current(conn, cfg).items():
        if not h:
            continue
        r = w[(w["strategy_key"] == h["strategy_key"]) & (w["version"] == h["version"])]
        rows.append({"slot": sl, "key": h["strategy_key"], **({} if r.empty else r.iloc[0][["exclude", "as_is", "zero", "synth_share"]].to_dict())})
    return pd.DataFrame(rows)


def ranked_top(conn, w: pd.DataFrame, k: int = 50) -> dict:
    rh = pd.read_sql_query("SELECT strategy_key, version, score, passes_gate FROM ranking_history WHERE date=(SELECT MAX(date) FROM ranking_history)", conn)
    top = rh[rh["passes_gate"] == 1].sort_values("score", ascending=False).head(k).merge(w, on=["strategy_key", "version"], how="left")
    have = top.dropna(subset=["zero"])
    return {"k": k, "with_data": len(have), "zero_nonpositive": int((have["zero"] <= 0).sum()), "asis_nonpositive": int((have["as_is"] <= 0).sum())}


def twin() -> dict:
    p = Path("data/universe/twin_test.json")
    return json.loads(p.read_text()) if p.exists() else {}


def f(x, s="{:+.2f}"):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else s.format(x)


def render(conn, cfg, as_of: str) -> str:
    d = load(conn)
    w, gen = latest_by_mode(d)
    vc, gs, fam, hd, rt, tw = verdict_changes(w), generator_sensitivity(d), by_family(conn, w), holders(conn, cfg, w), ranked_top(conn, w), twin()
    L = ["# Phase D1: dependence on the synthetic dead companies", "",
         f"Computed {as_of}, read-only, from `survivorship_backtests` (generator `{gen_label(gen)}`, factory window 2016-19, 5,000-trade cap per run). Per-trade figures are net, costs deducted.", "",
         "## 1. What the three treatments do to the ranked set", "",
         f"{vc['n']:,} strategies with all three modes. Typical strategy: {vc['synth_share_median']:.0%} of its trades are in synthetic companies (90th percentile {vc['synth_share_p90']:.0%}).", "",
         "| treatment | strategies positive | share |", "|---|---:|---:|"]
    for m, lab in (("exclude", "survivors only"), ("as_is", "with synthetic dead companies (used by the ranking)"), ("zero", "worst case: every unpriced death a total loss")):
        L.append(f"| {lab} | {vc['pos'][m]:,} | {vc['pos'][m] / vc['n']:.0%} |")
    L += ["", f"- Mean per-trade change: survivors-only to as_is {f(-vc['mean_gap_exclude_minus_asis'])} points; as_is to worst case {f(-vc['mean_gap_asis_minus_zero'])} points.",
          f"- Verdict changes: {vc['exclude_pos_as_is_neg']} strategies are positive survivors-only and negative as_is; **{vc['as_is_pos_zero_neg']} are positive as_is and non-positive in the worst case** "
          f"({vc['as_is_pos_zero_neg'] / vc['n']:.0%} of the set) - their verdict rests on the unidentifiable assumption.",
          f"- Ordering: rank correlation as_is vs worst case {vc['rho_as_is_zero']:+.2f}; survivors-only vs as_is {vc['rho_exclude_as_is']:+.2f}. Top-50 overlap as_is vs worst case {vc['top50_overlap_as_is_zero']}/50; survivors-only vs as_is {vc['top50_overlap_exclude_as_is']}/50.",
          f"- Of the {rt['k']} best-scored strategies in the latest ranking snapshot ({rt['with_data']} with survivorship data): {rt['zero_nonpositive']} are non-positive in the worst case, {rt['asis_nonpositive']} non-positive as_is.", "",
          "## 2. By family (medians across the family's strategies)", "",
          "| family | strategies | survivors only % | as_is % | worst case % | positive as_is | positive worst case | synthetic share of trades |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, r in fam.head(16).iterrows():
        L.append(f"| {name} | {int(r.strategies)} | {f(r.exclude * 100)} | {f(r.as_is * 100)} | {f(r.zero * 100)} | {r.pos_asis:.0%} | {r.pos_zero:.0%} | {r.synth:.0%} |")
    L += ["", "The seven forward-positive families plus turn_of_month (`lab_search` funds are paper-only and have no survivorship backtest):", "",
          "| family | strategies with data | as_is % | worst case % | positive in worst case |", "|---|---:|---:|---:|---:|"]
    for name in FAMILIES:
        if name in fam.index:
            r = fam.loc[name]
            L.append(f"| {name} | {int(r.strategies)} | {f(r.as_is * 100)} | {f(r.zero * 100)} | {r.pos_zero:.0%} |")
        else:
            L.append(f"| {name} | 0 | n/a | n/a | n/a (not backtested: scored on paper only, or no template) |")
    L += ["", "## 3. The five slot holders", "", "| slot | strategy | survivors only % | as_is % | worst case % | synthetic share |", "|---:|---|---:|---:|---:|---:|"]
    for r in hd.itertuples():
        L.append(f"| {r.slot} | {r.key[:44]} | {f(getattr(r, 'exclude', np.nan) * 100)} | {f(getattr(r, 'as_is', np.nan) * 100)} | {f(getattr(r, 'zero', np.nan) * 100)} | {f(getattr(r, 'synth_share', np.nan) * 100, '{:.0f}%')} |")
    L += ["", "Holders without numbers are Lab-search funds, which are scored on paper evidence only and have no survivorship backtest.", "",
          "## 4. Dependence on the generator configuration", "",
          f"Generators tried on the same strategies: {', '.join(f'{g} ({gs['counts'][g]} strategies)' for g in gs['generators'])}. "
          f"{gs['n_multi']} strategies have as_is results under two or more: median spread between their lowest and highest per-trade figure {f(gs['median_spread'] * 100)} points, "
          f"90th percentile {f(gs['p90_spread'] * 100)}; **{gs['flips']} ({gs['flip_share']:.0%}) change sign** between configurations; rank correlation first vs latest configuration {gs['rho_first_last']:+.2f}. "
          "Configurations differ by more than the generator (later ones add dead companies' fundamentals and volume, so fundamental and liquidity strategies can trade them), so this is an upper bound on generator-only sensitivity.", ""]
    if tw:
        fl = tw.get("failures", {})
        L += ["## 5. What the real data can and cannot say", "",
              f"- Twin test (pre-registered, {fl.get('companies', '?')} real failures against synthetic twins, {fl.get('trades_real', 0):,} real vs {fl.get('trades_twin', 0):,} twin trades): "
              f"mean per trade real {f(fl.get('mean_real', np.nan) * 100)} % vs twin {f(fl.get('mean_twin', np.nan) * 100)} %, verdict {fl.get('verdict')}. "
              "It was run after five generator configurations had been looked at on the same 70 companies, so the pass is not an independent confirmation.",
              "- Real dead-company prices exist for about 418 of ~7,500 delisted common stocks, and the 70-80 failures used are the ones that survived into public price histories: a clean acquisition keeps its history and a bankruptcy often does not. The synthetic share of the traded universe peaks near 52 % (2016).",
              "- **Identifiable:** the survivors-only result, the sign and size of the gap to as_is under the stated assumptions, and the worst-case floor. **Not identifiable from available data:** the true return distribution of the unpriced dead companies, hence the true value between the as_is and worst-case columns."]
    L += ["", "## 6. Would paid point-in-time delisted data change the decision?", "",
          f"It would remove the assumption that separates the as_is and worst-case columns, which is the deciding assumption for {vc['as_is_pos_zero_neg']:,} of {vc['n']:,} strategies ({vc['as_is_pos_zero_neg'] / vc['n']:.0%}) and for {rt['zero_nonpositive']} of the {rt['with_data']} best-scored strategies that have survivorship data (positive as_is, non-positive in the worst case). "
          "But no strategy has reached 20 independent forward entry dates, and every candidate fails on forward evidence long before survivorship is the binding constraint; the data would sharpen the backtest prior, which the audit has found to carry little ranking information. "
          "Expected benefit to research integrity: real but second-order now. **Recommendation: do not buy yet.** Revisit if a family passes the prospective test (A6) and its verdict then depends on the survivorship assumption; at that point the data answers a decision that matters.", "",
          "## What could be wrong with this analysis", "",
          "- Per-trade figures come from one simulator on one 2016-19 window with a 5,000-trade cap; the synthetic share and gaps differ by window.",
          "- Strategies are compared across generators only where they were re-run; later configurations also changed what the strategy could trade.",
          "- The worst case (every unpriced death total loss) is deliberately extreme; reality is between the columns, and the twin test's pass is not independent.",
          "- Family medians weight each strategy equally, so a family with many near-duplicate variants counts many times."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    now = datetime.now(timezone.utc)
    text = render(conn, cfg, now.strftime("%Y-%m-%d %H:%M UTC"))
    out = Path("reports") / f"audit_survivorship_{now:%Y-%m-%d}.md"
    out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
