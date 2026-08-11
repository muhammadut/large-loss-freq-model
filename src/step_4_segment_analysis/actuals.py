"""Actual large-loss counts per segment, per year.

Reuses the Step-1 loader so a loss is flagged here EXACTLY as it was when the
rates were calibrated (same $200K threshold, cat-scope, segment keys, count
grain). Any other counting would make the expected-vs-actual lenses meaningless.
"""
from __future__ import annotations
import pandas as pd

from step_1_frequency.config import load_config as load_step1
from step_1_frequency import data as S1


def load_actuals(step1_config_path: str):
    """Load + flag the book once. Returns (df, step1_cfg)."""
    cfg = load_step1(step1_config_path)
    df = S1.load_and_prepare(cfg)
    # Normalise the CovType key exactly as Step 2 does (upper-case), so counts
    # merge cleanly with the projected premium / rate table.
    if "CovType" in df.columns:
        df["CovType"] = df["CovType"].astype(str).str.upper()
    return df, cfg


def counts_for_year(df: pd.DataFrame, cfg, year: int) -> pd.DataFrame:
    """Per-segment actual large-loss count for one year: [*keys, actual_losses]."""
    keys = cfg.seg_keys
    sub = df[df[cfg.year_col] == year]
    out = (sub.groupby(keys, observed=True)["is_large_loss"].sum()
           .reset_index().rename(columns={"is_large_loss": "actual_losses"}))
    out["actual_losses"] = out["actual_losses"].astype(int)
    return out
