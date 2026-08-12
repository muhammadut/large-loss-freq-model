# Large-Loss Frequency Model

A commercial Property & Casualty (P&C) insurance analytics pipeline that answers one
board-level question:

> **"Are we getting more big claims than our pricing assumed — and if so, exactly where?"**

It learns, from four years of history, how often each slice of the book produces a
**large loss**, projects how many to expect this year, compares that to what actually
happened, and flags the segments that are drifting. A separate, self-contained track
does the same job for slow-reporting **liability** business, where a raw year-to-date
count is misleading until you account for how young the year still is.

---

## TL;DR

- **What it is:** a 5-step pipeline over commercial P&C policy data. Steps 1–4 form the
  **property / mixed-book chain**; Step 5 is a **separate parallel track** for liability.
- **Large loss** = any policy whose total incurred loss is **≥ $200,000** (a fixed dollar line).
- **Step 1** fits a statistical model to get a **frequency rate** (expected large losses per
  $1 of premium) for each **segment** (`coverage type × region × industry`), smoothed with
  **credibility** so thin segments borrow strength from their industry.
- **Step 2** projects each segment's **full-year premium** from what is visible so far.
- **Step 3** multiplies rate × premium → **expected count**, compares to **actual**, and
  returns a **GREEN / AMBER / RED** verdict with a percentile and a "why it moved" waterfall.
- **Step 4** breaks the same numbers down **per segment** to say *where to act*.
- **Step 5** scores the still-developing **liability** year using a development **ladder**
  (how much of the year has emerged) and an empirical **band** (what "normal" looks like at
  this age). **It reads its own data file and NONE of Step 1's output.**
- **Latest headline verdict (2024):** expected **187.8** large losses, actual **181**,
  **33rd percentile → GREEN**. Out-of-sample backtest **4/4 in band**.

---

## Part 1 — Orientation (read this first)

*A self-contained tour of the whole system for a first-time reader. Jargon is kept
(this is a technical model) but every term is defined where it first appears and shown
with a real number. The equations, full validation, and per-step detail are in Part 2.*

### The problem it solves

