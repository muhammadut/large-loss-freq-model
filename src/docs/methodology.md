# Expected Large Loss Frequency Model: Methodology

> **Purpose:** Establish a rigorous, transparent, and refreshable framework for estimating expected large loss frequency at the portfolio level, contextualising actual experience within statistical ranges, and decomposing deviations into actionable drivers.
>
> **Guiding principles:** Frequency first (not severity). Explainability over sophistication. Portfolio-aware and refreshable. Pricing-ready outputs. Must support board-level narratives.

---

## Table of Contents

1. [Statistical Foundation](#1-statistical-foundation)
2. [Portfolio-Aware Frequency Estimation](#2-portfolio-aware-frequency-estimation)
3. [Deviation Attribution Framework](#3-deviation-attribution-framework)
4. [Implementation Approach](#4-implementation-approach)
5. [Industry Context and References](#5-industry-context-and-references)

---

## 1. Statistical Foundation

### 1.1 Why Model Large Loss Frequency?

Large losses (those exceeding a defined threshold, e.g. $500K or $1M) are low-frequency, high-impact events. Without an explicit expectation framework, every large loss is interpreted as adverse, even when it falls within the normal range of statistical variation for the portfolio. A frequency model provides:

- A **point estimate** of expected large loss count for a given exposure base
- A **distributional range** (percentiles / confidence intervals) that separates routine volatility from structural change
- A **decomposition** of actual-vs-expected gaps into business-meaningful drivers

### 1.2 Core Distributional Assumptions

#### 1.2.1 Poisson Distribution

The natural starting point for count data. If large losses arrive independently at a constant rate per unit of exposure, the count $N$ in a period follows:

$$P(N = k) = \frac{e^{-\lambda} \lambda^k}{k!}, \quad k = 0, 1, 2, \ldots$$

where $\lambda$ is the expected count (mean = variance).

**Key property:** The Poisson is fully characterised by a single parameter $\lambda$. For a portfolio with exposure $E$ and frequency rate $f$ (losses per unit of exposure), the expected count is:

$$\lambda = f \times E$$

**When Poisson is appropriate:**
- Losses are independent across policies
- The frequency rate is stable within a homogeneous segment
- There is no material unobserved heterogeneity within the segment

#### 1.2.2 Negative Binomial Distribution

When the portfolio contains unobserved heterogeneity (different sub-populations with different underlying rates), the observed count variance exceeds the Poisson mean ("overdispersion"). The Negative Binomial arises naturally as a **Poisson-Gamma mixture**: if $\lambda$ itself follows a Gamma distribution across risk units, the marginal count is Negative Binomial.

$$P(N = k) = \binom{k + r - 1}{k} \left(\frac{r}{r + \mu}\right)^r \left(\frac{\mu}{r + \mu}\right)^k$$

where $\mu$ is the mean count and $r$ is the dispersion parameter. The variance is:

$$\text{Var}(N) = \mu + \frac{\mu^2}{r}$$

When $r \to \infty$, the Negative Binomial converges to the Poisson. Smaller $r$ indicates greater overdispersion.

**When to prefer Negative Binomial:**
- Heterogeneity across segments is not fully captured by observable rating factors
- Empirical variance-to-mean ratio materially exceeds 1.0
- The portfolio mixes lines of business or geographies with different underlying rates

#### 1.2.3 Other Candidate Distributions

| Distribution | Use Case | Notes |
|---|---|---|
| **Zero-Inflated Poisson (ZIP)** | Excess of zero-count periods relative to Poisson | Structural zeros (segments that *cannot* produce a large loss) vs sampling zeros |
| **Mixed Poisson (general)** | Rate heterogeneity modelled via mixing distribution other than Gamma | Allows heavier tails than Negative Binomial |
| **Binomial** | Fixed, known number of exposure units, each with independent loss probability | Rarely used for large losses (exposure count often unknown or variable) |

**Recommendation:** Start with Poisson at the segment level. If goodness-of-fit diagnostics (deviance residuals, chi-squared test, variance-to-mean ratio) indicate overdispersion, upgrade to Negative Binomial. This is consistent with standard actuarial practice in GLM-based pricing (see CAS Monograph No. 5, Goldburd et al.).

### 1.3 Estimating Expected Frequency from Exposure Data

#### 1.3.1 Rate-per-Exposure Approach

The fundamental building block is an **observed frequency rate**:

$$\hat{f}_s = \frac{n_s}{E_s}$$

where $n_s$ is the observed large loss count in segment $s$ and $E_s$ is the exposure measure (earned premium, policy count, or insured value — see Section 2.2 for choice of measure).

The expected count for a future period with exposure $E_s'$ is:

$$\hat{\lambda}_s = \hat{f}_s \times E_s'$$

When multiple years of history are available, pool across periods with appropriate adjustments:

$$\hat{f}_s = \frac{\sum_{t} n_{s,t}}{\sum_{t} E_{s,t}}$$

This assumes stationarity of the underlying rate. Where there is evidence of trend, apply a trend factor (see Section 1.5).

#### 1.3.2 GLM-Based Estimation

For richer segmentation, a **Generalised Linear Model** with a log link and Poisson (or Negative Binomial) error structure provides a principled framework:

$$\log(\lambda_i) = \log(E_i) + \beta_0 + \beta_1 x_{i1} + \beta_2 x_{i2} + \ldots$$

where $E_i$ enters as an **offset** (exposure), and $x_{i1}, x_{i2}, \ldots$ are segment covariates (line of business, geography, size band, etc.). This approach:

- Produces relativities across segments
- Handles sparse cells by borrowing strength from main effects
- Is the actuarial standard for pricing (CAS Monograph No. 5)
- Outputs directly translate to pricing loads

### 1.4 Confidence Intervals and Percentile Ranges

Placing actual experience "in context" requires distributional bounds around the expected count.

#### 1.4.1 Exact Poisson Intervals

For an expected count $\lambda$, the probability of observing $k$ or fewer losses is:

$$P(N \leq k \mid \lambda) = \sum_{j=0}^{k} \frac{e^{-\lambda} \lambda^j}{j!}$$

This can be inverted to find **percentile bounds**. The exact 95% interval for the count is derived from the chi-squared relationship:

$$\left[ \frac{1}{2} \chi^2_{2k, \, 0.025}, \quad \frac{1}{2} \chi^2_{2(k+1), \, 0.975} \right]$$

where $k$ is the observed count.

**Practical interpretation:** If $\lambda = 8$ expected large losses per year, the 5th–95th percentile range is approximately [3, 14]. Any actual count within this range is **consistent with random volatility** and does not, by itself, indicate a structural problem.

#### 1.4.2 Negative Binomial Intervals

When using the NB distribution, percentiles are obtained from the NB quantile function (readily available in R's `qnbinom()` or Python's `scipy.stats.nbinom.ppf()`).

#### 1.4.3 Simulation-Based Intervals

For complex portfolios where the aggregate count is the sum of many heterogeneous segment-level Poisson/NB counts:

1. For each segment $s$, draw $N_s \sim \text{Poisson}(\lambda_s)$ (or NB)
2. Compute $N_{\text{total}} = \sum_s N_s$
3. Repeat 10,000–50,000 times
4. Extract empirical percentiles from the simulated distribution of $N_{\text{total}}$

This approach naturally captures the correlation structure (or lack thereof) across segments and produces a portfolio-level prediction interval.

#### 1.4.4 Reporting Percentile Bands

| Band | Interpretation | Narrative |
|---|---|---|
| Actual within 25th–75th percentile | **Within normal range** | "Experience is consistent with expectations" |
| Actual within 10th–25th or 75th–90th percentile | **Moderately unusual** | "Experience is somewhat [favourable/adverse] but within plausible variation" |
| Actual below 10th or above 90th percentile | **Statistically notable** | "Experience warrants investigation — may indicate structural shift" |
| Actual below 5th or above 95th percentile | **Exceptional** | "Strong evidence of deviation from expectations" |

### 1.5 Handling Thin Data

Large losses are, by definition, rare. Many segments will have very few or zero observed losses, making raw frequency rates unreliable.

#### 1.5.1 Credibility Weighting (Buhlmann-Straub)

Blend segment-specific experience with a broader benchmark (e.g., portfolio-wide or industry rate):

$$\hat{f}_s^{\text{cred}} = Z_s \cdot \hat{f}_s + (1 - Z_s) \cdot \hat{f}_{\text{benchmark}}$$

where $Z_s$ is the **credibility factor**:

$$Z_s = \frac{E_s}{E_s + K}$$

$K$ is the Buhlmann credibility parameter, estimated as the ratio of **between-segment variance** to **within-segment (process) variance**. In the Poisson case, the process variance is $\lambda / E$, so:

$$K = \frac{\text{expected process variance}}{\text{variance of hypothetical means}} = \frac{\bar{f}}{\hat{\sigma}^2_{\text{between}}}$$

**Interpretation:** Segments with more exposure get more weight on their own experience; thin segments are pulled toward the portfolio or industry benchmark. This prevents overreacting to a single large loss in a small segment.

#### 1.5.2 Hierarchical / Multilevel Models

A Bayesian or empirical Bayesian approach generalises credibility weighting:

$$f_s \sim \text{Gamma}(\alpha, \beta) \quad \text{(prior across segments)}$$
$$N_s \mid f_s \sim \text{Poisson}(f_s \times E_s)$$
$$f_s \mid N_s \sim \text{Gamma}(\alpha + N_s, \; \beta + E_s) \quad \text{(posterior)}$$

The posterior mean is:

$$\hat{f}_s^{\text{Bayes}} = \frac{\alpha + N_s}{\beta + E_s}$$

This is mathematically equivalent to Buhlmann credibility for Poisson-Gamma mixtures but extends naturally to more complex hierarchies (line > geography > size band).

#### 1.5.3 Practical Guidelines for Thin Data

| Situation | Recommended Approach |
|---|---|
| Segment has 0 losses but meaningful exposure | Use credibility-weighted estimate; do not set expected to zero |
| Segment has < 3 years of data | Weight toward broader benchmark (Z < 0.3 typically) |
| Segment has no historical data (new product) | Use analogous segment or industry benchmark as prior |
| Very small segments (< 5% of portfolio) | Merge with adjacent segments or use hierarchical model |

#### 1.5.4 Trend Adjustment

Where there is evidence of systematic change in large loss frequency over time (e.g., social inflation, changing claim patterns), apply a log-linear trend:

$$f_t = f_0 \times e^{\delta \cdot t}$$

where $\delta$ is the annual trend rate estimated from the historical data. Use caution: with thin data, trend estimates have wide confidence intervals. Consider constraining to industry benchmarks or external research.

---

## 2. Portfolio-Aware Frequency Estimation

### 2.1 Design Principle

The expected large loss frequency must reflect the **current** portfolio composition, not just historical averages. As the portfolio grows, shifts mix, or enters new segments, the expectation must update accordingly. This is the core requirement for a "refreshable" model.

### 2.2 Choice of Exposure Measure

The exposure measure determines how frequency rates are normalised. The choice depends on the line of business and available data:

| Exposure Measure | Best For | Advantages | Limitations |
|---|---|---|---|
| **Earned Premium** | All lines (default) | Directly available; aligns with financial reporting | Rate changes inflate premium without changing risk count; must adjust for rate level |
| **Policy Count** | Homogeneous lines (e.g., personal auto) | Simple; not distorted by rate changes | Doesn't reflect policy size variation |
| **Insured Value / TIV** | Property lines | Reflects scale of exposure | Not available for all lines; subject to valuation issues |
| **Payroll / Revenue** | Workers' comp, GL | Standard industry basis | May not correlate with large loss propensity |
| **On-Level Earned Premium** | All lines (preferred) | Adjusts for rate changes; true risk-volume measure | Requires rate-level tracking |

**Recommendation:** Use **on-level earned premium** as the primary exposure measure where available. This removes the confounding effect of rate changes and isolates true volume/mix changes. Where on-leveling is not feasible, use policy count or gross written premium with explicit rate-change adjustments.

### 2.3 Segmentation Strategy

#### 2.3.1 Segmentation Dimensions

The model should segment expected frequency along dimensions that:
1. Are known to drive large loss propensity
2. Are available in the exposure data
3. Have sufficient volume for credible estimation (or can be credibility-weighted)

**Recommended primary segmentation:**

| Dimension | Typical Categories | Rationale |
|---|---|---|
| **Line of Business** | Property, Casualty, Marine, Financial Lines, etc. | Fundamentally different loss generation processes |
| **Geography** | Country, region, or regulatory jurisdiction | Legal environment, weather exposure, economic conditions |
| **Policy Size Band** | Small (<$1M), Mid ($1M–$10M), Large (>$10M) | Larger policies have higher probability of breaching large loss threshold |
| **Industry / Occupancy Class** | Manufacturing, Services, Construction, etc. | Industry-specific hazard profiles |

#### 2.3.2 Granularity vs. Credibility Trade-off

More granular segmentation improves accuracy for individual cells but reduces credibility per cell. The practical rule:

$$\text{Minimum cell size} \approx \frac{1}{\hat{f}_s} \times 5$$

That is, each cell should have enough exposure to expect at least ~5 large losses over the observation period. Below this threshold, apply credibility weighting (Section 1.5.1) or merge cells.

**Hierarchy for borrowing strength:**

```
Portfolio Total
  └── Line of Business
        └── Geography
              └── Size Band
                    └── Industry Class
```

At each level, the estimate blends the cell's own experience with the parent level's rate, weighted by credibility.

### 2.4 Exposure-Based vs. Experience-Based Approaches

Two complementary approaches, with distinct strengths:

#### 2.4.1 Exposure-Based (A Priori) Approach

Start with **benchmark frequency rates** (from industry data, longer history, or pricing assumptions) and apply them to the current portfolio:

$$\lambda_{\text{expected}} = \sum_{s} f_s^{\text{benchmark}} \times E_s^{\text{current}}$$

**Strengths:**
- Immediately reflects portfolio composition changes
- Not distorted by recent random volatility
- Suitable for new or rapidly changing portfolios

**Weaknesses:**
- Benchmark rates may not reflect the insurer's underwriting selection
- Requires reliable external or historical benchmarks

#### 2.4.2 Experience-Based Approach

Use the insurer's **own historical large loss experience**, adjusted for exposure changes:

$$\hat{f}_s = \frac{\sum_t n_{s,t}}{\sum_t E_{s,t}}, \quad \lambda_{\text{expected}} = \sum_{s} \hat{f}_s \times E_s^{\text{current}}$$

**Strengths:**
- Reflects the insurer's specific underwriting, pricing, and claims management
- More accurate where sufficient credible history exists

**Weaknesses:**
- Subject to random volatility in thin segments
- Backward-looking; may miss recent portfolio shifts

#### 2.4.3 Recommended Blended Approach

$$\hat{f}_s^{\text{final}} = Z_s \cdot \hat{f}_s^{\text{experience}} + (1 - Z_s) \cdot f_s^{\text{benchmark}}$$

where $Z_s$ is the credibility factor for segment $s$ (Section 1.5.1). This produces estimates that:
- Leverage the insurer's own data where credible
- Fall back to benchmarks for thin segments
- Automatically recalibrate as the portfolio evolves

### 2.5 Making the Model Refreshable

The model must update seamlessly as the portfolio changes quarter over quarter.

#### 2.5.1 Architecture for Refreshability

```
┌──────────────────────────────────────────────────────────┐
│                    MODEL PARAMETERS                       │
│  (frequency rates by segment, credibility weights,        │
│   trend factors, dispersion parameters)                   │
│  ── Calibrated annually or semi-annually ──               │
└────────────────────────┬─────────────────────────────────┘
                         │ Applied to
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  CURRENT EXPOSURE DATA                     │
│  (earned premium, policy count by segment for the          │
│   reporting period)                                        │
│  ── Refreshed quarterly or monthly ──                      │
└────────────────────────┬─────────────────────────────────┘
                         │ Produces
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  EXPECTED FREQUENCY OUTPUT                  │
│  (expected count by segment, portfolio total,              │
│   percentile bands, AvE comparison)                        │
│  ── Produced each reporting period ──                      │
└──────────────────────────────────────────────────────────┘
```

**Key design choices:**
- **Separate parameters from exposure:** Frequency rates are calibrated on a longer cycle (annual). Current exposure data feeds in at each reporting period.
- **Rolling calibration window:** Use 5–10 years of history for rate estimation, with more recent years receiving higher weight if trends exist.
- **Automated data pipeline:** Exposure extracts feed directly into the model; no manual intervention required for routine refreshes.

#### 2.5.2 Handling Portfolio Changes Between Calibrations

When the portfolio mix shifts significantly between calibration cycles (e.g., a large new account or exit from a segment):

1. The exposure-based component of the blended estimate automatically adjusts
2. Flag segments where current exposure deviates > 20% from the calibration-period exposure for review
3. Consider interim recalibration if portfolio composition changes materially

### 2.6 Connecting to Pricing

The model's outputs are designed to be **pricing-ready by construction**:

#### 2.6.1 Frequency x Severity Framework

The large loss load in technical pricing follows:

$$\text{Large Loss Load} = f_s \times \bar{S}_s$$

where $f_s$ is the expected frequency rate from this model and $\bar{S}_s$ is the expected severity (average cost given a large loss exceeds the threshold). Severity is out of scope for Phase 1 but the frequency output slots directly into this formula.

#### 2.6.2 Pricing Applications

| Application | How Frequency Model Feeds In |
|---|---|
| **Technical price adequacy** | Benchmark large loss frequency per segment defines the "expected" load |
| **Rate monitoring** | Compare implied frequency in current rates vs. model expectation |
| **Segmentation refinement** | Identify segments where frequency is systematically higher/lower than portfolio average |
| **Underwriting guidelines** | Flag segments or size bands with deteriorating frequency trends |
| **Risk appetite calibration** | Set appetite limits informed by expected frequency and tail percentiles |

---

## 3. Deviation Attribution Framework

### 3.1 Objective

When actual large loss count deviates from expected, stakeholders need to know **why**. Was it random noise? Portfolio growth? A shift in mix toward riskier segments? Or a genuine change in underlying frequency? This section provides a mathematical framework to decompose the gap.

### 3.2 The Actual-vs-Expected Gap

Define:

$$\Delta N = N_{\text{actual}} - N_{\text{expected}}$$

where $N_{\text{expected}} = \sum_s \hat{f}_s \times E_s^{\text{current}}$.

The goal is to decompose $\Delta N$ into four additive components:

$$\Delta N = \underbrace{\Delta N_{\text{volume}}}_{\text{Growth}} + \underbrace{\Delta N_{\text{mix}}}_{\text{Composition}} + \underbrace{\Delta N_{\text{rate}}}_{\text{Frequency rate}} + \underbrace{\Delta N_{\text{random}}}_{\text{Volatility}}$$

### 3.3 Component Definitions

#### 3.3.1 Volume / Growth Effect

**Question:** How much of the change in expected count is due to overall portfolio growth (or contraction), holding mix and rates constant?

$$\Delta N_{\text{volume}} = \bar{f}_{\text{prior}} \times (E_{\text{current}}^{\text{total}} - E_{\text{prior}}^{\text{total}})$$

where $\bar{f}_{\text{prior}}$ is the portfolio-average frequency rate in the prior (baseline) period. This isolates the effect of writing more (or less) business at the same average risk level.

**Narrative example:** "We grew earned premium by 12%, which — at unchanged mix and frequency — accounts for approximately 2 additional expected large losses."

#### 3.3.2 Mix Effect

**Question:** How much of the change is due to shifts in portfolio composition across segments, holding total volume and segment-level rates constant?

$$\Delta N_{\text{mix}} = \sum_s \hat{f}_s^{\text{prior}} \times E_s^{\text{current}} - \bar{f}_{\text{prior}} \times E_{\text{current}}^{\text{total}}$$

Equivalently, this can be written as:

$$\Delta N_{\text{mix}} = E_{\text{current}}^{\text{total}} \times \sum_s \hat{f}_s^{\text{prior}} \times \left(\frac{E_s^{\text{current}}}{E_{\text{current}}^{\text{total}}} - \frac{E_s^{\text{prior}}}{E_{\text{prior}}^{\text{total}}}\right)$$

This measures the impact of changing the **weight** of each segment in the portfolio, evaluated at prior-period frequency rates.

**Narrative example:** "The shift toward larger casualty accounts (from 30% to 38% of portfolio) increased expected frequency by 1.5 losses, as this segment has a higher large loss rate."

#### 3.3.3 Rate / Frequency Effect

**Question:** How much of the change is due to the underlying frequency rate changing within segments?

$$\Delta N_{\text{rate}} = \sum_s (\hat{f}_s^{\text{current}} - \hat{f}_s^{\text{prior}}) \times E_s^{\text{current}}$$

This captures genuine shifts in loss propensity — e.g., due to social inflation, claims management changes, or underwriting tightening/loosening — **within** each segment.

**Narrative example:** "Casualty frequency rates increased from 0.8% to 1.0% of on-level premium, adding 3 expected large losses. This may reflect broader social inflation trends."

Note: This component can only be estimated when the model is recalibrated with updated frequency rates. Between calibrations, this effect is zero by construction and any gap flows to the random volatility component.

#### 3.3.4 Random Volatility

**Question:** How much of the actual-vs-expected gap is attributable to normal statistical variation?

$$\Delta N_{\text{random}} = N_{\text{actual}} - N_{\text{expected}}^{\text{updated}}$$

where $N_{\text{expected}}^{\text{updated}}$ incorporates the volume, mix, and rate effects above.

**Contextualising the residual:** Compare $\Delta N_{\text{random}}$ to the distributional range from Section 1.4:

- Compute the standard deviation of the expected count: $\sigma = \sqrt{\lambda}$ (Poisson) or $\sigma = \sqrt{\mu + \mu^2/r}$ (NB)
- Express the residual in standard deviation units: $z = \Delta N_{\text{random}} / \sigma$
- Report the corresponding percentile of the actual count

| Residual ($z$-score) | Interpretation |
|---|---|
| $|z| < 1.0$ | Within 1 SD — normal volatility |
| $1.0 \leq |z| < 1.65$ | Between 1–1.65 SD — somewhat unusual |
| $1.65 \leq |z| < 2.0$ | Between 1.65–2 SD — notable, warrants monitoring |
| $|z| \geq 2.0$ | Beyond 2 SD — strong signal of structural change |

### 3.4 Mathematical Framework: Bridge Decomposition

The full decomposition follows the **sequential (additive) bridge** methodology, analogous to premium bridge analysis in financial reporting.

#### 3.4.1 Step-by-Step Bridge

Starting from the prior-period expected count:

$$N_{\text{expected}}^{\text{prior}} = \sum_s \hat{f}_s^{\text{prior}} \times E_s^{\text{prior}}$$

| Step | Formula | Running Total |
|---|---|---|
| **Start** | $N_{\text{expected}}^{\text{prior}}$ | Baseline |
| **+ Volume** | $+ \bar{f}_{\text{prior}} \times \Delta E^{\text{total}}$ | After growth |
| **+ Mix** | $+ \sum_s \hat{f}_s^{\text{prior}} \times E_s^{\text{current}} - \bar{f}_{\text{prior}} \times E_{\text{current}}^{\text{total}}$ | After mix shift |
| **+ Rate** | $+ \sum_s \Delta \hat{f}_s \times E_s^{\text{current}}$ | Updated expectation |
| **= Expected (current)** | $N_{\text{expected}}^{\text{current}}$ | — |
| **+ Random** | $+ (N_{\text{actual}} - N_{\text{expected}}^{\text{current}})$ | — |
| **= Actual** | $N_{\text{actual}}$ | End point |

#### 3.4.2 Interaction Terms

In a strict multiplicative decomposition, interaction terms arise between volume, mix, and rate effects. The additive sequential approach attributes interactions to the later-applied factor. For the purpose of explainability and board-level narratives, this is acceptable and standard practice. Document the decomposition order and be consistent period to period.

An alternative is a **Shapley value** decomposition, which averages over all possible orderings to produce a symmetric, order-invariant attribution. This is mathematically elegant but harder to explain to non-technical stakeholders. **Recommendation:** Use the sequential additive approach for primary reporting; offer Shapley decomposition as a sensitivity check if stakeholders question ordering effects.

### 3.5 Waterfall Visualisation

The bridge naturally maps to a **waterfall chart**:

```
Prior Expected  ████████████████████  20.0
+ Volume        ███                   +2.4
+ Mix           ██                    +1.5
+ Rate          ████                  +3.1
= New Expected  ███████████████████████████  27.0
+ Random        ██                    +2.0
= Actual        █████████████████████████████  29.0
```

**Design recommendations:**
- Green bars for effects that reduce expected count; red/orange for increases
- Grey bar for random volatility (it is not inherently good or bad)
- Annotate each bar with the narrative explanation
- Show the percentile of actual within the expected distribution
- Include the prior period and current period side-by-side for context

### 3.6 Hypothesis Testing: Random vs. Structural

To formally assess whether the residual (after volume, mix, and rate adjustments) is consistent with random variation:

**Poisson Exact Test:**

$$H_0: N_{\text{actual}} \sim \text{Poisson}(\lambda_{\text{expected}})$$

Compute the p-value:
- One-sided (adverse): $P(N \geq N_{\text{actual}} \mid \lambda_{\text{expected}})$
- Two-sided: $2 \times \min(P(N \leq N_{\text{actual}}), P(N \geq N_{\text{actual}}))$

Reject at the 5% level if p-value < 0.05, suggesting the deviation is unlikely to be purely random.

**Practical caveat:** With very low expected counts (e.g., $\lambda < 5$), even a single additional loss can be "statistically significant." Frame results in terms of percentiles rather than binary hypothesis tests for board-level communication.

---

## 4. Implementation Approach

### 4.1 Data Requirements

#### 4.1.1 Minimum Data Elements

| Data Element | Source | Granularity | Notes |
|---|---|---|---|
| **Large loss register** | Claims system | Individual loss level | All losses exceeding the large loss threshold; include occurrence date, line, geography, policy size |
| **Earned premium** | Finance / UW system | Segment level (line × geography × size band) | By accident year/quarter; on-level preferred |
| **Policy count** | Policy admin system | Segment level | Alternative exposure measure |
| **Rate change history** | Pricing / UW | By line and year | Required for on-leveling premium |
| **Large loss threshold** | Pricing / Risk Appetite | Single value or by-line | Must align with existing definitions |
| **Industry benchmarks** | Market data, brokers, reinsurers | By line and geography | For credibility weighting and validation |

#### 4.1.2 Data Quality Considerations

- **Threshold consistency:** Ensure the large loss definition is applied consistently across years. If the threshold has changed, restate historical data on a consistent basis (e.g., index to current monetary terms).
- **Development:** Large losses may develop over time (especially casualty/liability). Use developed-to-ultimate loss counts where possible, or restrict to losses exceeding threshold at a consistent development point (e.g., 24 months).
- **Catastrophe exclusion:** Decide whether catastrophe losses (e.g., nat cat events) are in scope. If excluded, define the exclusion criteria clearly and consistently.
- **Minimum history:** 5+ years preferred for stable frequency estimation; 10+ years ideal for trend detection. Shorter histories require heavier reliance on benchmarks.

### 4.2 Phased Implementation Plan

#### Phase 1: Foundation (Months 1–3)

**Objective:** Produce the first actual-vs-expected large loss frequency report.

| Task | Detail |
|---|---|
| 1.1 Align definitions | Confirm large loss threshold, exposure measure, and segmentation with Pricing and Risk Appetite |
| 1.2 Extract and clean data | Large loss register + exposure data, minimum 5 years |
| 1.3 Calculate segment-level frequency rates | Raw rates by line × geography × size band |
| 1.4 Apply credibility weighting | Blend segment rates with portfolio-level benchmarks |
| 1.5 Compute expected frequency | Apply rates to current exposure |
| 1.6 Build percentile bands | Poisson-based intervals around expected count |
| 1.7 Produce first AvE report | Actual vs expected with percentile context |
| 1.8 Stakeholder review | Present to Pricing, Risk, and Management; gather feedback |

**Deliverable:** Quarterly large loss frequency report showing expected count, actual count, percentile, and high-level deviation narrative.

#### Phase 2: Attribution (Months 4–6)

**Objective:** Add the deviation attribution waterfall.

| Task | Detail |
|---|---|
| 2.1 Build period-over-period bridge | Volume, mix, rate, random decomposition |
| 2.2 Implement waterfall visualisation | Interactive chart with drill-down by segment |
| 2.3 Automate data refresh | Pipeline for quarterly exposure updates |
| 2.4 Enhance segmentation | Add industry class or sub-line detail where credible |
| 2.5 Validate against known events | Back-test the model against historical periods with known drivers |

**Deliverable:** Waterfall chart with narrative, automated quarterly refresh.

#### Phase 3: Pricing Integration (Months 7–12)

**Objective:** Connect frequency outputs to pricing decisions.

| Task | Detail |
|---|---|
| 3.1 Link to severity model | Combine frequency with severity estimates for full large loss load |
| 3.2 Segment-level adequacy assessment | Compare model-implied frequency loads to current pricing |
| 3.3 Build underwriting dashboards | Segment-level frequency trends and alerts |
| 3.4 Integrate with risk appetite framework | Express appetite limits in frequency terms |
| 3.5 Formalise governance | Define model ownership, calibration cycle, documentation standards |

**Deliverable:** Pricing-integrated large loss framework with underwriting tools.

### 4.3 Technology and Architecture

#### 4.3.1 Recommended Stack

| Component | Recommendation | Rationale |
|---|---|---|
| **Statistical engine** | R or Python | Open source; deep actuarial library ecosystem |
| **R packages** | `actuar` (distributions, credibility), `MASS` (glm.nb), `stats` (glm) | Standard actuarial toolkit |
| **Python packages** | `chainladder-python`, `scipy.stats`, `statsmodels`, `gemact` | CAS-sponsored; well-maintained |
| **Data storage** | SQL database or data warehouse | Structured exposure and loss data |
| **Visualisation** | Power BI, Tableau, or R Shiny / Python Dash | Interactive waterfall charts and drill-downs |
| **Automation** | Scheduled scripts (cron / Airflow / Azure Data Factory) | Quarterly refresh without manual intervention |

#### 4.3.2 Model Governance

- **Version control:** All model code in Git
- **Documentation:** Methodology document (this document), technical specification, validation report
- **Calibration log:** Record each recalibration: date, data used, parameter changes, rationale
- **Peer review:** Annual independent review of model assumptions and outputs
- **Audit trail:** Log all data inputs and outputs for each reporting period

### 4.4 Reporting and Visualisation

#### 4.4.1 Board-Level Dashboard (1 page)

| Element | Content |
|---|---|
| **Headline metric** | Actual large loss count vs. expected, with percentile indicator |
| **Traffic light** | Green (within 25th–75th), amber (10th–25th or 75th–90th), red (outside 10th–90th) |
| **Waterfall chart** | Volume → Mix → Rate → Random decomposition |
| **Trend chart** | Rolling 4-quarter actual vs expected with confidence band |
| **Key narrative** | 2–3 sentence summary of the main driver(s) |

#### 4.4.2 Management-Level Report (3–5 pages)

- Board dashboard plus:
- Segment-level detail (by line, geography, size band)
- Individual large loss listing with segment attribution
- Frequency trend by segment
- Credibility assessment by segment
- Comparison to industry benchmarks (where available)

#### 4.4.3 Pricing / Actuarial Workbench

- Full segment-level frequency rates with confidence intervals
- Relativities across segments
- Implied frequency load per unit of exposure
- Back-test results and model diagnostics
- Data quality flags and credibility indicators

---

## 5. Industry Context and References

### 5.1 Actuarial Standards and Professional Guidance

| Standard / Guidance | Relevance |
|---|---|
| **ASOP No. 25** — Credibility Procedures | Governs the application of credibility in ratemaking and reserving; directly applicable to the blended frequency estimation approach |
| **ASOP No. 12** — Risk Classification | Guides segmentation decisions; ensures rating variables are actuarially sound |
| **ASOP No. 23** — Data Quality | Standards for evaluating and documenting data quality in actuarial analyses |
| **ASOP No. 56** — Modeling | Requirements for actuarial model governance, documentation, and validation |
| **CAS Statement of Principles — Ratemaking** | Fundamental principles underlying the frequency × severity pricing framework |

### 5.2 Key Research and Publications

#### CAS Publications

1. **Goldburd, M., Khare, A., Tevet, D., & Guller, D.** — *Generalized Linear Models for Insurance Rating* ([CAS Monograph No. 5](https://www.casact.org/monograph/cas-monograph-no-5), 2nd ed.). The standard reference for GLM-based frequency and severity modeling in P&C insurance. Covers Poisson and Negative Binomial frequency models, exposure offsets, and model validation. On the Exam 8 syllabus.

2. **Venter, G.** — *["Comparison of Actual and Expected Losses as a Means of Loss Analysis"](https://www.casact.org/abstract/comparison-actual-and-expected-losses-means-loss-analysis)* (CAS). Early framework for AvE analysis in loss monitoring.

3. **Parodi, P.** — *["Loss Modelling from First Principles"](https://eforum.casact.org/article/91190-loss-modelling-from-first-principles)* (CAS E-Forum; also published in *British Actuarial Journal*, 2024). Derives frequency models (Poisson processes, Levy processes, multivariate Bernoulli) from first principles. Includes sections on when Poisson assumptions break down.

4. **CAS E-Forum** — *["GLM for Dummies (and Actuaries)"](https://eforum.casact.org/article/83925-glm-for-dummies-and-actuaries)*. Accessible introduction to GLM-based frequency modeling for practicing actuaries.

5. **Clark, D.R.** — *"Basics of Reinsurance Pricing"* (CAS Study Note, revised 2014). Covers exposure rating, experience rating, and the frequency-severity framework for excess of loss reinsurance. Directly relevant to estimating excess-layer frequency.

6. **Korn, R.** — *"Strategies for Modeling Large Losses"* (Variance, Vol. 11). Frequency-severity stochastic approaches to large loss development. Directly addresses the modeling challenge this project faces.

7. **Meyers, G.G.** — *Stochastic Loss Reserving Using Bayesian MCMC Models* ([CAS Monograph No. 1](https://www.casact.org/monograph/cas-monograph-no-1), 2015). Bayesian approaches including overdispersed Poisson. Relevant for hierarchical frequency estimation.

8. **CAS Monograph No. 3** — *[Stochastic Loss Reserving Using Generalized Linear Models](https://www.casact.org/monograph/cas-monograph-no-3)*. GLM framework for frequency/severity with overdispersed Poisson.

9. **CAS Monograph No. 13** — *[Penalized Regression and Lasso Credibility](https://www.casact.org/publications-research/publications/flagship-publications/cas-monographs/monograph-no-13)*. Regularised GLMs for frequency/severity/pure premium — relevant for high-dimensional segmentation with sparse data.

#### SOA / Academic Publications

10. **Klugman, S.A., Panjer, H.H., & Willmot, G.E.** — *Loss Models: From Data to Decisions* (5th ed., 2019, Wiley). Comprehensive treatment of frequency distributions (Poisson, NB, mixed Poisson, Panjer (a,b,0) class), credibility theory, and aggregate loss modeling. Standard exam reference (SOA Exam STAM / CAS Exam MAS-I).

11. **Mildenhall, S.J. & Major, J.A.** — *Pricing Insurance Risk: Theory and Practice* (2022, Wiley). Comprehensive treatment of aggregate distributions, frequency-severity models, and computational methods (FFT). Modern reference for the frequency × severity pricing framework.

12. **Frees, E.W.** — *[Loss Data Analytics](https://openacttexts.github.io/Loss-Data-Analytics/)* (open-access textbook). Modern treatment of frequency modeling, GLMs, credibility, and Bayesian approaches with R code examples.

13. **Bühlmann, H. & Gisler, A.** — *A Course in Credibility Theory and its Applications* (Springer). Definitive treatment of credibility theory, including Bühlmann-Straub models for frequency estimation.

14. **Mahler, H.C. & Dean, C.G.** — *"Credibility"*, Chapter 8 in *Foundations of Casualty Actuarial Science*. Comprehensive treatment of limited fluctuation and Bühlmann credibility with insurance applications.

15. **Jewell, W.S.** — *"Credible Means are Exact Bayesian for Exponential Families"* (ASTIN Bulletin). Theoretical foundation for the equivalence of Bühlmann credibility and Bayesian estimation for Poisson-Gamma models.

16. **Mayerson, A.L.** — *"A Bayesian View of Credibility"* (Proceedings of the CAS, Vol. 64, 1964). Foundational paper connecting Bayesian inference and credibility theory.

17. **SOA** — *[Experience Study Calculations](https://www.soa.org/495953/globalassets/assets/files/research/experience-study-calculations.pdf)* (revised March 2024). Methodology for expected-vs-actual analysis — directly relevant to the AvE framework in Section 3.

18. **Pittarello, G., Luini, E., & Marchione, M.M.** — *"GEMAct: a Python package for non-life (re)insurance modeling"* ([Annals of Actuarial Science](https://www.cambridge.org/core/journals/annals-of-actuarial-science/article/gemact-a-python-package-for-nonlife-reinsurance-modeling/5A91AD85ADCD4196BF9CA0F2896D779B), 2024). Implements (a,b,0) and (a,b,1) frequency classes, collective risk model, and reinsurance structures.

#### Deviation Attribution / Bridge Analysis

19. **Price-Volume-Mix (PVM) Analysis** — Standard FP&A methodology widely applied in insurance for premium bridge analysis. The same decomposition logic (volume, mix, rate) applies directly to frequency bridge analysis.

20. **Shapley, L.S.** — *"A Value for n-Person Games"* (1953). Foundation for the Shapley value approach to symmetric decomposition, applicable as an alternative to sequential bridge analysis.

### 5.3 Open-Source Actuarial Tools

| Tool | Language | Key Capabilities | Link |
|---|---|---|---|
| **actuar** | R | Loss distributions (Poisson, NB, mixed Poisson, Panjer recursion), credibility (Bühlmann-Straub), aggregate models, simulation of hierarchical portfolios | CRAN |
| **ChainLadder** | R | Reserving methods; Mack, Bootstrap (overdispersed Poisson), GLM-based approaches; useful for developing large loss counts to ultimate | [mages.github.io/ChainLadder](https://mages.github.io/ChainLadder/) |
| **MASS** | R | `glm.nb()` for Negative Binomial GLM fitting | CRAN (base R) |
| **fitdistrplus** | R | Distribution fitting (`fitdist()`) and goodness-of-fit testing for frequency and severity | CRAN |
| **pscl** | R | Zero-inflated Poisson and NB regression (`zeroinfl()`, `hurdle()`) | CRAN |
| **epitools** | R | Exact Poisson confidence intervals via `pois.conf.int()` (Garwood method) | CRAN |
| **chainladder-python** | Python | CAS-sponsored; triangles, IBNR, development factors; scikit-learn-style API | [github.com/casact/chainladder-python](https://github.com/casact/chainladder-python) |
| **gemact** | Python | Non-life (re)insurance modeling; collective risk model; (a,b,0) and (a,b,1) frequency classes; XoL pricing with reinstatements | [Cambridge Core](https://www.cambridge.org/core/journals/annals-of-actuarial-science/article/gemact-a-python-package-for-nonlife-reinsurance-modeling/5A91AD85ADCD4196BF9CA0F2896D779B) |
| **aggregate** | Python | Aggregate distribution modeling via FFT convolution; DecL language for specifying frequency-severity models (Mildenhall) | PyPI |
| **scipy.stats** | Python | Poisson, NB, Gamma distributions; chi-squared for exact CIs; hypothesis tests | scipy.org |
| **statsmodels** | Python | GLMs with Poisson/NB families; Zero-Inflated Poisson; exposure offsets; robust standard errors | statsmodels.org |
| **PyMC** | Python | Full Bayesian Poisson-Gamma hierarchical models via MCMC/variational inference; ideal for credibility-weighted estimation | pymc.io |
| **Loss Data Analytics** | R (textbook) | Comprehensive open-access textbook with code examples | [openacttexts.github.io](https://openacttexts.github.io/Loss-Data-Analytics/) |

### 5.4 Community and Continuing Education

- **Actuarial Open Source Community** ([actuarialopensource.org](https://www.actuarialopensource.org/)): Hub for open-source actuarial tools and collaboration
- **CAS E-Forum**: Peer-reviewed practical research papers
- **Variance Journal**: CAS-sponsored journal for longer research articles
- **ASTIN Bulletin**: International actuarial research journal (risk theory, credibility, loss models)

---

## Appendix A: Notation Summary

| Symbol | Definition |
|---|---|
| $N$ | Random variable: large loss count |
| $\lambda$ | Expected count (Poisson parameter) |
| $\mu$ | Mean count (Negative Binomial) |
| $r$ | Dispersion parameter (Negative Binomial) |
| $f_s$ | Frequency rate for segment $s$ (losses per unit of exposure) |
| $E_s$ | Exposure for segment $s$ |
| $Z_s$ | Credibility factor for segment $s$ |
| $K$ | Bühlmann credibility parameter |
| $n_s$ | Observed large loss count in segment $s$ |
| $\Delta N$ | Actual minus expected large loss count |
| $\delta$ | Annual frequency trend rate |

## Appendix B: Worked Example — Bridge Decomposition

**Setup:** Property & Casualty portfolio, two segments.

| Segment | Prior Period ||| Current Period |||
|---|---|---|---|---|---|---|
| | Exposure ($M) | Freq Rate | Expected Count | Exposure ($M) | Freq Rate | Expected Count |
| **Property** | 500 | 0.010 | 5.0 | 550 | 0.010 | 5.5 |
| **Casualty** | 300 | 0.020 | 6.0 | 400 | 0.022 | 8.8 |
| **Total** | 800 | 0.01375 | 11.0 | 950 | — | 14.3 |

**Actual large loss count in current period:** 18

**Bridge calculation:**

1. **Prior expected:** 11.0
2. **Volume effect:** $0.01375 \times (950 - 800) = +2.1$
3. **Mix effect:** $(0.010 \times 550 + 0.020 \times 400) - (0.01375 \times 950) = 13.5 - 13.1 = +0.4$
4. **Rate effect:** $(0.010 - 0.010) \times 550 + (0.022 - 0.020) \times 400 = 0 + 0.8 = +0.8$
5. **Updated expected:** $11.0 + 2.1 + 0.4 + 0.8 = 14.3$
6. **Random residual:** $18 - 14.3 = +3.7$

**Percentile context:** For $\lambda = 14.3$, the 90th percentile is approximately 19. The actual count of 18 is at roughly the 85th percentile — somewhat above average but within the plausible range.

**Narrative:** "Large loss count of 18 was 7 above the prior-year expectation of 11. Of this increase: 2.1 reflects portfolio growth (+19% exposure), 0.4 reflects the mix shift toward casualty, 0.8 reflects a higher casualty frequency rate (potentially social inflation), and the remaining 3.7 is within the range of normal statistical variation (85th percentile). No structural concern is indicated."

---

*Document version: 1.0 | Date: 2026-03-31 | Status: Draft for review*
