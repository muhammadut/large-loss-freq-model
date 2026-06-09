"""Orchestrator: wires the stages together into one auditable calibration run.

    config -> data -> quality gates (halt) -> panel -> GLM -> credibility
           -> validation gates -> write rate_table_final.csv + run_report.json

Ends at the credibilized rate table. The forward projection is downstream.
"""
from __future__ import annotations
import os
from datetime import datetime

from .config import load_config
from . import data as data_mod
from . import panel as panel_mod
from . import model as model_mod
from . import credibility as cred_mod
from . import validation as val
from . import report as report_mod


def run(config_path: str) -> dict:
    cfg = load_config(config_path)
    # Each run gets its own dated, human-readable folder: outputs/<name>_<date_time>/
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = os.path.join(cfg.output_dir, f"{cfg.run_name}_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)

    # ---- 1. load + data-quality gates (halt on fatal) -----------------------
    df = data_mod.load_and_prepare(cfg)
    quality = data_mod.quality_gates(df, cfg)
    data_mod.assert_quality(quality)

    n_large = int(df[df[cfg.year_col].isin(cfg.experience_years)]["is_large_loss"].sum())

    # ---- 2. panel + GLM + credibility (primary lens) ------------------------
    panel = panel_mod.build_panel(df, cfg)
    dropped = panel_mod.losses_dropped(df, panel, cfg)
    if dropped:
        print(f"NOTE: {dropped} large loss(es) dropped (zero-exposure segments).")

    model, dispersion = model_mod.fit(panel, cfg)
    glm_rates = model_mod.extract_rates(model, panel, cfg)
    cred, diag = cred_mod.apply_credibility(glm_rates, panel, cfg)

    # ---- 3. validation gates ------------------------------------------------
    gates = [
        val.gate_reconciliation(model, panel, cfg),
        val.gate_dispersion(dispersion, cfg),
        val.gate_thin_segment_share(cred, cfg),
        val.gate_backtest(df, cfg),
    ]
    seg_gate, decile_table = val.backtest_segment_diagnostics(df, cfg)
    gates.append(seg_gate)
    gates.append(val.gate_robustness(df, cfg, cred))          # measured on FINAL rates
    gates.append(val.gate_total_preservation(cred, df, cfg))

    # base-agreement: run the alternate lens through the same pipeline, AND
    # run that lens's exposure-integrity check (not just the primary lens).
    ba = cfg.gates.get("base_agreement")
    if ba:
        alt_lens = ba["alt_lens"]
        alt_col = cfg.col_for_lens(alt_lens)
        quality.append(data_mod.exposure_integrity(df, cfg, alt_col, alt_lens))
        p2 = panel_mod.build_panel(df, cfg, alt_col)
        m2, _ = model_mod.fit(p2, cfg)
        r2 = model_mod.extract_rates(m2, p2, cfg)
        c2, _ = cred_mod.apply_credibility(r2, p2, cfg)
        gates.append(val.gate_base_agreement(cred, c2, cfg))

    # ---- 4. outputs (all into the dated run folder) -------------------------
    rate_path = os.path.join(run_dir, "rate_table_final.csv")
    report_path = os.path.join(run_dir, "run_report.json")
    summary_path = os.path.join(run_dir, "run_summary.md")
    diagnostics_path = os.path.join(run_dir, "model_diagnostics.md")
    rate_table = report_mod.write_rate_table(cred, cfg, rate_path)

    # classical GLM diagnostics (AIC/BIC/p-values), with a valid nested comparison
    nested = model_mod.nested_aic_comparison(panel, cfg)
    report_mod.write_model_diagnostics_md(cfg, model, nested, dispersion, timestamp, diagnostics_path)
    extras = {
        "maturity_evidence": report_mod.maturity_table(df, cfg),
        "backtest_segment_deciles": decile_table,
    }
    report = report_mod.write_run_report(cfg, gates, quality, diag, dispersion,
                                         n_large, len(rate_table), report_path, extras=extras)
    report_mod.write_run_summary_md(cfg, gates, quality, dispersion, n_large,
                                    rate_table, timestamp, summary_path)
    report_mod.print_summary(cfg, gates, quality, dispersion, n_large, rate_table)

    print(f"  run folder      -> {run_dir}{os.sep}")
    print(f"  explained report-> {summary_path}   <-- what every check means")
    print(f"  model diagnostics-> {diagnostics_path}   <-- AIC/BIC/p-values, explained")
    print(f"  overall status  : {report['overall_status']}")

    if val.any_halt(gates):
        raise SystemExit("A validation gate returned HALT; see run report.")

    return {"rate_table": rate_table, "gates": gates, "report": report}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Large-Loss Frequency calibration pipeline.")
    ap.add_argument("--config", required=True, help="path to config.yaml")
    args = ap.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
