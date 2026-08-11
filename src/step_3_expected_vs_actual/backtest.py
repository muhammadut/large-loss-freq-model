"""Walk-forward backtest of the whole Step-3 chain.

For each target year Y we use ONLY information available before it:

    rates   = recalibrate the Step-1 GLM + credibility on years < Y (ref = Y-1)
    premium = Step-2 growth factors calibrated on years < Y, projected onto Y
    expected(Y) = Σ ( rate × projected premium )
    verdict = is the ACTUAL count of Y inside the model's 5–95% band?

Nothing from year Y (or later) touches the rates, the factors, or the band — so a
pass is genuine out-of-sample evidence that the production chain predicts a year
it never saw. Run at month 12 (full premium known → tests the rate model) and at
month 6 (premium also projected → the live mid-year scenario, both models OOS).

The most recent year is still developing (reporting lag), so it is reported for
context but NOT scored — comparing a full-year expectation to a partial-year
actual would fail the model for a data-maturity reason.
"""
from __future__ import annotations
import pandas as pd

from step_1_frequency import panel as panel_mod
from step_1_frequency import model as model_mod
from step_1_frequency import credibility as cred_mod
from step_2_premium import factors as F
from step_2_premium.project import project

from .ave import portfolio_ave
from . import actuals as AC


def _recalibrate_rates(df, s1cfg, train_years):
    """Step-1 calibration (GLM + credibility) on train_years only. Returns
    (rate_table[keys+final_rate], dispersion, portfolio_rate_for_unseen)."""
    p = panel_mod.build_panel(df, s1cfg, s1cfg.lens_col, train_years)
    m, disp = model_mod.fit(p, s1cfg)
    glm = model_mod.extract_rates(m, p, s1cfg, reference_year=max(train_years))
    cred, _ = cred_mod.apply_credibility(glm, p, s1cfg)
    port = float(p["large_loss_count"].sum() / p["expo"].sum())
    return cred[s1cfg.seg_keys + ["final_rate"]], float(disp), port


def _expected_for(df, s1cfg, cfg2, full_ys, vis, keys, Y, month, rates_fold, port):
    """Project premium for Y at `month` with prior-year factors, × the fold rates."""
    ftab = F.calibrate(full_ys, vis, cfg2, [y for y in cfg2.experience_years if y < Y])
    proj = project(vis, full_ys, ftab, cfg2, Y, month)
    el = proj.merge(rates_fold, on=keys, how="left")
    covered = el["final_rate"].notna()
    el["final_rate"] = el["final_rate"].fillna(port)          # unseen segment -> portfolio rate
    el["expected"] = el["final_rate"] * el["projected_premium"]
    cov = float(el.loc[covered, "projected_premium"].sum()
                / el["projected_premium"].sum() * 100) if len(el) else 0.0
    return el, cov


def run_backtest(df, s1cfg, cfg2, full_ys, vis, cfg):
    """Return (scored_rows_df, immature_rows_list)."""
    keys = cfg2.keys
    all_years = sorted(set(int(y) for y in df[s1cfg.year_col].unique()))
    rows = []

    for Y in cfg.bt_folds:
        train = [y for y in all_years if y < Y]
        if len(train) < 1:
            continue
        rates_fold, disp, port = _recalibrate_rates(df, s1cfg, train)
        actual = AC.total_for_year(df, s1cfg, Y)
        actual_seg = AC.counts_for_year(df, s1cfg, Y)
        for month in cfg.bt_run_months:
            el, cov = _expected_for(df, s1cfg, cfg2, full_ys, vis, keys, Y, month, rates_fold, port)
            expected = float(el["expected"].sum())
            v = portfolio_ave(expected, actual, disp, cfg.green_band, cfg.amber_band)
            seg = (el.groupby(keys, observed=True)["expected"].sum().reset_index()
                   .merge(actual_seg, on=keys, how="left").fillna({"actual_losses": 0}))
            rho = float(seg["expected"].corr(seg["actual_losses"], method="spearman"))
            rows.append({
                "year": Y, "train": f"{min(train)}–{max(train)}", "run_month": month,
                "expected": v["expected"], "actual": actual, "percentile": v["percentile"],
                "band_5_95": f"{v['ci_5th']}–{v['ci_95th']}",
                "in_band": bool(v["ci_5th"] <= actual <= v["ci_95th"]),
                "light": v["traffic_light"], "dispersion": round(disp, 2),
                "coverage_pct": round(cov, 0), "segment_spearman": round(rho, 2),
            })

    immature = []
    for Y in cfg.bt_immature:
        train = [y for y in all_years if y < Y]
        if not train:
            continue
        rates_fold, _, port = _recalibrate_rates(df, s1cfg, train)
        el, _ = _expected_for(df, s1cfg, cfg2, full_ys, vis, keys, Y, 12, rates_fold, port)
        immature.append({"year": Y, "expected": round(float(el["expected"].sum()), 1),
                         "reported": AC.total_for_year(df, s1cfg, Y),
                         "train": f"{min(train)}–{max(train)}"})

    return pd.DataFrame(rows), immature
