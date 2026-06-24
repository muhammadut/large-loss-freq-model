# Step 2 — Premium Projection

Projects each segment's **full-year earned premium**, so it can be multiplied by the
Step-1 frequency rate to produce expected large-loss counts:

```
expected large losses (segment) = rate (segment) × projected premium (segment)
```

## Run it

```bash
python src/premium_projection/run.py --config src/premium_projection/config.yaml
```

By default this runs on **`data_1`** — the same extract as the Step-1 rate table — so the
rate and the premium share one consistent basis. Outputs land in `outputs/premium/<run>_<date>/`:

| File | What it is |
|---|---|
| `growth_factor_table.csv` | the growth factor per **(segment × month)** — the reusable artifact |
| `projected_premium.csv` | projected full-year premium per segment |
| `expected_losses.csv` | premium × the Step-1 rate (if a rate table is found) |
| `report.md` | methodology, the backtest, the metrics, and caveats |

## The method

```
projected full-year premium = visible premium (so far) × growth factor
```
- **Visible premium** = policies already on the books at the run date (earned forward from
  each policy's start/end dates).
- **Growth factor** = `full-year ÷ visible`, learned from history **per segment** and
  **per run-month** (the later you run, the smaller the scale-up). Cancellations are baked
  into the historical factor — no separate term.

Validated by backtest (factors from prior years only, scored on held-out years): on
`data_1`, **~2.7% dollar-weighted error, ~89% of segments within ±10%**, and accuracy
tightens the later in the year you run (Q1 → Q3).

## Choosing the data file (config)

| Config | Data | Dates used | Backtest WAPE |
|---|---|---|---|
| `config.yaml` (default) | `data_1` (OG) | `FROM_DT` / `TO_DT` | ~2.7% |
| `config_data2.yaml` | `data_2` | `POLEFFDATE_M` / `POLEXPDATE_M` (true policy terms) | ~1.4% |

`data_2` is slightly more accurate (true policy dates) but is a **different extract** than
the Step-1 rate table — its premium is ~5% higher and its loss volume ~2×. **Use the
default (`data_1`) so both steps share one extract.** If you switch Step 2 to `data_2`,
also build Step 1 on `data_2` (`src/config/config_data2.yaml`) so the two halves stay
consistent.

## Two requirements when multiplying by the rate table

1. **Same segment definition** — both tables must use the same buckets (the 6 grouped
   rating regions). `data_1` already uses them; `data_2`'s province codes are collapsed via
   the `region_map` in `config_data2.yaml`.
2. **Same data extract** — rate and premium from the *same* file, or the expected-loss
   total inherits the files' loss/premium differences. The default keeps both on `data_1`.
