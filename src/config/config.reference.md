# `config.yaml` — field reference

Every business choice lives in `config.yaml`. This documents each field, its
valid values, and *why* it exists. Changing any of these is a config edit, not a
code change — which keeps refits reproducible and auditable.

## `run`
| field | meaning | default |
|---|---|---|
| `name` | label stamped into the run report | — |
| `output_dir` | where artifacts are written | `outputs` |

## `data`
| field | meaning |
|---|---|
| `path` | the source extract (read with `usecols` — only needed columns load) |
| `loss_col` | the incurred-loss column used to flag large losses |
| `year_col` | the time dimension (gets the year effect) |
| `cat_flag_col` | catastrophe flag; used to action `cat_scope` |
| `policy_period_col` | optional id (e.g. `POLICYPERIOD_ID_M`); enables the `count_grain` diagnostic |

## `large_loss`
| field | meaning | guidance |
|---|---|---|
| `threshold` | the large-loss dollar line | **$200,000** — the risk-tolerance definition. Fixed, business-aligned. |
| `mode` | threshold mode | **Only `fixed` is implemented** — `percentile` is rejected at config load (it drifts $194K–$249K across years; a definition that wobbles is not a definition). |
| `cat_scope` | catastrophe treatment | `assume_excluded` (default — book treated as non-cat; disclosed in the run report because the cat flag is empty here), `exclude_flagged` (drop flagged rows — **halts** if no usable flag), or `include_all` (disclosed). |

## `exposure`
| field | meaning |
|---|---|
| `lens` | the denominator: `premium` (default) / `tiv` / `earned_exposure`. **Changes the offset, the rate's meaning, and what you must project forward.** |
| `columns` | maps each lens name to its data column |

Lens guidance: **premium** = "losses per $ charged" (pricing lens, ~99% populated,
on-leveled by the year effect). **tiv** = "losses per $ of insured value" (hazard
lens; causal for property, a size-proxy for liability; ~80% populated; you must
project TIV forward). **earned_exposure** = "losses per volume unit". Premium and
TIV genuinely disagree on segment ranking — the `base_agreement` gate measures it.

## `segmentation`
| field | meaning |
|---|---|
| `keys` | the segment definition (the GLM relativities) |
| `industry_key` | the credibility complement anchor (thin cells shrink toward their **industry**) |
| `null_region_key` / `null_region_fill` | blanks here are bucketed (e.g. "Unknown"), never dropped — so no loss vanishes on a missing label |
| `region_map` (optional) | collapse fine-grained regions (e.g. province codes in some extracts) to the canonical grouped rating regions, so the segment definition is stable whichever data file is used. Used by `config_data2.yaml`; omit it for `data_1` (already grouped). |
| `drop_null_industry` | drop rows with no industry (2 rows here) |

## `calibration`
| field | meaning | guidance |
|---|---|---|
| `experience_years` | the calibration window | 5 years here |
| `reference_year` | the year-level the rate is read at | **MUST be the last fully-developed year.** The newest year is still maturing and would understate the rate. |
| `family` | model family | **Only `poisson` is implemented** — any other value is rejected at config load (statsmodels GLM holds NB dispersion fixed, a trap; the dispersion gate flags if NB is warranted). |
| `year_effect` | include `C(year)` | **Keep `true`.** This is the on-leveling term; without it the rate is biased by year-wide rate/inflation shifts. |

## `credibility`
| field | meaning |
|---|---|
| `level1_keys` | first complement level: cell → these → industry → portfolio. **Must include `industry_key`** (enforced at config load) — the hard-shaped hierarchy merges level-1 to industry. |
| `full_credibility_losses` | a segment with ≥ this many historical losses is labeled `credible` (informational) |

*Known V1 simplification (flagged for formal review): the Bühlmann `K` uses the raw between-group variance as the variance-of-hypothetical-means without subtracting process variance. For rare-event Poisson data this can over-credit thin segments; small at dispersion ≈ 1. The unbiased Bühlmann-Straub estimator is a Phase-2 refinement.*

## `validation`
Each gate has a threshold and an `on_fail` of `halt` or `warn`.

| gate | threshold field | trips when | typical `on_fail` |
|---|---|---|---|
| `reconciliation` | `tol_pct` | fitted total ≠ actual total (implementation invariant) | **halt** |
| `dispersion` | `max_ratio` | Pearson χ²/df too high | warn |
| `thin_segment_share` | `max_thin_pct` | too many thin segments (informational — a PASS is *not* "segments are credible") | warn |
| `backtest` | `holdout_year` | held-out aggregate actual outside 5–95% band | warn |
| `backtest_segment` | `min_spearman` | segment-level holdout rank calibration too weak | warn |
| `robustness_drop_yr` | `max_p95_move_pct` | **FINAL**-rate p95 move too large when newest year dropped | warn |
| `base_agreement` | `alt_lens`, `min_corr` | lenses disagree (informational) | warn |
| `total_preservation` | `max_drift_pct` | credibility moved the portfolio total beyond tolerance | warn |

Data-quality gates (run before modeling): `years_present`, `min_large_losses` (halt); `cat_scope`, `exposure_integrity[<lens>]` (per active **and** alternate lens), `count_grain` (informational/warn).
