"""Expected large-loss counts per segment.

    expected = Step-1 rate  ×  Step-2 projected premium      (summed to portfolio)

Reuses the Step-2 machinery (factor table + projection) and the frozen Step-1
rate table. The rate table is CONSUMED, never re-fit (Rule 4 of the spec).
"""
from __future__ import annotations
import glob
import json
import os
import numpy as np
import pandas as pd

from step_2_premium.config import load_config as load_step2
from step_2_premium import factors as F
from step_2_premium.project import project


def build_step2(step2_config_path: str):
    """Build the Step-2 artifacts once (reads the book, calibrates the factor
    table). Returns (cfg2, full_ys, visible_ysm, factor_table)."""
    cfg2 = load_step2(step2_config_path)
    book = F.load_book(cfg2)
    full_ys, visible_ysm = F.build_panels(book, cfg2)
    ftab = F.calibrate(full_ys, visible_ysm, cfg2, cfg2.experience_years)
    return cfg2, full_ys, visible_ysm, ftab


def load_rate_table(glob_pattern: str):
    """Newest rate_table_final.csv + its Step-1 dispersion (from the sibling
    run_report.json, for the confidence band). Returns (rates, path, dispersion)."""
    hits = glob.glob(glob_pattern, recursive=True)
    if not hits:
        raise SystemExit(f"No rate table found for pattern {glob_pattern!r}. "
                         f"Run Step 1 first (python src/run.py --config src/config/config.yaml).")
    path = max(hits, key=os.path.getmtime)
    rates = pd.read_csv(path)
    if "final_rate" not in rates.columns:
        raise SystemExit(f"Rate table {path} has no 'final_rate' column.")
    dispersion = None
    rr = os.path.join(os.path.dirname(path), "run_report.json")
    if os.path.exists(rr):
        try:
            dispersion = float(json.load(open(rr, encoding="utf-8")).get("dispersion"))
        except Exception:
            dispersion = None
    return rates, path, dispersion


def expected_for_year(cfg2, full_ys, visible_ysm, ftab, rates, year, month):
    """Per-segment expected counts for `year` as if run at end of `month`.
    Returns (df[*keys, projected_premium, frequency_rate, expected_losses,
    actual_premium], covered_pct)."""
    keys = cfg2.keys
    proj = project(visible_ysm, full_ys, ftab, cfg2, year, month)
    el = proj.merge(rates[keys + ["final_rate"]], on=keys, how="left")
    covered = el["final_rate"].notna()
    el["frequency_rate"] = el["final_rate"].fillna(0.0)
    el["expected_losses"] = el["frequency_rate"] * el["projected_premium"]
    covered_pct = float(el.loc[covered, "projected_premium"].sum()
                        / el["projected_premium"].sum() * 100) if len(el) else 0.0
    cols = keys + ["projected_premium", "frequency_rate", "expected_losses", "actual_premium"]
    return el[cols].copy(), covered_pct
