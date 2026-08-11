#!/usr/bin/env python3
"""Entry point for Step 4 — Segment analysis.

    python src/step_4_segment_analysis/run.py --config src/step_4_segment_analysis/config.yaml

Reads the latest Step-1 rate table, rebuilds the Step-2 premium panels, counts the
actual large losses, and writes the four-lens segment report in
outputs/step_4_segment_analysis/<run>_<date>/:
    step_4_segment_analysis.md   the four business lenses (concentration / accuracy / drift / confidence)
    segment_master.csv    every segment × every metric (rate, Z, expected/actual/O-E per year)
"""
from __future__ import annotations
import glob
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows consoles default to cp1252; make our summary safe to print regardless.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

from step_4_segment_analysis.config import load_config
from step_4_segment_analysis import actuals as AC
from step_4_segment_analysis import segments as SEG
from step_4_segment_analysis import investigate as INV
from step_4_segment_analysis import report as R

from step_2_premium.config import load_config as load_step2
from step_2_premium import factors as F


def _latest_rate_table(glob_pattern: str) -> str:
    hits = glob.glob(glob_pattern, recursive=True)
    if not hits:
        raise SystemExit(f"No rate table found for pattern {glob_pattern!r}. "
                         f"Run Step 1 first (python src/run.py --config src/config/config.yaml).")
    return max(hits, key=os.path.getmtime)


def run(config_path: str):
    cfg = load_config(config_path)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = os.path.join(cfg.output_dir, f"{cfg.run_name}_{ts}")
    os.makedirs(out, exist_ok=True)

    print("Building Step-2 premium panels …")
    cfg2 = load_step2(cfg.step2_config)
    book = F.load_book(cfg2)
    full_ys, _vis = F.build_panels(book, cfg2)

    rate_path = _latest_rate_table(cfg.rate_table_glob)
    rates = pd.read_csv(rate_path)
    if "final_rate" not in rates.columns:
        raise SystemExit(f"Rate table {rate_path} has no 'final_rate' column.")

    print("Loading and flagging actuals (Step-1 basis) …")
    actuals_df, s1cfg = AC.load_actuals(cfg.step1_config)

    print("Building segment analysis …")
    years = cfg.years
    master, vy = SEG.build_master(rates, full_ys, actuals_df, s1cfg, cfg2, years)
    conc_all, conc_top = SEG.concentration(master, cfg.top_segments)
    under, over, rho = SEG.accuracy(master, years, cfg.material_expected)
    drift_moving, _ = SEG.drift(master, years, cfg.drift_min_losses, cfg.drift_hot, cfg.drift_cold)
    views = {"conc_all": conc_all, "conc_top": conc_top, "under": under, "over": over,
             "rho": rho, "drift_moving": drift_moving, "confidence": SEG.confidence(master)}

    R.write_segment_report(os.path.join(out, "step_4_segment_analysis.md"), master, vy, years, views)

    # ---- investigation: validate the misses, dossier the real ones ----------
    print("Investigating segment-level misses …")
    summary, mat, dossiers, detail = INV.investigate(
        rates, full_ys, actuals_df, s1cfg, cfg2, years,
        alpha=cfg.significance_alpha, material=cfg.material_expected, n_dossiers=cfg.n_dossiers)
    R.write_investigation_report(os.path.join(out, "segment_investigation.md"),
                                 summary, mat, dossiers, years)

    # enrich the master CSV with the significance verdict, then write it
    master = master.merge(detail, on=cfg2.keys, how="left")
    R.write_csv(master.drop(columns=["seg"]).sort_values("expected", ascending=False),
                os.path.join(out, "segment_master.csv"))

    print("\n" + "=" * 70)
    print(f"  SEGMENT ANALYSIS — anchor year {vy}")
    print("=" * 70)
    print(f"  segments: {len(master)} | rate table {os.path.basename(os.path.dirname(rate_path))}")
    print(f"  concentration: top5 = {conc_all.head(5)['contribution_pct'].sum():.0f}% of expected losses")
    print(f"  accuracy: rank rho {rho:.2f} | {len(under)} under / {len(over)} over shown")
    print(f"  drift: {len(drift_moving)} segments running hot/cold")
    print(f"  investigation: {summary['n_sig_high']} sig-high / {summary['n_sig_low']} sig-low of "
          f"{summary['n_material']} material (chance ~{summary['expected_each']:.0f} each) -> "
          f"{'well-calibrated' if summary['well_calibrated'] else 'review'}; {len(dossiers)} dossiers")
    print(f"\n  outputs -> {out}{os.sep}")
    print("=" * 70)
    return {"out": out, "master": master}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    run(ap.parse_args().config)


if __name__ == "__main__":
    main()
