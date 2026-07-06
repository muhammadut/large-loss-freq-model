# Step 3 — Expected vs Actual

The board-facing deliverable. Takes the Step-1 **rate** and the Step-2 **projected
premium**, multiplies them into an **expected large-loss count**, compares it to the
**actual** count, and wraps that in a percentile, a traffic-light, an attribution
waterfall, and an auto-generated narrative.

```
expected count = Σ ( Step-1 rate × Step-2 projected premium )   vs   actual count
        → percentile → GREEN / AMBER / RED → waterfall → board narrative
```

## Run it

```bash
# after Step 1 (rate table) and Step 2 exist:
python src/expected_vs_actual/run.py --config src/expected_vs_actual/config.yaml
```

Outputs land in `outputs/expected_vs_actual/<run>_<date>/`:

| File | What it is |
|---|---|
| `board_report.md` | **the deliverable** — verdict, waterfall, segment movers, current-year watch, caveats |
| `segment_analysis.md` | **four business lenses per segment** — concentration, accuracy, drift, confidence |
| `segment_master.csv` | every segment × every metric (rate, Z, expected/actual/O-E per year) |
| `backtest_report.md` | walk-forward out-of-sample validation (see below) |
| `segment_ave.csv` | per-segment expected vs actual (verdict year) |
| `ave_summary.csv` | the portfolio verdict row |
| `waterfall.csv` | the attribution bridge (volume / mix / rate / random) |
| `narrative.txt` | the auto board paragraph |
| `ave_report.json` | machine-readable audit record |

## What it produces (demo run, `data_1`)

- **Verdict — 2024:** expected **187.8**, actual **181**, **33rd percentile**, **GREEN**
  (normal range ~168–214, 100% rate coverage).
- **Waterfall 2023 → 2024:** volume + mix + (frozen) rate + random reconcile exactly to the
  actual.
- **2025 watch:** full-year expected ≈ 206, but only 139 reported — flagged as
  **development lag**, not a verdict (see below).

*(Rates are calibrated on 2021–2024; the immature 2025 is excluded from Step-1 calibration —
including it deflated rates ~10%. See `DECISIONS.md` D5.)*

## Segment analysis (`segment_analysis.md`) — four business lenses

Once the total is trusted, the business needs to know *where* to act. This report answers four
questions on the shipped rates (no new modelling — frozen rate × each year's premium vs actual):

1. **Concentration** — where the exposure is. *(Top 5 segments carry ~33% of expected losses;
   63 of 296 carry 80% — all top-5 are Realty.)*
2. **Accuracy** — the biggest per-segment misses, each tagged **structural** (persistent across
   years → a pricing signal, e.g. COR·Retail under-rated) or **noise** (a one-off spike).
3. **Emerging risk (drift)** — segments running **hot / cold** vs their own rate (O/E trend),
   limited to ≥5-loss segments so it isn't tiny-segment noise.
4. **Confidence** — how much expected loss rests on **thin, low-credibility** rates (the "big
   bets to validate"). *(~62% of expected losses sit in credible segments.)*

It's a **starter** — severity, sub-industry, and per-policy cuts are the obvious next depth.

## Does it hold up in backtest? (yes — walk-forward, out-of-sample)

Every run also writes `backtest_report.md`. It hides each target year and rebuilds the
**whole chain from prior years only** — rates recalibrated on years < Y (Step-1 GLM +
credibility), premium factors recalibrated on years < Y (Step-2) — then predicts Y and
checks the actual lands inside the model's 5–95% band. Nothing from year Y touches the
rates, factors, or band, so a pass is genuine out-of-sample evidence.

| Target | Trained on | Run month | Expected | Actual | Percentile | In 5–95% band | Segment ρ |
|---|---|---:|---:|---:|---:|:---:|---:|
| 2023 | 2021–2022 | m12 | 181.9 | 165 | 11th | ✓ | 0.58 |
| 2023 | 2021–2022 | m6  | 180.0 | 165 | 14th | ✓ | 0.58 |
| 2024 | 2021–2023 | m12 | 190.7 | 181 | 26th | ✓ | 0.56 |
| 2024 | 2021–2023 | m6  | 193.7 | 181 | 19th | ✓ | 0.56 |

**4/4 out-of-sample predictions in band.** Month 12 tests the rate model alone (full premium
known); **month 6 puts the premium projection out-of-sample too** — i.e. the live mid-year
forecast, both models blind to the year. Thin early folds (2023 sees only two training years)
sit slightly high but stay in band; the estimate tightens with history (the full rate table
lands 2024 at 181.8 vs 181). **2025 is excluded** from scoring — it is still developing
(expected ~206 vs 139 reported), the same reporting-lag caveat as the verdict.

Configure the folds in `config.yaml` (`backtest.folds`, `backtest.run_months`,
`backtest.immature_years`).

## Two design choices worth knowing

1. **The verdict runs on the last fully-developed year (2024), not the latest (2025).**
   Actual counts by year are 140 / 158 / 165 / 181 / **139** — 2025 *drops* despite premium
   growth. That is reporting/development lag: large claims take time to be reported and to
   breach the $200K line. Comparing a full-year *expectation* to a partial-year *actual*
   would manufacture a false RED, so 2025 is shown only as a flagged watch. (This is the
   same reason Step 1 reads rates at `reference_year: 2024`.)
2. **The rate table is frozen, so the waterfall's rate effect is ~0.** Step 3 *consumes*
   `rate_table_final.csv`; it never re-fits. Between annual recalibrations the year-over-year
   move in expected losses is therefore volume + mix (+ irreducible random noise) only.

## How it stays consistent with Steps 1 & 2

Step 3 is an **orchestrator** — it doesn't re-declare business choices, it points at the
two upstream configs:

```yaml
upstream:
  step1_config: "src/config/config.yaml"                # rates + actual-loss flagging
  step2_config: "src/premium_projection/config.yaml"    # premium projection machinery
  rate_table_glob: "outputs/**/rate_table_final.csv"    # newest frozen rate table
```

That guarantees the **actual** count is flagged with the *same* $200K threshold, cat-scope,
and segment definition the **rates** were calibrated on — otherwise expected-vs-actual is
apples-to-oranges. Change the data basis in one place (the upstream configs) and Step 3
follows. A `config_data2.yaml` variant points all three steps at `data_2`.

## The confidence band

The count is Poisson around the expected mean. If Step 1's dispersion (read automatically
from the rate table's `run_report.json`) exceeds the gate tolerance (1.5), the band widens
to a Negative Binomial with variance = φ·μ. On `data_1` dispersion is **1.15**, so Poisson
is used. A percentile inside 25–75 is GREEN, inside 10–90 AMBER, else RED.
