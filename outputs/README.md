# outputs/

Generated artifacts live here — **nothing in this folder is hand-written** (except
this file). Each run of the pipeline creates its own dated subfolder, so runs never
overwrite each other:

```
outputs/<run_name>_<date_time>/
```

The TIV cross-check run writes to `outputs/tiv/<run_name>_<date_time>/`.

## What each run folder contains

| File | What it is |
|---|---|
| `rate_table_final.csv` | **the deliverable** — the credibilized large-loss rate per segment (use the `final_rate` / `final_rate_per_1M` column) |
| `run_summary.md` | human-readable report: every data-quality and validation check, its result, and **what it means** — open this first |
| `model_diagnostics.md` | classical fit statistics (deviance, AIC/BIC, dispersion, coefficient p-values), each explained |
| `run_report.json` | machine-readable record of the run — keep it to **diff against future refits** (drift detection) |

## How to produce one

```bash
python src/run.py --config src/config/config.yaml
```

Run folders are not tracked in version control (only this explainer is) — regenerate
them by running the pipeline.
