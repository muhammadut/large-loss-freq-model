#!/usr/bin/env python3
"""Entry point for Part 2 (premium projection).

    python src/premium_projection/run.py --config src/premium_projection/config.yaml

Produces, in outputs/premium/<run>_<date_time>/:
    growth_factor_table.csv   the factor per (segment × month)   [the reusable artifact]
    projected_premium.csv     projected full-year premium per segment (demo run)
    expected_losses.csv       projected premium × Part-1 rate    [if a rate table is found]
    report.md                 methodology + tests + metrics
"""
from __future__ import annotations
import glob
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from premium_projection.config import load_config
from premium_projection import factors as F
from premium_projection import backtest as B
from premium_projection.project import project
from premium_projection import report as R


def _latest_rate_table(pattern):
    hits = glob.glob(pattern, recursive=True)
    return max(hits, key=os.path.getmtime) if hits else None


def run(config_path: str):
    import pandas as pd
    cfg = load_config(config_path)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = os.path.join(cfg.output_dir, f"{cfg.run_name}_{ts}")
    os.makedirs(out, exist_ok=True)

    print("Loading book and building panels …")
    df = F.load_book(cfg)
    full_ys, visible_ysm = F.build_panels(df, cfg)

    # production factor table (all experience years) — the reusable artifact
    ftab = F.calibrate(full_ys, visible_ysm, cfg, cfg.experience_years)
    R.write_csv(ftab, os.path.join(out, "growth_factor_table.csv"))

    # honest backtest (factors from prior years only)
    print("Backtesting …")
    bt = B.run_backtest(full_ys, visible_ysm, cfg)

    # demo projection for the configured run point
    proj = project(visible_ysm, full_ys, ftab, cfg, cfg.project_year, cfg.project_month)
    R.write_csv(proj, os.path.join(out, "projected_premium.csv"))

    # optional: multiply by the Part-1 rate table -> expected losses
    coverage = {"has_rates": False}
    rt_path = _latest_rate_table(cfg.rate_table_glob) if cfg.rate_table_glob else None
    if rt_path:
        rates = pd.read_csv(rt_path)
        rate_col = "final_rate" if "final_rate" in rates.columns else None
        if rate_col:
            el = proj.merge(rates[cfg.keys + [rate_col]], on=cfg.keys, how="left")
            covered = el[rate_col].notna()
            el["expected_large_losses"] = el[rate_col].fillna(0) * el["projected_premium"]
            R.write_csv(el[cfg.keys + ["projected_premium", rate_col, "expected_large_losses"]],
                        os.path.join(out, "expected_losses.csv"))
            coverage = {"has_rates": True,
                        "total_expected": float(el["expected_large_losses"].sum()),
                        "covered_pct": float(el.loc[covered, "projected_premium"].sum()
                                             / el["projected_premium"].sum() * 100),
                        "rate_table": rt_path}

    # the markdown
    R.write_report_md(cfg, ftab, bt, proj, coverage, os.path.join(out, "report.md"))

    # console summary
    seg = bt[bt.method == "per-segment"]
    print("\n" + "=" * 70)
    print(f"  PREMIUM PROJECTION — {cfg.run_name}")
    print("=" * 70)
    print(f"  segments: {proj[cfg.keys].drop_duplicates().shape[0]} | "
          f"factor table: {len(ftab)} rows (segment × month)")
    print(f"  backtest per-segment: WAPE ~{seg.wape.mean():.1f}%  within±10% ~{seg.within.mean():.0f}%")
    if coverage["has_rates"]:
        print(f"  expected large losses ({cfg.project_year}): {coverage['total_expected']:.0f}  "
              f"(rate coverage {coverage['covered_pct']:.0f}%)")
        print(f"  rate table used: {coverage['rate_table']}")
    else:
        print("  (no Part-1 rate table found — produced premium only)")
    print(f"\n  outputs -> {out}{os.sep}")
    print("=" * 70)
    return {"out": out, "backtest": bt, "coverage": coverage}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    run(ap.parse_args().config)


if __name__ == "__main__":
    main()
