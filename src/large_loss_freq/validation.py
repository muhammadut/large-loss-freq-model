"""The validation gates. Each returns a structured GateResult so every run is
auditable and future refits can be diffed against prior ones (drift detection).

Status:  PASS | WARN | HALT  (HALT only when a gate's on_fail == 'halt')
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
import numpy as np
import pandas as pd
from scipy import stats

from .config import Config
from . import panel as panel_mod
from . import model as model_mod
from . import credibility as cred_mod


@dataclass
class GateResult:
    name: str
    value: Any
    threshold: Any
    status: str       # PASS | WARN | HALT
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


def _status(ok: bool, on_fail: str) -> str:
    if ok:
        return "PASS"
    return "HALT" if on_fail == "halt" else "WARN"


# --------------------------------------------------------------------------- #
def gate_reconciliation(model, panel, cfg: Config) -> GateResult:
    g = cfg.gates["reconciliation"]
    actual = float(panel["large_loss_count"].sum())
    fitted = float(model.fittedvalues.sum())
    ok = abs(actual - fitted) <= max(1.0, g["tol_pct"] / 100.0 * actual)
    return GateResult("reconciliation", f"actual={actual:.0f}, fitted={fitted:.2f}",
                      f"|diff| <= {g['tol_pct']}%", _status(ok, g["on_fail"]),
                      "IMPLEMENTATION INVARIANT (not a model-performance test): a Poisson "
                      "MLE with intercept reproduces the total by construction; failure here "
                      "means an offset/convergence bug, not a good or bad model.")


def gate_dispersion(dispersion: float, cfg: Config) -> GateResult:
    g = cfg.gates["dispersion"]
    ok = dispersion <= g["max_ratio"]
    return GateResult("dispersion", round(dispersion, 3), f"<= {g['max_ratio']}",
                      _status(ok, g["on_fail"]),
                      "Pearson chi2/df near 1 => Poisson adequate; high => missing driver / consider NB.")


def gate_thin_segment_share(cred_df: pd.DataFrame, cfg: Config) -> GateResult:
    g = cfg.gates["thin_segment_share"]
    thr = cfg.full_credibility_losses
    thin_pct = float((cred_df["hist_large_losses"] < thr).mean() * 100)
    ok = thin_pct <= g["max_thin_pct"]
    return GateResult("thin_segment_share", f"{thin_pct:.1f}% thin (<{thr} losses)",
                      f"<= {g['max_thin_pct']}%", _status(ok, g["on_fail"]),
                      "INFORMATIONAL: share of segments too thin to trust raw — these rely on the "
                      "credibility complement. A PASS here does NOT mean segments are individually credible.")


def gate_backtest(df: pd.DataFrame, cfg: Config) -> GateResult:
    """Aggregate out-of-sample: train on years before holdout, predict the
    (mature) holdout year's total."""
    g = cfg.gates["backtest"]
    holdout = g["holdout_year"]
    train_years = [y for y in cfg.experience_years if y < holdout]
    p = panel_mod.build_panel(df, cfg, cfg.lens_col, train_years)
    m, _ = model_mod.fit(p, cfg)
    rates = model_mod.extract_rates(m, p, cfg, reference_year=max(train_years))
    expo = (df[df[cfg.year_col] == holdout].groupby(cfg.seg_keys, observed=True)[cfg.lens_col]
            .sum().reset_index(name="expo"))
    bt = expo.merge(rates, on=cfg.seg_keys, how="left")
    bt["glm_rate"] = bt["glm_rate"].fillna(rates["glm_rate"].mean())
    expected = float((bt["glm_rate"] * bt["expo"]).sum())
    actual = int(df[df[cfg.year_col] == holdout]["is_large_loss"].sum())
    lo, hi = stats.poisson.ppf([0.05, 0.95], expected)
    ok = lo <= actual <= hi
    return GateResult("backtest", f"predicted={expected:.0f}, actual={actual}",
                      f"actual in [{lo:.0f},{hi:.0f}]", _status(ok, g["on_fail"]),
                      f"Aggregate out-of-sample: train < {holdout}, predict {holdout}.")


def backtest_segment_diagnostics(df: pd.DataFrame, cfg: Config):
    """Segment-level holdout calibration (the aggregate backtest can pass while
    segments are mispriced). Returns (GateResult, decile_table_list)."""
    g = cfg.gates["backtest_segment"]
    holdout = cfg.gates["backtest"]["holdout_year"]
    train_years = [y for y in cfg.experience_years if y < holdout]
    p = panel_mod.build_panel(df, cfg, cfg.lens_col, train_years)
    m, _ = model_mod.fit(p, cfg)
    rates = model_mod.extract_rates(m, p, cfg, reference_year=max(train_years))
    expo = (df[df[cfg.year_col] == holdout].groupby(cfg.seg_keys, observed=True)[cfg.lens_col]
            .sum().reset_index(name="expo"))
    actual = (df[df[cfg.year_col] == holdout].groupby(cfg.seg_keys, observed=True)["is_large_loss"]
              .sum().reset_index(name="actual"))
    bt = (expo.merge(rates, on=cfg.seg_keys, how="left").merge(actual, on=cfg.seg_keys, how="left")
          .fillna({"actual": 0}))
    bt["glm_rate"] = bt["glm_rate"].fillna(rates["glm_rate"].mean())
    bt["expected"] = bt["glm_rate"] * bt["expo"]
    rho = float(bt["expected"].corr(bt["actual"], method="spearman"))

    # decile calibration: bucket segments by predicted expected count
    bt = bt.sort_values("expected", ascending=False).reset_index(drop=True)
    bt["bucket"] = (pd.qcut(bt.index + 1, 10, labels=False) + 1).astype(int)
    dec = (bt.groupby("bucket").agg(segments=("expected", "size"),
                                    expected=("expected", "sum"),
                                    actual=("actual", "sum")).reset_index())
    decile_table = [{"bucket": int(r.bucket), "segments": int(r.segments),
                     "expected": round(float(r.expected), 2), "actual": int(r.actual)}
                    for r in dec.itertuples()]
    ok = rho >= g["min_spearman"]
    gr = GateResult("backtest_segment", round(rho, 3), f"Spearman >= {g['min_spearman']}",
                    _status(ok, g["on_fail"]),
                    "Segment-level holdout rank calibration; pricing uses segment rates, "
                    "not just the portfolio total.")
    return gr, decile_table