Large losses — single policy-coverage records whose **incurred loss** (paid + reserved)
is **≥ $200,000** — are rare and volatile. In any year the book can run above or below
"normal" for two very different reasons: **random fluctuation** (an unlucky draw) or
**structural change** (a segment's true risk shifted, or the price is wrong). The business
needs to separate those, per segment and in total, every year — and feed the resulting
frequency rates into pricing. This pipeline produces exactly that: an **expected**
large-loss count per segment, an **actual-vs-expected** verdict, and a **where-to-act**
breakdown. It models *how many* large losses (frequency), not *how severe* (severity).

Consumers: pricing/actuarial (the rate table), portfolio management (the board verdict),
underwriting (the per-segment signals).

### What one row of data is

Both source files are policy-coverage records. The columns that drive everything:

| column | meaning | example value |
|---|---|---|
| `CovType` | coverage type | `COVCP` (property) or `COVCL` (liability) |
| `ratingregion` | rating region | `COR`, `NEWOR`, `ABandT`, `QC`, `Atlantic` |
| `MAIN_OPGROUP` | industry / operations group | `Realty`, `Restaurant`, `Contractors` |
| `ROLLING_YEAR` | accident year | `2024` |
| `TOTAL_COVERAGE_INCURREDLOSS_M` | incurred loss (paid + reserved) | `261,679` → counts as a large loss |
| `TOTAL_EARNED_PREMIUM` | earned premium — the **exposure** measure | `48,120` |

A **segment** is the combination `CovType × ratingregion × MAIN_OPGROUP` (~296 of them).
A **large loss** is a *row* with incurred ≥ $200,000 — note this is a *policy-coverage*
crossing the line on aggregate, not necessarily one single $200K claim. The liability file
additionally stores the same policy re-measured at +1…+5 years (`LOSS_N_plus_1…5`), which
is what lets Step 5 reconstruct how losses emerge over time.

### The three concepts you need

**1. Frequency rate — large losses per dollar of exposure.**
"Exposure" is how much business is at risk; here it is measured by earned premium (more
premium ⇒ more policies ⇒ more chances for a large loss). The *rate* is expected large
losses per \$1 of premium, usually shown per \$1M for readability. Example: Step 1 assigns
`COVCP · NEWOR · Restaurant` a rate of **0.567 per \$1M**. A segment earning \$20M of premium
is therefore expected to produce `0.567 × 20 ≈ 11` large losses a year.

**2. Credibility — how much to trust a thin segment's own number.**
**88.5%** of segments have fewer than 5 historical large losses — too few to trust their raw
rate. Credibility assigns a weight `Z ∈ [0,1]`: the final rate is `Z ×` the segment's own
model estimate `+ (1 − Z) ×` a **complement** (its same-industry average, then the whole
portfolio). Example: `COVCP · NEWOR · Restaurant` has `Z = 0.463`, so its final rate `0.567`
is a blend of its own GLM estimate `0.623` (the raw fit of the Poisson count-regression — the **GLM**, detailed in Step 1; weight 0.463) and its industry complement `0.519`
(weight 0.537). A segment with almost no exposure gets `Z ≈ 0` and simply inherits the
industry rate.

**3. Development / immaturity — losses report late.**
A claim is reported and reserved over time, so a recent ("immature") accident year shows
**fewer** large losses than it eventually will. This is visible directly in the liability
triangle: accident year 2021 showed **9** large losses at age 0 but **37** by age 48. A
fresh year's low count is therefore *incomplete*, not *good*. Property reports fast enough to
ignore this; liability does not — only ~**10.7%** of a liability year's ultimate large losses
are visible at age 0, which is the entire reason Step 5 exists.

### The pipeline, end to end (one pass, real numbers)

**Steps 1–4 run on `basic_data_1.csv`** (the whole commercial book, property + liability
together):

1. **Step 1 — frequency.** Fit a Poisson GLM (a regression for counts) with a year effect,
   then apply credibility → a frozen `rate_table_final.csv` of **296** segment rates (e.g.
   `0.567/$M` for the Restaurant segment above).
2. **Step 2 — premium.** Project each segment's *full-year* earned premium from what has been
   earned so far (a growth factor per segment and calendar month).
3. **Step 3 — expected vs actual.** For each segment, `expected = rate × projected premium`;
   sum to the portfolio. For 2024: **expected 187.8** vs **actual 181** → **33rd percentile**
   → **GREEN** (well within normal). The *total* is trusted.
4. **Step 4 — where to act.** Break that same expected-vs-actual down per segment. Example
   signal: `COVCP · COR · Retail` was expected **≈ 2.5** but saw **8** (Poisson tail
   probability `p = 0.004` — under a 0.4% chance of 8+ large losses if the rate were correct — and under-rated in most years) → a genuine **structural**
   signal, written up as a dossier. `COVCP · COR · Realty` (16.5 expected) is the single
   largest concentration.

**Step 5 runs separately on `liability_data_10_yrs.csv`:**

5. **Step 5 — liability development.** Build the triangle, a recent-weighted **ladder**
   (% developed by age: 10.7% at age 0 … 92.6% at age 60), and its own credibilised rate.
   For accident year **2025 at age 0**: expected-if-fully-developed `60.4`, discounted to the
   year's age → **expected-by-now 6.5**; the empirical **normal band** is `[1–20]`; actual so
   far is **4** → **TOO EARLY** (too little has emerged to call the year *low* — but a count
   above 20 would still fire **ALARM**). Accident year **2024 at age 12**: band `[7–35]`,
   actual **17** → **OK**.

### Why liability appears in two places (important)

Liability (`COVCL`) shows up in **both** Step 1 and Step 5. This is deliberate:

- **Step 1** computes a rate for *every* segment, including the **153** `COVCL` segments —
  but it treats them like property, ignoring that their counts are immature.
- **Step 5** is the *correct* liability treatment: it uses the separate file with
  development history to account for late reporting, and produces the age-aware verdict.
- Today the two are **independent**, and **Step 5's verdict is the one to trust for
  liability**. Folding Step 5's development-aware rate back into Step 1 — so the board sees a
  single reconciled number — is a planned production step (`DECISIONS.md`), not yet built.

---

## Glossary — every term, plain English

| Term | Meaning |
|---|---|
| **Large loss** | A policy whose **total incurred loss ≥ $200,000**. "Incurred" = paid + reserved, where **reserved** = the insurer's current estimate of cost not yet paid — so incurred is the best current estimate of the ultimate cost. A fixed dollar threshold, not a percentile. |
| **Segment** | A bucket of similar policies. Here: **`CovType × ratingregion × MAIN_OPGROUP`** = coverage type × rating region × industry group. Every rate, count, and verdict is computed per segment. |
| **CovType (coverage type)** | What the policy insures. Two values in the book: **`COVCP`** (commercial property) and **`COVCL`** (commercial liability/casualty). The model treats both symmetrically — it is **not** property-only. |
| **Exposure** | How much business is at risk of producing a loss, measured here by **earned premium** (premium earned over the period). Alternatives the code supports: **TIV** (Total Insured Value) or **earned exposure units**. It is the denominator of the rate — at a fixed rate, doubling a segment's exposure doubles its expected large-loss count. |
| **Premium** | The money charged for the coverage. Used here both as the **exposure lens** (denominator of the rate) and as the thing Step 2 projects to a full year. |
| **Frequency rate** | Expected number of large losses **per $1 of exposure**. Multiply by premium → an expected **count**. Often shown "per $1M" for readability. |
| **GLM (Generalized Linear Model)** | A regression that predicts counts. We use a **Poisson** GLM with a **log link** and an **offset** — the standard actuarial way to model "counts per unit of exposure". |
| **Offset** | A predictor forced into the model with coefficient 1. Putting `log(exposure)` in as an offset makes the model predict a **rate per unit exposure** instead of a raw count. |
| **On-leveling / year effect** | A `year` term in the GLM that absorbs year-to-year shifts (inflation, mix, reporting) so the rate reflects a common reference year rather than being skewed by one bad year. |
| **Credibility** | How much to trust a segment's **own** thin history vs. a broader average. `Z` (0–1) is the weight on the segment's own data; `1 − Z` leans on a **complement** (its industry, then the whole portfolio). Thin data → low `Z` → shrink toward the parent. |
| **Complement** | The broader average a thin segment borrows from. Always the **same-industry** parent first (never an unrelated book) — ASOP 25 discipline. |
| **Development / immaturity** | Claims take time to be reported and to have their cost recognized. A recent ("immature") year shows **fewer** large losses than it eventually will. |
| **Ladder (development pattern)** | The schedule of **what % of a year's ultimate large losses have emerged by each age** (0, 12, 24… months). Built from historical triangles. |
| **Band** | An **empirical** range of "normal" counts for a year at a given age, measured from recent history. Actual above the band = **ALARM**; below = **LOW**; inside = **OK**. |
| **Triangle** | The classic actuarial table: accident years down the rows, development age across the columns, counts in the cells. Only the lower-left (already observed) is filled. |
| **Dispersion (φ)** | A check on the Poisson assumption. φ ≈ 1 means Poisson fits; φ > 1.5 means counts are more variable than Poisson and we widen bands (Negative Binomial). |

---

# Part 2 — The mechanics

*Everything below is the full technical reference: the architecture, the equations, each
step in detail, validation, and how to run it. Part 1 above is enough to understand the
system; Part 2 is what you read to work on it.*

## Why two methods? (Property is fast, liability is slow)

Large losses do not all show up on the same clock.

```
        % of a year's ultimate LARGE LOSSES visible, by months of age
        0mo      12mo     24mo     36mo     48mo     60mo    ultimate
PROPERTY (COVCP)   ~fast:  most of the year's large losses are known within months.
                   A current-year count is meaningful almost immediately.

LIABILITY (COVCL)  ~slow:  10.7%    30.2%    51.0%    67.6%    81.6%    92.6%   100%
                   Only ~1 in 9 large losses is visible at age 0.
```

If you scored a fresh **liability** year the way you score property — comparing its
tiny year-to-date count against a **full-year** expectation — every young year would be
scored **LOW / under target** purely because the claims have not been reported yet. That
is a false LOW on every immature year.

So the pipeline splits:

- **Property / mixed book (Steps 1–4)** — reports fast enough to score a year against a
  full-year expected count directly. This is the main chain.
- **Liability (Step 5)** — reports slowly, so it gets a dedicated method that first asks
  *"how far along is this year?"* (the ladder), discounts the expectation to that age, and
  compares the actual-so-far to an **empirical band** rather than a single number. It even
  decides whether the year is simply **TOO EARLY** to judge on the low side.

Both tracks share the same statistical basis (a Poisson-style rate plus Bühlmann
credibility), but Step 5 **re-implements** it standalone on its own dataset so the
liability track never depends on the property chain.

---

## Corrected architecture & data flow

```
 PROPERTY / MIXED-BOOK CHAIN
 source: data/basic_data_1.csv   (~2.88M policy-coverage rows, 2021–2025, ~573 MB)
 ─────────────────────────────────────────────────────────────────────────────────

   ┌─────────────────────┐   writes    ┌───────────────────────────┐
   │  step_1_frequency   │ ──────────► │   rate_table_final.csv    │  ← FROZEN deliverable
   │  Poisson GLM +      │             │  final_rate per segment    │    (296 segments)
   │  Bühlmann credibility│            └────────────┬──────────────┘
   │  segment =                                     │
   │  CovType×region×industry                       │  glob: outputs/**/rate_table_final.csv
   └─────────────────────┘                          │  (newest by mtime wins)
                                                     │
   ┌─────────────────────┐                          ├───────────────┬──────────────────┐
   │  step_2_premium     │  rebuilt on-demand       ▼               ▼                  │
   │  per-segment growth │  by steps 3 & 4   ┌──────────────┐ ┌──────────────────────┐ │
   │  factor → full-year │ ───────────────► │  step_3_     │ │  step_4_             │ │
   │  premium projection │                  │  expected_   │ │  segment_analysis    │ │
   │  (needs nothing     │                  │  vs_actual   │ │  4 lenses + dossiers │ │
   │   upstream)         │                  │ board verdict│ │  "where do we act?"  │ │
   └─────────────────────┘                  └──────────────┘ └──────────────────────┘ │
                                             reuses step1+step2 cfg   reuses step1+step2 cfg
                                             ▲───────────────────────────────────────────┘
                                             both are PARALLEL consumers of Step 1
                                             (Step 4 is NOT downstream of Step 3)


 LIABILITY TRACK — SEPARATE · PARALLEL · SELF-CONTAINED
 source: data/liability_data_10_yrs.csv   (its OWN file, 2016–2025, 10 accident years)
 ─────────────────────────────────────────────────────────────────────────────────

   ┌────────────────────────────────────────────────────────────────────┐
   │  step_5_liability_development                                        │
   │  filters CovType == "COVCL"  (liability only)                        │
   │  segment = ratingregion × MAIN_OPGROUP   (CovType fixed, NOT a key)  │
   │  triangle → recent-weighted ladder → credibilised exposure rate      │
   │           → empirical band (5-method comparison) → verdict + 2 backtests│
   │                                                                      │
   │  ── reads NO rate_table_final.csv.  Reads NO Step 1/2/3/4 output. ── │
   │  ── re-implements the credibility logic locally so it stands alone.──│
   └────────────────────────────────────────────────────────────────────┘

     THERE IS NO ARROW FROM rate_table_final.csv TO STEP 5. That edge does not exist.
```

**Who reads the rate table?** Only **Step 3** and **Step 4**. Step 5 does not.
**Is Step 1 property-only?** No — it models `COVCP` and `COVCL` together (`CovType` is a
segmentation key). Step 5 is the one that carves out `COVCL`, from a *different* file.

---

## The shared frequency math (Step 1's engine)

Everything downstream rests on one number per segment: **`final_rate`** = expected large
losses per $1 of exposure. It is produced in two stages.

### Stage 1 — the GLM (learn a raw rate, on-leveled for year)

```
large_loss_count  ~  C(CovType) + C(ratingregion) + C(MAIN_OPGROUP) + C(ROLLING_YEAR)
                     family = Poisson,   link = log,   offset = log(exposure)
```

- Poisson counts model; `log(exposure)` as an **offset** turns the prediction into a
  **rate per $1 of exposure**.
- `C(ROLLING_YEAR)` is the **on-leveling year effect**; rates are read out at the
  **reference year (2024)** with the offset zeroed → `glm_rate`.
- Negative Binomial is deliberately **not** fitted; instead **dispersion**
  `φ = pearson_chi² / df_resid` is reported as a Poisson-adequacy check.

### Stage 2 — hierarchical Bühlmann credibility (smooth the thin segments)

```
Z_s          = E_s / (E_s + K)
final_rate_s = Z_s · glm_rate_s  +  (1 − Z_s) · complement_s
```

- `E_s` = the segment's historical exposure; `K` = Bühlmann constant
  = `mean / between-group variance` (estimated separately at each level).
- The **complement** walks a same-industry hierarchy (ASOP 25 — never borrow from an
  unrelated book):

```
   cell (CovType×region×industry)
        └── complement = Level-1  (CovType × industry), blended toward…
                          └── Level-2 (industry), blended toward…
                                       └── portfolio rate
```

*V1 simplification (disclosed):* the between-group variance is raw exposure-weighted
without subtracting process variance — it can slightly over-credit thin segments. Flagged
as a Phase-2 Bühlmann-Straub refinement.

### WORKED EXAMPLE — a real segment (top row of `rate_table_final.csv`)

Segment **`CovType=COVCP, ratingregion=NEWOR, MAIN_OPGROUP=Restaurant`**:

| quantity | value |
|---|---|
| historical large losses | 12 |
| `glm_rate` (per $1M) | 0.6231 |
| `complement_rate` (per $1M) | 0.5186 |
| credibility `Z` | 0.4626 |
| **`final_rate` (per $1M)** | **0.567** |
| `final_rate` (per $1) | 5.6697e-07 |
| credible? (≥ 5 losses) | yes |

Check the blend:

```
0.4626 × 0.6231  +  (1 − 0.4626) × 0.5186
= 0.2882          +  0.2787
= 0.5669  ≈  0.567   ✓
```

> Note: `rate_table_final.csv` carries `Z`, `glm_rate`, `complement_rate`, `final_rate`
> (and per-1M / `credible` / `hist_large_losses`) — it does **not** carry an exposure column.

---

## Step 1 — Frequency calibration

**Folder:** `src/step_1_frequency/` · **Config:** `src/config/config.yaml` · **Entry:** `pipeline.py:main`

**What it does.** Turns the raw policy extract into the frozen per-segment `final_rate`.
Pipeline: `config → data + quality gates → segment×year panel → Poisson GLM → hierarchical
Bühlmann credibility → validation gates → write rate_table_final.csv + run_report.json`.

**Why.** Every downstream verdict is `rate × premium`. This step *is* the rate.

**Input.** `data/basic_data_1.csv` (only needed columns read). Loss = `TOTAL_COVERAGE_INCURREDLOSS_M`,
year = `ROLLING_YEAR`, exposure lens = `TOTAL_EARNED_PREMIUM`, segment keys = `CovType`,
`ratingregion`, `MAIN_OPGROUP`.

**Key config defaults.**

| Setting | Value | Note |
|---|---|---|
| `large_loss.threshold` | `200000` (`mode: fixed`) | percentile mode rejected at load |
| `calibration.experience_years` | `2021, 2022, 2023, 2024` | **2025 excluded** — counts still developing |
| `reference_year` | `2024` | last fully-developed year |
| exposure `lens` | `premium` (`TOTAL_EARNED_PREMIUM`) | alt: tiv / earned_exposure |
| `family` | `poisson`, `year_effect: true` | NB rejected at load |
| cat scope | `assume_excluded` | disclosed: cat flag is empty |
| credibility | `buhlmann_hierarchical`, `level1_keys: [CovType, MAIN_OPGROUP]` | |
| validation | **8 gates** (see below) | reconciliation = **halt**; rest = warn |

**8 validation gates:** reconciliation (1% tol, **halt**), dispersion (max 1.5), thin_segment_share
(max 90%), backtest (holdout 2024), backtest_segment (min Spearman 0.45), robustness_drop_yr
(max p95 move 40%), base_agreement (alt-lens TIV min corr 0.80), total_preservation (max drift 2.0%).

**Output** (into `outputs/annual_recalibration_2025_<timestamp>/`):
`rate_table_final.csv` (the deliverable), `run_report.json` (machine-readable audit + dispersion),
`run_summary.md`, `model_diagnostics.md`.

**WORKED NUMBERS — latest run.** 644 large losses · **296 segments** · dispersion **1.120** ·
overall **WARN** with 3 informational warnings (alt-lens exposure integrity 2.8%, total
preservation **+3.74%**, base agreement 0.565). `CovType` splits **143 `COVCP` + 153 `COVCL`**
segments — property and liability modeled together. Backtest: predicted **184** for 2024,
actual **181**. Robustness: drop newest year → p95 rate move **32.6%**, 0 segments > 50%.
**88.5%** of segments are thin (< 5 losses) and get shrunk.

---

## Step 2 — Premium projection

**Folder:** `src/step_2_premium/` · **Config:** `src/step_2_premium/config.yaml` · **Entry:** `run.py`

**What it does.** Forecasts each segment's **full-year earned premium** from the premium
visible so far this year, so a rate can become an expected count:

```
expected large losses (segment) = final_rate (segment) × projected_premium (segment)
```

**Why.** Mid-year you have only part of the premium. To judge whether large-loss counts are
on track you must first estimate the *full-year* premium each segment will end up earning.

**Input.** `data/basic_data_1.csv` — **the same extract as Step 1** (deliberate, so the
expected-loss total is self-consistent). Same segment buckets `CovType × ratingregion × MAIN_OPGROUP`.

**Method (as implemented).**

```
projected_full_year_premium = visible_premium_so_far × growth_factor(segment, run-month)

visible[seg,M]        = cumulative premium of policies started by end of month M
full[seg]             = visible[seg,12]
own_factor[seg,M]     = Σ full[seg] / Σ visible[seg,M]          (pooled across years)
portfolio_factor[M]   = Σ full(all) / Σ visible[M](all)
factor[seg,M]         = clip(own_factor, 1.0, clip_max)  if enough history
                      = portfolio_factor[M]              otherwise (thin → fallback)
```

The factor is ≥ 1 by construction (later in the year → less scale-up needed). Cancellations
are already baked into the historical earned premium — no separate term.

**Key config defaults:** `experience_years` 2021–2025 · `clip_max_factor` 5.0 ·
`min_visible_premium` 1000 · backtest `holdout_years` 2023/24/25 at `run_months` 3/6/9,
`within_pct` 10% · demo projection `year=2025, month=6`.

**WORKED EXAMPLE — real segment `COVCL × ABandT × Agriculture`, demo run 2025 @ month 6:**

| quantity | value |
|---|---|
| visible premium (through June) | 150,329 |
| growth factor (month 6, own) | 1.17283 |
| projected full-year premium | 150,329 × 1.17283 = **176,310** |
| actual full-year premium | 178,010 |
| projection error | **−1.0%** |
| → expected large losses | 176,310 × 4.83655e-07 = **0.0853** |

**Backtest (per-segment, avg over 2023/24/25 × Q1/H1/Q3):** WAPE (weighted absolute percentage error — total absolute error as a % of total premium) ≈ **2.7%**,
within ±10% ≈ **89%**, beating the single-global-factor baseline at every point; accuracy
tightens through the year (2025: Q1 6.3% → H1 2.6% → Q3 0.7% WAPE). Portfolio factors by
run-month: Apr 1.69×, Jul 1.25×, Oct 1.07×, Dec 1.00×.

**Output** (285 segments latest run, under `outputs/premium/step_2_premium_<ts>/`):
`growth_factor_table.csv` (the reusable artifact — factor per segment×month),
`projected_premium.csv`, `expected_losses.csv` (portfolio total ≈ **208** expected large
losses on ≈ 547.8M projected premium, 100% rate coverage), `report.md`.

---

## Step 3 — Expected vs Actual (the board deliverable)

**Folder:** `src/step_3_expected_vs_actual/` · **Config:** `src/step_3_expected_vs_actual/config.yaml` · **Entry:** `run.py`

**What it does.** The board-facing verdict. Multiplies Step 1's frozen rate by Step 2's
projected premium → **expected** count, compares to **actual**, and wraps it in a
percentile, a **GREEN/AMBER/RED** traffic light, a "why it moved" waterfall, an auto-written
narrative, and a walk-forward out-of-sample backtest. It is an **orchestrator** — it makes
no business choices of its own; it points at the Step 1 & Step 2 configs so the actual count
is flagged with the exact same $200K threshold / cat scope / segment keys the rates were built on.

**How it finds its inputs.** Globs `outputs/**/rate_table_final.csv` and takes the **newest
by mtime**; requires a `final_rate` column; reads Step 1's dispersion from the sibling
`run_report.json` for the confidence band. Rebuilds Step 2 in-process.

**The equation** (per segment, summed to portfolio):

```
expected_losses   = final_rate × projected_premium
expected(portfolio)= Σ expected_losses
actual            = Σ (incurred ≥ $200K) for the year
gap               = actual − expected      (run_month = 12 → full-year premium known)
```

**Percentile + traffic light.** Count ~ **Poisson(expected)**; if φ > 1.5 it widens to a
Negative Binomial (variance = φ·μ). Then `percentile = cdf(actual) × 100` (cdf = cumulative distribution function — the probability of seeing this many or fewer);
**GREEN** if percentile ∈ [25,75], else **AMBER** if ∈ [10,90], else **RED**.

**Waterfall (Laspeyres bridge)** — decomposes prior-year expected → this-year actual:

```
prior_expected + Volume + Mix + Rate = current_expected ;  + Random = actual
  Volume = premium growth at prior avg rate
  Mix    = shift toward higher/lower-frequency segments
  Rate   ≈ 0 (table frozen between recalibrations)
  Random = Poisson noise (z = random / √current_expected)
```

**Backtest (walk-forward, out-of-sample).** For each fold year, rates AND premium factors are
recalibrated **from scratch** on prior years only, then the fold year is predicted at
run-months 6 and 12. Pass = actual inside the model's 5–95% band. `2025` is projected for
context but **never scored** (reporting lag).

**WORKED EXAMPLE — real 2024 verdict:**

| quantity | value |
|---|---|
| Expected | **187.8** |
| Actual | **181** |
| Gap | −6.8 |
| Percentile | **32.7 → 33rd** |
| Normal range (5–95th) | **166 – 211** |
| Count model | Poisson (φ = 1.12 ≤ 1.5) |
| **Colour** | **GREEN** (33 ∈ [25,75]) |
| Rate coverage | 100% |

Waterfall 2023→2024: prior **168.1** + Volume **+17.9** + Mix **+1.8** + Rate **+0.0**
= expected **187.8**; + Random **−6.8** (z = −0.49) = actual **181**.

**Backtest: 4/4 in band.** 2023 m6 180.0 vs 165 (AMBER) · 2023 m12 181.9 vs 165 (AMBER) ·
2024 m6 193.7 vs 181 (AMBER) · 2024 m12 190.7 vs 181 (GREEN). Segment ρ ≈ 0.56–0.58.

**2025 watch line (not a verdict).** Full-year expected ≈ **206**, only **139 reported** —
the drop despite premium growth is the classic reporting-lag signature. Counts by year:
2021 **140** / 2022 **158** / 2023 **165** / 2024 **181** / 2025 **139 ⚠**.

**Output** (`outputs/step_3_expected_vs_actual/<run>_<date>/`): `board_report.md` (the
deliverable), `backtest_report.md`, `segment_ave.csv`, `ave_summary.csv`, `waterfall.csv`,
`narrative.txt`, `backtest.csv`, `ave_report.json`.

---

## Step 4 — Segment analysis (where do we act?)

**Folder:** `src/step_4_segment_analysis/` · **Config:** `src/step_4_segment_analysis/config.yaml` · **Entry:** `run.py`

**What it does.** Takes the **shipped rates** × **each year's premium** and compares expected
vs actual **per segment** — no new model, just diagnostic lenses. Step 3 says the *total* is
trusted; Step 4 says *where* to focus. It resolves the same rate table (newest by mtime),
rebuilds Step 2 in-process, and flags actuals with the identical $200K / cat / key rules.

**The four lenses (run on anchor year 2024, 2022–2024 for trend):**

1. **Concentration** — rank segments by `expected = final_rate × premium`; report each
   segment's share and the cumulative curve (top-5, top-10, how many cover 80%).
2. **Accuracy** — among material segments (`expected ≥ 1.0`), the biggest under-rated
   (positive gap) and over-rated (negative gap) misses; tag **structural** (same-sign miss in
   most tracked years) vs **noise**. Also the portfolio **Spearman ρ** (rank correlation of expected vs actual; +1 = perfect ordering).
3. **Drift / emerging risk** — for segments with ≥ 5 historical losses, recent O/E
   = (act₂₃+act₂₄)/(exp₂₃+exp₂₄); **HOT** if ≥ 1.25, **COLD** if ≤ 0.75.
4. **Confidence** — split expected loss into **credible** vs **thin**; report the % sitting on
   credible rates and the "big bets on thin data".

**Fifth layer — Significance / investigation** (`investigate.py`): Poisson tail probabilities
per material segment (`signal` if min tail p < 0.05), a **portfolio calibration check** (how
many segments land outside the band vs the ~α·n expected by chance), a per-segment
classification (UNDER-rated persistent / one-year spike / OVER-rated / noise), and written
**dossiers** on the most significant segments.

> Naming note: the code's fourth lens is **Confidence** (thin-data), and **Significance** is
> the separate investigation layer — they are not the same thing.

**WORKED NUMBERS — latest run:**
- 296 segments; **63 of 296** cover 80% of expected losses.
- **Concentration:** top-5 = **33%**, top-10 = 43%. Top 5 all Realty (COVCP·COR·Realty 16.5 exp / 8.8%, COVCP·BCMS·Realty 14.0, COVCP·NEWOR·Realty 13.3, COVCP·ABandT·Realty 12.2, COVCP·Atlantic·Realty 6.7).
- **Accuracy:** Spearman **ρ = 0.56**. Top under-rating: COVCP·ABandT·Realty (12.2→20, +7.8, noise), COVCP·COR·Retail (2.5→8, +5.5, **structural**), COVCP·COR·Realty (16.5→20, +3.5, structural).
- **Drift:** **8 segments** running hot — e.g. COVCP·ABandT·Education O/E 4.38, COVCL·QC·Contractors 2.94.
- **Confidence:** **62%** of expected loss in **34 credible** segments; **262 thin**.
- **Investigation:** of **40 material** segments, **2 sig-high / 0 sig-low** (~2 expected by chance) → **well-calibrated**. Two dossiers: **COVCP·COR·Retail** (p=0.004, 3-yr net O/E 1.96 → *UNDER-rated, persistent, investigate*) and **COVCP·ABandT·Realty** (p=0.026, net O/E 1.01 → *one-year spike, watch*).

**Output** (`outputs/step_4_segment_analysis/<run>_<ts>/`): `step_4_segment_analysis.md` (the
four lenses), `segment_investigation.md` (calibration + dossiers), `segment_master.csv`
(every segment × every metric, ~105 KB).

---

## Step 5 — Liability development (separate parallel track)

**Folder:** `src/step_5_liability_development/` · **Config:** `src/step_5_liability_development/config.yaml` · **Entry:** `run.py`

> **Self-containment (critical).** Step 5 **does NOT read `rate_table_final.csv`** — a grep
> of the whole module finds zero references. Its **only** external read is one CSV,
> `data/liability_data_10_yrs.csv`. It imports nothing from Steps 1–4 and **re-implements**
> the Bühlmann credibility logic locally so it runs standalone. There is **no `upstream:`
> block** in its config.

**What it does.** Scores the still-developing accident year for commercial **liability
(COVCL)** large losses — *"are the large losses we're seeing normal, or alarming?"* —
without the false-alarm trap of comparing a partly-emerged actual to a full-year expected.

**Input.** `data/liability_data_10_yrs.csv` (10 accident years 2016–2025), filtered to
`CovType == "COVCL"`. Segment = **`ratingregion × MAIN_OPGROUP`** (CovType is fixed, so it is
**not** a key). Null segment keys → `"UNKNOWN"` (keeps ~6% of rows / real large losses).

### (1) The triangle — large-loss policy counts by accident year × age

| year | 0 | 12 | 24 | 36 | 48 | 60 |
|---|---|---|---|---|---|---|
| 2016 | 0 | 0 | 1 | 0 | 0 | 0 |
| 2017 | 1 | 3 | 6 | 3 | 0 | 0 |
| 2018 | 8 | 13 | 20 | 15 | 11 | 17 |
| 2019 | 16 | 24 | 12 | 20 | 27 | 29 |
| 2020 | 14 | 7 | 11 | 23 | 36 | 38 |
| 2021 | 9 | 14 | 23 | 31 | 37 | — |
| 2022 | 1 | 14 | 22 | 34 | — | — |
| 2023 | 8 | 17 | 31 | — | — | — |
| 2024 | 4 | 17 | — | — | — | — |
| 2025 | 4 | — | — | — | — | — |

### (2) Recent-weighted ladder — real % developed by age

Early rungs (ages 0 and 12) are estimated from **recent years only (≥ 2021)** because
reporting has slowed; later rungs pool all years; tail factor **1.08** from age 60 to ultimate.

| age (mo) | cdf | **% developed** | source |
|---|---|---|---|
| 0 | 9.337 | **10.7%** | recent |
| 12 | 3.313 | **30.2%** | recent |
| 24 | 1.962 | **51.0%** | pooled |
| 36 | 1.479 | **67.6%** | pooled |
| 48 | 1.226 | **81.6%** | pooled |
| 60 | 1.080 | **92.6%** | pooled (tail 1.08) |

Recent-weighting pulls age-0 down from a pooled ~21% to **10.7%** and age-12 from ~37% to
**30.2%**, so a fresh year is not over-expected (which would score it **LOW**).

### (3) Credibilised exposure rate

`cell rate = developed losses ÷ earned exposure` (frequency per $ exposure), with the **same**
two-level Bühlmann shrinkage as Step 1 (industry → portfolio, same-industry complement).
Counts are grossed to ultimate first (`dev_count = raw_count × cdf`) so immaturity does not
bias the rate low. Calibration years **2019–2022** only (excludes tiny 2018, too-green
2023/24/25). Readable figure ≈ **0.38 large losses per $M premium** (premium is
readability-only; the true basis is per-exposure, e.g. `final_rate` ≈ 8.6e-05 per $).

### (4) Expected-by-now

```
expected_full   = Σ_cells ( final_rate_cell × exposure_cell )   # the LEVEL, known day one
expected_by_now = expected_full × %developed(age)               # discount to the year's age
```

The current year is **never** projected off its own tiny count; the ladder only discounts the
rate-based expectation down to the year's age.

### (5) Empirical band + 5-method comparison

The band **is** the alarm — measured from the recent history of the count at that age (per $M
exposure, last 5 years) scaled to the score year's exposure. A walk-forward comparison over
**27 held-out cells** (nominal 80% coverage) compares five band-construction methods:

| method | coverage | false-alarm | **false-ALARM** (high side) | rel_width | fit_score |
|---|---|---|---|---|---|
| **percentile** | 85.2% | 14.8% | 3.7% | 1.46 | **0.271** ← best fit_score |
| min_max | 88.9% | 11.1% | 0.0% | 1.86 | 0.368 |
| **hybrid** *(ships)* | 88.9% | 11.1% | **0.0%** | 1.91 | 0.375 |
| std (±2σ) | 96.3% | 3.7% | 0.0% | 2.64 | 0.559 |
| poisson | 29.6% | 70.4% | 22.2% | 0.57 | 0.590 |

**The honest note.** `percentile` **wins** the measurable `fit_score` (0.271, lower = better),
but **`hybrid` ships**. Why: `fit_score = |coverage − nominal| + 0.15 × rel_width` is
*transparent but deliberately incomplete* — it scores only calibration + tightness, the two
things measurable on this short history. It **excludes** the two things that justify hybrid:
(a) the **false-ALARM rate** (hybrid = 0%, i.e. it never falsely fires ALARM on a normal year), and
(b) **extrapolation / small-n robustness** (percentile cannot produce a value beyond its
historical range and its coverage swings 63%→85% across 3–5-year windows). So `fit_score`
**ranks** the methods but does not **select** — the choice is a documented judgment call.
`poisson` is disqualified outright (fires on ~70% of normal cells). The method is
config-swappable (`band_method`) with no code change.

### (6) Band-driven verdict logic

```
if   actual > band_hi                     -> ALARM       # upper side works at ANY age
elif actual < band_lo                     -> LOW
elif band_lo <= too_early_lo_floor (=1)   -> TOO EARLY   # a low year is indistinguishable
else                                      -> OK          #   from early-reporting noise
```

The LOW side is only trusted when the band floor sits materially above zero; otherwise the
year is **TOO EARLY** to judge low — but **ALARM still fires** at any age.

**Two worked verdicts (real `verdict.csv`):**

| year | age | %dev | exp_full | exp_now | band [lo–hi] | actual | verdict |
|---|---|---|---|---|---|---|---|
| **2024** | 12 | 30.2% | 56.0 | 16.9 | **[7 – 35]** (ctr 20.0) | **17** | **OK** |
| **2025** | 0 | 10.7% | 60.4 | 6.5 | **[1 – 20]** (ctr 9.3) | **4** | **TOO EARLY** |

- **2024:** floor 7 > 1, so a real low/high call is possible; actual 17 ∈ [7,35] → **OK**.
- **2025:** floor = 1 ≤ 1, so only a blow-up (actual > 20) could fire; actual 4 → **TOO EARLY**.

### (7) Two backtests (don't conflate them)

- **A — rate stability** (leave-one-year-out; the shared ladder cancels, so this isolates the
  **rate**): errors +16.8% / +4.8% / −4.1% / −11.6% for 2019–2022 → **mean |error| ≈ 9.3%**.
  The rate is stable across years.
- **B — the ladder itself** (leave-one-year-out emergence; error does **not** cancel — the
  honest test): mean |error| ≈ **119%** from age 0, **~103%** from age 12, **~86%** from age 24,
  **~31%** from age 36. Young-age projection is unreliable — exactly why the band widens and
  the TOO EARLY gate exists.

### (8) Reporting-drift finding

Reporting speed has **slowed over the decade**: age-0 large losses per $M fell from ~35 (2018)
to ~4–9 (2024), visible in the triangle's age-0 column. Pooled early ladder factors are
therefore stale and over-expect a fresh year — which is why ages 0 and 12 are recent-weighted
(≥ 2021) while stable later rungs stay pooled. A second drift source: the **fixed $200K
threshold** under claim inflation slowly lets more claims cross a static line over time
(consider indexing).

**Output** (`outputs/step_5_liability_development/<run>_<ts>/`): `triangle.csv`, `ladder.csv`,
`segment_rates.csv`, `band_shootout.csv`, `band_shootout_cells.csv`, `verdict.csv`,
`backtest_rate.csv`, `backtest_ladder.csv`.

**Production wiring (planned, not yet built).** The liability rate is meant to eventually fold
into `step_1_frequency` and have its verdict merged with property in
`step_3_expected_vs_actual`. That merge is still **Open** (`DECISIONS.md`).

---

## Validation & honest limits

**What the numbers say works:**

| Check | Result |
|---|---|
| Step 1 dispersion (Poisson adequacy) | **1.12** (≈ 1 → Poisson fine) |
| Step 1 holdout backtest (2024) | predicted **184** vs actual **181** |
| Step 1 robustness (drop newest year) | p95 rate move **32.6%**, 0 segments > 50% |
| Step 2 premium projection | WAPE ≈ **2.7%**, **89%** within ±10% |
| Step 3 walk-forward OOS | **4/4** folds inside 5–95% band |
| Step 5 rate stability (backtest A) | mean |error| ≈ **9.3%** |

**Genuine limits (stated plainly):**

- **The young-year low side is unknowable.** Step 5 backtest B shows ~119% error projecting
  from age 0. That is why the band is wide early and why **TOO EARLY** exists — we can catch a
  blow-up at any age, but we cannot responsibly call a *low* liability year that is only
  10.7% developed.
- **Tail factor is an assumption.** The 1.08 factor from age 60 to ultimate is judgment, not
  data.
- **Fixed $200K threshold drifts under inflation.** A static dollar line lets more claims
  cross it over time; consider indexing the threshold.
- **Grain = a policy, not a claim.** A "large loss" is a *policy* whose **aggregate** incurred
  ≥ $200K, not a single large claim.
- **Rate basis is exposure, not premium.** Any "per $M premium" figure is for readability; the
  real denominator is earned exposure.
- **Credibility V1 simplification.** Between-group variance is raw (no process-variance
  subtraction) — can slightly over-credit thin segments; Phase-2 Bühlmann-Straub refinement flagged.
- **Cat scope assumed excluded.** The catastrophe flag in the extract is empty, so the book is
  treated as non-cat — disclosed, not verified.

---

## How to run (in order)

Each step resolves the **newest** `rate_table_final.csv` by modification time, so run Step 1
first if you want the rest to see a fresh rate table. Steps 3 and 4 rebuild Step 2 in-process,
so Step 2 need not be run separately for them. Step 5 is standalone.

```bash
# 1. Frequency calibration  →  rate_table_final.csv   (reads data/basic_data_1.csv)
python src/run.py --config src/config/config.yaml

# 2. Premium projection      (reads data/basic_data_1.csv; standalone)
python src/step_2_premium/run.py --config src/step_2_premium/config.yaml

# 3. Board verdict           (reads newest rate table + rebuilds Step 2)
python src/step_3_expected_vs_actual/run.py --config src/step_3_expected_vs_actual/config.yaml

# 4. Segment analysis        (reads newest rate table + rebuilds Step 2)
python src/step_4_segment_analysis/run.py --config src/step_4_segment_analysis/config.yaml

# 5. Liability development    (SEPARATE track; reads data/liability_data_10_yrs.csv ONLY)
python src/step_5_liability_development/run.py --config src/step_5_liability_development/config.yaml
```

**Data files:**

| File | Used by | Notes |
|---|---|---|
| `data/basic_data_1.csv` | Steps 1–4 | ~2.88M rows, 2021–2025, ~573 MB, read once (~1 min) |
| `data/liability_data_10_yrs.csv` | Step 5 only | 10 accident years 2016–2025 |

---

## Repo map

| Path | Role |
|---|---|
| `src/step_1_frequency/` | Poisson GLM + Bühlmann credibility → `rate_table_final.csv` |
| `src/step_2_premium/` | per-segment growth factor → full-year premium projection |
| `src/step_3_expected_vs_actual/` | board verdict: rate × premium vs actual (GREEN/AMBER/RED) |
| `src/step_4_segment_analysis/` | four lenses + significance dossiers (where to act) |
| `src/step_5_liability_development/` | **separate** liability track: ladder + band + verdict |
| `src/config/config.yaml` | Step 1 master config (threshold, years, lens, credibility, 8 gates) |
| `src/config/config_tiv.yaml` | alternate Step 1 config using the TIV exposure lens |
| `src/docs/DECISIONS.md` | every modeling decision across all 5 steps |
| `data/basic_data_1.csv` | source extract for the property/mixed chain (Steps 1–4) |
| `data/liability_data_10_yrs.csv` | source extract for the liability track (Step 5) |
| `outputs/` | timestamped run folders for each step |

---

## Outputs at a glance

| Step | Key output | The one number |
|---|---|---|
| 1 | `rate_table_final.csv` | `final_rate` per segment (e.g. 0.567 /$M for COVCP·NEWOR·Restaurant) |
| 2 | `growth_factor_table.csv`, `expected_losses.csv` | portfolio expected ≈ 208 large losses |
| 3 | `board_report.md` | 2024: **187.8 expected / 181 actual / 33rd pct / GREEN** |
| 4 | `segment_master.csv`, `segment_investigation.md` | top-5 = 33% of expected; 2 UNDER-rated signals |
| 5 | `verdict.csv` | 2024 → **OK** [7–35]; 2025 → **TOO EARLY** [1–20] |
