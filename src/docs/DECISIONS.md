# Modeling Decisions &amp; Rationale

> **Purpose.** Record every load-bearing decision in the large-loss frequency model —
> *what* we chose, *why*, *what we rejected*, and the *evidence* — so the segment rates
> are defensible, the reasoning is transparent, and the next engineer understands the
> "why" behind the code. This is the due-diligence trail behind `rate_table_final.csv`.
>
> Framing note: the early work was an honest *exploration* (exploration is supposed to
> try things that don't pan out). This document is depersonalised on purpose — it
> records what the evidence supported, not who tried what.

---

## At a glance

| # | Decision | We chose | Because (one line) |
|---|---|---|---|
| D1 | Scope | Frequency, not severity | The business question is "was this *count* expected?"; severity is a later phase. |
| D2 | Large-loss threshold | **$200,000 fixed** | The risk-tolerance definition — aligned across pricing/risk/reporting; a data-derived line drifts. |
| D3 | Segmentation | Coverage × Region × Industry | The dimensions that drive large-loss propensity and are populated. |
| D4 | Rate-inflation fix | **GLM with a year effect** | On-levels premium automatically; the missing piece in the first attempt. |
| D5 | Reference year | **2024** (last developed) | The newest year is still maturing and would understate the rate. |
| D6 | Exposure lens | **Premium** primary, TIV cross-check | Premium is complete, pricing-aligned, and far more stable than TIV. |
| D7 | Distribution | **Poisson** (not Negative Binomial) | Once industry is in the model, the data is ~equidispersed (1.15). |
| D8 | Thin segments | **Hierarchical Bühlmann credibility** | 86% of segments are too thin to trust raw; shrink to same-industry. |
| D9 | Count grain | Coverage-row over threshold | Differs from event-count by ~1%; documented, not hidden. |
| D10 | Catastrophe scope | **Assume excluded** | The cat flag is empty in this extract; the assumption is disclosed. |

---

## The decisions in detail

### D1 — Frequency, not severity
**Context.** Large losses are reported, but there's no yardstick for whether a count
was expected. **Decision.** Model the *frequency* (count) of large losses; treat
severity as a complementary later phase. **Why.** The business's stated need is to tell
"normal tail volatility" from "structural change" — that's a question about *how often*,
and a frequency model answers it with a point estimate + a distribution. **Evidence.**
Matches the project's guiding principles ("frequency first; explainability over
sophistication").

### D2 — Threshold = $200,000 (fixed dollar amount)
**Decision.** A large loss is any incurred loss ≥ **$200,000**, a fixed dollar line.
**Why.** It is the definition the business already uses (the risk-tolerance model),
so the model aligns across pricing, risk appetite, and reporting — a core principle.
**Alternative rejected — a data-derived percentile** (e.g. "top 5% of losses each
year"). **Why rejected:** it *drifts every refresh* — the 95th percentile of yearly
losses ranges **$194K–$249K** across 2021–2025. A definition that moves 28% with the
data isn't a definition. The threshold is a business dial; the model runs at any value
(sensitivity available at $250K/$500K/$1M).

### D3 — Segmentation = Coverage × Region × Industry
**Decision.** Segment on `CovType × ratingregion × MAIN_OPGROUP` (~300 segments).
**Why.** These are the dimensions that plausibly drive large-loss propensity *and* are
populated in the data. **Evidence.** Industry is by far the strongest driver — two
industry groups (Realty + Contractors) account for ~52% of all large losses, and adding
industry to the model roughly halves the residual over-dispersion. Region, by contrast,
turns out to be weak (its coefficients are insignificant and adding it slightly *raises*
AIC) — the model surfaces this honestly in `model_diagnostics.md` rather than hiding it.
Blank regions are bucketed to "Unknown" (never dropped), so no loss vanishes on a
missing label.

### D4 — Rate-inflation fix = a year fixed effect (on-levelling)
**Context.** Premium grows year-over-year partly from *rate changes* (we charge more),
not just more risk. So "losses ÷ premium" can *fall* even when risk is flat — a "fake
improving frequency." **Decision.** Put a **year effect** (`C(ROLLING_YEAR)`) in the GLM;
read segment rates at one reference year. **Why.** The year dials absorb year-wide
price/inflation shifts, leaving clean, on-levelled segment rates — closely analogous to
manually on-levelling premium, but learned from the data with no rate-change table.
**Alternative rejected — no year term** (pool years naively). **Why rejected:** it bakes
the rate-inflation drift into the rate. This was the single most consequential gap in the
first attempt: the year column was used to split rows but never entered the model, so the
on-levelling never happened.

### D5 — Reference year = 2024 (the last fully-developed year)
**Context.** Large losses are reported and reserved over time (development / IBNR), so the
newest year's count is always incomplete. **Decision.** Fit on all years (2021–2025) but
read the rate at **2024**. **Why.** Anchoring to a still-maturing year would understate
the rate. **Evidence.** The newest year's large-loss count is ~20–25% below the prior year
at *every* threshold (the signature of immaturity, not a quiet year). Recorded each run in
`run_report.json` → `maturity_evidence`. **Caveat / open item:** we *infer* immaturity from
the count drop; confirming it would need valuation/claim-development data not in this
extract.

### D6 — Exposure lens = premium (primary), TIV (cross-check)
**Decision.** Calibrate the production rate on **earned premium**; also produce a **TIV**
rate as a deliberately different cross-check. **Why premium.** It is present on ~99% of
rows, aligns with pricing (the rate is a loss-ratio-flavoured quantity that feeds
pricing), and is on-levelled by the year effect. **Why keep TIV.** It answers a different
question (hazard per dollar of asset value) and a stakeholder asked to try it.
**Evidence that they are *not* interchangeable** (so premium is the right primary):
TIV is less complete (285 vs 299 segments), more over-dispersed (1.46 vs 1.15), and far
less stable (dropping a year moves up to 78% of TIV rates vs ≤29% for premium; 49
segments swing >50% vs 0). The two lenses rank segments only moderately alike (Spearman
0.63) — a **structural** difference, surfaced by the `base_agreement` gate. Where they
disagree most is itself a useful signal (price out of step with asset value).

### D7 — Distribution = Poisson (not Negative Binomial)
**Decision.** Fit a **Poisson** GLM. **Why.** After segmenting by industry, the data is
~equidispersed — the dispersion ratio is **1.15** (≈1), so plain Poisson is adequate and
more explainable. **Alternative rejected — Negative Binomial via the GLM family default.**
**Why rejected:** in `statsmodels`' GLM, the NB dispersion parameter (`alpha`) is held
*fixed* at a default rather than estimated — so an "NB" fit that way answers "how good is
NB at an arbitrary dispersion?", not a fair comparison. The first attempt's NB models had
this trap. The config now *rejects* `family: negative_binomial` at load (rather than
silently fitting a mis-specified NB); the dispersion gate flags if NB ever becomes
warranted.

### D8 — Thin segments = hierarchical Bühlmann credibility
**Context.** Large losses are rare, so most segments have very little data. **Decision.**
Shrink each segment's GLM rate toward a **same-industry** complement, weighted by Bühlmann
credibility `Z = E / (E + K)`. **Why.** **86%** of segments have fewer than 5 historical
large losses — their raw rates are noise. Without this, the model's "highest-risk"
segments were *zero-loss* Fishing cells (a single stray loss in the small Fishing book
inflated the whole industry). Credibility collapses those to ~the industry average while
data-rich segments keep their own rate, and the portfolio total moves only +0.43%.
**Standard.** Same-industry shrinkage (not toward an unrelated portfolio average) follows
ASOP 25. **Open item:** the `K` estimator uses a documented V1 simplification (it does not
subtract process variance from the between-segment variance); small at dispersion ≈ 1,
flagged for a formal credibility-theory review.

### D9 — Count grain = coverage-row over threshold
**Decision.** Count a "large loss" as a coverage record whose incurred ≥ threshold.
**Why.** It is simple and, here, ≈ the distinct-event count. **Evidence.** 783
coverage-rows collapse to 777 distinct policy-periods (a ~1% difference) — documented by
the `count_grain` gate. If event-count were required, a claim/event ID and a dedup rule
would be needed; that's a documented assumption, not a silent choice.

### D10 — Catastrophe scope = assume excluded
**Decision.** Treat the book as already non-catastrophe (`cat_scope: assume_excluded`).
**Why.** Catastrophe losses (e.g. one hailstorm) shouldn't drive a "how often does this
*normally* happen" rate, but the catastrophe flag is **100% empty** in this extract, so we
cannot filter them. **How handled.** The assumption is *disclosed* in every run report
(the `cat_scope` gate), not hidden. If a usable cat flag is supplied, `exclude_flagged`
mode filters them; if "all-in" is intended, that is set and disclosed too. **Open item:**
raise the empty cat flag with the data owner.

---

## The earlier exploration — and why we don't advocate those models

The first pass was a 12-model scan varying the exposure base (TIV / premium /
earned-exposure) and the distribution (Poisson / Negative Binomial). It was a reasonable
*exploration* — trying multiple exposure bases is exactly how we later discovered that
rate changes are small in this book. But none of the 12 are a defensible *production*
model, for concrete reasons:

| Issue in the exploration | Why it's a problem | How this model fixes it |
|---|---|---|
| **No year effect** (year was a grouping key, never a model term) | Leaves the rate-inflation trap uncorrected — premium-based rates drift | D4: year fixed effect (on-levelling) |
| **Ranked models by AIC across different aggregations** (60-row vs 1,299-row models) | AIC is only comparable on the *same* data; the smaller table always "wins" for the wrong reason | D7 + `model_diagnostics.md` §3 demonstrates the *valid* nested-AIC use |
| **Negative Binomial with a fixed `alpha`** | Not a fair Poisson-vs-NB comparison; deviance not comparable across families | D7: Poisson, with NB rejected-at-load |
| **Losses silently dropped on a blank key** (671 vs 675) | Real losses vanish from the analysis | D3: blanks bucketed to "Unknown" |
| **Perfect separation unhandled** (zero-loss industries → −18 coefficients) | Nonsense rates with meaningless error bars | D8: credibility shrinks them; flagged in diagnostics |
| **Data-derived threshold** (~$230K, one year) | Drifts every refresh; not business-aligned | D2: fixed $200K |
| **No credibility, no out-of-sample test** | Thin-segment noise reaches the output; no proof it generalises | D8 + the backtest gates |

The honest summary: the exploration pointed the way (especially the multi-lens
comparison), but it stopped at "explore," and its headline metric (AIC) couldn't carry the
weight placed on it. The current model is what that exploration *implied*: one lens, a year
effect, plain Poisson, full segmentation, credibility, and validation gates.

---

## Due diligence — what we validated

Every run records these (in `run_summary.md` / `run_report.json`), so the rate table is
backed by evidence, not assertion:

- **Reconciliation** — the fitted total equals the actual total (a wiring check).
- **Out-of-sample backtest** — train on 2021–23, predict 2024: **184 vs 181**, inside the
  normal range. The model predicts a year it never saw.
- **Segment-level backtest** — checks the *segments* (not just the total) are ranked
  sensibly out-of-sample.
- **Dispersion 1.15** — Poisson's assumption holds; no fancier model needed.
- **Robustness** — dropping the newest year barely moves the final rates.
- **Total preservation** — credibility redistributes risk without moving the total (+0.43%).
- **Base agreement** — premium vs TIV compared every run; the divergence is understood and
  documented, not ignored.

**What this means for the rate table.** Each `final_rate` is a GLM relativity (the
defensible part of the signal), on-levelled by the year effect, then credibility-weighted
toward its industry so thin segments can't inject noise — and the whole thing reproduces a
held-out year. That is why we present the segment rates as trustworthy, with the residual
open items (maturity confirmation, the `K` refinement, the cat flag) listed honestly above.

---

## Step 2 — premium projection (decisions)

### S2.1 — Project premium per segment by a growth factor, not a regression
**Decision.** `projected full-year premium = visible premium × growth factor`, where the
factor = `full-year ÷ visible-by-run-month`, learned per segment from history.
**Why.** Earned premium is largely an accounting quantity (the in-force book earns forward
from its dates); only the not-yet-written new business is uncertain, and the growth factor
captures it empirically. **Alternative rejected — a multi-feature OLS regression.** On a
held-out year it was off ~167% *per segment* (a global dollar-scale fit dominated by the
biggest segments), while a simple per-segment factor was ~2.7% — so the regression added
negative value over a transparent factor.

### S2.2 — Per-segment factor, but NO credibility shrinkage
**Decision.** Use each segment's own growth factor (lightly clipped); do **not** shrink it
toward the portfolio. **Why.** Unlike rare large losses (Step 1), premium is *dense* — even
a small segment has thousands of premium dollars, so its own ratio is well-measured. The
backtest confirmed raw per-segment beats credibility-shrunk here. (The opposite of Step 1 —
the backtest decided, not a copied recipe.)

### S2.3 — The growth factor is run-month-specific
**Decision.** Calibrate (and store) a factor per **(segment × month)**. **Why.** The later
in the year you run, the more business is already visible, so the smaller the scale-up
(portfolio: Feb ≈ 1.7×, Apr ≈ 1.4×, Jul ≈ 1.1×, Oct ≈ 1.0×). Cancellations are already
netted into the historical factor, so no separate cancellation term is added.

### S2.4 — Data basis: both steps run on `data_1` (the OG extract)
**Decision.** Calibrate the rate (Step 1) and project premium (Step 2) on the **same file,
`data_1`**, so `expected = rate × premium` is self-consistent. Step 2 reads policy dates
from `data_1`'s `FROM_DT`/`TO_DT` (validated: ~2.7% backtest WAPE, sane month curve).
**Why this matters.** `data_2` (the newer extract with true policy dates) is **a different
dataset**: for the same 205,128 policies it carries ~5% more premium and **~2× the large
losses** (1,487 vs 783 ≥ \$200K). Mixing files (rate from one, premium from the other) would
silently inherit those differences. **Open item for the data owner:** explain the 2× loss
gap between `data_1` and `data_2` before `data_2` is used as a loss/rate basis. Both steps
have a `data_2` config variant for when that is resolved.

### Two hard requirements for `expected = rate × premium`
1. **Same segment definition** — both tables must use the same buckets (the 6 grouped
   rating regions). `data_2`'s province codes are collapsed via a config `region_map`,
   verified by a premium-share match.
2. **Same data extract** — or the expected-loss total inherits the files' loss/premium
   differences. The default keeps both on `data_1`.

---

## Step 3 — Expected vs Actual

### S3.1 — The verdict runs on the last fully-developed year, not the latest
**Decision.** The GREEN/AMBER/RED verdict is taken on **2024**; the most recent year
(2025) is shown only as a flagged *watch*. **Why.** Actual large-loss counts by year are
140 / 158 / 165 / 181 / **139** — 2025 *falls* despite premium growth, the signature of
reporting/development lag (claims take time to be reported and to breach $200K). Comparing
a full-year *expectation* (~200) to a partial-year *actual* (139) would manufacture a false
RED. This mirrors Step 1 reading rates at `reference_year: 2024`. **V1 limitation:** no IBNR
/ count-development factor yet (the practical guide flags it for Phase 2).

### S3.2 — Consume the frozen rate table; never re-fit
**Decision.** Step 3 reads `rate_table_final.csv` and multiplies; it does not re-run the
GLM. **Why.** The rate table changes only at the annual recalibration (Step 1). A
consequence, made explicit in the report: the attribution waterfall's **rate effect is ~0**
between recalibrations, so a year-over-year move in expected losses is volume + mix + noise.

### S3.3 — Poisson band unless Step 1's dispersion says otherwise
**Decision.** Put a **Poisson** interval around the expected count; widen to Negative
Binomial (variance = φ·μ) only if the dispersion exceeds the Step-1 gate tolerance (1.5).
**Why.** Consistency with Step 1's own standard — dispersion here is **1.15**, so plain
Poisson is adequate. The dispersion is read automatically from the rate table's
`run_report.json`, so the band tracks the model rather than a hard-coded assumption.

### S3.4 — Orchestrate the upstream configs, don't restate them
**Decision.** Step 3's config points at the Step-1 and Step-2 configs rather than
re-declaring the threshold / segments / cat-scope. **Why.** The **actual** count must be
flagged exactly as the **rates** were calibrated, or expected-vs-actual is
apples-to-oranges. Referencing one source of truth per choice makes the three steps switch
data basis together (a `config_data2.yaml` variant flips all three to `data_2`).

### S3.5 — Validate the whole chain with a walk-forward backtest, not just Step 1
**Decision.** Ship a walk-forward backtest that, for each fold year Y, recalibrates **both**
the credibilized rates (Step 1) **and** the premium growth factors (Step 2) on years `< Y`,
then predicts Y and checks the actual lands in the 5–95% band — at month 12 (rate model
alone) and month 6 (premium projected too, the live mid-year case). **Why.** Step 1 already
backtests the *rates* on one held-out year; this extends it to the *production chain* Step 3
actually runs (credibilized rates × projected premium → verdict), across multiple years, so
the claim "the system works" is out-of-sample evidence, not an in-sample fit. **Result
(data_1):** 4/4 OOS predictions in band (2023, 2024 × months 6, 12), segment rank ρ ≈ 0.57.
**Honest caveat:** thin early folds (2023 trains on two years) run slightly high but stay in
band, converging as history accrues. **2025 is not scored** — still developing (S3.1).
