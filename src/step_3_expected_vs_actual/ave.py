"""Portfolio Actual-vs-Expected: where does the actual count sit in the
distribution the model implies, and what colour is that?

The count is Poisson around the expected mean. If Step-1's dispersion says the
spread is wider than Poisson (φ > 1), widen the band into a Negative Binomial
with variance = φ·μ. Then the percentile of the actual, a 5th–95th range, and a
GREEN / AMBER / RED verdict.
"""
from __future__ import annotations
from scipy import stats


def _band_model(expected: float, dispersion):
    """Return a frozen scipy distribution for the count. Poisson while the
    dispersion is within the Step-1 gate's tolerance (<=1.5, "Poisson adequate");
    otherwise a Negative Binomial with variance = phi*mu to widen the band."""
    phi = dispersion or 1.0
    if phi <= 1.5 or expected <= 0:
        return stats.poisson(expected), "Poisson"
    r = expected / (phi - 1.0)          # NB with mean=expected, var=phi*expected
    p = r / (r + expected)
    return stats.nbinom(r, p), f"NegBin(phi={phi:.2f})"


def portfolio_ave(expected: float, actual: int, dispersion=None,
                  green_band=(25, 75), amber_band=(10, 90)) -> dict:
    dist, model = _band_model(expected, dispersion)
    percentile = float(dist.cdf(actual) * 100)
    lo, hi = int(dist.ppf(0.05)), int(dist.ppf(0.95))

    if green_band[0] <= percentile <= green_band[1]:
        light = "GREEN"
    elif amber_band[0] <= percentile <= amber_band[1]:
        light = "AMBER"
    else:
        light = "RED"

    return {
        "expected": round(expected, 1),
        "actual": int(actual),
        "gap": round(actual - expected, 1),
        "percentile": round(percentile, 1),
        "ci_5th": lo,
        "ci_95th": hi,
        "band_model": model,
        "traffic_light": light,
    }