def gate_robustness(df: pd.DataFrame, cfg: Config, full_cred: pd.DataFrame) -> GateResult:
    """Drop the newest (possibly immature) year and refit; the FINAL (credibilized)
    rates should be stable. We measure the board-facing FINAL rates, not the raw GLM
    rates — raw thin-segment rates swing wildly but credibility absorbs most of it."""
    g = cfg.gates["robustness_drop_yr"]
    newest = max(cfg.experience_years)
    kept = [y for y in cfg.experience_years if y != newest]
    p = panel_mod.build_panel(df, cfg, cfg.lens_col, kept)
    m, _ = model_mod.fit(p, cfg)
    glm = model_mod.extract_rates(m, p, cfg, reference_year=cfg.reference_year)
    cred_drop, _ = cred_mod.apply_credibility(glm, p, cfg)

    merged = full_cred[cfg.seg_keys + ["final_rate"]].merge(
        cred_drop[cfg.seg_keys + ["final_rate"]], on=cfg.seg_keys, suffixes=("_all", "_drop"))
    corr = float(merged["final_rate_all"].corr(merged["final_rate_drop"]))
    rel = (merged["final_rate_drop"] / merged["final_rate_all"] - 1).abs() * 100
    p95 = float(rel.quantile(0.95))
    n_big = int((rel > 50).sum())
    # Pass on a STABILITY metric (p95 relative move), not correlation: credibility
    # compresses rates into a narrow band, which makes correlation hypersensitive
    # and a poor robustness signal. "No segment moves much" is what we actually want.
    ok = p95 <= g["max_p95_move_pct"]
    return GateResult("robustness_drop_yr",
                      f"final-rate p95 move={p95:.1f}%, >50%={n_big}, corr={corr:.3f}",
                      f"p95 move <= {g['max_p95_move_pct']}%", _status(ok, g["on_fail"]),
                      f"FINAL-rate stability when dropping {newest}; measured post-credibility.")


def gate_total_preservation(cred_df: pd.DataFrame, df: pd.DataFrame, cfg: Config) -> GateResult:
    """Credibility should redistribute, not MATERIALLY move, the portfolio total.
    (It is a tolerance check, not exact preservation by construction.)"""
    g = cfg.gates["total_preservation"]
    expo = (df[df[cfg.year_col] == cfg.reference_year].groupby(cfg.seg_keys, observed=True)[cfg.lens_col]
            .sum().reset_index(name="expo_ref"))
    chk = cred_df.merge(expo, on=cfg.seg_keys, how="left").fillna({"expo_ref": 0.0})
    exp_glm = float((chk["glm_rate"] * chk["expo_ref"]).sum())
    exp_final = float((chk["final_rate"] * chk["expo_ref"]).sum())
    drift = (exp_final - exp_glm) / exp_glm * 100 if exp_glm else 0.0
    ok = abs(drift) <= g["max_drift_pct"]
    return GateResult("total_preservation", f"GLM={exp_glm:.2f} -> final={exp_final:.2f} ({drift:+.2f}%)",
                      f"|drift| <= {g['max_drift_pct']}%", _status(ok, g["on_fail"]),
                      "Credibility redistributes risk; the total should move only within tolerance.")


def gate_base_agreement(primary_final: pd.DataFrame, alt_final: pd.DataFrame,
                        cfg: Config) -> GateResult:
    """Informational: do the primary and alternate lenses rank segments alike?"""
    g = cfg.gates["base_agreement"]
    both = primary_final[cfg.seg_keys + ["final_rate"]].merge(
        alt_final[cfg.seg_keys + ["final_rate"]], on=cfg.seg_keys, suffixes=("_prm", "_alt"))
    rho = float(both["final_rate_prm"].corr(both["final_rate_alt"], method="spearman"))
    ok = rho >= g["min_corr"]
    return GateResult("base_agreement", round(rho, 3), f">= {g['min_corr']} (informational)",
                      _status(ok, g["on_fail"]),
                      f"Spearman(primary '{cfg.lens}' vs '{g['alt_lens']}'). "
                      "Low => the lenses measure genuinely different things (price vs asset value).")


def any_halt(gates: list[GateResult]) -> bool:
    return any(gr.status == "HALT" for gr in gates)
