# Liability development track

Scores the **current, still-developing** accident year for commercial **liability**
(COVCL) large losses (incurred ≥ $200k) — answering *"are the large losses we're
seeing in line with expectations, or should we be alarmed?"* without the false-alarm
trap of comparing a partly-emerged actual to a full-year expected.

Property (COVCP) is **not** here — it develops fast and is scored in full from
`basic_data_1.csv` by the main pipeline. This is the parallel liability track; the two
meet in the expected-vs-actual board. See `../docs/immature_year_approach.md`.

## Run it

```bash
python src/step_5_liability_development/run.py --config src/step_5_liability_development/config.yaml
```

Outputs land in `outputs/step_5_liability_development/<run>_<date>/`: `ladder.csv`, `triangle.csv`,
`segment_rates.csv`, `verdict.csv`, `backtest_rate.csv`, `backtest_ladder.csv`,
`band_shootout.csv`, `band_shootout_cells.csv`.

## STATUS — implemented

Both agreed design changes are now **coded and running** (`bands.py` + `pipeline.py`):
1. **Recent-weighted ladder early rungs** — the ages in `develop.recent_ladder.recent_ages`
   (`[0, 12]`) use accident years `>= recent_from_year` (2021) only; later rungs pool all years.
   Reporting has slowed (age-0 large losses per $M fell ~35 → ~4–9 across 2018→2024), so this
   pulls age-0 %developed from the pooled ~21% down to the recent **~10.7%** (age-12 ~37% → **30.2%**).
2. **Empirical per-age band + configurable band method** (`bands.py`). The band is *measured*
   from the recent history of the count at each age (per $M) scaled to the current book, with the
   method **selectable** via `verdict.band_method` ∈ {`min_max`, `std`, `percentile`, `poisson`,
   `hybrid`} (default `hybrid`), picked by the **walk-forward shoot-out** (`bands.shootout`).

## Method (four numbers)

1. **Ladder** — % of liability large losses developed by age (from 10 snapshot years).
   *Timing only.* Recent-weighted early rungs (reporting has slowed): **10.7%** at age 0,
   **30.2%**/1yr, then **51.0%**/2yr, **67.6%**/3yr, **81.6%**/4yr, **92.6%**/5yr.
2. **Rate** — developed large losses per unit **earned exposure**, calibrated on
   developed-enough years (2019–2022), credibilised across ~150 thin segments
   (Bühlmann `Z = E/(E+K)`, shrink to same-industry then portfolio). ~0.38 per $M premium.
3. **Expected** — `rate × exposure` (level, known day one) `× %developed(age)` (discount
   to the year's current age) = **expected-by-now**.
4. **Verdict** — compare actual-reported-so-far to the **empirical band** →
   `TOO EARLY / LOW / OK / ALARM`.

## The band is the point (read this)

The band **is** the alarm, so it is measured and validated, not asserted. For each age we take the
**recent history of the count at that age** (per $M, last `band_recent_window` = 5 accident years)
and scale it to the score year's own exposure. **The band shoot-out** (walk-forward over 27 held-out
cells, scored on coverage + false-alarm + width) ranks the five methods:

| method | coverage | false-alarm | false-*ALARM* | rel. width | note |
|---|---|---|---|---|---|
| percentile | 85% | 15% | 4% | 1.46 | tightest, but can't extrapolate + jumpy at small n |
| min_max | 89% | 11% | 0% | 1.86 | fragile (stretches to worst single year) |
| **hybrid** *(default)* | **89%** | **11%** | **0%** | 1.91 | 0 false-ALARMs, extrapolates, stated coverage |
| std (±2σ) | 96% | 4% | 0% | 2.64 | over-covers → no real alarm |
| poisson | 30% | 70% | 22% | 0.57 | **disqualified** — fires on 70% of normal cells |

`hybrid` is the default (nominal coverage for a 10–90 band = 80%): percentile edges it on the
*measurable* axis but the backtest cannot see extrapolation or small-n fragility, where hybrid wins;
the method stays **configurable** so percentile can be swapped in. Verdict labels: **`TOO EARLY`**
(band floor ≤ `too_early_lo_floor` → can't tell a low year from early-reporting noise) / `LOW` /
`OK` / **`ALARM`** (beyond the band — fires at any age, so a genuine blowout is never missed).
On the current book: **2024** (age 12, band [7–35]) → **OK** (17); **2025** (age 0, band [1–20]) →
**TOO EARLY** (4, can only catch a blow-up this early).

## Validation (two separate backtests — don't conflate them)

- **`backtest_rate`** — leave-one-year-out on the rate: ~9% error. Proves the rate is
  *stable across years*. **Does NOT validate the ladder** (the shared factor cancels).
- **`backtest_ladder`** — leave-one-year-out on the emergence pattern: ~120% error from
  age 0, ~31% by age 3. The honest test — and the reason for the wide young-year band.

## Known limitations (flag to stakeholders)

- **Grain:** "large loss" = a **policy** whose *aggregate* incurred crosses $200k, not a
  single $200k claim. Confirm this matches intent.
- **Fixed $200k threshold** under claim inflation slowly drifts the pattern (more claims
  cross a static line over time) — consider indexing.
- **Tail factor 1.08** past age 60 is an assumption until history extends.
- **Rate basis is exposure** (correct for frequency); premium is carried for readability
  only. Any doc saying "× premium" must be reconciled to this.

## Production wiring

The rate step reuses the same logic as `step_1_frequency` (GLM + year-effect on-leveling +
credibility). This module implements it standalone for review; folding the rate into
`step_1_frequency` (run with a liability config + the develop gross-up) is the production
form. The verdict then merges with property in `step_3_expected_vs_actual`.
