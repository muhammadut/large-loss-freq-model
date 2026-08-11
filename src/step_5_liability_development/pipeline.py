"""Liability development pipeline — the parallel track to the property frequency model.

Flow (see README):
    load -> triangle -> ladder(% developed by age)
         -> developed segment panel -> credibilised rate (frequency per $ exposure)
         -> partial verdict for the immature years (expected-by-now vs actual + band)
         -> leave-one-out backtest (is the rate trustworthy out of sample?)

Design notes:
  * Development speed is a COVERAGE property, so the ladder is estimated on all
    liability together (coarse), then applied per segment (granular) -- two tables
    joined on nothing but the coverage being liability.
  * The rate is built on DEVELOPED counts (each calibration year grossed up to
    ultimate) so it is not biased low by immaturity.
  * The current year is NEVER projected off its own tiny count. Expected comes from
    rate x premium (stable, known day one); the ladder only discounts it to the age.
  * Credibility mirrors src/step_1_frequency/credibility.py: Z = E/(E+K), shrink each
    thin cell toward its same-industry complement, then the portfolio. Re-implemented
    here (not imported) so this track runs standalone and reviews end-to-end.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import os

import numpy as np
import pandas as pd
import yaml

import bands as B

try:
    from scipy.stats import poisson as _poisson, nbinom as _nbinom
    _HAVE_SCIPY = True
except Exception:                       # pragma: no cover - scipy optional
    _HAVE_SCIPY = False


# --------------------------------------------------------------------------- config
@dataclass
class Cfg:
    raw: dict

    def __getitem__(self, k): return self.raw[k]
    @property
    def path(self): return self.raw["data"]["path"]
    @property
    def year_col(self): return self.raw["data"]["year_col"]
    @property
    def cov_col(self): return self.raw["data"]["covtype_col"]
    @property
    def coverage(self): return self.raw["data"]["coverage"]
    @property
    def mat_col(self): return self.raw["data"]["maturity_loss_col"]
    @property
    def dev_cols(self): return list(self.raw["data"]["dev_loss_cols"])
    @property
    def expo_col(self): return self.raw["data"]["exposure_col"]
    @property
    def prem_col(self): return self.raw["data"]["premium_col"]
    @property
    def threshold(self): return float(self.raw["large_loss"]["threshold"])
    @property
    def seg_keys(self): return list(self.raw["segmentation"]["seg_keys"])
    @property
    def industry_key(self): return self.raw["segmentation"]["industry_key"]
    @property
    def lv(self): return int(self.raw["develop"]["latest_valuation_year"])
    @property
    def step(self): return int(self.raw["develop"]["step_months"])
    @property
    def tail(self): return float(self.raw["develop"]["tail_factor"])
    @property
    def recent_ladder(self): return self.raw["develop"].get("recent_ladder") or {}
    @property
    def calib_years(self): return list(self.raw["calibration"]["experience_years"])
    @property
    def score_years(self): return list(self.raw["verdict"]["score_years"])
    @property
    def band_lo(self): return float(self.raw["verdict"]["band_lo"])
    @property
    def band_hi(self): return float(self.raw["verdict"]["band_hi"])
    @property
    def dev_cv(self): return {int(k): float(v) for k, v in self.raw["develop"].get("development_cv", {}).items()}
    @property
    def cv_rate(self): return float(self.raw["verdict"].get("cv_rate", 0.0))
    @property
    def maturity_gate(self): return float(self.raw["verdict"].get("maturity_gate", 0.0))
    @property
    def too_early_lo_floor(self): return int(self.raw["verdict"].get("too_early_lo_floor", 1))
    @property
    def band_method(self): return str(self.raw["verdict"].get("band_method", "hybrid"))
    @property
    def band_recent_window(self):
        w = self.raw["verdict"].get("band_recent_window")
        return int(w) if w else None
    @property
    def band_min_train(self): return int(self.raw["verdict"].get("band_min_train", 3))


def load_config(path: str) -> Cfg:
    with open(path, "r", encoding="utf-8") as fh:
        return Cfg(raw=yaml.safe_load(fh))


# --------------------------------------------------------------------------- helpers
def latest_lag(year: int, cfg: Cfg) -> int:
    """Newest development lag observable for an accident year (0..len(dev_cols))."""
    return int(min(len(cfg.dev_cols), cfg.lv - year))


def lag_col(lag: int, cfg: Cfg) -> str:
    """Column holding the incurred at a given lag (0 = at maturity)."""
    return cfg.mat_col if lag == 0 else cfg.dev_cols[lag - 1]


def age_of(lag: int, cfg: Cfg) -> int:
    return lag * cfg.step


# --------------------------------------------------------------------------- load
def load(cfg: Cfg) -> pd.DataFrame:
    cols = [cfg.year_col, cfg.cov_col, *cfg.seg_keys, cfg.mat_col, *cfg.dev_cols,
            cfg.expo_col, cfg.prem_col]
    cols = list(dict.fromkeys(cols))            # de-dup, keep order
    df = pd.read_csv(cfg.path, usecols=cols, na_values=["NULL"])
    df = df[df[cfg.cov_col] == cfg.coverage].copy()
    df[cfg.year_col] = df[cfg.year_col].astype(int)
    # Impute null segment keys BEFORE any groupby: pandas groupby drops NaN keys by
    # default, which would silently remove ~6% of rows (and real large losses) from
    # the rate and the actual counts. Keep them as an explicit "UNKNOWN" cell.
    for k in cfg.seg_keys:
        df[k] = df[k].astype("object").where(df[k].notna(), "UNKNOWN")
    return df


# --------------------------------------------------------------------------- triangle + ladder
def triangle(df: pd.DataFrame, cfg: Cfg) -> pd.DataFrame:
    """Long form [year, lag, age, count] of large-loss counts, observable cells only."""
    rows = []
    for y, g in df.groupby(cfg.year_col):
        for lag in range(len(cfg.dev_cols) + 1):
            col = lag_col(lag, cfg)
            if g[col].notna().any():                       # snapshot exists
                rows.append({"year": int(y), "lag": lag, "age": age_of(lag, cfg),
                             "count": int((g[col] >= cfg.threshold).sum())})
    return pd.DataFrame(rows)


def _a2a_factor(tri: pd.DataFrame, a: int, cfg: Cfg):
    """Volume-weighted age-to-age factor from age `a` to `a+step` over the given rows."""
    cur = tri[tri["age"] == a]
    nxt = tri[tri["age"] == a + cfg.step]
    m = cur.merge(nxt, on="year", suffixes=("_a", "_n"))
    if len(m) and m["count_a"].sum() > 0:
        return float(m["count_n"].sum() / m["count_a"].sum())
    return None


def ladder(tri: pd.DataFrame, cfg: Cfg) -> dict:
    """Volume-weighted age-to-age factors -> cdf -> % developed, plus a cdf(age) lookup.

    RECENT-WEIGHTED EARLY RUNGS: reporting has slowed, so the ages listed in
    `develop.recent_ladder.recent_ages` are estimated from recent accident years only
    (>= recent_from_year); every other rung pools all years. This pulls the age-0
    %developed down (~21% pooled -> ~11% recent) so a fresh year is not over-expected.
    Falls back to the pooled factor if the recent window is too thin at that age.
    """
    ages = sorted(tri["age"].unique())
    rl = cfg.recent_ladder
    recent_on = bool(rl.get("enabled"))
    recent_ages = set(rl.get("recent_ages", []))
    recent_tri = tri[tri["year"] >= int(rl.get("recent_from_year", 0))] if recent_on else tri

    a2a, a2a_src = {}, {}
    for a in ages:
        if recent_on and a in recent_ages:
            f = _a2a_factor(recent_tri, a, cfg)
            src = "recent"
            if f is None:                       # recent window too thin -> pooled fallback
                f, src = _a2a_factor(tri, a, cfg), "pooled(fallback)"
        else:
            f, src = _a2a_factor(tri, a, cfg), "pooled"
        if f is not None:
            a2a[a] = f
            a2a_src[a] = src
    last = max(ages)
    cdf = {last: cfg.tail}
    for a in sorted([x for x in ages if x < last], reverse=True):
        cdf[a] = a2a.get(a, 1.0) * cdf.get(a + cfg.step, cfg.tail)
    pct = {a: 1.0 / cdf[a] for a in cdf}
    return {"a2a": a2a, "a2a_src": a2a_src, "cdf": cdf, "pct_developed": pct, "ages": ages}


def cdf_at(lad: dict, age: int) -> float:
    cdf = lad["cdf"]
    if age in cdf:
        return cdf[age]
    return cdf[min(cdf, key=lambda a: abs(a - age))]


def pct_at(lad: dict, age: int) -> float:
    return 1.0 / cdf_at(lad, age)


def book_by_year(df: pd.DataFrame, cfg: Cfg) -> pd.DataFrame:
    """Per accident year: earned exposure in $M (the day-one-known size the band scales to)."""
    b = (df.groupby(cfg.year_col).agg(expo=(cfg.expo_col, "sum")).reset_index()
           .rename(columns={cfg.year_col: "year"}))
    b["expo_M"] = b["expo"] / 1e6
    return b[["year", "expo_M"]]


# --------------------------------------------------------------------------- developed panel + rate
def developed_panel(df: pd.DataFrame, cfg: Cfg, lad: dict, years) -> pd.DataFrame:
    """Per (segment, year): exposure + DEVELOPED large-loss count (grossed to ultimate)."""
    out = []
    for y in years:
        lag = latest_lag(y, cfg)
        col = lag_col(lag, cfg)
        cdf = cdf_at(lad, age_of(lag, cfg))
        g = df[df[cfg.year_col] == y]
        g = g.assign(_is_large=(g[col] >= cfg.threshold).astype(float))
        agg = (g.groupby(cfg.seg_keys, observed=True)
                 .agg(expo=(cfg.expo_col, "sum"),
                      prem=(cfg.prem_col, "sum"),
                      raw_count=("_is_large", "sum"))
                 .reset_index())
        agg["dev_count"] = agg["raw_count"] * cdf          # gross up to ultimate
        agg["year"] = y
        out.append(agg)
    panel = pd.concat(out, ignore_index=True)
    panel = panel[panel["expo"] > 0].copy()                # a rate needs a denominator
    return panel


def _K(rates, expo, mean) -> float:
    """Buhlmann K = mean / between-group variance (mirrors step_1_frequency.compute_K,
    including its documented V1 simplification: raw between-variance, no process-var
    subtraction)."""
    rates = np.asarray(rates, float); expo = np.asarray(expo, float)
    if len(rates) < 2:
        return float(expo.sum())
    w = expo / expo.sum()
    bvar = float(np.average((rates - mean) ** 2, weights=w))
    if bvar < 1e-30:
        return float(expo.sum())
    return float(mean / bvar)


def credibilised_rate(panel: pd.DataFrame, cfg: Cfg):
    """Cell rate = developed losses / exposure, shrunk toward the same-industry
    complement then the portfolio. Returns (cell_frame, diag)."""
    ind = cfg.industry_key
    keys = cfg.seg_keys

    cell = (panel.groupby(keys, observed=True)
            .agg(expo=("expo", "sum"), dev_losses=("dev_count", "sum")).reset_index())
    cell["raw_rate"] = cell["dev_losses"] / cell["expo"]

    l1 = (panel.groupby(ind, observed=True)
          .agg(l1_expo=("expo", "sum"), l1_losses=("dev_count", "sum")).reset_index())
    l1["l1_raw"] = l1["l1_losses"] / l1["l1_expo"]

    port = float(panel["dev_count"].sum() / panel["expo"].sum())

    # industry (level 1) shrunk to portfolio
    K_l1 = _K(l1["l1_raw"].values, l1["l1_expo"].values, port)
    l1["Z1"] = l1["l1_expo"] / (l1["l1_expo"] + K_l1)
    l1["l1_blend"] = l1["Z1"] * l1["l1_raw"] + (1 - l1["Z1"]) * port

    # cell shrunk to its industry complement (K from within-industry spread)
    cell = cell.merge(l1[[ind, "l1_raw", "l1_blend"]], on=ind, how="left")
    Kvals = []
    for _, sub in cell.groupby(ind):
        if len(sub) >= 2:
            Kvals.append(_K(sub["raw_rate"].values, sub["expo"].values, sub["l1_raw"].iloc[0]))
    K_cell = float(np.mean(Kvals)) if Kvals else float(cell["expo"].sum())

    cell["Z"] = cell["expo"] / (cell["expo"] + K_cell)
    cell["complement"] = cell["l1_blend"].fillna(port)
    cell["final_rate"] = cell["Z"] * cell["raw_rate"] + (1 - cell["Z"]) * cell["complement"]
    prem_M = float(panel["prem"].sum()) / 1e6
    diag = {"portfolio_rate": port, "K_cell": K_cell, "K_l1": K_l1,
            "n_cells": int(len(cell)), "thin_share": float((cell["Z"] < 0.5).mean()),
            "rate_per_Mprem": float(panel["dev_count"].sum() / prem_M) if prem_M else float("nan")}
    return cell, diag


# --------------------------------------------------------------------------- verdict
def ladder_cv(cfg: Cfg, age: int) -> float:
    """CV of the %developed estimate at an age (nearest observed), from the backtest."""
    d = cfg.dev_cv
    if not d:
        return 0.0
    return d[age] if age in d else d[min(d, key=lambda a: abs(a - age))]


def _band(mean: float, cv_extra: float, lo: float, hi: float):
    """Predictive central interval [lo, hi] around expected count `mean`.

    Not a pure Poisson band: it adds the uncertainty in the DEVELOPMENT pattern and
    the RATE (combined coefficient of variation `cv_extra`) on top of count-sampling
    noise, via a Gamma-Poisson (negative binomial): var = mean + (cv_extra*mean)^2.
    This is what makes the band correctly WIDE for fresh years (where %developed is
    itself ~100% uncertain) and tight for mature ones -- so we stop crying wolf at age 0.
    """
    if mean <= 0:
        return (0, 0)
    var = mean + (cv_extra * mean) ** 2
    if _HAVE_SCIPY:
        if var > mean * 1.01:                       # over-dispersed -> negative binomial
            r = mean ** 2 / (var - mean)
            p = r / (r + mean)
            return (int(_nbinom.ppf(lo, r, p)), int(_nbinom.ppf(hi, r, p)))
        return (int(_poisson.ppf(lo, mean)), int(_poisson.ppf(hi, mean)))
    z = 1.2816
    half = z * math.sqrt(var)
    return (max(0, int(round(mean - half))), int(round(mean + half)))


def score(df: pd.DataFrame, cfg: Cfg, lad: dict, cell_rates: pd.DataFrame,
          tri: pd.DataFrame) -> pd.DataFrame:
    """Portfolio-level partial verdict for each immature score year.

    Two independent central estimates are shown:
      * expected_by_now  = model (credibilised rate x exposure x %developed) -- the
        forward-looking projection;
      * the BAND [lo, hi] = EMPIRICAL, from `bands.build_band` on the recent history of
        the count at this age (per $M) scaled to this year's exposure. The band -- not
        the projection -- is what the verdict compares the actual against.
    Falls back to the modelled (ladder-CV) band only when a year/age has fewer than
    `band_min_train` historical points.
    """
    # Key the lookup by an explicit tuple regardless of how many seg_keys there are:
    # a single-key set_index yields SCALAR keys, so tuple-based .get() would miss and
    # silently fall back to the median. Normalise both sides to tuples.
    _raw_rates = cell_rates.set_index(cfg.seg_keys)["final_rate"]
    rate_lookup = {(k if isinstance(k, tuple) else (k,)): v for k, v in _raw_rates.items()}
    book = book_by_year(df, cfg)
    em = B.emergence_rates(tri, book)
    book_M = dict(zip(book["year"], book["expo_M"]))
    rows = []
    for y in cfg.score_years:
        lag = latest_lag(y, cfg)
        col = lag_col(lag, cfg)
        age = age_of(lag, cfg)
        pct = pct_at(lad, age)
        g = df[df[cfg.year_col] == y]
        # expected full-year = sum over cells of final_rate x cell exposure
        seg = (g.assign(_is_large=(g[col] >= cfg.threshold).astype(float))
                 .groupby(cfg.seg_keys, observed=True)
                 .agg(expo=(cfg.expo_col, "sum"), actual=("_is_large", "sum"))
                 .reset_index())
        seg["rate"] = seg.apply(lambda r: rate_lookup.get(tuple(r[k] for k in cfg.seg_keys), np.nan), axis=1)
        seg["rate"] = seg["rate"].fillna(cell_rates["final_rate"].median())
        exp_full = float((seg["rate"] * seg["expo"]).sum())
        actual = int(seg["actual"].sum())
        exp_now = exp_full * pct

        # --- empirical band (with modelled fallback) --------------------------
        rts = B.train_rates(em, age, y, recent_window=cfg.band_recent_window,
                            min_train=cfg.band_min_train)
        if rts is not None and book_M.get(y, 0) > 0:
            lo_f, hi_f, centre = B.build_band(cfg.band_method, rts, book_M[y],
                                              cfg.band_lo, cfg.band_hi)
            band_src = cfg.band_method
        else:                                       # too little history -> modelled band
            cv_extra = math.sqrt(ladder_cv(cfg, age) ** 2 + cfg.cv_rate ** 2)
            lo_f, hi_f = _band(exp_now, cv_extra, cfg.band_lo, cfg.band_hi)
            centre = exp_now
            band_src = "modelled(fallback)"
        lo, hi = int(math.floor(lo_f)), int(math.ceil(hi_f))

        # Verdict is band-driven. Upper (ALARM) side works at any age; lower (LOW) side
        # is only meaningful when the band floor sits above `too_early_lo_floor` -- below
        # that a genuinely low year can't be told apart from early-reporting noise.
        if actual > hi:                             # beyond even the widened band -> real signal at ANY age
            light = "ALARM"
        elif actual < lo:
            light = "LOW"
        elif lo <= cfg.too_early_lo_floor:          # band can't discriminate a low year yet
            light = "TOO EARLY"
        else:
            light = "OK"
        rows.append({"year": y, "age_months": age, "pct_developed": round(pct, 3),
                     "expected_full": round(exp_full, 1), "expected_by_now": round(exp_now, 1),
                     "band_method": band_src, "band_centre": round(centre, 1),
                     "band_lo": lo, "band_hi": hi,
                     "actual_by_now": actual, "verdict": light,
                     "status": "final" if pct >= 0.9 else "provisional"})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- backtest
def backtest_rate(df: pd.DataFrame, cfg: Cfg, lad: dict) -> pd.DataFrame:
    """Leave-one-year-out: predict a completed year's developed count from the OTHER
    years' rate x its exposure, and check. Uses portfolio-level developed counts.

    CAVEAT (do not over-read): both `predicted` and `actual_developed` are grossed up
    by the SAME cdf, so any error in the ladder/tail CANCELS. This validates that the
    RATE is stable across years -- it does NOT validate the development pattern. For
    that, see backtest_ladder()."""
    years = cfg.calib_years
    rec = []
    dev = {}
    for y in years:
        lag = latest_lag(y, cfg); col = lag_col(lag, cfg); cdf = cdf_at(lad, age_of(lag, cfg))
        g = df[df[cfg.year_col] == y]
        cnt = float((g[col] >= cfg.threshold).sum()) * cdf
        expo = float(g[cfg.expo_col].sum())
        dev[y] = (cnt, expo)
    for y in years:
        others = [z for z in years if z != y]
        rate = sum(dev[z][0] for z in others) / sum(dev[z][1] for z in others)
        pred = rate * dev[y][1]
        actual = dev[y][0]
        rec.append({"year": y, "rate_others": round(rate, 4), "predicted": round(pred, 1),
                    "actual_developed": round(actual, 1),
                    "error_pct": round(pred / actual - 1, 3) if actual else float("nan")})
    return pd.DataFrame(rec)


def backtest_ladder(tri: pd.DataFrame, cfg: Cfg) -> pd.DataFrame:
    """Leave-one-year-out DEVELOPMENT backtest: predict a finished year's count at a
    later age from an EARLIER age, using factors learned from the OTHER years, and
    check. Here the ladder error does NOT cancel, so this genuinely tests the pattern.
    Expect large errors from young ages (the honest ~100%->~12% story)."""
    T: dict = {}
    for _, r in tri.iterrows():
        T.setdefault(int(r["year"]), {})[int(r["age"])] = int(r["count"])
    ages = sorted({a for d in T.values() for a in d})
    target = 48 if 48 in ages else max(ages)

    def a2a_excl(a, excl):
        num = den = 0
        for y, d in T.items():
            if y == excl:
                continue
            if a in d and (a + cfg.step) in d:
                den += d[a]; num += d[a + cfg.step]
        return num / den if den else 1.0

    def grow(a, to, excl):
        g, x = 1.0, a
        while x < to:
            g *= a2a_excl(x, excl); x += cfg.step
        return g

    rows = []
    for y, d in sorted(T.items()):
        if target not in d or d[target] < 5:        # need a real, comparable target
            continue
        for a in [x for x in ages if x < target and x in d]:
            pred = d[a] * grow(a, target, y)
            rows.append({"year": y, "from_age": a, "to_age": target,
                         "predicted": round(pred, 1), "actual": d[target],
                         "abs_error": abs(pred / d[target] - 1)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- orchestrate
def run(config_path: str) -> dict:
    cfg = load_config(config_path)
    df = load(cfg)
    tri = triangle(df, cfg)
    lad = ladder(tri, cfg)
    panel = developed_panel(df, cfg, lad, cfg.calib_years)
    cell_rates, diag = credibilised_rate(panel, cfg)
    verdict = score(df, cfg, lad, cell_rates, tri)
    bt = backtest_rate(df, cfg, lad)
    bt_ladder = backtest_ladder(tri, cfg)
    book = book_by_year(df, cfg)
    band_cells, band_scores = B.shootout(tri, book, lo=cfg.band_lo, hi=cfg.band_hi,
                                         recent_window=cfg.band_recent_window,
                                         min_train=cfg.band_min_train)
    return {"cfg": cfg, "triangle": tri, "ladder": lad, "panel": panel,
            "cell_rates": cell_rates, "diag": diag, "verdict": verdict,
            "backtest": bt, "backtest_ladder": bt_ladder,
            "band_scores": band_scores, "band_cells": band_cells}
