# Scoring the current (undeveloped) accident year — approach

> Status: **agreed direction, hardening on data.** The engine that computes the development
> pattern is built (`src/development/`). Wiring it into the Step-3 verdict waits on a unified
> extract that covers a longer history and shares one basis with the frequency/premium model.

## The problem

The Step-3 verdict compares **expected** large losses (`frequency × premium`) to **actual**.
For a *mature* year that is fair. For the **current** accident year it is not: large claims take
time to be **reported** and to grow past the **$200,000** threshold, so the actual count is
understated at any early valuation. Comparing a full-year expected to a partly-reported actual
manufactures a false alarm (e.g. a recent year showing ~139 against an expected ~205 is mostly
un-emerged claims, not a good year).

## The key finding: it is a liability problem, not a property problem

From a valuation triangle (the same loss count seen at successive as-of dates):

| Coverage | Develops | % reported at 12 months | Adjustment |
|---|---|---:|---|
| Commercial property (COVCP) | fast | ~100% | **none — use as-is** |
| Commercial liability (COVCL) | slow (settles over ~3–6 years) | ~35% | **yes — compare partials** |

So the two coverages are handled separately. Segments already carry `CovType`, so this splits
cleanly. (Development is *net*: counts can fall as well as rise — subrogation, reserve reductions
below threshold — so factors are net, not one-way.)

## The method: compare at the same stage of development ("partials")

Do **not** wait for the year to finish, and do **not** extrapolate a final number for the verdict.
Instead compare like-for-like at the current development age:

```
   Property   →  full expected        vs  full reported          (today's method; it is developed)
   Liability  →  expected-BY-THIS-AGE  vs  reported-BY-THIS-AGE   (the "partials")

   expected-by-age(coverage) = expected_ultimate(coverage) × %developed(coverage, age)
```

Both are the **same formula** with a coverage-specific `%developed` — property's is ~100%, so its
comparison is unchanged; liability's is < 100%, so it compares partials.

**Worked example (real data, liability, accident year 2024 at 12 months):**
- Expected by 12 months ≈ liability full-year expected × ~35% ≈ **17** (agrees with the historical
  count at that age).
- Reported by 12 months = **17** → **normal**. No waiting, no forecast.
- Had it shown ~35, that is outside the normal range → a genuine signal (liability running hot).

**Critical caution — small numbers.** Liability partials are small (single digits at early ages),
so "did we hit the number exactly" is the wrong test. Put a **Poisson normal range** around the
expected partial (expect ~3 → 0–7 is normal). Skipping this cries wolf every period.

**Optional companion (planning, not the verdict):** develop the reported count to ultimate —
`reported ÷ %developed`, or Bornhuetter-Ferguson `reported + expected × (1 − %developed)` which
leans on the frequency prior while the year is immature — clearly labelled a provisional estimate
that trues up on each re-run.

## How the data is organized

A **triangle**: `(accident_year × coverage × development_age) → cumulative count of large losses`.
Build it by counting each **dated snapshot** of the loss data and relabelling the valuation date
as an **age** (months since the accident year ended) so different years line up:

```
                    age 6   age 12   age 18 ...
   AY2023 liability            17       26
   AY2024 liability    7       17       25
```

Two structural points:
- **Coarse triangle, granular expected.** Development *speed* is a property of the **coverage**
  (not region/industry), so the triangle only needs `accident_year × coverage × age`. The detailed
  expected stays per segment (from the frequency model); multiply each segment's expected by *its
  coverage's* `%developed`. Two tables joined on coverage.
- **The one discipline: keep dated snapshots.** The triangle is "the same book counted at different
  dates" — archive every pull with its as-of date, or it cannot be reconstructed later.

## In production

Each reporting cycle: pull the latest data; count the current year by coverage; property is used
as-is; liability is compared at its current age (partials) with a widened normal range; the current
year is labelled **provisional — developing** and firms up on every re-run. Prior mature years are
**final**.

## What is built vs open

- **Built:** `src/development/` — triangle → per-coverage `%developed(age)` (chain-ladder), plus
  develop-to-ultimate (chain-ladder / Bornhuetter-Ferguson) and a per-coverage tail factor for
  liability's settlement beyond the observed window. Runs on a committed sample triangle.
- **Open:** the longer unified extract (locks liability factors + tail); wiring the partials verdict
  into Step 3; and a terminology pass (report large-losses-per-$M as **frequency**, since "rate"
  reads as premium).
