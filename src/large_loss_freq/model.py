"""Step 5: fit the Poisson GLM with a year fixed effect and read out the clean
segment rates at the reference year.

The year effect is what on-levels the rate (absorbs year-wide rate/inflation
shifts), so the segment coefficients come out at one consistent level.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from .config import Config


def build_formula(cfg: Config) -> str:
    """large_loss_count ~ C(seg_1) + ... + C(seg_k) [+ C(year)]"""
    terms = [f"C({k})" for k in cfg.seg_keys]
    if cfg.year_effect:
        terms.append(f"C({cfg.year_col})")
    return "large_loss_count ~ " + " + ".join(terms)


def fit(panel: pd.DataFrame, cfg: Config):
    """Fit the frequency GLM with log(exposure) as an offset.

    V1 uses Poisson. Negative Binomial is intentionally NOT auto-fitted: in
    statsmodels' GLM the NB dispersion (alpha) is held fixed at a default, which
    is a known trap. If the dispersion gate flags overdispersion we surface it
    rather than silently fit a mis-specified NB. Returns (model, dispersion).
    """
    formula = build_formula(cfg)
    family = sm.families.Poisson()
    model = smf.glm(formula, data=panel, family=family, offset=panel["log_exposure"]).fit()
    dispersion = float(model.pearson_chi2 / model.df_resid)
    return model, dispersion


def nested_aic_comparison(panel: pd.DataFrame, cfg: Config) -> list[dict]:
    """Fit the model in nested stages on the SAME panel (year-only → +each segment
    key → full) so AIC/BIC are genuinely comparable. This demonstrates the VALID
    use of AIC — comparing nested models on identical data — as opposed to ranking
    models fit to different aggregations (which is meaningless)."""
    results = []
    base = [f"C({cfg.year_col})"] if cfg.year_effect else []
    cumulative: list[str] = []
    specs = [("year only", [])]
    for k in cfg.seg_keys:
        cumulative = cumulative + [k]
        specs.append((f"+ {k}", list(cumulative)))
    specs[-1] = (specs[-1][0] + " (full)", specs[-1][1])

    for label, segs in specs:
        terms = [f"C({s})" for s in segs] + base
        formula = "large_loss_count ~ " + (" + ".join(terms) if terms else "1")
        m = smf.glm(formula, data=panel, family=sm.families.Poisson(),
                    offset=panel["log_exposure"]).fit()
        k = int(m.df_model) + 1
        bic = float(-2 * m.llf + k * np.log(m.nobs))
        results.append({"model": label,
                        "added": (segs[-1] if segs else "—"),
                        "params": k, "deviance": float(m.deviance),
                        "aic": float(m.aic), "bic": bic})
    return results


def extract_rates(model, panel: pd.DataFrame, cfg: Config,
                  reference_year: int | None = None) -> pd.DataFrame:
    """Predict the clean rate per $1 of exposure for each unique segment, at the
    reference-year level (offset zeroed). Returns keys + 'glm_rate'.

    Guards unseen categorical levels: statsmodels/patsy raises a cryptic error if
    asked to predict for a year (or any factor level) not in the fitted data. We
    convert that into a clear, actionable message. NOTE: the forward-projection
    layer (predicting a FUTURE year or a NEW segment) must add explicit fallback
    rules for unseen levels before calling predict(); this guard only fails loudly.
    """
    reference_year = cfg.reference_year if reference_year is None else reference_year
    if reference_year not in set(panel[cfg.year_col].unique()):
        raise ValueError(
            f"reference_year {reference_year} is not among the fitted year levels "
            f"{sorted(panel[cfg.year_col].unique())}. Predicting an unseen level is "
            f"not supported here — a future-year projection needs explicit unseen-level "
            f"fallback rules (map new levels to an industry/portfolio complement).")
    segs = panel[cfg.seg_keys].drop_duplicates().reset_index(drop=True)
    segs[cfg.year_col] = reference_year
    try:
        segs["glm_rate"] = model.predict(segs, offset=np.zeros(len(segs)))
    except Exception as exc:  # pragma: no cover - defensive clarity wrapper
        raise ValueError(
            f"GLM prediction failed, likely an unseen categorical level in {cfg.seg_keys}. "
            f"Add unseen-level fallback before predicting. Original error: {exc}") from exc
    return segs[cfg.seg_keys + ["glm_rate"]].copy()
