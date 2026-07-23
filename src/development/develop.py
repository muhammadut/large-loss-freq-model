"""Develop a still-maturing accident year's reported counts to ultimate.

Two methods, both per coverage (property passes through ~unchanged; liability is
scaled up):

  chain_ladder:          ultimate = reported / %developed        (= reported x CDF)
  bornhuetter_ferguson:  ultimate = reported + expected x (1 - %developed)

BF is steadier early in the year (it leans on the expected prior instead of
dividing a tiny reported count by a tiny %developed); it needs an expected-ultimate
prior per (accident_year, coverage) = Step-1 frequency x Step-2 premium.
"""
from __future__ import annotations
import pandas as pd

from . import triangle as T


def develop_accident_year(long, patterns, ay, method="chain_ladder", expected=None):
    """Return a per-coverage DataFrame for accident year `ay` at its latest snapshot."""
    rows = []
    for ct, pat in patterns.items():
        sub = long[(long["ay"] == ay) & (long["ct"] == ct)]
        if not len(sub):
            continue
        latest = sub.sort_values("age").iloc[-1]
        age, reported = int(latest["age"]), int(latest["count"])
        cdf = T.cdf_at(pat["cdf"], age)
        pct = 1.0 / cdf if cdf else 1.0
        chain_ladder = reported * cdf
        ultimate = chain_ladder
        if method == "bornhuetter_ferguson" and expected is not None:
            e = expected.get((ay, ct))
            if e is not None:
                ultimate = reported + e * (1.0 - pct)
        rows.append({
            "covtype": ct, "age_months": age, "reported": reported,
            "pct_developed": round(pct, 3), "cdf": round(cdf, 3),
            "chain_ladder_ultimate": round(chain_ladder, 1),
            "ultimate": round(ultimate, 1),
            "still_to_emerge": round(ultimate - reported, 1),
        })
    return pd.DataFrame(rows)


def load_expected_prior(path, cfg):
    """Optional expected-ultimate prior for BF: CSV [accident_year, covtype, expected]."""
    if not path:
        return None
    df = pd.read_csv(path)
    return {(int(r[cfg.ay_col]), r[cfg.ct_col]): float(r["expected"]) for _, r in df.iterrows()}
