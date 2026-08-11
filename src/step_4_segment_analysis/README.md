# Step 4 — Segment analysis

Once the portfolio total is trusted (Step 3), the business needs to know **where to act**.
This step answers that with four lenses on the **shipped rates** — no new model, just the
Step-1 rate × each year's premium vs the actual counts.

> **New here? Read [`segment_analysis_explained.md`](segment_analysis_explained.md)** — a
> standalone, zero-jargon walkthrough of all four lenses and what to do with them.

## Run it

```bash
python src/step_4_segment_analysis/run.py --config src/step_4_segment_analysis/config.yaml
```

It reads the **latest** `rate_table_final.csv` (so run Step 1 at least once first),
rebuilds the Step-2 premium panels itself, and writes to
`outputs/step_4_segment_analysis/<run>_<date>/`:

| File | What it is |
|---|---|
| `step_4_segment_analysis.md` | the four business lenses (below) |
| `segment_investigation.md` | **validates the misses** — significance test, calibration check, per-segment dossiers |
| `segment_master.csv` | every segment × every metric (rate, Z, expected/actual/O-E per year, p-values, classification) |

## The four lenses

1. **Concentration** — *where is the exposure?* A few segments carry most of it (top 5 ≈ 33%
   of expected large losses on `data_1`; all Realty). Where pricing/monitoring belongs.
2. **Accuracy** — *where is the model off, and does it matter?* Biggest per-segment misses,
   each tagged **structural** (persistent across years → a pricing signal) vs **noise**
   (a one-off spike). Plus the segment rank calibration (Spearman).
3. **Emerging risk (drift)** — *what's changing?* Segments running **hot / cold** vs their own
   rate (O/E trend), limited to ≥5-loss segments so it isn't tiny-segment noise.
4. **Confidence** — *which numbers can we trust?* How much expected loss sits on **thin,
   low-credibility** rates — the "big bets to validate" before any pricing move.

## Investigating the misses (`segment_investigation.md`)

The accuracy lens flags where actual ≠ expected; this report answers **is that miss real, or
just rare-event noise?** Large-loss counts are small and lumpy, so most big-looking gaps are
chance. For each material segment it computes the Poisson probability of the actual given the
predicted rate, checks the portfolio calibration (how many segments fall outside their band vs
how many chance predicts), and writes a **dossier** on the statistically real ones — multi-year
trajectory, whether the losses are spread across many policies or one event, and the loss sizes.

On `data_1` it validates the model (2 of 40 material segments significantly high, 0 low —
right at chance) and separates the two real signals: `COVCP · COR · Retail` (a persistent,
broad-based under-rating → investigate) from `COVCP · ABandT · Realty` (cold-then-hot, correctly
rated over the window → just watch). Tune `significance_alpha` and `dossiers` in `config.yaml`.

## Dependencies & consistency

Self-contained given Steps 1 & 2 exist. It imports:
- `step_1_frequency` (Step 1) — to flag actual losses the **same way the rates were calibrated**
  ($200K threshold, cat-scope, segment keys). This is what keeps expected-vs-actual honest.
- `step_2_premium` (Step 2) — to rebuild each year's premium per segment.

Business choices are not restated here; the config points at the Step-1 and Step-2 configs:

```yaml
upstream:
  step1_config: "src/config/config.yaml"
  step2_config: "src/step_2_premium/config.yaml"
  rate_table_glob: "outputs/**/rate_table_final.csv"
```

Tune the lenses (trend years, drift thresholds, materiality) in `config.yaml → analysis`.

## Caveats

It **counts**, it doesn't **cost** (frequency, not severity). Percentages mislead on tiny
segments — which is why concentration weights by expected losses and drift ignores sub-5-loss
segments. A **starter**: severity, sub-industry, and per-policy cuts are the obvious next depth.
