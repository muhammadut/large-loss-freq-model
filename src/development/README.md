# Step 5 — Claim-count development (IBNR)

The current accident year is **immature**: large claims take time to be reported and to cross
the $200K line, so a mid-cycle count understates the ultimate. This turns a **valuation
triangle** (the same loss count seen at successive as-of dates) into a per-coverage
**"% developed by age"** pattern, and develops the reported count to ultimate — so the year can
be scored fairly instead of two years late.

## The one finding that shapes everything

**It's a liability problem, not a property problem.**

| | Commercial property (COVCP) | Commercial liability (COVCL) |
|---|---|---|
| Development factors | ~**1.0** (noise) | large (1.75, 2.43, 1.50, …) |
| % developed at 12 months | ~**100%** | ~**35%** |
| Adjustment needed | **none** — pass through | **yes** — scale up |

Property is done within ~12 months (subrogation can even nudge counts *down*). Liability has a
long tail (~6 years to fully settle). So the two coverages get **separate** patterns and only
liability is materially adjusted. Our segments already carry `CovType`, so this splits cleanly.

## Run it

```bash
python src/development/run.py --config src/development/config.yaml
```

Outputs land in `outputs/development/<run>_<date>/`:

| File | What it is |
|---|---|
| `development_report.md` | the pattern + reported-vs-ultimate table + caveats |
| `development_pattern.csv` | % developed by (coverage, age) |
| `developed_years.csv` | reported vs ultimate per (accident year, coverage) |

Demo (sample triangle): property ~100% developed at 12mo, liability ~35%; accident-year 2024
develops from **189 reported → ~210 ultimate**, and the whole ~20 gap is liability.

## The triangle format

`src/development/development_triangle_sample.csv` — one row per `(accident_year, covtype)`; each
`asof_YYYY-MM-DD` column is the reported large-loss count as known on that valuation date:

```
accident_year,covtype,asof_2024-12-31,asof_2025-06-30,asof_2025-12-31,asof_2026-06-30
2024,COVCL,4,7,17,25
2024,COVCP,165,171,164,164
```

Replace the sample with the 10-year extract; the engine is data-agnostic.

## Methods (config `develop.method`)

- **`chain_ladder`** — `ultimate = reported / %developed`. Simple; the standalone demo.
- **`bornhuetter_ferguson`** — `ultimate = reported + expected × (1 − %developed)`. Steadier
  early in the year (leans on the Step-1 × Step-2 expected prior instead of dividing a tiny
  reported count by a tiny %developed). Supply the prior via `develop.expected_prior_csv`.

`develop.tail_factor` loads development past the observed window (liability keeps settling after
our triangle ends) — an **assumption** until the longer extract lands.

## How it plugs into the verdict (Step 3)

Two supported ways to use the pattern, matching the two options on the table:
1. **Develop to ultimate** — replace the immature actual with its developed estimate, then run
   the normal expected-vs-actual.
2. **Same-maturity** — compare the reported count against `expected × %developed` (what should be
   reported *by now*), no extrapolation.

Both need the development pattern this step produces. Wiring it into Step 3 waits on the unified
extract so the triangle and the frequency/premium model share one basis.

## Caveats

Counts move net (subrogation → some drop out); liability counts are small so factors are
directional (the 10-year triangle stabilises them); the tail factor is a placeholder to refine.
