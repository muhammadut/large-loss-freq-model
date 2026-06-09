# Large-Loss Frequency — Calibration Pipeline (`src/`)

Turns the raw policy/loss extract into a **credibilized segment rate table** — one
trustworthy "large losses per $1M of exposure" number per segment. It stops at the
rate table; the forward projection (premium → expected counts → actual-vs-expected)
is a separate downstream step that consumes the output.

---

## Quick start

```bash
# from the repo root
python src/run.py --config src/config/config.yaml        # premium lens (default)
python src/run.py --config src/config/config_tiv.yaml    # TIV lens (cross-check)
```
Requires Python with `pandas, numpy, scipy, statsmodels, pyyaml`. A run reads the
~600 MB CSV once (~1 min) — the terminal is quiet while it loads, then prints a
summary.

## What it does

```
config.yaml
   → load + clean + DATA-QUALITY gates (halt on bad input)
   → segment × year panel
   → Poisson GLM with year effect      → clean rates @ reference year
   → hierarchical Bühlmann credibility  → final, board-safe rates
   → 8 VALIDATION gates
   → writes a dated run folder
```

## What you get — a dated run folder

Every run creates its own timestamped folder so runs never overwrite each other:

```
outputs/annual_recalibration_2025_2026-06-09_140930/
├── rate_table_final.csv   ← THE DELIVERABLE — the rate per segment
├── run_report.json        ← machine-readable record (diff this across yearly refits)
├── run_summary.md         ← ★ human report: every check + what it means (open this first)
└── model_diagnostics.md   ← classical fit stats (deviance, AIC/BIC, p-values), each explained
```

**Start with `run_summary.md`** — it's a click-to-read explanation of exactly what
happened, with every check, its result, and how to interpret it.

## How to read the result

The terminal and `run_summary.md` show two groups of checks. Status icons: `✅` clear,
`⚠️` heads-up (be aware, not broken), `⛔` stops the run.

| Check | What it means (one line) |
|---|---|
| `years_present`, `min_large_losses` | enough clean data to model — **halt** if not |
| `cat_scope` | discloses the catastrophe basis (here: assume_excluded) |
| `exposure_integrity[lens]` | large losses with missing exposure under a lens (inflates rates) |
| `count_grain` | documents the count unit (coverage-row vs claim) |
| `reconciliation` | wiring check — model total = actual total (a FAIL = code bug) |
| `dispersion` | is Poisson's spread assumption holding? (~1 good, >1.5 = consider richer model) |
| `thin_segment_share` | how many segments are thin (informational) |
| `backtest` | predict a held-out year's **total** — real out-of-sample test |
| `backtest_segment` | did it get the **segments** right, not just the total? |
| `robustness_drop_yr` | drop newest year — do final rates stay stable? |
| `total_preservation` | credibility redistributes risk without moving the total |
| `base_agreement` | premium vs TIV ranking (they differ — informational) |

Two `⚠️` warnings are **expected every run**: `base_agreement` (premium and TIV
genuinely measure different things) and `exposure_integrity[tiv]` (2.3% of losses
lack TIV). Neither is a failure.

## The model

```
large_loss_count ~ C(CovType) + C(ratingregion) + C(MAIN_OPGROUP) + C(ROLLING_YEAR)
   family = Poisson   offset = log(exposure)   rates read at reference_year (2024)
```
The **year effect** on-levels the rate; rates are read at the last **fully-developed**
year (the newest year is still maturing and would understate the level).

## The lens (`exposure.lens`)

The lens is the denominator; it changes what the rate *means* and what you project forward.

| lens | rate means | notes |
|---|---|---|
| `premium` (default) | losses per $ **charged** | pricing-aligned, ~99% populated, on-leveled by the year effect |
| `tiv` | losses per $ of **insured value** | hazard view; ~80% populated; less stable; project **TIV** forward |
| `earned_exposure` | losses per **volume unit** | uncontaminated, 100% populated |

## Config

Everything tunable is in `config/config.yaml`; see `config/config.reference.md` for
every field. Nothing is hard-coded — and the config **rejects** unimplemented settings
(e.g. `family: negative_binomial`) at load, so a run can never silently do something
other than what the config states.

## Go deeper

- `docs/pipeline_guide.html` — how the code/config/pipeline work + how to build Part 2
- `docs/model_documentation.html` — the methodology (the *why*) + validation + what didn't work
- `config/config.reference.md` — every config field, documented
