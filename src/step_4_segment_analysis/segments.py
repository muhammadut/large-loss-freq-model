"""Segment-level intelligence — a starter deck of the four questions a business
actually asks once it trusts the portfolio total:

    1. CONCENTRATION  — where is our large-loss exposure? (a few segments carry it)
    2. ACCURACY       — where is the model right/wrong per segment, and is a miss
                        structural (persistent) or just noise (one-off)?
    3. DRIFT          — which segments are heating up or cooling down vs their rate?
                        (the early-warning / emerging-risk signal)
    4. CONFIDENCE     — which segment rates rest on thin data? (big bets to validate)

Everything is built from the frozen rate table (Step 1) × each year's premium
(Step 2) vs the actual counts — no new modelling, just lenses on the shipped rates.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import actuals as AC


def build_master(rates, full_ys, actuals_df, s1cfg, cfg2, years):
    """One row per segment with rate/credibility + expected, actual, O/E per year."""
    keys, ycol = cfg2.keys, cfg2.year_col
    cols = [c for c in ["final_rate", "final_rate_per_1M", "Z", "hist_large_losses", "credible"]
            if c in rates.columns]
    m = rates[keys + cols].copy()
    for Y in years:
        prem = (full_ys[full_ys[ycol] == Y][keys + ["full"]].rename(columns={"full": f"prem_{Y}"}))
        m = m.merge(prem, on=keys, how="left")
        m[f"prem_{Y}"] = m[f"prem_{Y}"].fillna(0.0)
        m[f"exp_{Y}"] = m["final_rate"] * m[f"prem_{Y}"]
        a = AC.counts_for_year(actuals_df, s1cfg, Y).rename(columns={"actual_losses": f"act_{Y}"})
        m = m.merge(a, on=keys, how="left")
        m[f"act_{Y}"] = m[f"act_{Y}"].fillna(0).astype(int)
        m[f"oe_{Y}"] = np.where(m[f"exp_{Y}"] > 0, m[f"act_{Y}"] / m[f"exp_{Y}"], np.nan)

    vy = years[-1]                                   # verdict year (materiality/accuracy anchor)
    m["seg"] = m[keys].astype(str).agg(" · ".join, axis=1)
    m["expected"] = m[f"exp_{vy}"]
    m["actual"] = m[f"act_{vy}"]
    m["deviation"] = m["actual"] - m["expected"]
    tot = m["expected"].sum()
    m["contribution_pct"] = m["expected"] / tot * 100 if tot else 0.0

    # persistence: how many of the tracked years share the sign of (actual - expected)
    dev_cols = [(m[f"act_{Y}"] - m[f"exp_{Y}"]) for Y in years]
    signs = np.sign(pd.concat(dev_cols, axis=1))
    m["years_over"] = int(0)
    m["years_over"] = (signs > 0).sum(axis=1).astype(int)     # actual > expected
    m["years_under"] = (signs < 0).sum(axis=1).astype(int)    # actual < expected

    # drift: recent O/E (last two tracked years, dollar-ish weighted by expected)
    if len(years) >= 2:
        y1, y2 = years[-2], years[-1]
        exp_recent = m[f"exp_{y1}"] + m[f"exp_{y2}"]
        act_recent = m[f"act_{y1}"] + m[f"act_{y2}"]
        m["oe_recent"] = np.where(exp_recent > 0, act_recent / exp_recent, np.nan)
    else:
        m["oe_recent"] = m[f"oe_{vy}"]
    return m, vy


# ---- view selectors -------------------------------------------------------

def concentration(m, top=12):
    d = m.sort_values("expected", ascending=False).copy()
    d["cumulative_pct"] = d["contribution_pct"].cumsum()
    return d, d.head(top)


def accuracy(m, years, material=1.0, top=6):
    """Biggest per-segment misses in the verdict year, tagged structural vs noise."""
    n = len(years)
    mat = m[m["expected"] >= material].copy()
    under = mat[mat["deviation"] > 0].sort_values("deviation", ascending=False).head(top).copy()
    over = mat[mat["deviation"] < 0].sort_values("deviation").head(top).copy()

    def tag(row, direction):
        yrs = row["years_under"] if direction == "over" else row["years_over"]
        return "structural" if yrs >= max(2, n - 1) else "noise"
    under["pattern"] = under.apply(lambda r: tag(r, "under"), axis=1)   # actual>expected persistently
    over["pattern"] = over.apply(lambda r: tag(r, "over"), axis=1)      # actual<expected persistently
    rho = float(m["expected"].corr(m["actual"], method="spearman"))
    return under, over, rho


def drift(m, years, material_losses=5, hot=1.25, cold=0.75, top=8):
    """Segments running HOT / COLD vs their own rate, among the ones with enough
    history to be meaningful. Ranked by how far recent O/E is from 1."""
    d = m[m["hist_large_losses"] >= material_losses].copy()
    d["signal"] = np.where(d["oe_recent"] >= hot, "HOT",
                  np.where(d["oe_recent"] <= cold, "COLD", "stable"))
    d["dist"] = (d["oe_recent"] - 1.0).abs()
    moving = d[d["signal"] != "stable"].sort_values("dist", ascending=False).head(top)
    return moving, d


def confidence(m, top=6):
    """Big bets on thin data: material expected losses but a low-credibility rate."""
    cred_col = "credible" if "credible" in m.columns else None
    total_exp = m["expected"].sum()
    if cred_col:
        is_cred = m[cred_col].astype(str).str.lower().eq("yes")
    else:
        is_cred = m["Z"] >= 0.5
    share_credible = float(m.loc[is_cred, "expected"].sum() / total_exp * 100) if total_exp else 0.0
    thin_material = (m[(~is_cred) & (m["expected"] >= 1.0)]
                     .sort_values("expected", ascending=False).head(top).copy())
    return share_credible, int(is_cred.sum()), int((~is_cred).sum()), thin_material
