#!/usr/bin/env python3
"""Entry point for Step 3 — Expected vs Actual.

    python src/step_3_expected_vs_actual/run.py --config src/step_3_expected_vs_actual/config.yaml

Consumes Step 1 (rate table) and Step 2 (premium projection), compares expected
to actual large-loss counts, and writes the board deliverable in
outputs/step_3_expected_vs_actual/<run>_<date>/:
    board_report.md     the verdict + waterfall + narrative + caveats (open this)
    segment_ave.csv     per-segment expected vs actual (verdict year)
    ave_summary.csv     portfolio verdict row
    waterfall.csv       the attribution bridge
    narrative.txt       the auto board paragraph
    ave_report.json     machine-readable audit record
"""
from __future__ import annotations
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

from step_3_expected_vs_actual.config import load_config
from step_3_expected_vs_actual import actuals as AC
from step_3_expected_vs_actual import expected as EX
from step_3_expected_vs_actual import ave as AV
from step_3_expected_vs_actual import waterfall as WF
from step_3_expected_vs_actual import narrative as NA
from step_3_expected_vs_actual import backtest as BT
from step_3_expected_vs_actual import report as R


def _seg_frame(cfg2, full_ys, vis, ftab, rates, actuals_df, s1cfg, keys, year, month):
    """Per-segment [*keys, projected_premium, frequency_rate, expected_losses,
    actual_losses] for one year — expected (Step 2 × rate) joined to actual."""
    el, cov = EX.expected_for_year(cfg2, full_ys, vis, ftab, rates, year, month)
    ac = AC.counts_for_year(actuals_df, s1cfg, year)
    seg = el.merge(ac, on=keys, how="outer")
    for c in ["projected_premium", "frequency_rate", "expected_losses"]:
        seg[c] = seg[c].fillna(0.0)
    seg["actual_losses"] = seg["actual_losses"].fillna(0).astype(int)
    return seg, cov


def run(config_path: str):
    cfg = load_config(config_path)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = os.path.join(cfg.output_dir, f"{cfg.run_name}_{ts}")
    os.makedirs(out, exist_ok=True)
    month = cfg.run_month

    print("Building Step-2 factor table and loading the rate table …")
    cfg2, full_ys, vis, ftab = EX.build_step2(cfg.step2_config)
    rates, rate_path, disp_auto = EX.load_rate_table(cfg.rate_table_glob)
    dispersion = float(cfg.overdispersion) if cfg.overdispersion is not None else (disp_auto or 1.0)
    keys = cfg2.keys

    print("Loading and flagging actuals (Step-1 basis) …")
    actuals_df, s1cfg = AC.load_actuals(cfg.step1_config)

    # ---- verdict year (mature) + prior year (for the waterfall) -------------
    seg_v, cov_v = _seg_frame(cfg2, full_ys, vis, ftab, rates, actuals_df, s1cfg,
                              keys, cfg.verdict_year, month)
    seg_p, _ = _seg_frame(cfg2, full_ys, vis, ftab, rates, actuals_df, s1cfg,
                          keys, cfg.prior_year, month)

    actual_v = AC.total_for_year(actuals_df, s1cfg, cfg.verdict_year)
    expected_v = float(seg_v["expected_losses"].sum())
    verdict = AV.portfolio_ave(expected_v, actual_v, dispersion,
                               cfg.green_band, cfg.amber_band)

    wf = WF.attribution(seg_p, seg_v, keys)
    narrative = NA.board_narrative(verdict, wf, cfg.verdict_year, cfg.prior_year)

    # ---- current-year watch (immature) --------------------------------------
    current_watch = None
    by_year = AC.counts_by_year(actuals_df, s1cfg)
    if cfg.current_year is not None:
        seg_c, _ = _seg_frame(cfg2, full_ys, vis, ftab, rates, actuals_df, s1cfg,
                              keys, cfg.current_year, 12)   # month 12: full premium known
        current_watch = {
            "year": cfg.current_year,
            "expected": float(seg_c["expected_losses"].sum()),
            "actual_reported": AC.total_for_year(actuals_df, s1cfg, cfg.current_year),
        }

    # ---- walk-forward backtest (recalibrates rates + factors per fold) ------
    print("Backtesting (walk-forward, out-of-sample) …")
    bt, immature = BT.run_backtest(actuals_df, s1cfg, cfg2, full_ys, vis, cfg)
    R.write_csv(bt, os.path.join(out, "backtest.csv"))
    R.write_backtest_report(os.path.join(out, "backtest_report.md"), bt, immature, cfg.verdict_year)

    # (Per-segment analysis is its own step now — see src/step_4_segment_analysis/.)

    # ---- write artifacts ----------------------------------------------------
    R.write_csv(seg_v.sort_values("expected_losses", ascending=False),
                os.path.join(out, "segment_ave.csv"))
    R.write_csv(pd.DataFrame([verdict]), os.path.join(out, "ave_summary.csv"))
    R.write_csv(pd.DataFrame([wf]), os.path.join(out, "waterfall.csv"))
    with open(os.path.join(out, "narrative.txt"), "w", encoding="utf-8") as fh:
        fh.write(narrative + "\n")
    R.write_json(os.path.join(out, "ave_report.json"), {
        "run": cfg.run_name, "timestamp": ts, "rate_table": rate_path,
        "dispersion": dispersion, "run_month": month, "rate_coverage_pct": round(cov_v, 1),
        "verdict_year": cfg.verdict_year, "prior_year": cfg.prior_year,
        "verdict": verdict, "waterfall": wf, "current_watch": current_watch,
        "backtest": bt.to_dict(orient="records"), "backtest_immature": immature,
    })
    R.write_board_report(
        os.path.join(out, "board_report.md"), cfg=cfg, rate_table_path=rate_path,
        dispersion=dispersion, verdict=verdict, wf=wf, narrative=narrative,
        seg_verdict=seg_v, keys=keys, verdict_year=cfg.verdict_year,
        prior_year=cfg.prior_year, run_month=month, current_watch=current_watch,
        by_year=by_year)

    # ---- console summary ----------------------------------------------------
    print("\n" + "=" * 70)
    print(f"  EXPECTED vs ACTUAL — verdict year {cfg.verdict_year}")
    print("=" * 70)
    print(f"  expected {verdict['expected']:.1f} | actual {verdict['actual']} | "
          f"{verdict['percentile']:.0f}th pct | {verdict['band_model']} | "
          f"{verdict['traffic_light']}")
    print(f"  rate coverage {cov_v:.0f}% | rate table {os.path.basename(os.path.dirname(rate_path))}")
    if len(bt):
        print(f"  backtest (walk-forward): {int(bt['in_band'].sum())}/{len(bt)} OOS predictions "
              f"inside the 5–95% band across folds {sorted(set(bt['year']))}")
    if current_watch:
        print(f"  watch {current_watch['year']}: expected ~{current_watch['expected']:.0f} "
              f"vs {current_watch['actual_reported']} reported (immature — not a verdict)")
    print(f"\n  outputs -> {out}{os.sep}")
    print("=" * 70)
    return {"out": out, "verdict": verdict, "waterfall": wf}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    run(ap.parse_args().config)


if __name__ == "__main__":
    main()
