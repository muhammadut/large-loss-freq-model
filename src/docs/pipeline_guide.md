# Pipeline, Code & Config Guide

> How the calibration pipeline is built, organised, and configured — written so you can
> **run it, change it, and build the prediction layer (Part 2) on top of it.** Jargon is
> explained as it appears. Pairs with `methodology.md` (the *why*) and `DECISIONS.md` (the
> decisions and what we rejected).

---

## 1. Big picture & where it stops

This pipeline turns the raw policy/loss extract into a **credibilized rate table** — one
trustworthy "large losses per $1M of exposure" number per segment. It is calibrated once
a year and then frozen.

```
INPUT   data/basic_data_1.csv  +  config.yaml
          │
          ▼   this pipeline (calibration)
   load → quality gates → panel → Poisson GLM (year effect) → credibility → validation gates
          │
          ▼
OUTPUT  outputs/<run>/rate_table_final.csv   (the deliverable)
        outputs/<run>/run_report.json        (every gate result — diff across refits)
          │
          ▼   Part 2 — YOU BUILD THIS (predictions)
   rate × projected exposure → expected count → percentile / traffic-light → board report
```

**Where it stops:** it produces **rates**, not predictions. It does *not* project future
exposure, compute an expected count for next year, or build the percentile/traffic-light.
Section 9 is your spec for that.

---

## 2. Concepts in 60 seconds

The minimum vocabulary. (Full explanations in `methodology.md`.)

| Term | One-line meaning |
|---|---|
| **Frequency** | how *often* large losses happen (this project), not severity (how big) |
| **Large loss** | any loss above a dollar line. Ours: **$200,000** |
| **Exposure / lens** | the "per what" you divide by — premium, TIV, or earned-exposure. Sets what the rate *means* |
| **Segment** | a slice of the book: Coverage × Region × Industry. ~300 of them |
| **GLM** | the model that learns a clean rate for every segment at once |
| **Offset** | the trick that pins exposure into the GLM so it returns a *rate*, not a count (`offset = log(exposure)`) |
| **Relativity** | a multiplier: how a segment differs from baseline (e.g. 2.2×) |
| **Year effect** | one dial per year that absorbs price/inflation shifts so rates come out at one consistent level ("on-levelling") |
| **Credibility / Z** | how much to trust a segment's own data (0–1); thin segments shrink toward their industry average |
| **Dispersion** | a check on the model's spread assumption. ≈1 good; high = consider a richer model |

---

## 3. How the code is organised

One small Python package, one module per pipeline stage.

```
src/
├── config/
│   ├── config.yaml            # the premium run (default)
│   ├── config_tiv.yaml        # the TIV-lens run (same, lens: tiv)
│   └── config.reference.md    # every config field documented
├── step_1_frequency/           # the package
│   ├── config.py        # load + validate config (fails loudly on bad input)
│   ├── data.py          # load, clean, cat-scope, data-quality gates
│   ├── panel.py         # build the segment × year table
│   ├── model.py         # fit the Poisson GLM, extract clean rates
│   ├── credibility.py   # shrink thin segments (Bühlmann)
│   ├── validation.py    # the 8 validation gates
│   ├── explanations.py  # plain-English text for each check (used by the reports)
│   ├── report.py        # write rate table + run summary + diagnostics
│   └── pipeline.py      # orchestrates all of the above
├── run.py               # entry point: python src/run.py --config ...
└── docs/                # documentation (this guide, DECISIONS.md, methodology, ...)
```

**Mental model:** data flows *down* the list — `data → panel → model → credibility →
validation → report` — and `pipeline.py` is the conductor that calls them in order.
`config.py` is read by all of them; nothing else holds settings.

---

## 4. How the config works

Everything tunable is in `config.yaml` — the threshold, the lens, the segments, the
experience years, the gate thresholds. **The code reads the config; you never edit code
to change a business choice.**

```yaml
large_loss:
  threshold: 200000        # the large-loss dollar line
  cat_scope: assume_excluded
exposure:
  lens: premium            # premium | tiv | earned_exposure  <-- the big switch
calibration:
  reference_year: 2024     # read rates at the last fully-developed year
  family: poisson
validation:
  dispersion: {max_ratio: 1.5, on_fail: warn}
  backtest:   {holdout_year: 2024, on_fail: warn}
```

- **Change the threshold to $500K?** Edit one line (`threshold: 500000`) and re-run. No code change.
- **Fail-fast safety:** the config *rejects* settings that aren't implemented, at load
  time, with a clear message (e.g. `family: negative_binomial` or `mode: percentile`).
  So a config can never silently run a different model than it states.
