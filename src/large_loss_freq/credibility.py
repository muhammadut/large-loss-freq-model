"""Step 6: hierarchical Buhlmann credibility.

A raw GLM gives every segment a rate with equal confidence and cannot tell a
well-observed rate from a one-loss fluke. Credibility shrinks each cell's GLM
rate toward a SAME-INDUSTRY complement, in proportion to how much exposure backs
it (ASOP 25: never pull a cell toward an unrelated book).

Hierarchy:  cell -> (CovType x industry) -> industry -> portfolio
    Z_s = E_s / (E_s + K)
    final_rate_s = Z_s * glm_rate_s + (1 - Z_s) * complement_s
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .config import Config


def compute_K(rates, exposures, mean) -> float:
    """Buhlmann K = expected process variance / variance of hypothetical means.
    Guarded: <2 groups or ~zero between-variance => return total exposure (=> the
    degenerate case yields moderate, not spurious-full, credibility).

    KNOWN V1 SIMPLIFICATION (flagged for formal credibility-theory review): the
    variance-of-hypothetical-means is approximated by the raw exposure-weighted
    between-group variance, WITHOUT subtracting the expected process (sampling)
    variance. For rare-event Poisson data, observed between-group spread overstates
    the true VHM, which understates K and can over-credit thin segments. The effect
    is expected to be small at dispersion ~1, but the unbiased Buhlmann-Straub
    estimator (subtract process variance) is a Phase-2 refinement."""
    rates = np.asarray(rates, dtype=float)
    exposures = np.asarray(exposures, dtype=float)
    if len(rates) < 2:
        return float(exposures.sum())
    w = exposures / exposures.sum()
    between_var = float(np.average((rates - mean) ** 2, weights=w))
    if between_var < 1e-30:
        return float(exposures.sum())
    return float(mean / between_var)


def apply_credibility(glm_rates: pd.DataFrame, panel: pd.DataFrame, cfg: Config):
    """Return (result_frame, diagnostics). result_frame adds: complement_rate,
    hist_exposure, hist_large_losses, Z, final_rate."""
    keys = cfg.seg_keys
    ind = cfg.industry_key
    L1 = cfg.level1_keys

    # ---- aggregates per level (over the experience window) -------------------
    cell = (panel.groupby(keys, observed=True)
            .agg(hist_exposure=("expo", "sum"), hist_large_losses=("large_loss_count", "sum"))
            .reset_index())

    l1 = (panel.groupby(L1, observed=True)
          .agg(l1_exposure=("expo", "sum"), l1_losses=("large_loss_count", "sum")).reset_index())
    l1["l1_raw"] = l1["l1_losses"] / l1["l1_exposure"]

    l2 = (panel.groupby([ind], observed=True)
          .agg(l2_exposure=("expo", "sum"), l2_losses=("large_loss_count", "sum")).reset_index())
    l2["l2_raw"] = l2["l2_losses"] / l2["l2_exposure"]

    portfolio_rate = float(panel["large_loss_count"].sum() / panel["expo"].sum())

    # ---- K per level (variance components) -----------------------------------
    K_l2 = compute_K(l2["l2_raw"].values, l2["l2_exposure"].values, portfolio_rate)

    K_l1_vals = []
    for _, sub in l1.merge(l2[[ind, "l2_raw"]], on=ind, how="left").groupby(ind):
        if len(sub) >= 2:
            K_l1_vals.append(compute_K(sub["l1_raw"].values, sub["l1_exposure"].values, sub["l2_raw"].iloc[0]))
    K_l1 = float(np.mean(K_l1_vals)) if K_l1_vals else float(l1["l1_exposure"].sum())

    cell_r = cell.copy()
    cell_r["cell_raw"] = cell_r["hist_large_losses"] / cell_r["hist_exposure"]
    cell_r = cell_r.merge(l1[L1 + ["l1_raw"]], on=L1, how="left")
    K_cell_vals = []
    for _, sub in cell_r.groupby(L1):
        if len(sub) >= 2:
            K_cell_vals.append(compute_K(sub["cell_raw"].values, sub["hist_exposure"].values, sub["l1_raw"].iloc[0]))
    K_cell = float(np.mean(K_cell_vals)) if K_cell_vals else float(cell["hist_exposure"].sum())

    # ---- blend down the hierarchy --------------------------------------------
    l2["Z_l2"] = l2["l2_exposure"] / (l2["l2_exposure"] + K_l2)
    l2["l2_blended"] = l2["Z_l2"] * l2["l2_raw"] + (1 - l2["Z_l2"]) * portfolio_rate

    l1 = l1.merge(l2[[ind, "l2_blended"]], on=ind, how="left")
    l1["Z_l1"] = l1["l1_exposure"] / (l1["l1_exposure"] + K_l1)
    l1["l1_blended"] = l1["Z_l1"] * l1["l1_raw"] + (1 - l1["Z_l1"]) * l1["l2_blended"]

    out = (glm_rates
           .merge(cell[keys + ["hist_exposure", "hist_large_losses"]], on=keys, how="left")
           .merge(l1[L1 + ["l1_blended"]], on=L1, how="left"))
    out["hist_exposure"] = out["hist_exposure"].fillna(0.0)
    out["hist_large_losses"] = out["hist_large_losses"].fillna(0).astype(int)
    out["complement_rate"] = out["l1_blended"].fillna(portfolio_rate)
    out["Z"] = out["hist_exposure"] / (out["hist_exposure"] + K_cell)
    out["final_rate"] = out["Z"] * out["glm_rate"] + (1 - out["Z"]) * out["complement_rate"]
    out = out.drop(columns=["l1_blended"])

    diag = {"portfolio_rate": portfolio_rate, "K_cell": K_cell, "K_l1": K_l1, "K_l2": K_l2}
    return out, diag
