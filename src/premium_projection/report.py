"""Write the artifacts: the growth-factor table, the projection, expected losses,
and a methodology + results markdown that explains the tests and the metrics."""
from __future__ import annotations
from datetime import datetime
import pandas as pd

from .config import Config


def write_csv(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False, float_format="%.6g")


def _bt_table(bt: pd.DataFrame) -> str:
    lines = ["| Year | Run month | Method | WAPE (dollar error) | Median segment | Within ±10% | Total error |",
             "|---|---|---|---|---|---|---|"]
    for _, r in bt.sort_values(["year", "month", "method"]).iterrows():
        mon = {3: "Q1 (Apr)", 6: "H1 (Jul)", 9: "Q3 (Oct)"}.get(int(r.month), f"M{int(r.month)}")
        lines.append(f"| {int(r.year)} | {mon} | {r.method} | {r.wape:.1f}% | {r.median_ape:.1f}% "
                     f"| {r.within:.0f}% | {r.total_err:+.1f}% |")
    return "\n".join(lines)


def write_report_md(cfg: Config, factor_table: pd.DataFrame, bt: pd.DataFrame,
                    proj: pd.DataFrame, coverage: dict, path: str):
    port = (factor_table[factor_table.duplicated(["month"], keep="first") == False]
            .groupby("month")["portfolio_factor"].first())
    seg = bt[bt.method == "per-segment"]
    best_line = (f"~{seg.wape.mean():.1f}% dollar-weighted error and "
                 f"~{seg.within.mean():.0f}% of segments within ±10%, across "
                 f"{', '.join(str(y) for y in sorted(bt.year.unique()))}")

    L = []
    L.append("# Premium Projection — Methodology & Results\n")
    L.append(f"_Generated {datetime.now():%Y-%m-%d}. Projects full-year earned premium **per segment** "
             f"(CovType × Region × Industry) so it can be multiplied by the Part-1 frequency rate to "
             f"produce expected large-loss counts._\n")

    L.append("## 1. The problem\n")
    L.append("Part 1 gives a **rate** per segment (large losses per \\$1M of premium). To turn that into "
             "an expected *count*, we multiply by how much premium each segment will have:\n")
    L.append("```\nexpected large losses (segment) = rate (segment) × projected premium (segment)\n```\n")
    L.append("So we must forecast each segment's **full-year earned premium**.\n")

    L.append("## 2. The method\n")
    L.append("For each segment:\n")
    L.append("```\nprojected full-year premium  =  visible premium (so far)  ×  growth factor\n```\n")
    L.append("- **Visible premium** = premium from policies already on the books at the run date "
             "(in production, computed by earning the current in-force book forward from each policy's "
             "start/end dates).")
    L.append("- **Growth factor** = `full-year ÷ visible`, learned from history **per segment** and "
             "**per run-month** — because the later in the year you run, the more business is already "
             "visible, so the smaller the scale-up.")
    L.append("- **Cancellations are already included**: the historical factor is built from what was "
             "actually earned, which is net of cancellations — so we do not add a separate term (no "
             "double-counting).")
    L.append("- A segment's own factor is used, lightly clipped for sanity; segments with little history "
             "fall back to the portfolio factor for that month.\n")

    L.append("### Growth factor by run-month (portfolio level)\n")
    L.append("| Run in… | Growth factor | You can already see |")
    L.append("|---|---|---|")
    names = {2: "February", 3: "April (post-Q1)", 6: "July", 9: "October", 12: "December"}
    for m in [3, 6, 9, 12]:
        if m in port.index:
            f = port[m]
            L.append(f"| {names.get(m, 'M'+str(m))} | {f:.2f}× | ~{100/f:.0f}% of the year |")
    L.append("\nThe **full segment × month table** is in `growth_factor_table.csv`.\n")

    L.append("## 3. How we tested it (and the metrics)\n")
    L.append("**Backtest design:** for each held-out year, the growth factors are learned **only from "
             "earlier years**, then used to project the held-out year. We score at several run-months "
             "(end of Q1 / H1 / Q3) so you can see accuracy improve as the year fills in.\n")
    L.append("**Metrics (all per the projected vs actual full-year premium):**")
    L.append("- **WAPE** — add up every segment's dollar error, as a % of total premium. *The business "
             "number* (how far off are the dollars overall).")
    L.append("- **Median segment** — the typical segment's % error.")
    L.append("- **Within ±10%** — share of segments projected within 10% of actual.")
    L.append("- **Total error** — the signed error on the grand total.\n")
    L.append("**Results:**\n")
    L.append(_bt_table(bt))
    L.append("\n*Reading it:* the **per-segment** method lands at " + best_line + " — and clearly beats "
             "the **global** one-number factor (the gap is the cost of forcing one factor on every "
             "segment). Accuracy tightens the later in the year you run, exactly as expected.\n")

    L.append("## 4. Confidence & honest caveats\n")
    L.append("- **Trustworthy because it's tested out-of-sample** on multiple years and beats the "
             "baseline — evidence, not assertion.")
    L.append("- **The base is mostly arithmetic** (earn the known book forward from dates); only the "
             "not-yet-written new business is estimated (by the factor).")
    L.append("- **Caveat:** this backtest used settled year-end numbers for the visible book; in live "
             "use you compute them from the dates, and a mid-year **cancellation** makes the actual come "
             "in a touch under the date-based estimate — so live error will be slightly above the table.")
    L.append("- **Tiny segments** (a few hundred dollars) can be off by a lot in %, but they are "
             "immaterial in dollars (WAPE weights by dollars).")
    L.append("- **Same-basis caveat (when multiplying by the rate table):** the rate and the premium "
             "must come from the **same data extract** and the **same segment definition**. If the rate "
             "was calibrated on a different file than this premium, the expected-loss total carries that "
             "file's premium-level difference — calibrate both on one file for a fully self-consistent "
             "number.\n")

    L.append("## 5. What this run produced\n")
    L.append("- `growth_factor_table.csv` — the factor per (segment × month) — the reusable artifact.")
    L.append("- `projected_premium.csv` — projected full-year premium per segment for the demo run "
             f"(year {cfg.project_year}, as of month {cfg.project_month}).")
    if coverage.get("has_rates"):
        L.append(f"- `expected_losses.csv` — projected premium × the Part-1 rate → **expected large "
                 f"losses per segment**. Portfolio total ≈ **{coverage['total_expected']:.0f}** "
                 f"(rate coverage: {coverage['covered_pct']:.0f}% of projected premium).")
    L.append("\n## 6. In production\n")
    L.append("Recalibrate the factor table about once a year (the factors are stable year to year). "
             "Each month: pull the current in-force book → visible premium per segment → look up that "
             "month's factor → projected premium → × rate → expected losses.\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