- **Two configs ship:** `config.yaml` (premium, the deliverable) and `config_tiv.yaml`
  (identical but `lens: tiv`, writing to `outputs/tiv/`). One config per run.

---

## 5. The pipeline, stage by stage

| Stage (module) | What it does |
|---|---|
| **Load & clean & quality gates** (`data.py`) | reads only the needed columns; fills blank regions with "Unknown" (no loss lost on a missing label); applies cat-scope; flags each row ≥ $200K. A "halt" gate (e.g. a missing year) stops the run here. |
| **Build the panel** (`panel.py`) | collapses 2.88M rows into one row per **segment × year** with the large-loss count and total exposure (under the chosen lens) |
| **Fit the GLM & extract rates** (`model.py`) | fits the Poisson GLM with the **year effect**, reads each segment's clean rate at the reference year, computes **dispersion** |
| **Apply credibility** (`credibility.py`) | shrinks each segment's raw rate toward its **industry** average, weighted by `Z` |
| **Validate** (`validation.py`) | runs the 8 gates, each PASS / WARN / HALT with the actual numbers |
| **Report** (`report.py`) | writes `rate_table_final.csv`, `run_summary.md`, `model_diagnostics.md`, `run_report.json` |

The model:
```
large_loss_count ~ C(CovType) + C(ratingregion) + C(MAIN_OPGROUP) + C(ROLLING_YEAR)
   family = Poisson    offset = log(exposure)    rates read at year = 2024
```

---

## 6. The lens: premium vs TIV (both are produced)

The lens is the denominator. It changes what the rate *means* and, for Part 2, **what
you must project forward.**

| | Premium (primary) | TIV (cross-check) |
|---|---|---|
| Rate means | large losses per $ **charged** | large losses per $ of **insured value** |
| Answers | a **pricing** question | a **hazard** question |
| Output file | `outputs/rate_table_final.csv` | `outputs/tiv/rate_table_final.csv` |
| Project forward in Part 2 | projected **premium** | projected **TIV** |

**Why premium is primary (real numbers):** premium is the more defensible engine —
**299 segments vs 285** (TIV is missing on ~20% of rows), **dispersion 1.15 vs 1.46**,
and far more stable — dropping the newest year moves premium's final rates ≤29% (0
segments >50%) but TIV's up to 78% (**49** segments >50%). They also rank segments
differently (Spearman **0.63**). TIV is a useful *different* view, not interchangeable.

**Units gotcha:** rates are "per $1M of exposure", so the magnitudes differ by lens — a
premium rate looks like `0.567` (per $1M premium); the same idea on TIV looks like
`0.0007` (per $1M of insured value, a much bigger denominator). Always multiply a rate by
exposure measured in the *same* lens.

---

## 7. The validation gates

Every run self-checks; results are stored in `run_report.json` so **next year's refit can
be diffed against this one** (drift detection). Each gate's plain-English meaning is in
`run_summary.md`.

**Validation gates:** `reconciliation` (wiring check, total matches), `dispersion`
(≤1.5), `thin_segment_share` (informational), `backtest` (predict a held-out year's
total), `backtest_segment` (got the segments right too), `robustness_drop_yr` (final
rates stable when newest year dropped), `total_preservation` (credibility didn't move the
total), `base_agreement` (premium vs TIV — informational).

**Data-quality gates (run first; "halt" ones stop the pipeline):** `years_present`,
`min_large_losses` (halt); `cat_scope`, `exposure_integrity[lens]` (per active **and**
alternate lens), `count_grain`.

**Reading a WARN:** WARN = "be aware," not "broken." Two WARNs are expected every run —
`base_agreement` (premium and TIV genuinely differ) and `exposure_integrity[tiv]` (the
~2.3% of losses with missing TIV). HALT is the only status that stops a run.

---

## 8. The outputs (schemas)

### `rate_table_final.csv` — the deliverable
| Column | Meaning |
|---|---|
| `CovType, ratingregion, MAIN_OPGROUP` | the segment key |
| `hist_large_losses` | large losses this segment had in the window (its data weight) |
| `Z` | credibility weight 0–1 (how much its own data was trusted) |
| `glm_rate` / `glm_rate_per_1M` | raw GLM rate (per $1 / per $1M), *before* credibility |
| `complement_rate(_per_1M)` | the industry rate it was shrunk toward |
| **`final_rate`** / `final_rate_per_1M` | **the rate to use** (per $1 / per $1M), after credibility |
| `credible` | "yes" if ≥5 historical losses, else "NO-shrink" |

