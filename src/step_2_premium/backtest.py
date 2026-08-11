"""Honest backtest: for each held-out year, learn factors from PRIOR years only,
project the held-out year at several run-months, and score against actuals.
Also scores the global (one-number) factor as a baseline."""
from __future__ import annotations
import numpy as np
import pandas as pd

from .config import Config
from . import factors as F
from .project import project


def metrics(pred, actual, within_pct=10.0) -> dict:
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    m = a > 1
    a, p = a[m], p[m]
    ape = np.abs(p - a) / a
    return {
        "segments": int(m.sum()),
        "wape": float(np.abs(p - a).sum() / a.sum() * 100),        # dollar-weighted % error
        "median_ape": float(np.median(ape) * 100),                 # typical segment
        "within": float((ape <= within_pct / 100).mean() * 100),  # % within tolerance
        "total_err": float((p.sum() - a.sum()) / a.sum() * 100),   # grand total (signed)
    }


def run_backtest(full_ys: pd.DataFrame, visible_ysm: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    rows = []
    for Y in cfg.holdout_years:
        prior = [y for y in cfg.experience_years if y < Y]
        if not prior:
            continue
        ftab = F.calibrate(full_ys, visible_ysm, cfg, prior)
        for M in cfg.run_months:
            proj = project(visible_ysm, full_ys, ftab, cfg, Y, M)
            # per-segment method
            mm = metrics(proj["projected_premium"], proj["actual_premium"], cfg.within_pct)
            rows.append({"year": Y, "month": M, "method": "per-segment", **mm})
            # global baseline: everyone gets the portfolio month-factor
            port = float(ftab[ftab.month == M]["portfolio_factor"].iloc[0])
            gm = metrics(proj["visible_premium"] * port, proj["actual_premium"], cfg.within_pct)
            rows.append({"year": Y, "month": M, "method": "global-factor", **gm})
    return pd.DataFrame(rows)
