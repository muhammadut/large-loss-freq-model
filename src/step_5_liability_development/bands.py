"""The band — the empirical "normal range" of the large-loss count at an age.

The band *is* the alarm: an actual inside it is normal, outside it is a signal. So it
is MEASURED from the historical spread of the count at that age (per unit exposure),
scaled to the current book -- not asserted. Five construction methods are offered and
picked by a walk-forward shoot-out (see `shootout`); the chosen one is set in config
(`verdict.band_method`).

Why per-EXPOSURE, and why a recent window:
  * The count at an age is compared across years of different SIZE, so we work in
    "large losses per $M earned exposure" and multiply back by the target year's own
    (day-one-known) exposure. Premium is distorted by rate changes; exposure is the
    clean base for a frequency.
  * The book and the reporting pattern have STABILISED recently (older years carry a
    now-defunct, faster-reporting regime). So the spread is measured on a recent window
    -- the same reason the early ladder rungs are recent-weighted. This is what makes
    the age-12 band tight (recent counts 14/14/17/17) instead of drowned in old noise.

Every builder takes the training years' per-$M rates and the target book's exposure
(in $M) and returns (lo_count, hi_count, centre_count). `lo`/`hi` are the central-
interval tail probabilities (e.g. 0.10 / 0.90 -> middle 80%).
"""
from __future__ import annotations
from statistics import NormalDist
import numpy as np

try:
    from scipy.stats import poisson as _poisson, nbinom as _nbinom
    _HAVE_SCIPY = True
except Exception:                       # pragma: no cover - scipy optional
    _HAVE_SCIPY = False

_N = NormalDist()                       # stdlib exact inverse-normal (scipy-free fallback)


# --------------------------------------------------------------------------- ppf helpers
def _z(q):
    """Exact inverse standard-normal quantile (any q in (0,1)) via the stdlib."""
    return _N.inv_cdf(q)


def _pois_ppf(q, mu):
    if mu <= 0:
        return 0
    if _HAVE_SCIPY:
        return int(_poisson.ppf(q, mu))
    # Normal approximation fallback (adequate for a band)
    return max(0, int(round(mu + _z(q) * np.sqrt(mu))))


def _nbinom_ppf(q, mu, var):
    if mu <= 0:
        return 0
    if var <= mu * 1.01:                # not over-dispersed -> Poisson
        return _pois_ppf(q, mu)
    if _HAVE_SCIPY:
        r = mu ** 2 / (var - mu)
        p = r / (r + mu)
        return int(_nbinom.ppf(q, r, p))
    return max(0, int(round(mu + _z(q) * np.sqrt(var))))


# --------------------------------------------------------------------------- the 5 methods
# Each: (rates: np.ndarray per $M, book: target exposure $M, lo, hi) -> (lo_ct, hi_ct, centre_ct)

def band_min_max(rates, book, lo, hi):
    """Lowest & highest historical rate x book size. Simple, but has NO stated
    coverage and stretches to the worst single year -> fragile with few years."""
    c = float(np.mean(rates)) * book
    return max(0.0, float(np.min(rates)) * book), float(np.max(rates)) * book, c


def band_std(rates, book, lo, hi):
    """Mean +/- 2 sigma of the rate x book. Assumes symmetry; small skewed counts
    break that, and it can dip below 0 (floored). With <2 points there is no spread
    to measure -> degrade to the Poisson bounce so the band never collapses to a point."""
    if len(rates) < 2:
        return band_poisson(rates, book, lo, hi)
    m = float(np.mean(rates)); s = float(np.std(rates, ddof=1))
    c = m * book
    return max(0.0, (m - 2 * s) * book), (m + 2 * s) * book, c


def band_percentile(rates, book, lo, hi):
    """Empirical lo-hi percentile of the historical rates x book. Honest and
    distribution-free, but crude (and jumpy) with few years, and it ignores the
    pure count-sampling bounce. With <2 points the quantiles collapse -> Poisson."""
    if len(rates) < 2:
        return band_poisson(rates, book, lo, hi)
    c = float(np.mean(rates)) * book
    return float(np.quantile(rates, lo)) * book, float(np.quantile(rates, hi)) * book, c


def band_poisson(rates, book, lo, hi):
    """Pure Poisson bounce of the count around the expected mean rate x book. Captures
    count-sampling noise ONLY -> too tight, because it ignores real year-to-year drift
    in the rate itself."""
    mu = float(np.mean(rates)) * book
    return _pois_ppf(lo, mu), _pois_ppf(hi, mu), mu


def band_hybrid(rates, book, lo, hi):
    """Year-to-year spread (systematic) + Poisson bounce (sampling), as one predictive
    interval. mu = mean rate x book; add the rate's own CV as over-dispersion:
    var = mu + (cv*mu)^2 -> negative binomial. Combines BOTH real sources of variation,
    has a stated coverage, and self-tightens where the history is steady."""
    m = float(np.mean(rates))
    mu = m * book
    cv = (float(np.std(rates, ddof=1)) / m) if (len(rates) > 1 and m > 0) else 0.0
    var = mu + (cv * mu) ** 2
    return _nbinom_ppf(lo, mu, var), _nbinom_ppf(hi, mu, var), mu


METHODS = {
    "min_max": band_min_max,
    "std": band_std,
    "percentile": band_percentile,
    "poisson": band_poisson,
    "hybrid": band_hybrid,
}