Example row: `COVCP, NEWOR, Recreation, hist=6, Z=0.39, final_per_1M=0.567` → "for
Recreation property in NEWOR, expect ~0.567 large losses per $1M of premium."

### `run_report.json` — the audit trail
Config used, every gate result, the credibility diagnostics, the `maturity_evidence`
table (why 2024 is the reference year), and the `backtest_segment_deciles` calibration.
Keep these across years and **diff them** — if dispersion was 1.15 last year and 1.8 this
year, that's a flag. (`run_summary.md` is the human-readable twin; `model_diagnostics.md`
holds the classical fit stats.)

---

## 9. Building Part 2 — the prediction layer (your spec)

> **Status: built (Steps 2 + 3).** The premium projection lives in
> `src/step_2_premium/` (Step 2) and the expected-vs-actual output layer — percentile,
> traffic-light, attribution waterfall, board narrative — lives in
> `src/step_3_expected_vs_actual/` (Step 3; see its README). The spec below is the design they
> implement: the "core" and rules 1–4 are Step 2/3's contract, and "What to output" is
> exactly what Step 3 writes to `board_report.md`.

This is what consumes the rate table. The core is one multiplication; the care is in four
consistency rules.

### The core
```
expected large losses = Σ over segments [ final_rate × projected exposure ]
```
Use the `final_rate` column (per $1) × the segment's projected exposure, summed over all
segments → the portfolio expected count. Then put a Poisson range around it for the
percentile / traffic-light.

**Worked example (one segment):** Recreation/NEWOR property, `final_rate_per_1M = 0.567`,
you project $80M premium → expected ≈ `0.567 × 80 = 45` large losses for that segment. Sum
across all segments for the portfolio total.

### The four rules you must respect
1. **Lens must match** — a premium rate multiplies projected **premium**; a TIV rate
   multiplies projected **TIV**. Never cross them.
2. **Rate level must match the exposure level** — the rate is at the **2024** level.
   Multiply by exposure at a comparable level (our book's rate level is roughly flat, so
   nominal is fine; if prices move materially, on-level the projected premium first).
3. **Handle unseen segments** — a new region/industry not in the rate table has **no
   rate**. Don't crash — map it to its industry (or portfolio) complement. The calibration
   deliberately raises a clear error on unseen levels so this can't pass silently.
4. **Don't re-fit — consume the frozen table** — quarterly refreshes *read*
   `rate_table_final.csv`; they do not re-run the GLM. The rate table changes only at the
   annual recalibration.

### What to output
- Portfolio **expected count** + per-segment expected counts
- A **range** (Poisson 5th–95th; widen with the dispersion if overdispersed) and the
  **percentile** of actual
- A **traffic light** (green 25–75th, amber 10–90th, red outside) and the auto-narrative
- Later: the volume / mix / rate / random **attribution waterfall**

The methodology for these (percentile bands, attribution) is in `methodology.md` §1.4 and
§3, and the worked end-to-end example is in `practical_guide.md`.

---

## 10. How to run it

```bash
# premium (default)
python src/run.py --config src/config/config.yaml      # -> outputs/<run>/rate_table_final.csv

# TIV cross-check
python src/run.py --config src/config/config_tiv.yaml  # -> outputs/tiv/<run>/rate_table_final.csv
```
Requires Python with `pandas, numpy, scipy, statsmodels, pyyaml`. A run reads the ~600 MB
CSV once (~1 min) and writes the dated run folder.

---

## Glossary

| Term | Meaning |
|---|---|
| **Offset** | the exposure term locked into the GLM (coefficient = 1) so it models a rate, not a count |
| **Panel** | the segment × year summary table the GLM fits |
| **Year effect** | per-year dials that absorb price/inflation shifts (on-levelling) |
| **Credibility (Z)** | 0–1 weight on a segment's own data vs its industry average |
| **Complement** | the fallback rate a thin segment is shrunk toward (its industry) |
| **Dispersion** | Pearson χ²/df; ≈1 means Poisson's spread assumption holds |
| **Reference year** | the (developed) year whose level the rate is expressed at. Here 2024 |
| **Lens** | the exposure denominator (premium / TIV / earned-exposure) |
| **Gate** | a pass/fail self-check with numbers attached, recorded for refit diffing |
| **Backtest** | train on the past, predict a held-out year, check accuracy |
