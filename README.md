# Large-Loss Frequency Model

> Estimate **how many** large losses a commercial P&C portfolio should expect — per
> segment and in total — so that actual experience can be judged *"normal vs.
> structural,"* and the segment rates can feed pricing. **Frequency first**, not severity.

---

## 1. The model in one formula

For each **segment** (a slice of the book = `Coverage type × Region × Industry`), the
expected number of large losses is its **exposure** times its **frequency rate**:

```
   expected large losses  =  exposure  ×  frequency_rate
                  λ_s      =     E_s    ×       f_s
```

The frequency rate `f_s` is what we calibrate. A Poisson GLM learns it for every
segment at once, on the log scale (because rates *multiply*):

```
   log( expected count )  =  log(exposure)  +  β0  +  β_coverage  +  β_region  +  β_industry  +  β_year
                             └── offset ──┘   └──────── the segment "relativities" ────────┘   └ on-level ┘
```

Read it piece by piece:

| Term | Plain meaning |
|---|---|
| `log(exposure)` — the **offset** | Pins the denominator in (premium, or TIV) so the model returns a **rate**, not a raw count. Coefficient forced to 1. |
| `β0` | The baseline log-rate for the reference segment. |
| `β_coverage, β_region, β_industry` | The **relativities** — how each segment differs from baseline. `exp(β) = ` a multiplier (e.g. `2.2×`). |
| `β_year` | The **year effect** — one dial per year that soaks up price/inflation shifts so the rate is "on-levelled" to one consistent year. |

Then a **credibility** step smooths thin segments toward their industry average, so a
segment with one stray loss doesn't get a wild rate:

```
   final_rate_s  =  Z_s · glm_rate_s  +  (1 − Z_s) · industry_complement_s
```

