"""Apply the growth-factor table: visible premium x factor -> projected full-year
premium, per segment. In production the visible premium comes from the current
in-force book (earned forward from the policy dates); here it comes from the
year's data at the chosen run-month (the same quantity, just settled)."""
from __future__ import annotations
import numpy as np
import pandas as pd

from .config import Config


def project(visible_ysm: pd.DataFrame, full_ys: pd.DataFrame, factor_table: pd.DataFrame,
            cfg: Config, year: int, month: int) -> pd.DataFrame:
    """Return per-segment projection for `year` as if run at end of `month`.
    Columns: *keys, visible_premium, factor, projected_premium, actual_premium."""
    keys, ycol = cfg.keys, cfg.year_col
    vis = (visible_ysm[(visible_ysm[ycol] == year) & (visible_ysm.month == month)]
           [keys + ["visible"]].rename(columns={"visible": "visible_premium"}))
    fac = factor_table[factor_table.month == month][keys + ["factor", "portfolio_factor"]]
    out = vis.merge(fac, on=keys, how="left")
    # a segment with no learned factor (new this year) -> the portfolio month-factor
    port = float(factor_table[factor_table.month == month]["portfolio_factor"].iloc[0])
    out["factor"] = out["factor"].fillna(port)
    out["projected_premium"] = out["visible_premium"] * out["factor"]
    actual = full_ys[full_ys[ycol] == year][keys + ["full"]].rename(columns={"full": "actual_premium"})
    out = out.merge(actual, on=keys, how="left")
    return out.drop(columns=["portfolio_factor"])