def build_band(method, rates, book, lo, hi):
    """Dispatch to a named band method. `rates` = per-$M-exposure counts from the
    training years at one age; `book` = target year's exposure ($M)."""
    rates = np.asarray(rates, dtype=float)
    if method not in METHODS:
        raise KeyError(f"unknown band_method '{method}'. Options: {sorted(METHODS)}")
    lo_ct, hi_ct, centre = METHODS[method](rates, book, lo, hi)
    return float(lo_ct), float(hi_ct), float(centre)


# --------------------------------------------------------------------------- emergence table
def emergence_rates(tri, book):
    """From the triangle + per-year book, build {age: DataFrame[year, count, expo_M, rate]}
    where rate = count / exposure_M. This is the raw material every band method reads."""
    import pandas as pd
    m = tri.merge(book, on="year", how="inner")
    m = m[m["expo_M"] > 0].copy()
    m["rate"] = m["count"] / m["expo_M"]
    return {int(a): g.sort_values("year")[["year", "count", "expo_M", "rate"]].reset_index(drop=True)
            for a, g in m.groupby("age")}


def train_rates(em, age, test_year, recent_window=None, min_train=3):
    """Per-$M rates at `age` from accident years STRICTLY BEFORE test_year (walk-forward),
    optionally restricted to the most recent `recent_window` such years. Returns None if
    fewer than `min_train` points (band would be unreliable)."""
    if age not in em:
        return None
    g = em[age]
    prior = g[g["year"] < test_year]
    if recent_window:
        prior = prior.sort_values("year").tail(recent_window)
    if len(prior) < min_train:
        return None
    return prior["rate"].to_numpy(dtype=float)


# --------------------------------------------------------------------------- walk-forward shoot-out
def shootout(tri, book, lo=0.10, hi=0.90, recent_window=None, min_train=3, methods=None):
    """Walk-forward backtest of every band method on the real history.

    For each accident year (the held-out "test"), and each age it has actually reached,
    build the band from the OTHER (earlier) years only and check whether the test year's
    real count lands inside. Because all historical years are assumed NORMAL, we want:
      * coverage  ~ the nominal middle (hi-lo) -- much higher = band too wide (useless);
                    much lower = too many false alarms (band too tight);
      * a tight band (small width) at that coverage -- the tie-breaker.
    Catch-rate (does it fire on a genuinely BAD year?) is NOT testable here -- the history
    has no labelled bad years. We are explicit about that limit.

    Returns (per_cell_df, summary_df).
    """
    import pandas as pd
    methods = methods or list(METHODS)
    em = emergence_rates(tri, book)
    ages = sorted(em)
    test_years = sorted(tri["year"].unique())

    cells = []
    for ty in test_years:
        for age in ages:
            g = em[age]
            row = g[g["year"] == ty]
            if row.empty:
                continue
            actual = float(row["count"].iloc[0])
            tbook = float(row["expo_M"].iloc[0])
            rts = train_rates(em, age, ty, recent_window=recent_window, min_train=min_train)
            if rts is None or tbook <= 0:
                continue
            for meth in methods:
                lo_ct, hi_ct, centre = build_band(meth, rts, tbook, lo, hi)
                inside = (actual >= np.floor(lo_ct)) and (actual <= np.ceil(hi_ct))
                cells.append({
                    "method": meth, "year": int(ty), "age": int(age),
                    "n_train": len(rts), "actual": actual, "centre": round(centre, 1),
                    "lo": round(lo_ct, 1), "hi": round(hi_ct, 1),
                    "width": round(hi_ct - lo_ct, 1),
                    "rel_width": round((hi_ct - lo_ct) / centre, 2) if centre > 0 else np.nan,
                    "inside": bool(inside),
                    "below": bool(actual < np.floor(lo_ct)),
                    "above": bool(actual > np.ceil(hi_ct)),
                })
    per_cell = pd.DataFrame(cells)
    if per_cell.empty:
        return per_cell, pd.DataFrame()

    nominal = hi - lo
    rows = []
    for meth, g in per_cell.groupby("method"):
        n = len(g)
        cov = g["inside"].mean()
        rows.append({
            "method": meth, "n_cells": n,
            "coverage": round(cov, 3),
            "cov_gap": round(cov - nominal, 3),           # +ve = wider than nominal
            "false_alarm": round(1 - cov, 3),
            "low_rate": round(g["below"].mean(), 3),
            "high_rate": round(g["above"].mean(), 3),
            "mean_rel_width": round(g["rel_width"].mean(), 2),
            "mean_width": round(g["width"].mean(), 1),
        })
    summary = pd.DataFrame(rows).sort_values("method").reset_index(drop=True)
    # fit_score = a TRANSPARENT calibration+tightness lens ONLY:
    #   |coverage - nominal| + 0.15 * mean_rel_width   (lower is better)
    # It deliberately does NOT encode the two things that actually justify the shipped
    # default: the false-ALARM rate (`high_rate`, shown as its own column) and
    # extrapolation / small-n robustness (untestable on this history). So fit_score
    # RANKS the methods but does NOT by itself pick the winner -- percentile tends to
    # win fit_score yet ships behind `hybrid`, which is window-insensitive and never
    # false-ALARMs. The choice is a documented judgment (verdict.band_method), informed
    # by -- not dictated by -- this number. See README / immature_year_approach.md.
    summary["fit_score"] = (summary["coverage"] - nominal).abs() + 0.15 * summary["mean_rel_width"].fillna(9)
    summary = summary.sort_values("fit_score").reset_index(drop=True)
    return per_cell, summary
