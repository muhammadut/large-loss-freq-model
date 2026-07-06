"""Deviation attribution waterfall (sequential Laspeyres).

Explains the move from the prior year's expected count to this year's actual,
split into the pieces a board cares about:

    prior_expected  +Volume  +Mix  +Rate  = current_expected  +Random  = actual

  Volume  growth in total premium, valued at the prior average rate
  Mix     shift of premium toward higher/lower-frequency segments
  Rate    change in the per-segment rates themselves
          (≈ 0 here — the rate table is FROZEN between annual recalibrations)
  Random  the irreducible Poisson noise (actual − current_expected)

By construction the four pieces reconcile exactly to (actual − prior_expected).
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def attribution(prior_df: pd.DataFrame, current_df: pd.DataFrame, keys) -> dict:
    b = prior_df.merge(current_df, on=keys, suffixes=("_prior", "_current"), how="outer")
    for c in ["projected_premium_prior", "projected_premium_current",
              "frequency_rate_prior", "frequency_rate_current",
              "expected_losses_prior", "expected_losses_current",
              "actual_losses_prior", "actual_losses_current"]:
        if c in b.columns:
            b[c] = b[c].fillna(0.0)

    E_prior = b["projected_premium_prior"].sum()
    E_current = b["projected_premium_current"].sum()
    prior_expected = b["expected_losses_prior"].sum()
    current_expected = b["expected_losses_current"].sum()
    r_bar_prior = prior_expected / E_prior if E_prior > 0 else 0.0

    volume = r_bar_prior * (E_current - E_prior)
    remix = (b["frequency_rate_prior"] * b["projected_premium_current"]).sum()
    mix = remix - r_bar_prior * E_current
    rate = ((b["frequency_rate_current"] - b["frequency_rate_prior"])
            * b["projected_premium_current"]).sum()

    actual = int(b["actual_losses_current"].sum())
    random = actual - current_expected
    sigma = np.sqrt(current_expected) if current_expected > 0 else 1.0

    out = {
        "prior_expected": round(prior_expected, 1),
        "volume_effect": round(volume, 1),
        "mix_effect": round(mix, 1),
        "rate_effect": round(rate, 1),
        "current_expected": round(current_expected, 1),
        "random_effect": round(random, 1),
        "actual": actual,
        "random_z": round(random / sigma, 2),
    }
    # Reconciliation invariant: the attributed pieces must equal the total move.
    attributed = volume + mix + rate + random
    assert abs((actual - prior_expected) - attributed) < 0.1, "Waterfall does not balance"
    return out
