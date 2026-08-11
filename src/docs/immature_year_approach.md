# Scoring the current (undeveloped) accident year — liability method

> Status: **implemented and running** (`src/step_5_liability_development/`, `bands.py` + `pipeline.py`). The
> pipeline uses the **recent-weighted ladder + empirical per-age band (method configurable)**
> described below; the band method was picked by a walk-forward shoot-out. Property is developed
> within ~12 months and is scored as-is elsewhere — **this doc is liability only.**

## The problem

Liability large losses (a policy whose incurred crosses **$200,000**) emerge slowly — a claim
grows for years as it settles. So the current accident year's count is understated at every early
valuation. Comparing a partly-emerged actual to a full-year expected manufactures a false alarm
(a recent year showing ~4 against a full-year ~48 is un-emerged claims, not a good year).

## The data

One dated year-end **snapshot** of the book, kept for 10 years, lined up per policy: for each
policy we have its incurred at age 0 and re-measured at +1..+5 years. This reconstructs
development. Losses are in dollars; a null future column means *not yet observable* (not zero);
zero-loss policies are kept (they are the exposure base). Grain: a **policy** crossing $200k
(confirm this matches the business definition of a "large loss").

## The pipeline (data → verdict)

1. **Triangle** — count policies ≥ $200k by `(accident_year × age)`. Pure counting; reconciles
   to the raw file.
2. **Ladder = "% visible by age"** (timing only). Built from the finished years. **Reporting has
   slowed over the decade** (large losses seen per $M at year-end fell from ~35 in 2018 to ~4–9 in
   recent years), so the early rungs are estimated from **recent years only** (≈ 10.7% visible at
   year-end, ≈ 30.2% at +1); later rungs (+2 onward: ≈ 51.0/67.6/81.6/92.6%) are stable across all
   years. Recent-weighting the early rungs is deliberate — using the old, faster number would
   over-expect and cry wolf.
3. **Rate = frequency per unit of earned EXPOSURE** (not premium — premium is distorted by rate
   changes; exposure is the correct base for frequency). Developed large losses ÷ exposure, per
   segment (`ratingregion × MAIN_OPGROUP`), **credibilised** (hierarchical Bühlmann `Z = E/(E+K)`:
   trust a segment's own data in proportion to its exposure, shrink the rest toward the
   same-industry complement, then the portfolio). Stable across years (a leave-one-out test
   predicts a held-out year within ~9%). These are **rates** — multiplied by a segment's own
   (often tiny) exposure they give a small, realistic expected count.
4. **Expected-by-now** = `rate × exposure × %visible(current age)`.
5. **The band (the critical piece — it *is* the alarm).** The normal range is **measured from the
   historical spread of the count at that age**, scaled to the current book's size — not asserted.
   Because age-0 counts are noisy (high year-to-year variation) the band is wide there; age-1
   counts are steady, so the band is tight and a real verdict is possible from year 1. The exact
   band construction is an **open question tested by backtest** (see below).
6. **Verdict** — actual-so-far vs the band. The alarm (upper) side always works; the **low** side
   is only meaningful when the band floor sits materially above zero. So: `actual > hi` → **ALARM**
   (fires at any age, so a genuine blowout is never missed); `actual < lo` → **LOW**;
   `band_lo ≤ too_early_lo_floor` → **TOO EARLY** (a low year can't yet be told from early-reporting
   noise — honest, not "fine"); else → **OK**. On the current book: **2024** (age 12, band [7–35])
   → **OK** (actual 17); **2025** (age 0, band [1–20]) → **TOO EARLY** (actual 4, only a blow-up is
   detectable this early).
7. **Tracking** — every accident year is re-scored each cycle; a cohort firms from TOO EARLY to a
   real OK as it ages (~year 1–2).

## The band method — tested and resolved

The band decides when the alarm trips, so it is not asserted. Five candidates were run through a
**walk-forward shoot-out** (`bands.shootout`): over every held-out (year, age) cell, build the band
from the *earlier* years only and check whether the real count lands inside. Scored on **coverage**
(share of normal cells inside the 10–90 band; nominal 80%), **false-alarm rate**, false-*ALARM*
(wrongly crying blow-up), and band **width**. 27 cells, recent 5-year window:

| Method | Coverage | False-alarm | False-*ALARM* | Rel. width | Verdict |
|---|---|---|---|---|---|
| Empirical 10–90th %ile | 85% | 15% | 4% | 1.46 | tightest, but can't extrapolate + jumpy at small n |
| Min–max | 89% | 11% | 0% | 1.86 | fragile (stretches to worst single year) |
| **Hybrid** *(default)* | **89%** | **11%** | **0%** | 1.91 | year-to-year CV + Poisson bounce; 0 false-ALARMs; extrapolates; stated coverage |
| Mean ± 2σ | 96% | 4% | 0% | 2.64 | over-covers → no real alarm |
| Poisson only | 30% | 70% | 22% | 0.57 | **disqualified** — fires on 70% of normal cells |

**Outcome:** `poisson` is decisively out (it treats normal year-to-year drift as an alarm);
`std`/`min_max` over-cover or are fragile. `percentile` edges `hybrid` on the *measurable* axis
(coverage + width) — but the backtest **cannot** see the two places `percentile` is weak: it can't
extrapolate past the worst observed year (an alarm must fire on the *unprecedented*), and its
quantiles are jumpy at n = 3–7. Under an asymmetric cost (a missed blow-up ≫ a false "looks light")
and `hybrid`'s zero false-ALARM record, **`hybrid` is the default**. Catch-rate itself is *not*
testable — history has no labelled bad years; we state that honestly. The method is **configurable**
(`verdict.band_method`) so `percentile` can be swapped in without code changes.

## Validation

- **Rate** — leave-one-year-out prediction of a held-out year (~9% mean error: 2019 +17%, 2020 +5%,
  2021 −4%, 2022 −12%). Confirms the rate is stable. (Does *not* validate the ladder — the shared
  development factor cancels.)
- **Ladder** — leave-one-year-out development test (mean |error| ~119% projecting the ultimate from
  age 0, ~103% from age 12, ~86% from age 24, ~31% from age 36). This is *why* the young-year band
  is wide and age 0 is TOO EARLY.
- **Band** — the walk-forward coverage/false-alarm shoot-out above.

## Honest limits (state to stakeholders)

- The brand-new year (age 0) is the least certain — real noise, not a defect; its honest output is
  a wide range, not a crisp call, plus the disaster alarm.
- Reporting speed is **drifting** (slowing) — re-fit the early ladder rungs each year.
- The tail past the observed window is an **assumption** until history extends.
- Thin segments lean heavily on their industry complement (credibility).

## Code

`src/step_5_liability_development/` (self-contained, runnable): `pipeline.py` (triangle → recent-weighted ladder →
credibilised exposure rate → empirical-band verdict → two backtests), `bands.py` (the five band
methods + walk-forward shoot-out), `config.yaml`, `run.py`. Reuses the credibility approach from
`src/step_1_frequency/`. Next (not yet done): fold the rate step into `step_1_frequency` (liability
config) and merge with the property verdict in `step_3_expected_vs_actual`; the `rate → frequency` rename.
