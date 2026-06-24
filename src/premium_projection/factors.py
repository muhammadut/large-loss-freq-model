"""Build the segment panels and calibrate the growth-factor table.

A policy is "visible by month M" of a year if it had started by the end of that
month (its effective date is on or before end-of-month-M). Earned premium of the
year's policies accumulates as more policies are written through the year:

    visible[segment, M]   = premium of policies in that segment started by end of month M
    full[segment]         = visible[segment, 12]  (the whole year)
    growth_factor[seg, M] = full[segment] / visible[segment, M]   (>= 1 by construction)

Calibration pools the ratio across the experience years (robust), clips it, and
falls back to the portfolio month-factor for segments with little history.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .config import Config


def load_book(cfg: Config) -> pd.DataFrame:
    df = pd.read_csv(cfg.data_path, usecols=cfg.keys + [cfg.year_col, cfg.premium_col,
                                                        cfg.eff_col, cfg.exp_col])
    if "CovType" in df.columns:
        df["CovType"] = df["CovType"].astype(str).str.upper()
    # collapse province-level regions to the canonical grouped rating regions (rate-table buckets)
    if cfg.region_map and cfg.null_region_key in df.columns:
        rm = cfg.region_map
        df[cfg.null_region_key] = df[cfg.null_region_key].map(lambda v: rm.get(v, v))
    if cfg.null_region_key and cfg.null_region_key in df.columns:
        df[cfg.null_region_key] = df[cfg.null_region_key].fillna(cfg.fill_value)
    for k in cfg.keys:
        df[k] = df[k].fillna(cfg.fill_value)
    df["_eff"] = pd.to_datetime(df[cfg.eff_col], errors="coerce")
    # First month of the rolling year the policy is visible: 1 if it started before
    # the year began, else the month of its effective date (clamped to 1..12).
    # Unparseable / missing dates fall back to month 1 (visible all year).
    jan1 = pd.to_datetime(dict(year=df[cfg.year_col], month=1, day=1))
    fv = np.where(df["_eff"] < jan1, 1, df["_eff"].dt.month)
    df["_fv"] = pd.Series(fv, index=df.index).fillna(1).clip(1, 12).astype(int)
    return df


def build_panels(df: pd.DataFrame, cfg: Config):
    """Return (full_ys, visible_ysm):
       full_ys     = [year, *keys, full]                full-year premium per segment-year
       visible_ysm = [year, *keys, month, visible]      cumulative visible premium by month
    """
    keys, prem, year = cfg.keys, cfg.premium_col, cfg.year_col
    by_fv = (df.groupby([year] + keys + ["_fv"], observed=True)[prem].sum().reset_index())
    frames = []
    for M in range(1, 13):
        sub = (by_fv[by_fv["_fv"] <= M].groupby([year] + keys, observed=True)[prem]
               .sum().reset_index().rename(columns={prem: "visible"}))
        sub["month"] = M
        frames.append(sub)
    visible_ysm = pd.concat(frames, ignore_index=True)
    full_ys = (visible_ysm[visible_ysm.month == 12][[year] + keys + ["visible"]]
               .rename(columns={"visible": "full"}))
    return full_ys, visible_ysm


def calibrate(full_ys: pd.DataFrame, visible_ysm: pd.DataFrame, cfg: Config,
              years: list) -> pd.DataFrame:
    """Pool full/visible over `years` per (segment, month) -> growth factor.
    Returns [*keys, month, own_factor, portfolio_factor, factor, hist_visible]."""
    keys, year = cfg.keys, cfg.year_col
    f = full_ys[full_ys[year].isin(years)].groupby(keys, observed=True)["full"].sum().reset_index()
    v = (visible_ysm[visible_ysm[year].isin(years)]
         .groupby(keys + ["month"], observed=True)["visible"].sum().reset_index())

    # portfolio factor per month = total full / total visible (all segments, pooled years)
    total_full = f["full"].sum()
    pf = v.groupby("month")["visible"].sum().rename("tot_visible").reset_index()
    pf["portfolio_factor"] = total_full / pf["tot_visible"]

    t = v.merge(f, on=keys, how="left").merge(pf[["month", "portfolio_factor"]], on="month", how="left")
    t["own_factor"] = t["full"] / t["visible"].replace(0, np.nan)
    # final factor: own (clipped to [1, clip_max]); portfolio fallback where history is thin
    own_clipped = t["own_factor"].clip(1.0, cfg.clip_max_factor)
    thin = (t["visible"] < cfg.min_visible_premium) | t["own_factor"].isna()
    t["factor"] = np.where(thin, t["portfolio_factor"], own_clipped)
    t = t.rename(columns={"visible": "hist_visible"})
    return t[keys + ["month", "own_factor", "portfolio_factor", "factor", "hist_visible"]]
