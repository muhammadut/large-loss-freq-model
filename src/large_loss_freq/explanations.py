"""Plain-English explanations of every data-quality and validation check.

Single source of truth so the per-run summary report and the README stay in
sync. Each entry: `what` (what the check verifies) and `how` (how to read a
pass/fail). Keyed by the check's BASE name; parametrized names like
`exposure_integrity[premium]` resolve via doc_for().

IMPORTANT: this prose is DATA-AGNOSTIC by design — it explains the concept, the
threshold, and how to read *the value shown beside it*, but never bakes in a
specific run's numbers. The numbers are supplied dynamically by the report. So
these explanations stay correct no matter what data the pipeline is run on.
"""

DOCS: dict[str, dict[str, str]] = {
    # ---- data-quality checks ------------------------------------------------
    "years_present": {
        "title": "Years present",
        "what": "Confirms every calendar year you asked to calibrate on is actually in the data.",
        "how": "A missing year would silently bias the rates, so this HALTS the run. PASS = all years found.",
    },
    "min_large_losses": {
        "title": "Minimum large losses",
        "what": "Checks there are enough large losses in the window to fit a stable model.",
        "how": "Too few losses and the rates are just noise, so this HALTS below the minimum. The value shown is the total large losses used.",
    },
    "cat_scope": {
        "title": "Catastrophe scope",
        "what": "States whether catastrophe (e.g. storm/flood) losses are included or excluded.",
        "how": "The value shows the chosen basis. 'assume_excluded' = the book is treated as non-catastrophe and the assumption is disclosed (used when no cat flag is available); 'exclude_flagged' = flagged cat rows are dropped. Surfaced so the choice is never silent.",
    },
    "exposure_integrity": {
        "title": "Exposure integrity (per lens)",
        "what": "Counts large losses sitting on rows that have no exposure under this lens — they enter the numerator while their exposure is missing from the denominator, which inflates the affected segment's rate.",
        "how": "The value is (such losses / total). Near-zero is fine; a large share means that lens has a data gap. The primary lens should be near-zero — a higher figure on an alternate lens is a reason to prefer the cleaner one.",
    },
    "count_grain": {
        "title": "Count grain",
        "what": "Documents the unit being counted: a 'coverage row over the threshold', which can differ slightly from a distinct claim/event.",
        "how": "The value shows how many coverage-rows collapse to distinct policy-periods. A small gap means row-count ≈ event-count; a large gap would mean many multi-coverage events, and you'd reconsider the count unit.",
    },
    # ---- validation gates ---------------------------------------------------
    "reconciliation": {
        "title": "Reconciliation",
        "what": "Checks the model's fitted total equals the actual total number of large losses.",
        "how": "This is a WIRING/SANITY check, not a measure of model quality — for this kind of model it passes by construction. A FAIL means a code bug (bad offset or non-convergence), not a bad model.",
    },
    "dispersion": {
        "title": "Dispersion",
        "what": "Tests whether the data is as 'spread out' as the Poisson model assumes (its spread should roughly equal its average).",
        "how": "1.0 = a perfect match; the value is shown beside this. Comfortably below the threshold (near 1) means plain Poisson is fine. Well above it means the data is more erratic than Poisson expects — look for a missing driver or use a richer model.",
    },
    "thin_segment_share": {
        "title": "Thin-segment share",
        "what": "The fraction of segments that have too few losses to trust on their own data.",
        "how": "INFORMATIONAL. A high share is expected for rare events; these segments rely on the credibility shrinkage. A PASS does NOT mean every individual segment rate is reliable on its own.",
    },
    "backtest": {
        "title": "Backtest (aggregate)",
        "what": "Trains the model on earlier years only, then predicts a later year it never saw, and checks the predicted total lands in the normal range.",
        "how": "The value shows predicted vs actual for the held-out year. Landing inside the 5–95% band is the pass — the real out-of-sample test of the portfolio number. A large miss means the model doesn't generalize.",
    },
    "backtest_segment": {
        "title": "Backtest (segment-level)",
        "what": "The same held-out year, but checks the model ranked the SEGMENTS correctly, not just the portfolio total — because pricing uses segment rates.",
        "how": "The value is a rank correlation (Spearman); higher is better. The total can be perfect while segments are mispriced, so this catches what the aggregate backtest cannot.",
    },
    "robustness_drop_yr": {
        "title": "Robustness (drop newest year)",
        "what": "Drops the newest (possibly still-developing) year, refits, and measures how much the FINAL credibilized rates move.",
        "how": "The value shows the p95 rate move and how many segments moved more than 50%. Small = no published rate hinges on a single year. (We measure final, not raw, rates on purpose — raw thin-segment rates swing, but credibility absorbs most of it.)",
    },
    "total_preservation": {
        "title": "Total preservation",
        "what": "Checks that the credibility step REDISTRIBUTES risk across segments without materially changing the portfolio total.",
        "how": "The value shows the GLM total → final total and the % drift. Near zero means the total is essentially unchanged — credibility only moved risk between segments, which is what it should do.",
    },
    "base_agreement": {
        "title": "Base agreement (primary vs alternate lens)",
        "what": "Compares how the primary lens and the alternate lens rank the segments.",
        "how": "INFORMATIONAL. The value is the rank correlation. A low number means the lenses rank segments differently — expected, because they measure different things (e.g. 'losses per dollar charged' vs 'per dollar of asset'). The gap itself is a useful signal, not a failure.",
    },
}


def doc_for(name: str) -> dict[str, str]:
    """Look up the explanation for a check, handling parametrized names like
    'exposure_integrity[premium]'."""
    base = name.split("[")[0]
    return DOCS.get(name) or DOCS.get(base) or {
        "title": name, "what": "(no explanation registered)", "how": ""}
