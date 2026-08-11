# Large-Loss Model — `src/`

One question, end to end: **"Are the big losses we're seeing normal, or should we worry?"**
The code is organized as **numbered steps** you run in order. Each `step_N_*/` folder is
self-contained (its own code, `config.yaml`, and `README.md`).

---

## The pipeline at a glance

```
   step_1_frequency ──┐
     (the rate)       ├──►  step_3_expected_vs_actual   ← the board verdict
   step_2_premium ────┤          (needs 1 + 2)
     (full-year $)    └──►  step_4_segment_analysis      ← segment investigation
                                  (needs 1 + 2)

   step_5_liability_development   ← parallel track for SLOW liability claims
                                    (self-contained today; merges into 1 & 3 later)
```

- **Property** (fast-reporting) flows through steps 1 → 2 → 3.
- **Liability** (slow-reporting) has its own step 5, because a liability year is only
  partly visible for years and needs the extra "timing + normal-range" machinery.
- Steps 3 and 4 both consume step 1's rate table + step 2's premium; they're parallel
  consumers, not sequential.

## Before you run

- Python with `pandas, numpy, scipy, statsmodels, pyyaml`.
- Data files in `data/` (git-ignored): `basic_data_1.csv` (property), `liability_data_10_yrs.csv`
  (liability). Steps 1–4 read the ~600 MB property CSV once (~1 min, quiet while loading).
- Every run writes its own **timestamped** folder under `outputs/`, so runs never overwrite.

---

## Run it, in order

### Step 1 — Frequency  · `step_1_frequency/`
The rate: how often a big loss happens per $ of business, per segment (the foundation).
```bash
python src/run.py --config src/config/config.yaml
```
- **Config:** `src/config/config.yaml`  · key defaults: threshold **$200k**, calibration years
  **2021–2024**, reference year **2024**, lens **premium**, family **poisson**.
- **Output:** `outputs/…/rate_table_final.csv` (the frozen deliverable) + `run_summary.md`.
- **Needs:** nothing — start here.

### Step 2 — Premium  · `step_2_premium/`
Projects each segment's full-year premium (the denominator step 3 multiplies the rate by).
```bash
python src/step_2_premium/run.py --config src/step_2_premium/config.yaml
```
- **Config:** `src/step_2_premium/config.yaml` · per-segment, per-month growth factor.
- **Output:** `outputs/step_2_premium/…` — projected premium per segment.
- **Needs:** nothing directly (rebuilt on demand by steps 3 & 4 too).

### Step 3 — Expected vs Actual  · `step_3_expected_vs_actual/`
The board verdict: expected count (rate × premium) vs actual → percentile, traffic light,
attribution waterfall, plain-English narrative.
```bash
python src/step_3_expected_vs_actual/run.py --config src/step_3_expected_vs_actual/config.yaml
```
- **Config:** `src/step_3_expected_vs_actual/config.yaml` · points at `step1_config`,
  `step2_config`, and finds the **newest** `rate_table_final.csv` via `rate_table_glob`.
- **Output:** `outputs/step_3_expected_vs_actual/…` — `board_report.md` + tables.
- **Needs:** **Step 1 must have run** (it reads the latest rate table). Rebuilds Step 2 itself.

### Step 4 — Segment Analysis  · `step_4_segment_analysis/`
Investigation layer: four business lenses over the shipped rates + significance dossiers.
```bash
python src/step_4_segment_analysis/run.py --config src/step_4_segment_analysis/config.yaml
```
- **Config:** `src/step_4_segment_analysis/config.yaml` (same upstream pointers as Step 3).
- **Output:** `outputs/step_4_segment_analysis/…` — `segment_master.csv`. See the folder's
  `segment_analysis_explained.md` for a plain-English tour.
- **Needs:** **Step 1 must have run.** Rebuilds Step 2 itself.

### Step 5 — Liability Development  · `step_5_liability_development/`
The slow-claim (immature-year) liability track: triangle → recent-weighted ladder →
credibilised exposure rate → **empirical normal-range band** → verdict, + two backtests.
```bash
python src/step_5_liability_development/run.py --config src/step_5_liability_development/config.yaml
```
- **Config:** `src/step_5_liability_development/config.yaml` · key defaults: threshold **$200k**,
  `band_method` **hybrid** (of 5, chosen by shoot-out), `band_recent_window` **5**,
  segments **region × industry**.
- **Output:** `outputs/step_5_liability_development/…` — `verdict.csv`, `ladder.csv`, `band_shootout.csv`, backtests.
- **Needs:** nothing — self-contained (uses `data/liability_data_10_yrs.csv`).

---

## What lives where

| Folder | What it is |
|---|---|
| `step_1_frequency/` … `step_5_liability_development/` | the pipeline, in order (each self-contained) |
| `config/` | Step 1's config + its lens variants (`config_tiv.yaml`, `config_data2.yaml`) + `config.reference.md` |
| `docs/` | cross-cutting docs: `DECISIONS.md` (every choice + why), `methodology.md`, `pipeline_guide.md`, `immature_year_approach.md` |
| `run.py` | shortcut entry point for Step 1 |
| `_archive/` | superseded prototypes kept for reference (not part of the pipeline) |

Each step's own `README.md` has the detail for that step. Start with `docs/DECISIONS.md`
for the reasoning behind the whole model.
