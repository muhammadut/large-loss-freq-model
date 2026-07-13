"""Segment investigation — validate the misses and dig into the real ones.

The question this answers: *when a segment predicts low but comes in high, is that
a genuine under-rating, or just rare-event noise?* Large-loss counts are small and
Poisson-lumpy, so most "big gaps" are chance. This module separates signal from
noise segment by segment, and builds a dossier on the ones that are real.

Per material segment (expected >= threshold), for the anchor year:
  p_high = P(count >= actual | expected)   -> is the actual significantly high?
  p_low  = P(count <= actual | expected)   -> significantly low?
Then a multi-year read (net O/E + how many years the actual beat expected) tells a
one-year spike apart from a persistent pattern, and a portfolio calibration check
(how many segments land outside their band vs how many chance predicts) validates
the model as a whole.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats

from . import actuals as AC


def _p_high(exp, act):
    return float(1 - stats.poisson.cdf(act - 1, max(exp, 1e-9)))


def _p_low(exp, act):
    return float(stats.poisson.cdf(act, max(exp, 1e-9)))


def _per_year(rates, full_ys, actuals_df, s1cfg, cfg2, year):
    keys, ycol = cfg2.keys, cfg2.year_col
    prem = full_ys[full_ys[ycol] == year][keys + ["full"]].rename(columns={"full": "prem"})
    act = AC.counts_for_year(actuals_df, s1cfg, year).rename(columns={"actual_losses": "act"})
    d = (rates[keys + ["final_rate", "Z", "hist_large_losses"]]
         .merge(prem, on=keys, how="left").merge(act, on=keys, how="left"))
    d["prem"] = d["prem"].fillna(0.0)
    d["act"] = d["act"].fillna(0).astype(int)
    d["exp"] = d["final_rate"] * d["prem"]
    return d


def _loss_detail(actuals_df, s1cfg, keyvals, keys, year):
    """Raw large-loss rows for one segment-year: count, distinct policies, sizes."""
    sub = actuals_df[(actuals_df[s1cfg.year_col] == year) & (actuals_df["is_large_loss"] == 1)]
    for k, v in zip(keys, keyvals):
        sub = sub[sub[k] == v]
    n = len(sub)
    npol = int(sub[s1cfg.policy_period_col].nunique()) if s1cfg.policy_period_col in sub.columns else None
    sizes = sorted(int(round(x, -3)) for x in sub[s1cfg.loss_col].tolist())
    return n, npol, sizes


def investigate(rates, full_ys, actuals_df, s1cfg, cfg2, years,
                alpha=0.05, material=1.0, n_dossiers=6):
    keys = cfg2.keys
    anchor = years[-1]
    per = {y: _per_year(rates, full_ys, actuals_df, s1cfg, cfg2, y) for y in years}
    base = per[anchor].copy()
    base["seg"] = base[keys].astype(str).agg(" · ".join, axis=1)

    exp_m = np.column_stack([per[y]["exp"].values for y in years])
    act_m = np.column_stack([per[y]["act"].values for y in years])
    base["net_exp"] = exp_m.sum(1)
    base["net_act"] = act_m.sum(1)
    base["net_oe"] = np.where(base["net_exp"] > 0, base["net_act"] / base["net_exp"], np.nan)
    base["years_over"] = (act_m > exp_m).sum(1)
    base["years_under"] = (act_m < exp_m).sum(1)
    for i, y in enumerate(years):
        base[f"exp_{y}"] = exp_m[:, i]
        base[f"act_{y}"] = act_m[:, i].astype(int)

    base["p_high"] = [_p_high(e, a) for e, a in zip(base["exp"], base["act"])]
    base["p_low"] = [_p_low(e, a) for e, a in zip(base["exp"], base["act"])]

    ny = len(years)

    def classify(r):
        if r["exp"] < material:
            return "immaterial (expected < threshold)"
        sig_high, sig_low = r["p_high"] < alpha, r["p_low"] < alpha
        if not (sig_high or sig_low):
            return "within normal range (noise)"
        if sig_high and r["years_over"] >= ny - 1 and r["net_oe"] >= 1.2:
            return "UNDER-rated — persistent, investigate"
        if sig_high:
            return "one-year high spike (lumpy) — watch"
        if sig_low and r["years_under"] >= ny - 1 and r["net_oe"] <= 0.8:
            return "OVER-rated — persistent, review"
        return "one-year low — watch"

    base["classification"] = base.apply(classify, axis=1)

    mat = base[base["exp"] >= material].copy()
    n = len(mat)
    n_high = int((mat["p_high"] < alpha).sum())
    n_low = int((mat["p_low"] < alpha).sum())
    summary = {
        "anchor_year": anchor, "n_material": n, "alpha": alpha,
        "n_sig_high": n_high, "n_sig_low": n_low,
        "expected_each": round(alpha * n, 1),
        "well_calibrated": (n_high + n_low) <= 2 * alpha * n + max(2, 0.02 * n),
    }

    # dossiers: the statistically significant segments, richest first
    sig = mat[(mat["p_high"] < alpha) | (mat["p_low"] < alpha)].copy()
    sig["rank"] = (sig[["p_high", "p_low"]].min(axis=1))
    sig = sig.sort_values("rank").head(n_dossiers)
    dossiers = []
    for _, r in sig.iterrows():
        keyvals = [r[k] for k in keys]
        nloss, npol, sizes = _loss_detail(actuals_df, s1cfg, keyvals, keys, anchor)
        dossiers.append({
            "seg": r["seg"], "keys": keyvals, "Z": float(r["Z"]),
            "hist_large_losses": int(r["hist_large_losses"]),
            "classification": r["classification"],
            "years": [{"year": y, "exp": float(r[f"exp_{y}"]), "act": int(r[f"act_{y}"])} for y in years],
            "net_exp": float(r["net_exp"]), "net_act": int(r["net_act"]), "net_oe": float(r["net_oe"]),
            "p_high": float(r["p_high"]), "p_low": float(r["p_low"]),
            "anchor_losses": nloss, "anchor_distinct_policies": npol, "anchor_sizes": sizes,
        })

    detail = base[keys + ["p_high", "p_low", "net_oe", "years_over", "classification"]].copy()
    return summary, mat, dossiers, detail
