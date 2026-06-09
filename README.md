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
              ▼   Part 2  (built next — see pipeline_guide.md §9)
        expected count = Σ ( rate × projected exposure )  →  percentile / traffic-light / board narrative
```

This repo covers everything **down to the rate table**. The forward projection
(turning rates into a board-facing expected-vs-actual number) is the next phase.

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
| **Dispersion** | **1.15** (≈1) | plain Poisson's spread assumption holds — no fancier model needed |
| **Robustness** | drop the newest year → final rates move ≤29%, **0** segments >50% | the rates don't hinge on one year |
| **Total preservation** | credibility drift **+0.43%** | smoothing redistributes risk without moving the total |
| **Credibility** | 86% of segments are thin → shrunk to industry | no single-loss segment sets a published rate |

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
| `src/` | the calibration pipeline (config-driven; see `src/README.md`) |
| `src/config/config.yaml` | the single source of truth for every business choice |
| `data/basic_data_1.csv` | the source extract (2021–2025) |
| `outputs/` | dated run folders (generated) |
| **Documentation** | |
| [`DECISIONS.md`](src/docs/DECISIONS.md) | every modeling decision, why, what we rejected, the evidence |
| `src/docs/pipeline_guide.md` | how the code/config/pipeline work + how to build Part 2 |
| `src/docs/methodology.md` | the full statistical methodology reference |
| `src/docs/practical_guide.md` | the end-to-end implementation spec + worked example |
| `src/config/config.reference.md` | every config field, documented |

---

## 8. Next step (Part 2 — predictions)

This pipeline produces **rates**. The next phase consumes them:

```
   expected = Σ ( final_rate × projected_exposure )   →   range / percentile / traffic-light
```

The hand-off spec — the formula, a worked example, and the four consistency rules
(match the lens, match the rate level, handle unseen segments, don't re-fit) — is in
**`src/docs/pipeline_guide.md` §9**.
