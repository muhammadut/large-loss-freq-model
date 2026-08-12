"""Auto-generated board narrative — the paragraph a human reads first.

Deterministic: same numbers in, same words out (no model call). It states the
verdict, then attributes the year-over-year move to the waterfall pieces that
are material, then a plain-English read on the random noise.
"""
from __future__ import annotations


def _ord(n) -> str:
    """English ordinal: 1->1st, 2->2nd, 3->3rd, 33->33rd, 11/12/13->th."""
    n = int(round(n))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def board_narrative(ave: dict, wf: dict, verdict_year, prior_year) -> str:
    z = wf["random_z"]
    lines = [
        f"Large-loss count for {verdict_year} was {ave['actual']}, against an expected "
        f"{ave['expected']:.0f} ({_ord(ave['percentile'])} percentile, "
        f"normal range {ave['ci_5th']}–{ave['ci_95th']}). Status: {ave['traffic_light']}.",
        "",
        f"Change from the {prior_year} expectation of {wf['prior_expected']:.0f}:",
    ]
    if abs(wf["volume_effect"]) >= 0.1:
        d = "growth" if wf["volume_effect"] > 0 else "contraction"
        lines.append(f"  - Portfolio {d} ({wf['volume_effect']:+.1f})")
    if abs(wf["mix_effect"]) >= 0.1:
        d = "higher-frequency" if wf["mix_effect"] > 0 else "lower-frequency"
        lines.append(f"  - Mix shift toward {d} segments ({wf['mix_effect']:+.1f})")
    if abs(wf["rate_effect"]) >= 0.1:
        d = "increased" if wf["rate_effect"] > 0 else "decreased"
        lines.append(f"  - Segment frequency rates {d} ({wf['rate_effect']:+.1f})")
    else:
        lines.append("  - Frequency rates unchanged (rate table frozen since last recalibration)")

    ctx = ("within normal variation" if abs(z) < 1.0
           else "somewhat unusual but within expectations" if abs(z) < 1.65
           else "statistically notable" if abs(z) < 2.0
           else "a strong signal of structural deviation")
    lines += [
        f"  - Random volatility ({wf['random_effect']:+.1f}): {ctx} (z={z:+.2f}).",
        "",
        ("Conclusion: experience is within expectations — no structural concern."
         if abs(z) < 1.65 else
         "Conclusion: the deviation warrants investigation."),
    ]
    return "\n".join(lines)
