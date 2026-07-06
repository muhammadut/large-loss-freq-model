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
| `segment_ave.csv` | per-segment expected vs actual (verdict year) |
| `ave_summary.csv` | the portfolio verdict row |
| `waterfall.csv` | the attribution bridge (volume / mix / rate / random) |
| `narrative.txt` | the auto board paragraph |
| `ave_report.json` | machine-readable audit record |

## What it produces (demo run, `data_1`)

- **Verdict — 2024:** expected **181.8**, actual **181**, **50th percentile**, **GREEN**
  (normal range 160–204, 100% rate coverage).
- **Waterfall 2023 → 2024:** 162.3 `+17.3 volume` `+2.2 mix` `+0.0 rate` = 181.8 expected
  `−0.8 random` = 181 actual. The pieces reconcile exactly.
- **2025 watch:** full-year expected ≈ 200, but only 139 reported — flagged as
  **development lag**, not a verdict (see below).

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
