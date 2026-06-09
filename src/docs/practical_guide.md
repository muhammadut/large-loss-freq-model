# Large Loss Frequency Model: Practical Implementation Guide (V1)

> **Audience:** Engineers and actuaries building the model.
> **Purpose:** End-to-end implementation specification. Every step has data schemas, code patterns, and expected outputs.
> **Scope:** Version 1 — "good estimate region without glaringly bad output." Elegance and edge-case robustness are Phase 2.
>
> **For business audience and methodology narrative**, see the Confluence page (`confluence_page.md`).

---

## Table of Contents

- [Worked Example: The Model End-to-End](#worked-example-the-model-end-to-end)
- [Core Design Decisions (V1 Scope)](#core-design-decisions-v1-scope)
0. [Setup and Dependencies](#step-0-setup-and-dependencies)
1. [Data Specification — What to Extract](#step-1-data-specification--what-to-extract)
2. [Load and Validate Data](#step-2-load-and-validate-data)
3. [Define Threshold and Filter Cat Losses](#step-3-define-threshold-and-filter-cat-losses)
4. [Aggregate Historical Data for Calibration](#step-4-aggregate-historical-data-for-calibration)
5. [Fit GLM with Year Fixed Effect (The Calibration Step)](#step-5-fit-glm-with-year-fixed-effect-the-calibration-step)
6. [Apply Hierarchical Credibility](#step-6-apply-hierarchical-credibility)
7. [Build the Rate Table](#step-7-build-the-rate-table)
8. [Project Current-Period Premium from In-Force](#step-8-project-current-period-premium-from-in-force)
9. [Calculate Expected Counts](#step-9-calculate-expected-counts)
10. [Produce the Actual vs Expected Report](#step-10-produce-the-actual-vs-expected-report)
11. [Shadow Rate Drift Monitor](#step-11-shadow-rate-drift-monitor)
12. [Build the Deviation Attribution Waterfall](#step-12-build-the-deviation-attribution-waterfall)
13. [Automate the Quarterly Refresh](#step-13-automate-the-quarterly-refresh)
14. [Annual Recalibration](#step-14-annual-recalibration)
15. [Appendix A: Full Pipeline Script](#appendix-a-full-pipeline-script)
16. [Appendix B: Data Extract SQL Templates](#appendix-b-data-extract-sql-templates)
17. [Appendix C: Test Scenarios and Expected Outputs](#appendix-c-test-scenarios-and-expected-outputs)
18. [Appendix D: Output Schemas](#appendix-d-output-schemas)

---

## Worked Example: The Model End-to-End

Before the implementation details, a concrete illustration of what the model produces. Keep this open while reading the rest of the guide — every step below corresponds to one piece of this example.

### Setup

**Portfolio:** 2 segments, 5 years of history. Projecting for 2026.

| Segment | What it is |
|---|---|
| **Segment A** | Property × Ontario |
| **Segment B** | General Liability × Ontario |

### Historical data (2021–2025)

| Year | A EP | A Losses | B EP | B Losses |
|---|---|---|---|---|
| 2021 | $100M | 4 | $100M | 6 |
| 2022 | $108M | 4 | $106M | 6 |
| 2023 | $117M | 4 | $112M | 6 |
| 2024 | $127M | 4 | $118M | 6 |
| 2025 | $137M | 4 | $125M | 6 |

Premium is rising year-over-year. Losses are flat. Naive "losses ÷ premium" per year shows a fake "improving frequency" — entirely an artifact of rate changes.

### Step-by-step outputs

| Step | Output |
|---|---|
| **1–3. Data prep + cat filter + threshold** | Losses ≥ $500K, non-cat only. 20 losses in A, 30 in B over 5 years. |
| **4. Aggregate** | Segment × Year panel ready for GLM. |
| **5. GLM with year fixed effect** | Segment rates at 2025 rate-level: **A = 0.0292 per $M, B = 0.0480 per $M**. Year effects implicitly capture the rate inflation. |
| **6. Hierarchical credibility** | With >20 losses per segment, both get Z ≈ 0.95. Rates barely move. |
| **7. Rate table** | Clean rates saved: A = 0.0295, B = 0.0482. |
| **8. Projected 2026 premium** | In-force annualized + segment trend: A = $148M, B = $133M. |
| **9. Expected counts** | A: 0.0295 × 148 = 4.4. B: 0.0482 × 133 = 6.4. **Total expected: 10.8.** |
| **10. Actual vs Expected** | Actual 2026 = 11 total. Percentile ≈ 55th. **Status: GREEN.** |
| **11. Shadow rate monitor** | Quarterly O/E tracking. No drift >20% for 2+ quarters → no alert. |
| **12. Waterfall** | Prior expected 10.0 → +Volume 0.7 → +Mix 0 → +Rate 0.1 → Current expected 10.8 → +Random 0.2 → Actual 11.0 ✓ |

### Board narrative (auto-generated)

> "Large loss count for 2026 was 11, against an expected 10.8 (55th percentile — within the normal range). The increase from the 2025 expectation of 10.0 is driven almost entirely by portfolio growth (+0.7). Mix was stable and frequency rates were flat. Random volatility (+0.2) is negligible. No structural concerns."

That's the model. The rest of the guide is the "how."

---

## Core Design Decisions (V1 Scope)

These are locked decisions for V1. Every step assumes them.

| Decision | What we chose | Why |
|---|---|---|
| **Segmentation** | Line of Business × Province | Simple, clean, no size-band boundary drift |
| **Distribution** | Poisson (NB if overdispersion detected) | Standard for count data; explainable |
| **Rate-inflation adjustment** | **GLM with year fixed effect** | Absorbs rate inflation without needing a rate-change table. Mathematically equivalent to on-leveling (Frisch-Waugh-Lovell) |
| **Exposure measure** | Earned premium (nominal) | No on-leveling needed; year FE handles it |
| **Credibility** | Hierarchical Bühlmann (Cell → LOB → Portfolio) | ASOP 25 compliant; defensible complement |
| **Large loss threshold** | Set by business (default $500K) | Aligns with pricing/risk appetite |
| **Catastrophe losses** | Filter out using cat flag | Non-cat book only; cat handled separately |
| **IBNR / development** | Assumed resolved by year-end | V1 simplification; document as limitation |
| **Renewal assumption** | 100% renewal, no mid-term cancellation | V1 simplification; document as limitation |
| **Decomposition ordering** | Sequential Laspeyres (Volume → Mix → Rate) | Standard FP&A approach, board-familiar |
| **Premium projection** | In-force annualization × segment trend (weighted blend) | Anchored to current book, captures momentum |

---

## Step 0: Setup and Dependencies

```bash
pip install pandas numpy scipy statsmodels matplotlib openpyxl pyarrow
```

```python
import pandas as pd
import numpy as np
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# Global constants — override per deployment
LARGE_LOSS_THRESHOLD = 500_000
EXPERIENCE_YEARS = list(range(2021, 2026))  # 5-year window
SEGMENT_KEYS = ["line_of_business", "province"]
CURRENT_YEAR = 2026
PRIOR_YEAR = 2025
CAT_FLAG_VALUES_TO_EXCLUDE = {"Y", True, 1, "YES"}
```

---

## Step 1: Data Specification — What to Extract

You need **three datasets** from your systems.

### 1.1 Dataset A: Loss Register (Claim-Level)

One row per large loss claim (or occurrence). Source: claims system.

**Extract rule:** All claims with `incurred_amount ≥ $250K` (pull broadly for headroom; filter to $500K later).

| Column | Type | Required | Notes |
|---|---|---|---|
| `claim_id` | str | **Yes** | Unique claim identifier |
| `occurrence_id` | str | Preferred | If multiple claimants per event |
| `policy_id` | str | **Yes** | Links to exposure record |
| `accident_date` | date | **Yes** | Determines accident year |
| `report_date` | date | Preferred | For development analysis |
| `valuation_date` | date | **Yes** | As-of date for incurred amount |
| `incurred_amount` | float | **Yes** | Paid + outstanding reserve |
| `line_of_business` | str | **Yes** | e.g., "Property", "General Liability" |
| `province` | str | **Yes** | 2-char code: ON, AB, QC, etc. |
| `cause_of_loss` | str | Preferred | For drill-down narrative |
| `catastrophe_flag` | str/bool | **Yes** | Y/N indicator for cat exclusion |

### 1.2 Dataset B: Historical Exposure Register

One row per policy per accident year. Source: policy admin / finance.

| Column | Type | Required | Notes |
|---|---|---|---|
| `policy_id` | str | **Yes** | Matches loss register |
| `accident_year` | int | **Yes** | Year exposure was earned |
| `line_of_business` | str | **Yes** | Must match loss coding |
| `province` | str | **Yes** | Must match loss coding |
| `earned_premium` | float | **Yes** | Nominal (no on-leveling required) |
| `policy_count` | float | **Yes** | Usually 1.0; fractional for mid-term |
| `effective_date` | date | Preferred | For in-force projection |
| `expiry_date` | date | Preferred | For in-force projection |

### 1.3 Dataset C: In-Force Snapshot

One row per currently-active policy at the projection run date. Source: policy admin.

| Column | Type | Required | Notes |
|---|---|---|---|
| `policy_id` | str | **Yes** | |
| `line_of_business` | str | **Yes** | |
| `province` | str | **Yes** | |
| `effective_date` | date | **Yes** | Policy start |
| `expiry_date` | date | **Yes** | Policy end |
| `written_premium` | float | **Yes** | Full-term premium |
| `term_months` | int | **Yes** | Policy term length |

### 1.4 Data Quality Gates

Before any modeling, the pipeline **must** verify:

- [ ] Every `claim.policy_id` exists in historical exposure
- [ ] LOB codes match exactly between loss and exposure data
- [ ] Province codes match exactly
- [ ] No missing accident years in the experience window
- [ ] Earned premium by year reconciles to finance reports (within 1%)
- [ ] `catastrophe_flag` is populated for all claims (not null)

**If any gate fails, halt the pipeline and flag it.** Do not produce outputs.

---

## Step 2: Load and Validate Data

```python
def load_data(loss_path, exposure_path, inforce_path=None):
    """Load datasets and run quality gates. inforce_path is optional
    (only needed for quarterly refresh, not annual recalibration)."""
    losses = pd.read_parquet(loss_path)
    exposure = pd.read_parquet(exposure_path)
    inforce = pd.read_parquet(inforce_path) if inforce_path else None

    # Derive accident_year if not present
    if "accident_year" not in losses.columns:
        losses["accident_year"] = pd.to_datetime(losses["accident_date"]).dt.year

    # Quality gates
    orphans = losses[~losses["policy_id"].isin(exposure["policy_id"])]
    assert len(orphans) == 0, f"FAIL: {len(orphans)} claims have no exposure record"

    loss_lobs = set(losses["line_of_business"].unique())
    exp_lobs = set(exposure["line_of_business"].unique())
    assert loss_lobs.issubset(exp_lobs), f"FAIL: LOB mismatch {loss_lobs - exp_lobs}"

    assert losses["catastrophe_flag"].notna().all(), "FAIL: catastrophe_flag has nulls"

    # Premium reconciliation (warning only — needs external check)
    total_ep = exposure[exposure["accident_year"].isin(EXPERIENCE_YEARS)]["earned_premium"].sum()
    print(f"OK: Data loaded. Total EP over experience window: ${total_ep:,.0f}")
    print(f"   Verify this reconciles to finance reports.")

    return losses, exposure, inforce
```

---

## Step 3: Define Threshold and Filter Cat Losses

```python
def filter_losses(losses_df, threshold=LARGE_LOSS_THRESHOLD):
    """Apply large-loss threshold and exclude catastrophe losses."""
    # Step 1: Apply threshold
    large = losses_df[losses_df["incurred_amount"] >= threshold].copy()

    # Step 2: Filter cat losses
    non_cat = large[~large["catastrophe_flag"].isin(CAT_FLAG_VALUES_TO_EXCLUDE)].copy()

    print(f"Total claims: {len(losses_df)}")
    print(f"Large (≥ ${threshold:,}): {len(large)}")
    print(f"Large + non-cat: {len(non_cat)} (excluded {len(large) - len(non_cat)} cat claims)")

    # Step 3: If occurrence_id present, aggregate to occurrence level
    if "occurrence_id" in non_cat.columns and non_cat["occurrence_id"].notna().any():
        non_cat = (
            non_cat.groupby(["occurrence_id", "accident_year", "line_of_business", "province"])
            .agg(total_incurred=("incurred_amount", "sum"))
            .reset_index()
            .rename(columns={"occurrence_id": "loss_id"})
        )
        # Re-filter at occurrence level
        non_cat = non_cat[non_cat["total_incurred"] >= threshold]
        print(f"Aggregated to occurrence level: {len(non_cat)} occurrences")
    else:
        non_cat = non_cat.rename(columns={"claim_id": "loss_id"})

    return non_cat
```

### Threshold sensitivity check (optional diagnostic)

```python
def threshold_sensitivity(losses_df, candidates=[250_000, 500_000, 1_000_000]):
    """Show large loss counts at different thresholds. Helps business pick."""
    rows = []
    for t in candidates:
        sub = losses_df[
            (losses_df["incurred_amount"] >= t)
            & (~losses_df["catastrophe_flag"].isin(CAT_FLAG_VALUES_TO_EXCLUDE))
        ]
        per_year = len(sub) / sub["accident_year"].nunique()
        rows.append({
            "threshold": f"${t:,.0f}",
            "total": len(sub),
            "avg_per_year": round(per_year, 1),
        })
    return pd.DataFrame(rows)
```

Business picks the threshold that gives 5–15+ losses per year at portfolio level.

---

## Step 4: Aggregate Historical Data for Calibration

Build a panel: one row per `(segment, accident_year)` with losses and exposure.

```python
def build_calibration_panel(losses_df, exposure_df, segment_keys=SEGMENT_KEYS,
                            experience_years=EXPERIENCE_YEARS):
    """Aggregate losses and exposure by segment × year."""
    # Aggregate losses
    loss_counts = (
        losses_df[losses_df["accident_year"].isin(experience_years)]
        .groupby(["accident_year"] + segment_keys)
        .agg(large_loss_count=("loss_id", "nunique"))
        .reset_index()
    )

    # Aggregate exposure
    exp_agg = (
        exposure_df[exposure_df["accident_year"].isin(experience_years)]
        .groupby(["accident_year"] + segment_keys)
        .agg(
            earned_premium=("earned_premium", "sum"),
            policy_count=("policy_count", "sum"),
        )
        .reset_index()
    )

    # Merge — keep all exposure rows (segments with 0 losses get count=0)
    panel = exp_agg.merge(
        loss_counts, on=["accident_year"] + segment_keys, how="left"
    )
    panel["large_loss_count"] = panel["large_loss_count"].fillna(0).astype(int)

    # Drop rows with zero exposure (can't contribute to GLM)
    panel = panel[panel["earned_premium"] > 0].copy()

    return panel
```

**Expected output schema:**

| accident_year | line_of_business | province | earned_premium | policy_count | large_loss_count |
|---|---|---|---|---|---|
| 2021 | Property | ON | 100_000_000 | 450 | 4 |
| 2021 | GL | ON | 100_000_000 | 600 | 6 |
| 2022 | Property | ON | 108_000_000 | 452 | 4 |
| ... | ... | ... | ... | ... | ... |

---

## Step 5: Fit GLM with Year Fixed Effect (The Calibration Step)

This is where the rate-inflation problem gets solved. The year fixed effect absorbs rate inflation automatically.

### The model

```
log(expected_large_losses) = β₀ + β_segment + β_LOB_year + log(earned_premium)
```

Where:
- `β_segment` = rate effect per (LOB × Province)
- `β_LOB_year` = year effect per (LOB × accident_year) — absorbs rate inflation
- `log(earned_premium)` = exposure offset

### Code

```python
def fit_frequency_glm(panel_df, segment_keys=SEGMENT_KEYS):
    """
    Fit Poisson GLM with LOB × year fixed effect to absorb rate inflation.
    Returns the model and an overdispersion diagnostic.
    The reference year (for rate extraction) is chosen in the extraction step.
    """
    df = panel_df.copy()
    df["log_exposure"] = np.log(df["earned_premium"])
    df["accident_year_str"] = df["accident_year"].astype(str)  # treat as categorical

    # Formula: LOB × Year interaction absorbs rate inflation per LOB
    # Province captures geographic variation in base rate
    formula = (
        "large_loss_count ~ C(line_of_business) * C(accident_year_str) "
        "+ C(province)"
    )

    # Try Poisson first
    model = smf.glm(
        formula, data=df,
        family=sm.families.Poisson(),
        offset=df["log_exposure"],
    ).fit()

    # Overdispersion check
    dispersion = model.pearson_chi2 / model.df_resid
    print(f"Poisson fit: Pearson χ² / df = {dispersion:.3f}")

    # If overdispersed, refit with NB
    if dispersion > 1.5:
        print(f"=> Overdispersion detected. Refitting with Negative Binomial.")
        model = smf.glm(
            formula, data=df,
            family=sm.families.NegativeBinomial(),
            offset=df["log_exposure"],
        ).fit()
        dispersion = model.pearson_chi2 / model.df_resid
        print(f"NB fit: Pearson χ² / df = {dispersion:.3f}")

    return model, dispersion
```

### Extract segment rates at the reference year level

```python
def extract_segment_rates(model, panel_df, segment_keys=SEGMENT_KEYS, reference_year=None):
    """
    Extract the 'clean' frequency rate per segment from the fitted GLM.
    The rate is expressed at the reference year's rate level (default: most recent).
    """
    if reference_year is None:
        reference_year = panel_df["accident_year"].max()

    # Build a prediction frame with one row per unique segment, at the reference year
    segments = panel_df[segment_keys].drop_duplicates().reset_index(drop=True)
    segments["accident_year_str"] = str(reference_year)
    segments["earned_premium"] = 1.0  # predict rate per $1
    segments["log_exposure"] = 0.0

    # Predict — the offset is zero so prediction is the rate per unit of exposure
    segments["glm_rate"] = model.predict(
        segments, offset=np.zeros(len(segments))
    )

    return segments[segment_keys + ["glm_rate"]].copy()
```

### What this produces

For our 2-segment example, the GLM fit yields:

| Segment | GLM rate (at 2025 level) |
|---|---|
| Property × ON | 0.0292 per $M |
| GL × ON | 0.0480 per $M |

The year-effect coefficients implicitly captured:
- Property rate inflation: ~8%/year cumulative
- GL rate inflation: ~6%/year cumulative

**You don't have to extract these — they're absorbed into the model's internal parameters. What matters is that the segment rates are now clean.**

### Why this replaces on-leveling

Under the Frisch-Waugh-Lovell theorem, including year as a fixed effect in the regression produces the same segment coefficients as pre-adjusting the data for year effects. The GLM does the on-leveling internally, using year patterns learned from the data itself — no rate-change filing table required.

---

## Step 6: Apply Hierarchical Credibility

Blend each segment's own GLM rate with its LOB-level complement (not portfolio-wide — ASOP 25 compliance).

### The formula

Two-step blend:

**Level 1 (cell → LOB):**
```
rate_blended_cell = Z_cell × rate_cell_glm + (1 − Z_cell) × rate_LOB
```

**Level 2 (LOB → Portfolio):**
```
rate_LOB_blended = Z_LOB × rate_LOB_avg + (1 − Z_LOB) × rate_portfolio
```

Where Z_cell and Z_LOB are Bühlmann credibility factors computed from exposure and variance.

### Code

```python
def apply_hierarchical_credibility(glm_rates, panel_df, segment_keys=SEGMENT_KEYS):
    """
    Two-level Bühlmann credibility:
      Level 1: cell (LOB x Province) toward LOB
      Level 2: LOB toward portfolio
    """
    # Step A: Aggregate exposure by cell
    cell_exposure = (
        panel_df.groupby(segment_keys)
        .agg(
            hist_exposure=("earned_premium", "sum"),
            hist_losses=("large_loss_count", "sum"),
        )
        .reset_index()
    )

    # Step B: LOB-level aggregates
    lob_agg = (
        panel_df.groupby("line_of_business")
        .agg(
            lob_exposure=("earned_premium", "sum"),
            lob_losses=("large_loss_count", "sum"),
        )
        .reset_index()
    )
    lob_agg["lob_rate"] = lob_agg["lob_losses"] / lob_agg["lob_exposure"]

    # Step C: Portfolio aggregate
    portfolio_rate = lob_agg["lob_losses"].sum() / lob_agg["lob_exposure"].sum()

    # Step D: Estimate Bühlmann K per level (simplified for V1)
    # Within-LOB: variance of cell rates around LOB mean (weighted by exposure)
    # Between-LOB: variance of LOB rates around portfolio mean
    def compute_K(rates, exposures, mean):
        if len(rates) < 2:
            return exposures.sum()
        weights = exposures / exposures.sum()
        weighted_var = np.average((rates - mean) ** 2, weights=weights)
        if weighted_var < 1e-15:
            return exposures.sum()
        return mean / weighted_var

    # K for LOB→Portfolio
    K_lob = compute_K(
        lob_agg["lob_rate"].values,
        lob_agg["lob_exposure"].values,
        portfolio_rate,
    )

    # K for Cell→LOB (per LOB, but we'll use a single average K for V1 simplicity)
    K_cell_values = []
    for lob, sub in cell_exposure.groupby("line_of_business"):
        lob_rate_val = lob_agg.loc[lob_agg["line_of_business"] == lob, "lob_rate"].iloc[0]
        if len(sub) >= 2:
            cell_rates = sub["hist_losses"] / sub["hist_exposure"]
            K_cell_values.append(
                compute_K(cell_rates.values, sub["hist_exposure"].values, lob_rate_val)
            )
    K_cell = np.mean(K_cell_values) if K_cell_values else cell_exposure["hist_exposure"].sum()

    # Step E: Apply credibility — Level 2 (LOB → Portfolio)
    lob_agg["Z_lob"] = lob_agg["lob_exposure"] / (lob_agg["lob_exposure"] + K_lob)
    lob_agg["lob_blended"] = (
        lob_agg["Z_lob"] * lob_agg["lob_rate"]
        + (1 - lob_agg["Z_lob"]) * portfolio_rate
    )

    # Step F: Apply credibility — Level 1 (cell → LOB)
    result = (
        glm_rates
        .merge(cell_exposure, on=segment_keys, how="left")
        .merge(lob_agg[["line_of_business", "lob_blended"]], on="line_of_business", how="left")
    )
    result["Z_cell"] = result["hist_exposure"] / (result["hist_exposure"] + K_cell)
    result["final_rate"] = (
        result["Z_cell"] * result["glm_rate"]
        + (1 - result["Z_cell"]) * result["lob_blended"]
    )

    print(f"Portfolio rate: {portfolio_rate:.6f}")
    print(f"K_LOB: {K_lob:,.0f}, K_Cell: {K_cell:,.0f}")
    print(f"Cell credibility range: {result['Z_cell'].min():.2f} – {result['Z_cell'].max():.2f}")

    return result
```

### Interpretation

| Credibility Z | Meaning |
|---|---|
| Z > 0.7 | Segment has enough data; its own GLM rate dominates |
| 0.3 < Z < 0.7 | Moderate blending toward LOB average |
| Z < 0.3 | Thin segment; rate is mostly pulled toward its LOB mean (not portfolio mean) |

**Key ASOP 25 defensibility point:** thin Professional-AB-Small segments are pulled toward **Professional-all-provinces** (same LOB, similar peril structure), not toward a Property-dominated portfolio average.

---

## Step 7: Build the Rate Table

```python
def build_rate_table(credibility_df, segment_keys=SEGMENT_KEYS, output_path=None):
    """Save the final rate table for downstream use."""
    rate_table = credibility_df[segment_keys + ["final_rate"]].copy()
    rate_table = rate_table.rename(columns={"final_rate": "frequency_rate"})

    if output_path:
        rate_table.to_csv(output_path, index=False)
        print(f"Rate table saved to {output_path}")

    return rate_table
```

### Example output

| line_of_business | province | frequency_rate |
|---|---|---|
| Property | ON | 0.000029 |
| Property | AB | 0.000035 |
| GL | ON | 0.000048 |
| GL | AB | 0.000041 |
| ... | ... | ... |

**This is the artifact that gets updated annually.** Quarterly refreshes consume it but don't modify it.

---

## Step 8: Project Current-Period Premium from In-Force

Translate the in-force snapshot into a projected earned premium per segment for the current period.

### Method: In-force annualization + segment trend (weighted blend)

Three components, combined with weights:

1. **In-force annualized** — anchor from currently active policies
2. **Segment historical trend** — momentum from past growth
3. **Prior-year earned premium** — baseline

```python
def annualize_inforce(inforce_df, segment_keys=SEGMENT_KEYS):
    """
    For each in-force policy, compute its annualized premium.
    Annualized = written_premium × (12 / term_months).
    Sum by segment.
    """
    df = inforce_df.copy()
    df["annualized_premium"] = df["written_premium"] * (12.0 / df["term_months"])

    return (
        df.groupby(segment_keys)
        .agg(inforce_annualized=("annualized_premium", "sum"))
        .reset_index()
    )


def compute_segment_trend(exposure_df, segment_keys=SEGMENT_KEYS, years=3):
    """
    Compute per-segment CAGR over the last N years.
    Returns a multiplicative growth factor (1 + CAGR).
    """
    recent_years = sorted(exposure_df["accident_year"].unique())[-years:]
    start_year = min(recent_years)
    end_year = max(recent_years)

    start = (
        exposure_df[exposure_df["accident_year"] == start_year]
        .groupby(segment_keys)
        .agg(start_ep=("earned_premium", "sum"))
        .reset_index()
    )
    end = (
        exposure_df[exposure_df["accident_year"] == end_year]
        .groupby(segment_keys)
        .agg(end_ep=("earned_premium", "sum"))
        .reset_index()
    )
    trend = start.merge(end, on=segment_keys, how="outer").fillna(0)
    n_years = end_year - start_year
    trend["growth_factor"] = np.where(
        (trend["start_ep"] > 0) & (n_years > 0),
        (trend["end_ep"] / trend["start_ep"]) ** (1 / n_years),
        1.0,  # default: no growth if data insufficient
    )
    # Cap extreme growth rates at ±50% to avoid projection blowup
    trend["growth_factor"] = trend["growth_factor"].clip(0.5, 1.5)
    return trend[segment_keys + ["growth_factor"]]


def project_premium(inforce_df, exposure_df, segment_keys=SEGMENT_KEYS,
                    weights=(0.5, 0.3, 0.2)):
    """
    Weighted blend of three projection methods:
      - 50% in-force annualized × trend (anchored + momentum)
      - 30% in-force annualized (pure anchor)
      - 20% last-year EP × trend (trend only)
    Weights sum to 1.0. Default favors anchored-plus-trend.
    """
    w_anchor_trend, w_anchor_only, w_trend_only = weights
    assert abs(sum(weights) - 1.0) < 0.001, "Weights must sum to 1.0"

    # Component 1: in-force annualized
    inforce_ann = annualize_inforce(inforce_df, segment_keys)

    # Component 2: segment trend
    trend = compute_segment_trend(exposure_df, segment_keys, years=3)

    # Component 3: last year EP
    last_year = exposure_df["accident_year"].max()
    last_ep = (
        exposure_df[exposure_df["accident_year"] == last_year]
        .groupby(segment_keys)
        .agg(last_ep=("earned_premium", "sum"))
        .reset_index()
    )

    # Merge all three
    proj = (
        inforce_ann.merge(trend, on=segment_keys, how="outer")
        .merge(last_ep, on=segment_keys, how="outer")
        .fillna({"inforce_annualized": 0, "growth_factor": 1.0, "last_ep": 0})
    )

    # Compute each method's projection
    proj["method_1"] = proj["inforce_annualized"] * proj["growth_factor"]
    proj["method_2"] = proj["inforce_annualized"]
    proj["method_3"] = proj["last_ep"] * proj["growth_factor"]

    # Weighted blend
    proj["projected_premium"] = (
        w_anchor_trend * proj["method_1"]
        + w_anchor_only * proj["method_2"]
        + w_trend_only * proj["method_3"]
    )

    print(f"Projected premium by segment:")
    print(proj[segment_keys + ["projected_premium"]].to_string(index=False))

    return proj[segment_keys + ["projected_premium"]]
```

### Example output

| line_of_business | province | projected_premium |
|---|---|---|
| Property | ON | 148_000_000 |
| GL | ON | 133_000_000 |
| ... | ... | ... |

---

## Step 9: Calculate Expected Counts

Apply the rate table to projected premium.

```python
def calculate_expected(projected_premium_df, rate_table, segment_keys=SEGMENT_KEYS):
    """Multiply projected premium by segment rate to get expected counts."""
    df = projected_premium_df.merge(rate_table, on=segment_keys, how="left")

    # Fill missing segments (new segments not in rate table) with portfolio average
    missing = df["frequency_rate"].isna()
    if missing.any():
        portfolio_avg = rate_table["frequency_rate"].mean()
        print(f"WARNING: {missing.sum()} segments missing rates. Using portfolio avg.")
        df.loc[missing, "frequency_rate"] = portfolio_avg

    df["expected_losses"] = df["projected_premium"] * df["frequency_rate"]

    total_expected = df["expected_losses"].sum()
    print(f"Total expected large losses: {total_expected:.1f}")

    return df
```

---

## Step 10: Produce the Actual vs Expected Report

Compare actual losses (when reporting retrospectively or YTD) to expected.

```python
def ave_report(expected_df, actual_count, use_nb=False, nb_dispersion=5.0):
    """
    Portfolio-level AvE report with percentile context and traffic light.
    """
    total_expected = expected_df["expected_losses"].sum()
    gap = actual_count - total_expected

    if use_nb:
        r = nb_dispersion
        p = r / (r + total_expected)
        percentile = stats.nbinom.cdf(actual_count, r, p) * 100
        ci_low = stats.nbinom.ppf(0.05, r, p)
        ci_high = stats.nbinom.ppf(0.95, r, p)
    else:
        percentile = stats.poisson.cdf(actual_count, total_expected) * 100
        ci_low = stats.poisson.ppf(0.05, total_expected)
        ci_high = stats.poisson.ppf(0.95, total_expected)

    if 25 <= percentile <= 75:
        traffic_light = "GREEN"
    elif 10 <= percentile <= 90:
        traffic_light = "AMBER"
    else:
        traffic_light = "RED"

    result = {
        "expected": round(total_expected, 1),
        "actual": int(actual_count),
        "gap": round(gap, 1),
        "percentile": round(percentile, 1),
        "ci_5th": int(ci_low),
        "ci_95th": int(ci_high),
        "traffic_light": traffic_light,
    }

    print("=" * 60)
    print("  ACTUAL vs EXPECTED LARGE LOSS FREQUENCY")
    print("=" * 60)
    for k, v in result.items():
        print(f"  {k:20}: {v}")
    print("=" * 60)

    return result
```

---

## Step 11: Shadow Rate Drift Monitor

Quarterly diagnostic to catch emerging rate drift between annual recalibrations.

### Approach: Cumulative O/E ratio per segment per quarter

```python
def shadow_rate_monitor(actual_ytd_df, expected_ytd_df, segment_keys=SEGMENT_KEYS,
                        alert_threshold=1.3, consecutive_quarters=2):
    """
    Track cumulative YTD observed/expected ratio per segment.
    Alert if ratio exceeds threshold for N consecutive quarters.
    """
    merged = expected_ytd_df.merge(actual_ytd_df, on=segment_keys, how="left")
    merged["actual_losses"] = merged["actual_losses"].fillna(0).astype(int)
    merged["OE_ratio"] = (
        merged["actual_losses"] / merged["expected_losses"].replace(0, np.nan)
    )

    def status(ratio):
        if pd.isna(ratio):
            return "—"
        if ratio >= alert_threshold:
            return "ALERT"
        if ratio >= 1.2:
            return "WATCH"
        return "OK"

    merged["status"] = merged["OE_ratio"].apply(status)

    print("\nShadow Rate Drift Monitor:")
    print(merged[segment_keys + ["expected_losses", "actual_losses", "OE_ratio", "status"]]
          .to_string(index=False, float_format="%.2f"))

    return merged
```

**Operational rule:** if any segment shows `status = "ALERT"` for 2+ consecutive quarters, trigger an interim recalibration review (don't wait for year-end).

---

## Step 12: Build the Deviation Attribution Waterfall

Decompose the change in expected (+ actual) from prior period to current period into Volume, Mix, Rate, and Random effects.

```python
def attribution_waterfall(prior_df, current_df, segment_keys=SEGMENT_KEYS):
    """
    Sequential Laspeyres decomposition:
      Prior Expected + Volume + Mix + Rate = Current Expected
      Current Expected + Random = Actual
    """
    bridge = prior_df.merge(
        current_df, on=segment_keys, suffixes=("_prior", "_current"), how="outer"
    ).fillna(0)

    E_prior = bridge["projected_premium_prior"].sum()
    E_current = bridge["projected_premium_current"].sum()

    prior_expected = bridge["expected_losses_prior"].sum()
    current_expected = bridge["expected_losses_current"].sum()

    r_bar_prior = prior_expected / E_prior if E_prior > 0 else 0

    # Volume: growth at prior average rate
    volume_effect = r_bar_prior * (E_current - E_prior)

    # Mix: apply prior rates to current exposure weights
    expected_remix = (
        bridge["frequency_rate_prior"] * bridge["projected_premium_current"]
    ).sum()
    mix_effect = expected_remix - r_bar_prior * E_current

    # Rate: change in rates at current exposure
    rate_effect = (
        (bridge["frequency_rate_current"] - bridge["frequency_rate_prior"])
        * bridge["projected_premium_current"]
    ).sum()

    # Random: residual
    actual_total = bridge["actual_losses_current"].sum()
    random_effect = actual_total - current_expected

    # Z-score for random
    sigma = np.sqrt(current_expected) if current_expected > 0 else 1
    z_score = random_effect / sigma

    result = {
        "prior_expected": round(prior_expected, 1),
        "volume_effect": round(volume_effect, 1),
        "mix_effect": round(mix_effect, 1),
        "rate_effect": round(rate_effect, 1),
        "current_expected": round(current_expected, 1),
        "random_effect": round(random_effect, 1),
        "actual": int(actual_total),
        "random_z_score": round(z_score, 2),
    }

    # Verification
    total_change = actual_total - prior_expected
    attributed = volume_effect + mix_effect + rate_effect + random_effect
    assert abs(total_change - attributed) < 0.1, "Attribution doesn't balance!"

    print("\nDeviation Attribution Waterfall:")
    for k, v in result.items():
        print(f"  {k:25}: {v}")

    return result
```

### Plot it

```python
def plot_waterfall(w, save_path=None):
    """Standard FP&A-style waterfall chart."""
    labels = ["Prior\nExpected", "Volume", "Mix", "Rate",
              "Current\nExpected", "Random", "Actual"]
    values = [w["prior_expected"], w["volume_effect"], w["mix_effect"],
              w["rate_effect"], w["current_expected"], w["random_effect"], w["actual"]]

    # Bar position calculations
    cum = [values[0]]
    for v in values[1:4]:
        cum.append(cum[-1] + v)
    cum.append(values[4])
    cum.append(cum[-1] + values[5])
    cum.append(values[6])

    bottoms = [0]
    for i in range(1, 4):
        bottoms.append(min(cum[i - 1], cum[i]))
    bottoms += [0, min(cum[4], cum[5]), 0]

    heights = [values[0]] + [abs(v) for v in values[1:4]] + [values[4], abs(values[5]), values[6]]

    colors = ["#4472C4"]
    for v in values[1:4]:
        colors.append("#E74C3C" if v > 0 else "#27AE60")
    colors += ["#4472C4", "#95A5A6", "#4472C4"]

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(labels, heights, bottom=bottoms, color=colors, edgecolor="white", width=0.6)

    for bar, val in zip(bars, values):
        y = bar.get_y() + bar.get_height() + 0.3
        text = f"{val:.1f}" if bar in [bars[0], bars[4], bars[6]] else f"{val:+.1f}"
        ax.text(bar.get_x() + bar.get_width() / 2, y, text,
                ha="center", va="bottom", fontweight="bold", fontsize=11)

    ax.set_ylabel("Large Loss Count")
    ax.set_title("Large Loss Frequency: Deviation Attribution", fontsize=14)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()
```

### Auto-generate narrative

```python
def generate_narrative(w, current_period, prior_period, percentile):
    """Board-ready narrative auto-generated from waterfall results."""
    actual = int(w["actual"])
    z = w["random_z_score"]

    lines = [
        f"Large loss count for {current_period} was {actual}, against an expectation "
        f"of {w['current_expected']:.1f} ({percentile:.0f}th percentile).",
        "",
        f"Change from the {prior_period} expectation of {w['prior_expected']:.1f}:",
    ]

    if abs(w["volume_effect"]) >= 0.1:
        d = "growth" if w["volume_effect"] > 0 else "contraction"
        lines.append(f"  - Portfolio {d} ({w['volume_effect']:+.1f})")
    if abs(w["mix_effect"]) >= 0.1:
        d = "higher-frequency segments" if w["mix_effect"] > 0 else "lower-frequency segments"
        lines.append(f"  - Mix shift toward {d} ({w['mix_effect']:+.1f})")
    if abs(w["rate_effect"]) >= 0.1:
        d = "increased" if w["rate_effect"] > 0 else "decreased"
        lines.append(f"  - Segment frequency rates {d} ({w['rate_effect']:+.1f})")

    ctx = ("within normal variation" if abs(z) < 1.0
           else "somewhat unusual but within expectations" if abs(z) < 1.65
           else "statistically notable" if abs(z) < 2.0
           else "strong signal of structural deviation")
    lines.append(f"  - Random volatility ({w['random_effect']:+.1f}): {ctx} (z={z:+.2f})")

    lines.append("")
    if abs(z) < 1.65:
        lines.append("Conclusion: Experience is within expectations. No structural concern.")
    else:
        lines.append("Conclusion: Deviation warrants investigation.")

    narrative = "\n".join(lines)
    return narrative
```

---

## Step 13: Automate the Quarterly Refresh

```python
def quarterly_refresh(loss_path, exposure_path, inforce_path, rate_table_path,
                      output_dir, current_year, current_quarter=None, prior_year=None):
    """
    Full quarterly refresh pipeline.
    - Load data, filter losses
    - Load rate table (frozen from last annual recalibration)
    - Project current-period premium from in-force
    - Calculate expected counts
    - Compare to YTD actuals
    - Run shadow rate monitor
    - Build waterfall vs prior year
    - Auto-generate narrative
    - Save all outputs
    """
    if prior_year is None:
        prior_year = current_year - 1

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load
    losses, exposure, inforce = load_data(loss_path, exposure_path, inforce_path)
    losses = filter_losses(losses)
    rate_table = pd.read_csv(rate_table_path)

    # Project current period
    proj_current = project_premium(inforce, exposure)
    expected_current = calculate_expected(proj_current, rate_table)

    # Actuals for current period (YTD)
    actual_current = (
        losses[losses["accident_year"] == current_year]
        .groupby(SEGMENT_KEYS)
        .agg(actual_losses=("loss_id", "nunique"))
        .reset_index()
    )
    expected_current = expected_current.merge(actual_current, on=SEGMENT_KEYS, how="left")
    expected_current["actual_losses"] = expected_current["actual_losses"].fillna(0).astype(int)

    # Portfolio AvE
    ave = ave_report(expected_current, expected_current["actual_losses"].sum())

    # Shadow monitor
    shadow_rate_monitor(
        expected_current[SEGMENT_KEYS + ["actual_losses"]],
        expected_current[SEGMENT_KEYS + ["expected_losses"]],
    )

    # Prior-period baseline for waterfall
    prior_actual = (
        losses[losses["accident_year"] == prior_year]
        .groupby(SEGMENT_KEYS).agg(actual_losses=("loss_id", "nunique")).reset_index()
    )
    # For waterfall we need the prior period's projected + expected + actual
    # Simplified: use prior year's actual exposure as "projected" for that year
    prior_exp = exposure[exposure["accident_year"] == prior_year].groupby(SEGMENT_KEYS).agg(
        projected_premium=("earned_premium", "sum")
    ).reset_index()
    prior_df = (
        prior_exp.merge(rate_table, on=SEGMENT_KEYS, how="left")
        .merge(prior_actual, on=SEGMENT_KEYS, how="left")
    )
    prior_df["expected_losses"] = prior_df["projected_premium"] * prior_df["frequency_rate"]
    prior_df["actual_losses"] = prior_df["actual_losses"].fillna(0).astype(int)

    wf = attribution_waterfall(prior_df, expected_current)
    plot_waterfall(wf, save_path=str(out / "waterfall.png"))

    # Narrative
    period_label = f"{current_year}" + (f" Q{current_quarter}" if current_quarter else "")
    narrative = generate_narrative(wf, period_label, str(prior_year), ave["percentile"])
    (out / "narrative.txt").write_text(narrative)
    print("\n" + narrative)

    # Save outputs
    expected_current.to_csv(out / "segment_ave.csv", index=False)
    pd.DataFrame([ave]).to_csv(out / "ave_summary.csv", index=False)
    pd.DataFrame([wf]).to_csv(out / "waterfall.csv", index=False)

    print(f"\nAll outputs saved to {out}/")
    return {"ave": ave, "waterfall": wf, "narrative": narrative}
```

---

## Step 14: Annual Recalibration

Once a year (typically at year-end), re-run the calibration with updated data.

```python
def annual_recalibration(loss_path, exposure_path, output_dir,
                         experience_years=None, reference_year=None):
    """
    Full annual recalibration:
      - Load data, filter losses
      - Aggregate for GLM
      - Fit GLM with year fixed effect
      - Apply hierarchical credibility
      - Build new rate table
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    losses, exposure, _ = load_data(loss_path, exposure_path, None)
    losses = filter_losses(losses)

    if experience_years is None:
        latest = exposure["accident_year"].max()
        experience_years = list(range(latest - 4, latest + 1))
    if reference_year is None:
        reference_year = max(experience_years)

    panel = build_calibration_panel(losses, exposure, experience_years=experience_years)

    # Calibrate
    model, dispersion = fit_frequency_glm(panel)
    glm_rates = extract_segment_rates(model, panel, reference_year=reference_year)

    # Credibility
    cred = apply_hierarchical_credibility(glm_rates, panel)

    # Build rate table
    rate_table = build_rate_table(cred, output_path=str(out / "rate_table.csv"))

    print(f"\nAnnual recalibration complete.")
    print(f"New rate table saved to {out / 'rate_table.csv'}")
    return rate_table
```

---

## Appendix A: Full Pipeline Script

```python
#!/usr/bin/env python3
"""
Large Loss Frequency Model — Full Pipeline
Usage:
  python run_pipeline.py --mode recalibrate --years 2021-2025
  python run_pipeline.py --mode refresh --year 2026 --quarter 4
"""
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["refresh", "recalibrate"], required=True)
    parser.add_argument("--year", type=int)
    parser.add_argument("--quarter", type=int)
    parser.add_argument("--years", type=str, help="e.g. 2021-2025")
    parser.add_argument("--loss-data", default="data/loss_register.parquet")
    parser.add_argument("--exposure-data", default="data/exposure_register.parquet")
    parser.add_argument("--inforce-data", default="data/inforce_snapshot.parquet")
    parser.add_argument("--rate-table", default="output/rate_table.csv")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    if args.mode == "recalibrate":
        start, end = map(int, args.years.split("-"))
        annual_recalibration(
            args.loss_data, args.exposure_data, args.output_dir,
            experience_years=list(range(start, end + 1)),
        )
    elif args.mode == "refresh":
        out = f"{args.output_dir}/{args.year}"
        if args.quarter:
            out += f"_Q{args.quarter}"
        quarterly_refresh(
            args.loss_data, args.exposure_data, args.inforce_data,
            args.rate_table, out, args.year, args.quarter,
        )


if __name__ == "__main__":
    main()
```

---

## Appendix B: Data Extract SQL Templates

### Loss Register

```sql
SELECT
    clm.claim_id,
    clm.occurrence_id,
    clm.policy_id,
    clm.accident_date,
    clm.report_date,
    clm.valuation_date,
    clm.incurred_amount,
    pol.line_of_business,
    COALESCE(clm.loss_province, pol.province) AS province,
    clm.cause_of_loss,
    COALESCE(clm.catastrophe_flag, 'N') AS catastrophe_flag
FROM claims clm
JOIN policies pol ON clm.policy_id = pol.policy_id
WHERE clm.incurred_amount >= 250000   -- pull broadly; filter at $500K later
  AND clm.accident_date >= '2018-01-01'
  AND clm.valuation_date = (SELECT MAX(valuation_date) FROM claims)
```

### Exposure Register

```sql
SELECT
    pol.policy_id,
    YEAR(pe.earned_from_date) AS accident_year,
    pol.line_of_business,
    pol.province,
    SUM(pe.earned_premium) AS earned_premium,
    COUNT(DISTINCT pol.policy_id) AS policy_count,
    MIN(pol.effective_date) AS effective_date,
    MAX(pol.expiry_date) AS expiry_date
FROM policy_earned pe
JOIN policies pol ON pe.policy_id = pol.policy_id
WHERE pe.earned_premium > 0
  AND YEAR(pe.earned_from_date) BETWEEN 2018 AND 2025
GROUP BY pol.policy_id, YEAR(pe.earned_from_date), pol.line_of_business, pol.province
```

### In-Force Snapshot

```sql
SELECT
    pol.policy_id,
    pol.line_of_business,
    pol.province,
    pol.effective_date,
    pol.expiry_date,
    pol.written_premium,
    DATEDIFF(MONTH, pol.effective_date, pol.expiry_date) AS term_months
FROM policies pol
WHERE pol.effective_date <= GETDATE()
  AND pol.expiry_date > GETDATE()
  AND pol.status = 'ACTIVE'
```

---

## Appendix C: Test Scenarios and Expected Outputs

Use these scenarios to validate the pipeline end-to-end.

### Test 1: Flat-frequency, rate-inflated book

**Input:**
- 5 years history, 2 segments, flat 4 & 6 losses/year
- Premium inflated 8%/yr (Property) and 6%/yr (GL)

**Expected:**
- GLM year effects capture rate inflation
- Extracted segment rates at 2025 level ≈ 0.029 and 0.048
- Naive 5-year avg rate would be biased upward by ~15–20%

### Test 2: Thin segment credibility

**Input:**
- Segment with 1 loss in 5 years, $5M exposure
- Same LOB has 20 losses, $200M exposure across all geos

**Expected:**
- Z_cell < 0.3
- Final rate pulled strongly toward LOB rate (not portfolio)
- Rate change from raw >50%

### Test 3: Waterfall balance

**Input:**
- Any prior/current period data

**Expected:**
- `prior_expected + volume + mix + rate + random == actual` (within 0.1 tolerance)
- Assert in code

### Test 4: Cat filter

**Input:**
- Loss register with 50% cat-flagged claims

**Expected:**
- `filter_losses` drops all cat
- Resulting count = non-cat claims only

### Test 5: Shadow rate alert

**Input:**
- Synthetic data where Q1–Q3 2026 actuals exceed expected by 40%

**Expected:**
- O/E ratio > 1.3 for all 3 quarters
- Status = ALERT for all 3 quarters
- Recommendation: trigger interim recalibration

---

## Appendix D: Output Schemas

### `rate_table.csv`
| Column | Type | Description |
|---|---|---|
| line_of_business | str | LOB identifier |
| province | str | 2-char province code |
| frequency_rate | float | Large losses per $1 of earned premium, at reference year level |

### `segment_ave.csv`
| Column | Type | Description |
|---|---|---|
| line_of_business | str | |
| province | str | |
| projected_premium | float | |
| frequency_rate | float | |
| expected_losses | float | |
| actual_losses | int | |

### `ave_summary.csv`
| Column | Type | Description |
|---|---|---|
| expected | float | Total portfolio expected |
| actual | int | Total actual |
| gap | float | actual - expected |
| percentile | float | Poisson/NB percentile of actual |
| ci_5th | int | 5th percentile bound |
| ci_95th | int | 95th percentile bound |
| traffic_light | str | GREEN/AMBER/RED |

### `waterfall.csv`
| Column | Type | Description |
|---|---|---|
| prior_expected | float | |
| volume_effect | float | |
| mix_effect | float | |
| rate_effect | float | |
| current_expected | float | |
| random_effect | float | |
| actual | int | |
| random_z_score | float | Standardized residual |

---

## V1 Known Limitations (For Documentation)

These are accepted scope trade-offs for V1. Document in every board pack.

| Limitation | Reason | Phase 2 plan |
|---|---|---|
| **No IBNR / development adjustment** | Assume losses are reported by year-end | Add count development factors if year-end reporting gap is material |
| **Non-cat only** | Cat handled separately via cat models | Integrate cat frequency as a second track if needed |
| **100% renewal assumption** | V1 simplification for premium projection | Add renewal model with segment-specific rates if material |
| **Year effect absorbs both rate inflation and real trend** | Can't separate without external benchmark | Optional: add an external index validation in Phase 2 |
| **Segmentation is LOB × Province** | Simple, stable, easy to explain | Add size band or industry class if data supports it |
| **Fixed-window experience period (5 years)** | Standard actuarial practice | Could explore exponentially-weighted if desired |

---

*Document version: V1.0 | Scope: Phase 1 production | Target: 6–8 weeks*
