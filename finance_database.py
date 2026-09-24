"""
FinanceDatabase (github.com/JerBouma/FinanceDatabase) — the last Addendum C
universe source. Approved by the owner 2026-09-24.

What it adds to Layer A: a sector / industry classification and identifiers
(ISIN, CUSIP, FIGI) per listing, and — where the files carry one — a delisted
flag. What it does NOT carry: listing or delisting DATES, or prices.

No dates is the constraint that shapes how it is used. Layer A's ticker-reuse
trap (426 of 676 "real dead" companies were impostors) came from attaching a
record by ticker alone to whoever holds that ticker today. A FinanceDatabase
row therefore attaches to a Layer A company only when its ticker AND its
normalised name agree with the SAME company (universe_layer_a.py). An
unmatched row is counted in the report, never added as a company: with no
dates it cannot be placed in time.

Its sector is kept in its own field (`fd_sector` / `fd_industry`), never mixed
into SIC divisions: two taxonomies merged by eye is a classification nobody
defined.

    python finance_database.py --fetch     shallow sparse clone, records the commit
    python finance_database.py --import    CSVs -> data/universe/financedatabase.parquet
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import glob
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger("finance_database")

DEFAULTS = {"repo": "https://github.com/JerBouma/FinanceDatabase.git",
            "clone_dir": "data/external/FinanceDatabase",
            "equities_glob": "database/equities*",
            "out": "data/universe/financedatabase.parquet"}
# Column names vary between releases; each field takes the first that exists.
FIELDS = {"symbol": ("symbol", "ticker"), "name": ("name", "short_name", "long_name"),
          "exchange": ("exchange",), "market": ("market",), "country": ("country",),
          "sector": ("sector",), "industry": ("industry",), "industry_group": ("industry_group",),
          "isin": ("isin",), "cusip": ("cusip",), "figi": ("figi", "composite_figi"),
          "delisted": ("delisted", "is_delisted")}


def settings(cfg: dict) -> dict:
    s = ((cfg.get("universe_reconstruction") or {}).get("financedatabase") or {})
    return {**DEFAULTS, **s}


def fetch(s: dict) -> dict:
    """Shallow, blob-filtered, sparse clone of just the equities files. Re-running updates it."""
    d = s["clone_dir"]
    if not os.path.isdir(os.path.join(d, ".git")):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", s["repo"], d], check=True)
    else:
        subprocess.run(["git", "-C", d, "pull", "--depth", "1"], check=True)
    subprocess.run(["git", "-C", d, "sparse-checkout", "set", "--no-cone", s["equities_glob"]], check=True)
    sha = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return {"clone_dir": d, "commit": sha, "files": len(_files(s))}


def _files(s: dict) -> list:
    root = os.path.join(s["clone_dir"], s["equities_glob"])
    out = []
    for p in glob.glob(root):
        if os.path.isdir(p):
            out += glob.glob(os.path.join(p, "**", "*.csv*"), recursive=True)
        elif p.endswith((".csv", ".csv.gz", ".csv.bz2", ".csv.xz")):
            out.append(p)
    return sorted(out)


def normalise(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Map one CSV onto FIELDS. A missing column is None, never a default."""
    cols = {c.lower().strip(): c for c in df.columns}
    out = pd.DataFrame(index=df.index)
    for f, names in FIELDS.items():
        c = next((cols[n] for n in names if n in cols), None)
        out[f] = df[c] if c is not None else None
    out["symbol"] = out["symbol"].astype("string").str.strip().str.upper()
    d = out["delisted"]
    out["delisted"] = d.map(lambda v: None if pd.isna(v) else str(v).strip().lower() in ("true", "1", "yes", "y")) \
        if d.notna().any() else None
    out["source_file"] = source
    return out[out["symbol"].notna() & (out["symbol"] != "")]


def import_csvs(s: dict) -> dict:
    files = _files(s)
    if not files:
        raise FileNotFoundError(f"no equities CSVs under {s['clone_dir']} — run --fetch first")
    parts = []
    for p in files:
        try:
            parts.append(normalise(pd.read_csv(p, dtype=str, keep_default_na=True), os.path.relpath(p, s["clone_dir"])))
        except Exception as e:                               # noqa: BLE001 — one bad file must not sink the rest
            log.warning(f"{p}: {type(e).__name__}: {e}")
    df = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["symbol", "exchange", "name"])
    sha = subprocess.run(["git", "-C", s["clone_dir"], "rev-parse", "HEAD"], capture_output=True,
                         text=True).stdout.strip() if os.path.isdir(os.path.join(s["clone_dir"], ".git")) else None
    df["commit"] = sha
    df["imported_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(s["out"]), exist_ok=True)
    df.to_parquet(s["out"], index=False)
    rep = {"rows": int(len(df)), "files": len(files), "commit": sha,
           "with_delisted_flag": int(df["delisted"].notna().sum()) if "delisted" in df else 0,
           "delisted_true": int((df["delisted"] == True).sum()) if "delisted" in df else 0,  # noqa: E712
           "with_sector": int(df["sector"].notna().sum())}
    with open(s["out"].replace(".parquet", "_report.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    return rep


def load(path: str = DEFAULTS["out"]) -> pd.DataFrame | None:
    return pd.read_parquet(path) if os.path.exists(path) else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FinanceDatabase: sector, identifiers, delisted flag (Addendum C).")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--import", dest="do_import", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    s = settings(load_config())
    if a.fetch:
        print(json.dumps(fetch(s), indent=1))
    if a.do_import:
        print(json.dumps(import_csvs(s), indent=1))
    if not (a.fetch or a.do_import):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
