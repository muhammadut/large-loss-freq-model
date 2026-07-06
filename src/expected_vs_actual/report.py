"""Write the Step-3 artifacts: the board report (markdown) plus the CSV/JSON
records behind it."""
from __future__ import annotations
import json
import os
import pandas as pd


def write_csv(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False)


def _movers(seg: pd.DataFrame, keys, n=8) -> pd.DataFrame:
    s = seg.copy()
    s["deviation"] = s["actual_losses"] - s["expected_losses"]
    s["seg"] = s[keys].astype(str).agg(" · ".join, axis=1)
    s = s.reindex(s["deviation"].abs().sort_values(ascending=False).index)
    return s[["seg", "expected_losses", "actual_losses", "deviation"]].head(n)


def write_board_report(path, *, cfg, rate_table_path, dispersion, verdict, wf,
                       narrative, seg_verdict, keys, verdict_year, prior_year,
                       run_month, current_watch, by_year):
    L = []
    A = L.append
    A("# Step 3 — Expected vs Actual (board report)\n")
    A("> Expected large-loss count = Σ ( Step-1 rate × Step-2 projected premium ), "
      "compared to what actually happened. This is the board-facing deliverable.\n")
    A("| Basis | Value |")
    A("|---|---|")
    A(f"| Data extract | `{os.path.basename(os.path.dirname(rate_table_path)) or rate_table_path}` (rate table) |")
    A(f"| Verdict year | **{verdict_year}** (last fully-developed year) |")
    A(f"| Premium basis | run at month {run_month} "
      f"({'full-year premium known' if run_month == 12 else 'mid-year projection'}) |")
    A(f"| Count model | {verdict['band_model']} (Step-1 dispersion "
      f"{dispersion:.2f} → {'Poisson adequate' if (dispersion or 1) <= 1.5 else 'overdispersed'}) |\n")

    # 1. Verdict
    A(f"## 1. Verdict — {verdict_year}\n")
    A("| Expected | Actual | Gap | Percentile | Normal range (5–95th) | Status |")
    A("|---:|---:|---:|---:|:---:|:---:|")
    A(f"| {verdict['expected']:.1f} | {verdict['actual']} | {verdict['gap']:+.1f} | "
      f"{verdict['percentile']:.0f}th | {verdict['ci_5th']}–{verdict['ci_95th']} | "
      f"**{verdict['traffic_light']}** |\n")
    A("```")
    A(narrative)
    A("```\n")

    # 2. Waterfall
    A(f"## 2. Why it moved — {prior_year} → {verdict_year} attribution waterfall\n")
    A("| Step | Count |")
    A("|---|---:|")
    A(f"| Prior expected ({prior_year}) | {wf['prior_expected']:.1f} |")
    A(f"| + Volume (portfolio growth) | {wf['volume_effect']:+.1f} |")
    A(f"| + Mix (segment shift) | {wf['mix_effect']:+.1f} |")
    A(f"| + Rate (frozen table) | {wf['rate_effect']:+.1f} |")
    A(f"| = Current expected ({verdict_year}) | {wf['current_expected']:.1f} |")
    A(f"| + Random (Poisson noise, z={wf['random_z']:+.2f}) | {wf['random_effect']:+.1f} |")
    A(f"| = Actual ({verdict_year}) | {wf['actual']} |\n")
    A("*Pieces reconcile exactly to (actual − prior expected). Rate effect is ~0 because "
      "the rate table is frozen between annual recalibrations — the move is volume + mix + noise.*\n")

    # 3. Segment movers
    A("## 3. Largest segment deviations (verdict year)\n")
    mv = _movers(seg_verdict, keys)
    A("| Segment | Expected | Actual | Deviation |")
    A("|---|---:|---:|---:|")
    for _, r in mv.iterrows():
        A(f"| {r['seg']} | {r['expected_losses']:.2f} | {int(r['actual_losses'])} | "
          f"{r['deviation']:+.2f} |")
    A("")

    # 4. Current-year watch
    if current_watch:
        cy = current_watch
        A(f"## 4. Current-year watch — {cy['year']} (⚠ still developing, NOT a verdict)\n")
        A(f"Full-year **expected ≈ {cy['expected']:.0f}**, but only **{cy['actual_reported']} "
          f"reported so far**. Reported counts by year:\n")
        A("| Year | Actual large losses |")
        A("|---:|---:|")
        for _, r in by_year.iterrows():
            flag = "  ⚠ developing" if int(r.iloc[0]) == cy["year"] else ""
            A(f"| {int(r.iloc[0])} | {int(r['actual_losses'])}{flag} |")
        A("")
        A(f"The {cy['year']} count *falls* versus {cy['year']-1} despite premium growth — the "
          "signature of **reporting/development lag** (large claims take time to be reported and "
          "to breach the threshold). Comparing a full-year expectation to a partial-year actual "
          "would manufacture a false RED. The verdict is therefore taken on the last fully-developed "
          f"year ({verdict_year}); {cy['year']} is revisited once mature.\n")

    # 5. Method & caveats
    A("## 5. Method & caveats\n")
    A("- **One multiplication, consistent bases.** Rate and premium are both calibrated on the "
      "same extract; the actual count is flagged with the same $200K threshold, cat-scope, and "
      "segment definition used to build the rates.\n"
      "- **Count grain.** The count is the coverage-row over threshold (same unit Step 1 calibrated "
      "on), not a de-duplicated claim/event count.\n"
      "- **Development lag (V1).** Losses are assumed reported by year-end; the most recent year is "
      "immature and shown only as a watch.\n"
      "- **Frozen rate table.** Step 3 consumes `rate_table_final.csv`; it never re-fits. Rates change "
      "only at the annual recalibration (Step 1).\n"
      f"- **Confidence band.** {verdict['band_model']} around the expected mean; a percentile inside "
      f"{cfg.green_band[0]}–{cfg.green_band[1]} is GREEN, inside {cfg.amber_band[0]}–{cfg.amber_band[1]} "
      "AMBER, else RED.\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def write_json(path, payload: dict):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
