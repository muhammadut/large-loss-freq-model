# Premium Projection (Part 2)

Projects each segment's **full-year earned premium**, so it can be multiplied by the
Part-1 frequency rate to produce expected large-loss counts:

```
expected large losses (segment) = rate (segment) × projected premium (segment)
```

## Run it

```bash
python src/premium_projection/run.py --config src/premium_projection/config.yaml
```

Outputs land in `outputs/premium/<run>_<date>/`:

| File | What it is |
|---|---|
| `growth_factor_table.csv` | the growth factor per **(segment × month)** — the reusable artifact |
| `projected_premium.csv` | projected full-year premium per segment |
| `expected_losses.csv` | premium × the Part-1 rate (if a rate table is found) |
| `report.md` | methodology, the backtest, the metrics, and caveats |

## The method

```
projected full-year premium = visible premium (so far) × growth factor
```
- **Visible premium** = policies already on the books at the run date (in production,
  earned forward from each policy's start/end dates).
- **Growth factor** = `full-year ÷ visible`, learned from history **per segment** and
  **per run-month** (the later you run, the smaller the scale-up). Cancellations are
  baked into the historical factor.

Validated by backtest (factors from prior years only, scored on held-out years):
**~1.4% dollar-weighted error, ~94% of segments within ±10%** — and accuracy tightens
the later in the year you run (Q1 ~2.5% → Q3 ~0.6%).

## Two hard requirements when multiplying by the rate table

1. **Same segment definition** — both tables must use the same buckets. This extract
   codes `ratingregion` at province level; the `region_map` in `config.yaml` collapses
   it to the 6 canonical grouped regions (verified by premium-share match).
2. **Same premium basis** — the rate and the premium should come from the *same* data
   file, or the expected-loss total inherits the files' premium-level difference.

## Config

Everything is in `config.yaml`: data path, segment keys, the `region_map`, experience
years, the clip/fallback for thin segments, and the backtest settings.
