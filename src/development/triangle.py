"""Build a claim-count development pattern from a valuation-snapshot triangle.

Age = months since the END of the accident year (Dec 31 of the accident year) to
the valuation (as-of) date. A cell is the reported large-loss count for that
accident year as known on that date.

Chain-ladder on counts:
  age-to-age factor(a) = sum(count at a+6mo) / sum(count at a)   over accident
                         years observed at BOTH ages (volume-weighted)
  cumulative factor(a)  = product of age-to-age factors from a onward x tail
  % developed(a)        = 1 / cumulative factor(a)

Counts can move DOWN as well as up (subrogation, reserve reductions below the
threshold), so factors are net and % developed can briefly exceed 100%.
"""
from __future__ import annotations
import pandas as pd

from .config import Config


def load_triangle(cfg: Config) -> pd.DataFrame:
    """Return long form: [ay, ct, age, count]."""
    df = pd.read_csv(cfg.triangle_path, comment="#")
    asof = [c for c in df.columns if c.startswith("asof_")]
    if not asof:
        raise SystemExit(f"No 'asof_YYYY-MM-DD' snapshot columns found in {cfg.triangle_path}")
    long = df.melt(id_vars=[cfg.ay_col, cfg.ct_col], value_vars=asof,
                   var_name="asof", value_name="count").dropna(subset=["count"])
    long["count"] = long["count"].astype(int)

    def age(row):
        y, m, _ = (int(x) for x in row["asof"].replace("asof_", "").split("-"))
        return (y - int(row[cfg.ay_col])) * 12 + (m - 12)   # months since accident-year END

    long["age"] = long.apply(age, axis=1)
    long = long.rename(columns={cfg.ay_col: "ay", cfg.ct_col: "ct"})
    return long[["ay", "ct", "age", "count"]].sort_values(["ct", "ay", "age"]).reset_index(drop=True)


def age_to_age(long: pd.DataFrame, ct: str) -> dict:
    """Volume-weighted 6-month age-to-age factors for one coverage."""
    d = long[long["ct"] == ct]
    out = {}
    for a in sorted(d["age"].unique()):
        step = d[d["age"] == a + 6].merge(d[d["age"] == a], on=["ay", "ct"], suffixes=("_n", "_a"))
        if len(step) and step["count_a"].sum() > 0:
            out[a] = float(step["count_n"].sum() / step["count_a"].sum())
    return out


def pattern(long: pd.DataFrame, ct: str, tail: float = 1.0) -> dict:
    """Return {'a2a', 'cdf', 'pct_developed'} for one coverage.
    `tail` is the factor from the last observed age to true ultimate."""
    a2a = age_to_age(long, ct)
    if not a2a:
        return {"a2a": {}, "cdf": {}, "pct_developed": {}}
    last = max(a2a) + 6
    cdf = {last: tail}
    for a in sorted(a2a, reverse=True):
        cdf[a] = a2a[a] * cdf.get(a + 6, tail)
    pct = {a: 1.0 / cdf[a] for a in cdf}
    return {"a2a": a2a, "cdf": cdf, "pct_developed": pct}


def cdf_at(cdf: dict, age: int) -> float:
    """Cumulative development factor for an arbitrary age (nearest observed age)."""
    if not cdf:
        return 1.0
    if age in cdf:
        return cdf[age]
    return cdf[min(cdf, key=lambda a: abs(a - age))]
