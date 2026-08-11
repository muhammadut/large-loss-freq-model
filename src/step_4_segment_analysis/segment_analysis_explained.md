# Segment Analysis — Results in Plain English

*A standalone read. It assumes you know nothing about insurance, statistics, or the model. By
the end you'll understand what a "segment" is, the four questions we answer about them, what
each result means, and what to actually do with it. Skim the **TL;DR**, then read the lenses
you care about.*

*(Segment codes below — `COVCP`/`COVCL` for coverage type, `COR`/`BCMS`/`NEWOR`/`ABandT`/`QC`/
`Atlantic` for region — are the raw codes exactly as they appear in the data and in
`segment_master.csv`, so every number here is verifiable. The industry names — Realty, Retail,
Education, etc. — are the meaningful part and carry the story.)*

---

## TL;DR

The model predicts **how many large insurance claims** (over $200,000) each slice of the book
should have. Once you trust the *total*, the next question is **"where do we act?"** — and for
that you have to look *inside* the total, slice by slice. We built four business lenses:

1. **Concentration** — *where is the risk?* A handful of slices carry most of it. **The top 5
   slices hold 33% of all expected large losses, and they're all Realty (real-estate property).**
2. **Accuracy** — *where is the model wrong, and does it matter?* Each miss is tagged
   **structural** (a repeating pattern → probably mispriced) or **noise** (a one-off). **Retail
   in the COR region is structurally under-rated** — it keeps having more losses than the rate
   predicts.
3. **Drift** — *what's changing?* Slices running hotter than their rate lately = emerging risk.
   **Education and Retail segments are heating up fast.**
4. **Confidence** — *which numbers can we trust?* Some slices carry real expected losses but rest
   on very few data points. **62% of expected losses sit in well-established slices; the rest
   lean on estimates.**

None of this is a new model — it's four different ways of *reading* the rates we already
shipped, next to what actually happened.

---

## Part 1 — What's a "segment," and why slice the book at all?