`Z` (0–1) is "how much we trust this segment's own data." Lots of history → `Z ≈ 1`
(keep your own rate); little history → `Z ≈ 0` (borrow your industry's).

**That `final_rate` per segment is the deliverable** (`rate_table_final.csv`).

---

## 2. What it does (end to end)

```
        raw extract  (2.88M policy-coverage rows, 2021–2025)
              │
              │   large loss = incurred ≥ $200,000 ;  segment = Coverage × Region × Industry
              ▼
   ┌────────────────────────────────┐
   │   segment × year panel          │   large-loss count + exposure per cell
   └────────────────────────────────┘
              │
              ▼   Poisson GLM  +  year effect (on-levelling)
   ┌────────────────────────────────┐
   │   raw GLM rate per segment      │   "losses per $1M — before smoothing"
   └────────────────────────────────┘
              │
              ▼   hierarchical credibility (shrink thin segments to industry)
   ┌────────────────────────────────┐
   │   FINAL rate per segment   ★    │   →  rate_table_final.csv   (THE DELIVERABLE)
   └────────────────────────────────┘
              │
              ▼   Step 2 (premium projection)  +  Step 3 (expected vs actual) — both built
        expected count = Σ ( rate × projected premium )  →  percentile / traffic-light / board narrative
```

This repo covers the model **end to end**: Step 1 → the rate table, Step 2 → projected
premium, Step 3 → the board-facing expected-vs-actual verdict (GREEN/AMBER/RED + waterfall
+ narrative).

---

## 3. How credibility tames the noise (the trust mechanism)

A raw GLM hands every segment a rate with equal confidence — it can't tell a
well-observed rate from a one-loss fluke. Credibility is the fix:

```
   THIN segment  (e.g. Fishing, 0 losses)        DATA-RICH segment  (e.g. Realty, 74 losses)
        raw GLM rate = 5.6   (noise)                  raw GLM rate = 0.46   (trustworthy)
               │  Z ≈ 0.00                                   │  Z ≈ 0.92
               ▼                                             ▼
        final ≈ industry average (0.39)              final ≈ its own rate (0.46)
        "borrow the neighbours"                      "keep your own"
```

The portfolio total barely moves (credibility only **redistributes** risk); the
nonsense thin-segment rates collapse to sensible industry levels.

---

## 4. Why you can trust the segment rates (due diligence)

Every run self-validates with **8 gates** and a **model-diagnostics report**. On the
current data:

| Evidence | Result | Means |
|---|---|---|
| **Out-of-sample backtest** | trained on 2021–23, predicted **184** for 2024; actual **181** | the model genuinely predicts a year it never saw |
| **Dispersion** | **1.12** (≈1) | plain Poisson's spread assumption holds — no fancier model needed |
| **Robustness** | drop the newest year → final-rate p95 move **33%**, **0** segments >50% | the rates don't hinge on one year |
| **Total preservation** | credibility drift **+3.7%** (warn) | the honest size of the V1 credibility approximation, once the immature year is excluded (Phase-2 refinement noted) |
| **Credibility** | 88% of segments are thin → shrunk to industry | no single-loss segment sets a published rate |

> **Calibrated on fully-developed years (2021–2024).** The immature 2025 is deliberately
> excluded — including it deflated rates ~10% (its losses aren't fully reported yet). See
> `DECISIONS.md` D5.

The full rationale — every decision, what we rejected, and the evidence — is in
**[`DECISIONS.md`](src/docs/DECISIONS.md)**.

---

## 5. Quick start

```bash
# from the repo root
python src/run.py --config src/config/config.yaml        # premium lens (default)
python src/run.py --config src/config/config_tiv.yaml    # TIV lens (cross-check)
```
Needs Python with `pandas, numpy, scipy, statsmodels, pyyaml`. A run reads the ~600 MB
CSV once (~1 min) — the terminal is quiet while it loads, then prints a summary.

---

## 6. What you get — a dated run folder

Every run drops its artifacts into a timestamped folder so runs never overwrite:

```
outputs/annual_recalibration_2025_<date_time>/
├── rate_table_final.csv     ← THE DELIVERABLE — the credibilized rate per segment
├── run_summary.md           ← ★ human report: every check + what it MEANS (open this first)
├── model_diagnostics.md     ← classical fit stats (deviance, AIC/BIC, p-values), each explained
└── run_report.json          ← machine-readable record (diff this across yearly refits)
```

Everything is **regenerated dynamically** each run — change the data, threshold, or lens
(via config) and every number, verdict, and comment updates to match.

---

## 7. Repo map

| Path | What it is |
|---|---|
| `src/large_loss_freq/` | **Step 1** — the rate calibration pipeline (config-driven; see `src/README.md`) |
| `src/premium_projection/` | **Step 2** — projects premium per segment, then × rate → expected losses (see its README) |
| `src/expected_vs_actual/` | **Step 3** — expected vs actual: percentile, traffic-light, waterfall, board narrative (see its README) |
| `src/config/config.yaml` | the single source of truth for every Step-1 business choice |
| `data/basic_data_1.csv` | the source extract (2021–2025) |
| `outputs/` | dated run folders (generated) |
| **Documentation** | |
| [`DECISIONS.md`](src/docs/DECISIONS.md) | every modeling decision (Steps 1–3), why, what we rejected, the evidence |
| `src/docs/pipeline_guide.md` | how the code/config/pipeline work across the three steps |
| `src/docs/methodology.md` | the full statistical methodology reference |
| `src/docs/practical_guide.md` | the end-to-end implementation spec + worked example |
| `src/config/config.reference.md` | every config field, documented |

---

## 8. Step 2 — premium projection (built)

Step 1 produces **rates**; Step 2 (`src/premium_projection/`) produces the **premium** to
multiply them by:

```
   expected large losses  =  Σ ( rate × projected premium )   per segment
```

```bash
python src/premium_projection/run.py --config src/premium_projection/config.yaml
```

It learns a per-segment, per-month **growth factor** from history (validated by backtest:
**~2.7% dollar-weighted error**, ~89% of segments within ±10%), applies it to the visible
book, and writes **expected losses per segment**. See `src/premium_projection/README.md`.

> **Both steps run on `data_1` by default**, so the rate and the premium share one extract
> and the expected-loss total is fully self-consistent. A `data_2` variant exists for each
> step (true policy dates, slightly tighter premium fit) — but `data_2` is a different
> extract (~5% more premium, ~2× the losses), so only use it for *both* steps together.

---

## 9. Step 3 — expected vs actual (the board deliverable, built)

Step 3 (`src/expected_vs_actual/`) closes the loop: it multiplies the Step-1 rate by the
Step-2 projected premium, compares the **expected** count to the **actual**, and turns it
into the board answer — a percentile, a traffic-light, an attribution waterfall, and a
plain-English narrative.

```bash
python src/expected_vs_actual/run.py --config src/expected_vs_actual/config.yaml
#   -> outputs/expected_vs_actual/<run>/board_report.md   (the deliverable)
```

**Demo verdict (2024, the last fully-developed year):** expected **187.8**, actual **181**
→ **33rd percentile**, **GREEN** (normal range ~168–214, 100% rate coverage). It also writes
an attribution waterfall (volume / mix / rate / random) and a **segment analysis** — four
business lenses (concentration, per-segment accuracy, emerging-risk drift, confidence) in
`segment_analysis.md`.

The verdict runs on **2024**, not 2025, on purpose: actual counts by year are
140/158/165/181/**139**, and 2025 *falls* because it is still being reported (development
lag). 2025 is shown as a flagged watch (full-year expected ≈ 200 vs 139 reported so far),
never a verdict — comparing a full-year expectation to a partial-year actual would fake a
RED. See `src/expected_vs_actual/README.md`.

**Backtested walk-forward (out-of-sample).** Each run also writes `backtest_report.md`: for
each fold year it recalibrates *both* the rates and the premium factors on prior years only,
then predicts the year blind. On `data_1`, **4/4** OOS predictions (2023, 2024 × run-months
6 and 12) land inside the 5–95% band — month 6 puts the premium projection out-of-sample
too, validating the *live* mid-year forecast, not just the rate model.

**The full model, one line:**

```bash
python src/run.py --config src/config/config.yaml                                   # Step 1 → rates
python src/premium_projection/run.py --config src/premium_projection/config.yaml    # Step 2 → premium
python src/expected_vs_actual/run.py --config src/expected_vs_actual/config.yaml    # Step 3 → verdict
```
