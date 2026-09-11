"""
The searchable strategy definition. Phase 08.

A genome is an **entry rule**, an **exit rule**, and a set of risk parameters.
The rules are expression trees the search composes itself from primitives and
operators — nobody writes them, which is the point. The search can arrive at

    rank(rsi_14) < 0.2  AND  zscore(volume, 20) > 1.5  AND  close > sma_50

without anyone having thought of it.

Trees are plain nested dicts so a genome serialises to JSON and lands in the
idea ledger unchanged. Every strategy ever tried can then be reproduced exactly
from its stored genome, which is what makes the lineage inspectable.

Two kinds of operator, and the distinction matters:

- **Time-series** ops (`lag`, `delta`, `zscore`, `pct_change`, crossovers) look
  backwards within one ticker, so they group by ticker and must never see
  another ticker's rows.
- **Cross-sectional** ops (`rank`) compare tickers against each other on the same
  day, so they group by date.

Getting that grouping wrong produces a rule that silently looks into other
stocks' futures, which would be a leak as serious as a bad train/test split.

Complexity is capped and penalised. An unconstrained tree grows until it
memorises history — the standard failure of genetic programming on noisy data,
and this data is very noisy.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import random

import numpy as np
import pandas as pd

# Columns the grammar may reference. Kept separate from FEATURE_COLS because the
# search also gets raw price, volume and liquidity, which the classifier does not.
BASE_PRIMITIVES = ["close", "volume", "returns", "dollar_volume_20"]

TS_TRANSFORMS = ("lag", "delta", "zscore", "pct_change")   # within a ticker
XS_TRANSFORMS = ("rank",)                                   # across tickers, same day
COMPARISONS = ("gt", "lt", "crosses_above", "crosses_below")
LOGIC = ("and", "or", "not")

WINDOWS = (3, 5, 10, 20, 50)


class Grammar:
    """
    What the search may build from, plus the statistics that make constants sane.

    Constants are drawn from each column's own observed quantiles rather than
    from a fixed range. A threshold of 70 is meaningful for RSI and meaningless
    for dollar volume; sampling blind would spend almost the entire search on
    conditions that are never true.
    """

    def __init__(self, feature_cols: list[str], stats: dict[str, dict],
                 max_depth: int = 4, seed: int | None = None):
        self.columns = list(dict.fromkeys(list(feature_cols) + BASE_PRIMITIVES))
        self.columns = [c for c in self.columns if c in stats]
        self.stats = stats
        self.max_depth = max_depth
        self.rng = random.Random(seed)

    # -- construction ------------------------------------------------------

    def random_value(self, depth: int = 0) -> dict:
        """A numeric-valued subtree: a column, optionally wrapped in transforms."""
        node = {"col": self.rng.choice(self.columns)}
        if depth < self.max_depth - 1 and self.rng.random() < 0.5:
            op = self.rng.choice(TS_TRANSFORMS + XS_TRANSFORMS)
            node = {"op": op, "args": [node]}
            if op in ("lag", "delta", "zscore", "pct_change"):
                node["n"] = self.rng.choice(WINDOWS)
        return node

    def _constant_for(self, node: dict) -> float:
        """Pick a threshold on the same scale as whatever it is compared against."""
        op = node.get("op")
        if op == "rank":
            return round(self.rng.uniform(0.02, 0.98), 3)
        if op == "zscore":
            return round(self.rng.uniform(-3.0, 3.0), 2)
        if op in ("delta", "pct_change"):
            return round(self.rng.uniform(-0.15, 0.15), 4)
        col = node.get("col") or self._first_col(node)
        q = self.stats.get(col, {}).get("quantiles")
        if not q:
            return round(self.rng.uniform(-1, 1), 3)
        return float(self.rng.choice(q))

    def _first_col(self, node: dict) -> str | None:
        if "col" in node:
            return node["col"]
        for a in node.get("args", []):
            c = self._first_col(a)
            if c:
                return c
        return None

    def random_condition(self, depth: int = 0) -> dict:
        """A boolean-valued subtree — the thing a rule ultimately is."""
        if depth < self.max_depth - 1 and self.rng.random() < 0.45:
            op = self.rng.choice(LOGIC)
            if op == "not":
                return {"op": "not", "args": [self.random_condition(depth + 1)]}
            return {"op": op, "args": [self.random_condition(depth + 1),
                                       self.random_condition(depth + 1)]}

        left = self.random_value(depth)
        op = self.rng.choice(COMPARISONS)
        if op in ("crosses_above", "crosses_below"):
            # Crossovers compare two series; against a constant they would just be
            # a threshold with extra steps.
            return {"op": op, "args": [left, self.random_value(depth)]}
        return {"op": op, "args": [left, {"const": self._constant_for(left)}]}

    def random_genome(self) -> dict:
        return {
            "entry": self.random_condition(),
            "exit": self.random_condition(),
            "risk": {
                "stop_atr_multiple": round(self.rng.uniform(0.5, 5.0), 2),
                "max_hold_days": self.rng.randint(2, 60),
                "max_open_positions": self.rng.randint(3, 30),
                "take_profit_pct": (None if self.rng.random() < 0.4
                                    else round(self.rng.uniform(3, 40), 1)),
            },
        }

    # -- variation ---------------------------------------------------------

    def mutate(self, genome: dict, rate: float = 0.3) -> dict:
        """Change one thing. Small steps make the lineage meaningful."""
        g = _clone(genome)
        choice = self.rng.random()
        if choice < 0.4:
            g["entry"] = self._mutate_node(g["entry"], rate)
        elif choice < 0.7:
            g["exit"] = self._mutate_node(g["exit"], rate)
        else:
            r = g["risk"]
            key = self.rng.choice(list(r))
            if key == "stop_atr_multiple":
                r[key] = round(min(5.0, max(0.5, r[key] * self.rng.uniform(0.7, 1.4))), 2)
            elif key == "max_hold_days":
                r[key] = int(min(60, max(2, r[key] + self.rng.randint(-8, 8))))
            elif key == "max_open_positions":
                r[key] = int(min(30, max(3, r[key] + self.rng.randint(-5, 5))))
            else:
                r[key] = (None if self.rng.random() < 0.3
                          else round(self.rng.uniform(3, 40), 1))
        return g

    def _mutate_node(self, node: dict, rate: float) -> dict:
        nodes = _all_nodes(node)
        target = self.rng.choice(nodes)
        if "const" in target:
            target["const"] = round(target["const"] * self.rng.uniform(0.6, 1.6), 4)
        elif "col" in target:
            target["col"] = self.rng.choice(self.columns)
        elif target.get("op") in COMPARISONS:
            target["op"] = self.rng.choice(COMPARISONS)
        elif target.get("op") in LOGIC and target["op"] != "not":
            target["op"] = self.rng.choice(("and", "or"))
        elif "n" in target:
            target["n"] = self.rng.choice(WINDOWS)
        else:
            return self.random_condition()
        return node

    def crossover(self, a: dict, b: dict) -> dict:
        """Take the entry rule from one parent and the exit and risk from the other."""
        child = _clone(a)
        if self.rng.random() < 0.5:
            child["exit"] = _clone(b["exit"])
        else:
            child["entry"] = _clone(b["entry"])
        if self.rng.random() < 0.5:
            child["risk"] = _clone(b["risk"])
        return child


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

def evaluate(node: dict, df: pd.DataFrame) -> pd.Series:
    """
    Turn a tree into a Series aligned to `df`.

    `df` must carry `ticker` and `date`. Time-series operators group by ticker so
    one stock's history never leaks into another's; `rank` groups by date so
    stocks are compared only against their same-day peers. Both are required for
    the result to mean anything.
    """
    if "const" in node:
        return pd.Series(node["const"], index=df.index, dtype="float64")
    if "col" in node:
        col = node["col"]
        if col not in df.columns:
            return pd.Series(np.nan, index=df.index, dtype="float64")
        return df[col].astype("float64")

    op = node["op"]
    args = node.get("args", [])

    if op == "not":
        return ~_as_bool(evaluate(args[0], df))
    if op in ("and", "or"):
        a, b = _as_bool(evaluate(args[0], df)), _as_bool(evaluate(args[1], df))
        return (a & b) if op == "and" else (a | b)

    if op in TS_TRANSFORMS:
        s = evaluate(args[0], df)
        n = int(node.get("n", 5))
        g = s.groupby(df["ticker"], observed=True)
        if op == "lag":
            return g.shift(n)
        if op == "delta":
            return s - g.shift(n)
        if op == "pct_change":
            prev = g.shift(n)
            return (s / prev.replace(0, np.nan)) - 1
        roll = g.transform(lambda x: x.rolling(n, min_periods=max(2, n // 2)).mean())
        std = g.transform(lambda x: x.rolling(n, min_periods=max(2, n // 2)).std())
        return (s - roll) / std.replace(0, np.nan)

    if op == "rank":
        s = evaluate(args[0], df)
        return s.groupby(df["date"], observed=True).rank(pct=True)

    if op in ("gt", "lt"):
        a, b = evaluate(args[0], df), evaluate(args[1], df)
        return (a > b) if op == "gt" else (a < b)

    if op in ("crosses_above", "crosses_below"):
        a, b = evaluate(args[0], df), evaluate(args[1], df)
        diff = a - b
        prev = diff.groupby(df["ticker"], observed=True).shift(1)
        return (diff > 0) & (prev <= 0) if op == "crosses_above" else (diff < 0) & (prev >= 0)

    raise ValueError(f"unknown operator: {op}")


def _as_bool(s: pd.Series) -> pd.Series:
    return s.fillna(False).astype(bool) if s.dtype != bool else s


def complexity(genome: dict) -> int:
    """Node count across both rules — what the fitness function charges for."""
    return len(_all_nodes(genome["entry"])) + len(_all_nodes(genome["exit"]))


def describe(node: dict) -> str:
    """Render a tree as readable text. Winning strategies have to be explainable."""
    if "const" in node:
        return f"{node['const']:g}"
    if "col" in node:
        return node["col"]
    op, args = node["op"], node.get("args", [])
    if op == "not":
        return f"not({describe(args[0])})"
    if op in ("and", "or"):
        return f"({describe(args[0])} {op} {describe(args[1])})"
    if op in TS_TRANSFORMS:
        return f"{op}({describe(args[0])}, {node.get('n')})"
    if op == "rank":
        return f"rank({describe(args[0])})"
    sym = {"gt": ">", "lt": "<"}.get(op)
    if sym:
        return f"{describe(args[0])} {sym} {describe(args[1])}"
    return f"{op}({describe(args[0])}, {describe(args[1])})"


def _all_nodes(node: dict) -> list[dict]:
    out = [node]
    for a in node.get("args", []):
        out.extend(_all_nodes(a))
    return out


def _clone(obj):
    if isinstance(obj, dict):
        return {k: _clone(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clone(v) for v in obj]
    return obj


def column_stats(df: pd.DataFrame, columns: list[str]) -> dict:
    """
    Quantiles per column, so generated constants sit inside the real distribution.

    Sampled from one slice of data rather than recomputed per fold — these only
    need to be roughly right, and recomputing per candidate would dominate the
    evaluation cost.
    """
    stats = {}
    for c in columns:
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(s) < 100:
            continue
        qs = s.quantile([0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]).round(4).tolist()
        stats[c] = {"quantiles": qs, "mean": float(s.mean()), "std": float(s.std())}
    return stats
