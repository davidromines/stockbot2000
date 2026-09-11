"""
Process-wide CPU limits. **Import this before numpy, pandas or xgboost.**

OpenBLAS, OpenMP and XGBoost each default to grabbing every core. On a 4-vCPU
VM that means one training run pegs the whole box — and this VM shares a fully
committed host with another, so "use everything" is not a neutral default.

The import order is not stylistic. OpenBLAS and OpenMP read their thread counts
from the environment **once, at load time**. Setting these variables after numpy
is imported does nothing at all, silently. Hence a separate module that does
nothing but set environment variables, imported first.

Uses setdefault throughout, so an explicit `OMP_NUM_THREADS=1 python ...` on the
command line still wins.
"""
import os

import yaml

# Every thread-pool variable the scientific stack reads. Not all libraries are
# installed, but setting an unused one is harmless and cheaper than guessing.
_THREAD_VARS = (
    "OMP_NUM_THREADS",          # OpenMP — XGBoost, scikit-learn
    "OPENBLAS_NUM_THREADS",     # OpenBLAS — numpy linear algebra
    "MKL_NUM_THREADS",          # Intel MKL, if numpy is ever built against it
    "NUMEXPR_NUM_THREADS",      # numexpr, pulled in by pandas
    "VECLIB_MAXIMUM_THREADS",   # Accelerate on macOS; harmless here
)

DEFAULT_MAX_THREADS = 3
DEFAULT_NICE = 10


def _compute_config(path: str = "config.yaml") -> dict:
    """
    Read just the `compute:` block.

    Deliberately does not import `universe.load_config` — that module pulls in
    pandas, which would load OpenBLAS before this module has set its thread
    count, defeating the whole purpose.
    """
    try:
        with open(path) as f:
            return (yaml.safe_load(f) or {}).get("compute", {}) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}


_cfg = _compute_config()
MAX_THREADS = int(_cfg.get("max_threads", DEFAULT_MAX_THREADS))
NICE_LEVEL = int(_cfg.get("nice_level", DEFAULT_NICE))

for _var in _THREAD_VARS:
    os.environ.setdefault(_var, str(MAX_THREADS))


def be_nice(level: int | None = None) -> int:
    """
    Lower this process's scheduling priority.

    For long batch jobs — the backfill, the feature build, training. Thread caps
    stop a job taking every core; `nice` stops the cores it does take from
    starving the desktop and this session. Returns the resulting niceness.

    Only ever increases niceness: lowering it needs privileges we do not have,
    and raising priority is not what any batch job here should be doing.
    """
    level = NICE_LEVEL if level is None else level
    try:
        current = os.nice(0)
        if level > current:
            return os.nice(level - current)
        return current
    except OSError:
        return 0


def summary() -> str:
    return f"CPU limits: {MAX_THREADS} threads, nice {NICE_LEVEL}"