A "book of business" is all the policies an insurer covers. The **portfolio total** ("we expect
~188 large losses this year") is useful for the boardroom, but useless for *action* — you can't
"raise the price of the whole book" or "watch the whole book." You act on **slices**.

We slice every policy three ways and combine them:

```
   coverage type   ×   region   ×   industry     =   a "segment"
   (COVCP / COVCL)     (COR, QC…)   (Realty…)        "COVCP · QC · Retail"
```

That gives ~**300 segments**. Each one gets its own predicted large-loss count. The four lenses
below are just four different questions you can ask across those 300 slices.

*(`COVCP` / `COVCL` are coverage types — roughly commercial-property vs commercial-liability
cover. `COR`, `BCMS`, `ABandT`, `NEWOR`, `QC`, `Atlantic` are grouped rating regions. You don't
need the exact decoding to follow the story — read them as "a coverage, in a region, for an
industry.")*

---

## Part 2 — The one number behind everything: **expected vs actual**

Every lens is built from the same simple comparison, per segment:

> **Expected** = the model's rate for that slice **×** how much premium that slice has.
> **Actual** = how many large losses that slice *really* had.

Example: if `COVCP · COR · Realty` is rated so that its premium implies **16.5 expected** large
losses, and it actually had **20**, then it ran **hot** — more losses than the rate implied. Do
that for all 300 slices and every lens falls out of it.

One derived number you'll see a lot: the **O/E ratio** = Actual ÷ Expected.

- **O/E = 1.0** → bang on the rate.
- **O/E = 2.0** → twice as many losses as the rate predicted (running hot).
- **O/E = 0.5** → half as many (running cold).

---

## Part 3 — Lens 1: Concentration — *where is the risk?*

**The business question:** if we only had time to price or watch a handful of slices, which
ones? **The finding:** the book is **very top-heavy**.

> The largest **5** segments carry **33%** of all expected large losses. The top **10** carry
> **43%**. Just **63 of 296** segments account for **80%** of the expected losses — the other
> ~230 barely move the needle.

| # | Segment | Expected large losses | Share | Running total |
|---:|---|---:|---:|---:|
| 1 | COVCP · COR · **Realty** | 16.5 | 8.8% | 8.8% |
| 2 | COVCP · BCMS · **Realty** | 14.0 | 7.5% | 16.2% |
| 3 | COVCP · NEWOR · **Realty** | 13.3 | 7.1% | 23.3% |
| 4 | COVCP · ABandT · **Realty** | 12.2 | 6.5% | 29.8% |
| 5 | COVCP · Atlantic · **Realty** | 6.7 | 3.6% | 33.4% |
| 6 | COVCP · ABandT · Contractors | 5.3 | 2.8% | 36.2% |
| 7 | COVCP · COR · Restaurant | 3.8 | 2.0% | 38.2% |

**Reading it:** the **top five slices are all Realty** (large-loss exposure on real-estate
property, spread across regions). That's the single most important fact in the whole analysis:
**Realty property is the engine of large-loss risk.** If a pricing review only ever looked at
five things, it's these.

**This is the "80/20 rule" in action** — a small number of slices drive most of the outcome. It
tells you where attention, pricing scrutiny, and monitoring should concentrate, and — just as
usefully — which ~230 slices are *immaterial* and not worth agonising over.

---

## Part 4 — Lens 2: Accuracy — *where is the model wrong, and does it matter?*

A model can nail the portfolio total while being wrong about individual slices (the errors
cancel out). So we check each slice: **did its actual come in above or below its expected — and
is that a repeating pattern or a one-time fluke?**

The pattern part is crucial. One hot year is weather; **three hot years is climate.** So each
miss is tagged:

- **structural** = actual landed on the same side of expected in most of the last three years →
  the rate is probably wrong, a real pricing signal.
- **noise** = a one-off swing → don't over-react.

**Slices with MORE losses than expected (possible under-pricing):**

| Segment | Expected | Actual | Gap | Pattern |
|---|---:|---:|---:|:--:|
| COVCP · ABandT · Realty | 12.2 | 20 | **+7.8** | noise *(one-year spike)* |
| COVCP · COR · **Retail** | 2.5 | 8 | **+5.5** | **structural ⚠** |
| COVCP · COR · Realty | 16.5 | 20 | +3.5 | **structural ⚠** |
| COVCP · COR · Restaurant | 3.8 | 7 | +3.2 | noise |
| COVCP · ABandT · Hospitality | 2.1 | 4 | +1.9 | **structural ⚠** |

**Slices with FEWER losses than expected (possible over-pricing):**

| Segment | Expected | Actual | Gap | Pattern |
|---|---:|---:|---:|:--:|
| COVCL · COR · Contractors | 2.9 | 0 | −2.9 | noise |
| COVCP · NEWOR · Contractors | 2.6 | 0 | −2.6 | **structural ⚠** |
| COVCP · ABandT · Restaurant | 3.4 | 1 | −2.4 | noise |
| COVCP · Atlantic · Retail | 1.9 | 0 | −1.9 | **structural ⚠** |

**Reading it — and why the tags matter:**

- The **biggest single miss** (`COVCP · ABandT · Realty`, +7.8) is tagged **noise** — it had a
  spike *this* year but not in the prior years, so it's most likely bad luck, not a broken rate.
  **Don't re-price on it.**
- `COVCP · COR · Retail` is only the *second*-biggest miss (+5.5) but it's tagged **structural** —
  it has run hot *repeatedly*. That's the one worth a pricing review, even though its single-year
  gap is smaller. **The tag changes the priority order.**

Overall, the model's segment **rank accuracy is 0.56** (on a 0–1 scale) — meaning it orders
slices from riskiest to safest reasonably well, not just the grand total. Not perfect; solidly
useful.

---

## Part 5 — Lens 3: Drift — *what's changing? (the early-warning lens)*

Concentration and accuracy are snapshots. **Drift is the trend** — the smoke detector. It asks:
which slices are running **hotter or colder than their own rate**, and *getting more so* over
time? A slice whose O/E climbs year after year is an **emerging risk** you want to catch *before*
it shows up as a bad year.

To avoid false alarms from tiny slices (where one extra claim swings everything), we only look at
slices with **at least 5 historical losses**.

| Segment | O/E 2022 | O/E 2023 | O/E 2024 | Recent | Signal |
|---|---:|---:|---:|---:|:--:|
| COVCP · ABandT · **Education** | 0.0 | 1.9 | **6.4** | 4.4 | 🔥 HOT, climbing |
| COVCL · QC · Contractors | 1.5 | 3.8 | 2.2 | 2.9 | 🔥 HOT |
| COVCP · QC · Retail | 4.5 | 4.0 | 1.7 | 2.8 | 🔥 HOT *(but cooling)* |
| COVCP · NEWOR · B&P Services | 1.8 | 1.5 | 3.8 | 2.7 | 🔥 HOT, climbing |
| COVCP · COR · **Retail** | 1.0 | 1.4 | **3.3** | 2.4 | 🔥 HOT, climbing |

**Reading it:**

- `COVCP · ABandT · Education` is the standout: O/E went 0 → 1.9 → **6.4**. It's had a sharp,
  accelerating rise in large losses relative to its rate. **Top of the watch list.**
- `COVCP · COR · Retail` shows up here **again** (1.0 → 1.4 → 3.3) — remember it was also flagged
  as *structurally under-rated* in Lens 2. Two independent lenses pointing at the same slice is a
  strong signal: this isn't noise, it's a slice the rate hasn't caught up with.
- Note the nuance: `COVCP · QC · Retail` is "hot" but its O/E is actually *falling* (4.5 → 1.7) —
  it was hot and is cooling. The trend direction matters as much as the level.

**What you do with it:** these are the slices to investigate *now* — pull the recent claims, ask
whether something changed (a big new client, a coverage change, a genuine risk shift), and decide
whether the rate needs to move before next year proves it the hard way.

---

## Part 6 — Lens 4: Confidence — *which numbers can we trust?*

Not every predicted number is equally solid. A slice with **many** historical losses has a rate
you can lean on; a slice with **2** losses has a rate that's mostly an educated guess (the model
"borrows" from its wider industry to fill the gap — a technique called *credibility*, scored 0–1,
where 1 = fully trust the slice's own data).

The danger is a slice that carries **real expected losses** but rests on **thin data** — a big
bet on a shaky number.

> **62%** of all expected large losses sit in **well-established** slices (34 slices with ≥5
> losses each). The other **262** slices are thin and lean on estimates. Below are the **"big
> bets on thin data"** — meaningful expected losses, low confidence:

| Segment | Expected | Confidence (0–1) | Historical losses |
|---|---:|---:|---:|
| COVCP · NEWOR · Contractors | 2.6 | 0.66 | 3 |
| COVCP · COR · Contractors | 2.4 | 0.67 | 4 |
| COVCP · Atlantic · Retail | 1.9 | 0.52 | 4 |
| COVCL · COR · Restaurant | 1.8 | 0.55 | **1** |

**Reading it:** the `COVCL · COR · Restaurant` slice expects ~1.8 large losses but has only **1**
in its whole history — that rate is essentially borrowed from the broader restaurant industry,
not observed. **Before you act on any of these (raise a price, flag a risk), validate them** —
they're the ones most likely to be an artifact of thin data rather than a real signal.

**Why this lens exists:** it stops you from confidently acting on a number that's really a guess.
It pairs with the others — e.g. if a slice shows up as "structurally under-rated" (Lens 2) *and*
"high confidence" (this lens), that's a strong case to re-price; if it's "under-rated" but "thin,"
you investigate first.

---

## Part 7 — How the four lenses fit together (one worked example)

Take `COVCP · COR · Retail` (retail-industry property in the COR region). It appears in three
lenses at once:

```
   Lens 2 (Accuracy):  expected 2.5, actual 8  →  STRUCTURAL under-rating (repeats)
   Lens 3 (Drift):     O/E 1.0 → 1.4 → 3.3      →  HOT and climbing
   Lens 4 (Confidence): enough history to be credible-ish
   ───────────────────────────────────────────────────────────────────────────
   Conclusion: this slice is genuinely running hotter than its rate, consistently,
   and it's not a thin-data fluke → a real candidate for a rate increase.
```

That's the point of having four lenses instead of one number: **agreement across independent
views turns a "huh, that's high" into an actionable, defensible decision.** A one-off spike (like
`COVCP · ABandT · Realty`'s +7.8) lights up *one* lens and gets correctly set aside; a real
problem lights up *several*.

---

## Part 8 — How it was built

No new model. It's the **shipped rates**, read four ways:

```
   For each of the ~300 segments, and each recent year (2022, 2023, 2024):
     expected = (the frozen rate for that slice)  ×  (that slice's premium that year)
     actual   = the real count of large losses in that slice that year
     O/E      = actual ÷ expected

   Then:
     Lens 1  sort slices by expected, add up the shares          → concentration
     Lens 2  compare expected vs actual, check the 3-year pattern → accuracy + structural/noise
     Lens 3  track O/E over the three years                       → drift (limited to ≥5-loss slices)
     Lens 4  read each slice's credibility + history count        → confidence
```

A few guardrails that keep it honest:

- **Frozen rates.** It uses the exact rate table the business will use — not a special version —
  so what you see is what you'd price on.
- **Small slices are quarantined.** The drift lens ignores slices with <5 historical losses,
  because O/E on a tiny slice swings wildly on a single claim.
- **"Structural" needs a pattern.** A miss is only tagged structural if it repeats across years,
  not on one bad year.

Reproduce it (run Step 1 at least once first, so a rate table exists):

```bash
python src/run.py --config src/config/config.yaml                                 # Step 1 → rates
python src/step_4_segment_analysis/run.py --config src/step_4_segment_analysis/config.yaml       # → this report
```

That second command writes `step_4_segment_analysis.md` (the technical version of this) and
`segment_master.csv` (all ~300 slices × every metric) into a dated `outputs/step_4_segment_analysis/…`
folder.

---

## Part 9 — Honest caveats

- **It's a starter, not the final word.** These are the four highest-value cuts to get moving.
  The obvious next depth: **severity** (how *big* the losses are, not just how many),
  **sub-industry** (finer slices), and **per-policy** drill-downs.
- **It counts, it doesn't cost.** Everything here is about the *number* of large losses. A slice
  with many small-ish large losses and one with a few enormous ones look similar here — severity
  is a separate lens we haven't built yet.
- **Percentages mislead on tiny slices.** A slice going from 0 to 2 losses is an "infinite %
  increase" but barely matters in dollars. That's exactly why concentration weights by expected
  losses and drift ignores sub-5-loss slices.
- **Confidence is about data volume, not correctness.** A "high confidence" rate can still be
  wrong if the world changed — that's what the drift lens is for. Use them together.

---

## Glossary

| Term | Plain meaning |
|---|---|
| **Segment / slice** | one coverage × region × industry combination (~300 total). |
| **Large loss** | a claim over **$200,000** — the ones tracked. |
| **Expected** | the model's predicted large-loss count for a slice (rate × premium). |
| **Actual** | how many large losses the slice really had. |
| **O/E ratio** | Actual ÷ Expected. >1 = hotter than the rate; <1 = colder. |
| **Concentration** | how much of the total risk sits in a few slices (the 80/20 view). |
| **Structural** | a miss that repeats across years → a real signal (probably mispriced). |
| **Noise** | a one-off swing → don't over-react. |
| **Drift** | how a slice's O/E is trending over time (the early-warning view). |
| **Credibility / confidence (0–1)** | how much a slice's rate rests on its own data vs borrowed from its industry. |
| **Rank accuracy (0.56)** | how well the model orders slices from riskiest to safest (0 = random, 1 = perfect). |
