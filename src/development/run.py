#!/usr/bin/env python3
"""Entry point for Step 5 — claim-count development.

    python src/development/run.py --config src/development/config.yaml

Reads a large-loss count development triangle, builds a per-coverage
"% developed by age" pattern, and develops each accident year's reported count to
ultimate. Writes to outputs/development/<run>_<date>/:
    development_report.md    the pattern + reported-vs-ultimate table + caveats
    development_pattern.csv  % developed by (coverage, age)
    developed_years.csv      reported vs ultimate per (accident year, coverage)
"""
from __future__ import annotations
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

from development.config import load_config
from development import triangle as T
from development import develop as D
from development import report as R


def run(config_path: str):
    cfg = load_config(config_path)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = os.path.join(cfg.output_dir, f"{cfg.run_name}_{ts}")
    os.makedirs(out, exist_ok=True)

    long = T.load_triangle(cfg)
    covtypes = list(long["ct"].unique())
    patterns = {ct: T.pattern(long, ct, tail=cfg.tail_factor.get(ct, 1.0)) for ct in covtypes}

    expected = D.load_expected_prior(cfg.expected_prior_csv, cfg)
    developed = [(ay, D.develop_accident_year(long, patterns, ay, cfg.method, expected))
                 for ay in sorted(long["ay"].unique())]

    # ---- write artifacts ----
    pat_rows = [{"covtype": ct, "age_months": a, "pct_developed": round(p["pct_developed"][a], 4),
                 "cdf": round(p["cdf"][a], 4)}
                for ct, p in patterns.items() for a in sorted(p["cdf"])]
    R.write_csv(pd.DataFrame(pat_rows), os.path.join(out, "development_pattern.csv"))
    R.write_csv(pd.concat([df.assign(accident_year=ay) for ay, df in developed], ignore_index=True),
                os.path.join(out, "developed_years.csv"))
    R.write_report(os.path.join(out, "development_report.md"), cfg, long, patterns, developed)

    # ---- console summary ----
    print("\n" + "=" * 70)
    print(f"  CLAIM DEVELOPMENT — method {cfg.method}")
    print("=" * 70)
    for ct in covtypes:
        pct12 = patterns[ct]["pct_developed"].get(12)
        s = f"{pct12*100:.0f}% developed @12mo" if pct12 else "n/a"
        print(f"  {ct}: {s}")
    latest_ay = max(long["ay"])
    df = dict(developed)[latest_ay]
    rep, ult = int(df["reported"].sum()), df["ultimate"].sum()
    print(f"  most recent year {latest_ay}: reported {rep} -> developed ~{ult:.0f} "
          f"(+{ult-rep:.0f}, ~all liability)")
    print(f"\n  outputs -> {out}{os.sep}")
    print("=" * 70)
    return {"out": out, "patterns": patterns, "developed": developed}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    run(ap.parse_args().config)


if __name__ == "__main__":
    main()
