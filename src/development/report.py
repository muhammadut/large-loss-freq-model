"""Write the claim-development artifacts."""
from __future__ import annotations
import pandas as pd


def write_csv(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False)


def write_report(path, cfg, long, patterns, developed):
    L = []; A = L.append
    A("# Step 5 — Claim-count development (IBNR)\n")
    A("> Recent accident years are **immature**: large claims take time to be reported and to "
      "cross the threshold, so the reported count understates the ultimate. This develops the "
      "reported counts to ultimate using a **per-coverage** pattern learned from a valuation "
      "triangle. Property develops fast; liability has a long tail — they are handled separately.\n")

    # 1. the development pattern per coverage
    A("## 1. Development pattern (% of ultimate reported by age)\n")
    for ct, pat in patterns.items():
        if not pat["pct_developed"]:
            continue
        tail = cfg.tail_factor.get(ct, 1.0)
        A(f"**{ct}** (tail factor {tail:.2f}):\n")
        A("| Age (months) | Age-to-age factor | % developed |")
        A("|---:|---:|---:|")
        ages = sorted(pat["cdf"])
        for a in ages:
            f = pat["a2a"].get(a)
            A(f"| {a} | {f'{f:.2f}' if f else '— (tail)'} | {pat['pct_developed'][a]*100:.0f}% |")
        A("")

    # 2. developed accident years
    A("## 2. Reported vs developed ultimate (latest snapshot)\n")
    A("| Accident year | Coverage | Age | Reported | % developed | Ultimate | Still to emerge |")
    A("|---:|---|---:|---:|---:|---:|---:|")
    for ay, df in developed:
        for _, r in df.iterrows():
            A(f"| {ay} | {r['covtype']} | {int(r['age_months'])}mo | {int(r['reported'])} | "
              f"{r['pct_developed']*100:.0f}% | {r['ultimate']:.0f} | {r['still_to_emerge']:+.0f} |")
        tot_rep = int(df["reported"].sum()); tot_ult = df["ultimate"].sum()
        A(f"| **{ay} total** | | | **{tot_rep}** | | **{tot_ult:.0f}** | "
          f"**{tot_ult-tot_rep:+.0f}** |")
    A("")

    A("## 3. How to read this & caveats\n")
    A("- **Property needs no adjustment.** Its factors are ~1.0 — the reported count is already "
      "the ultimate. All meaningful development is in **liability**.\n"
      "- **Net development.** Counts can fall as well as rise (subrogation, reserve reductions "
      "below the threshold), so factors are net and % developed can briefly exceed 100%.\n"
      "- **Liability tail.** The triangle window is shorter than liability's true settlement time "
      "(~6 years), so a **tail factor** loads the remaining development. It is an assumption until "
      "the longer extract lands.\n"
      "- **Small counts are noisy.** Liability counts are small, so these factors are directional; "
      "the expanded (10-year) triangle will stabilise them. Bornhuetter-Ferguson (blending with the "
      "Step-1 x Step-2 expected prior) is the steadier choice once wired in.\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
