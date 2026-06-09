"""Step 4: aggregate the row-level data into a segment x year panel.

One row per (segment, year): the number of large losses and the total exposure
(under the chosen lens). The log of exposure becomes the GLM offset.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .config import Config


def build_panel(df: pd.DataFrame, cfg: Config, lens_col: str | None = None,
                years: list | None = None) -> pd.DataFrame:
    """Segment x year panel for a given lens and set of years.

    Drops segment-year AGGREGATES whose summed exposure is non-positive (they
    cannot carry an offset). NOTE: this is an aggregate-level filter, not a
    row-level one — a large loss on a zero-exposure row still contributes to its
    segment-year count as long as the segment has exposure from other rows. The
    `exposure_integrity` data-quality gate reports how many large losses sit on
    non-positive-exposure rows under the active lens. The `lens_col`/`years`
    overrides let the validation gates re-panel on subsets without duplication.
    """
    lens_col = lens_col or cfg.lens_col
    years = cfg.experience_years if years is None else years
    keys = cfg.seg_keys

    sub = df[df[cfg.year_col].isin(years)]
    panel = (
        sub.groupby(keys + [cfg.year_col], observed=True)
        .agg(large_loss_count=("is_large_loss", "sum"), expo=(lens_col, "sum"))
        .reset_index()
    )
    panel = panel[panel["expo"] > 0].copy()
    panel["log_exposure"] = np.log(panel["expo"])
    return panel


def losses_dropped(df: pd.DataFrame, panel: pd.DataFrame, cfg: Config,
                   years: list | None = None) -> int:
    """How many large losses fell out because their segment had zero exposure.
    Reported (not asserted) so the run is transparent about any leakage."""
    years = cfg.experience_years if years is None else years
    raw = int(df[df[cfg.year_col].isin(years)]["is_large_loss"].sum())
    kept = int(panel["large_loss_count"].sum())
    return raw - kept
