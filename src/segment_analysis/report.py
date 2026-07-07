"""Write the segment-analysis artifacts: the markdown report and the master CSV."""
from __future__ import annotations
import pandas as pd


def write_csv(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False)


def write_segment_report(path, master, vy, years, views):
    u, o, rho = views["under"], views["over"], views["rho"]
    conc_all, conc_top = views["conc_all"], views["conc_top"]
    drift_moving = views["drift_moving"]
    share_cred, n_cred, n_thin, thin_mat = views["confidence"]

    n_seg = len(master)
    n80 = int((conc_all["contribution_pct"].cumsum() <= 80).sum()) + 1
    top5 = conc_all.head(5)["contribution_pct"].sum()
    top10 = conc_all.head(10)["contribution_pct"].sum()

    L = []; A = L.append
    A("# Segment analysis (Step 4)\n")
    A(f"> Four questions a business asks once it trusts the portfolio total, answered per "
      f"segment for **{vy}** (with {years[0]}–{years[-1]} for trend). Built from the frozen "
      f"rate table × each year's premium vs the actual counts — no new modelling, just lenses. "
      f"A plain-English walkthrough is in `segment_analysis_explained.md`.\n")

    # 1. Concentration
    A("## 1. Concentration — where the large-loss exposure actually is\n")
    A(f"The book is **top-heavy**: the largest **5** segments carry **{top5:.0f}%** of expected "
      f"large losses, the top **10** carry **{top10:.0f}%**, and just **{n80} of {n_seg}** "
      f"segments account for 80%. That is where pricing and monitoring attention belongs.\n")
    A("| # | Segment | Expected | Share | Cumulative | Hist losses |")
    A("|---:|---|---:|---:|---:|---:|")
    cum = conc_all["contribution_pct"].cumsum().reset_index(drop=True)
    for i, (_, r) in enumerate(conc_top.iterrows(), 1):
        A(f"| {i} | {r['seg']} | {r['expected']:.1f} | {r['contribution_pct']:.1f}% | "
          f"{cum.iloc[i-1]:.1f}% | {int(r['hist_large_losses'])} |")
    A("")

    # 2. Accuracy
    A("## 2. Accuracy — where the model is off, and whether it's structural\n")
    A(f"Segment rank calibration (Spearman) = **{rho:.2f}** — the model orders segments by risk "
      "well, not just the total. The misses below are tagged **structural** (the actual has been "
      "on the same side of expected in most tracked years → a pricing signal) or **noise** (a "
      "one-off swing).\n")
    A(f"**Actual above expected — possible under-rating ({vy}):**\n")
    A("| Segment | Expected | Actual | Gap | Pattern |")
    A("|---|---:|---:|---:|:--:|")
    for _, r in u.iterrows():
        A(f"| {r['seg']} | {r['expected']:.1f} | {int(r['actual'])} | {r['deviation']:+.1f} | "
          f"{'structural ⚠' if r['pattern']=='structural' else 'noise'} |")
    A(f"\n**Actual below expected — possible over-rating ({vy}):**\n")
    A("| Segment | Expected | Actual | Gap | Pattern |")
    A("|---|---:|---:|---:|:--:|")
    for _, r in o.iterrows():
        A(f"| {r['seg']} | {r['expected']:.1f} | {int(r['actual'])} | {r['deviation']:+.1f} | "
          f"{'structural ⚠' if r['pattern']=='structural' else 'noise'} |")
    A("")

    # 3. Drift
    A("## 3. Emerging risk — segments heating up or cooling down\n")
    A("O/E = actual ÷ expected. Above 1 = running **hot** (more losses than its rate implies); "
      "below 1 = **cold**. Restricted to segments with enough history to be meaningful "
      "(≥5 historical losses). These are the early-warning candidates.\n")
    if len(drift_moving):
        oe_cols = " | ".join(f"O/E {y}" for y in years)
        A(f"| Segment | {oe_cols} | Recent O/E | Signal |")
        A("|---|" + "---:|" * len(years) + "---:|:--:|")
        for _, r in drift_moving.iterrows():
            oes = " | ".join(f"{r[f'oe_{y}']:.2f}" if pd.notna(r[f'oe_{y}']) else "–" for y in years)
            tag = "HOT ↑" if r["signal"] == "HOT" else "COLD ↓"
            A(f"| {r['seg']} | {oes} | {r['oe_recent']:.2f} | {tag} |")
    else:
        A("*No material segment is currently running hot or cold beyond the thresholds.*")
    A("")

    # 4. Confidence
    A("## 4. Confidence — which rates rest on thin data\n")
    A(f"**{share_cred:.0f}%** of expected large losses sit in **credible** segments "
      f"(≥5 historical losses; {n_cred} segments); the remaining {n_thin} segments are thin and "
      "lean on their industry complement. The rates below are the **big bets on thin data** — "
      "material expected losses but a low-credibility own-rate, so they are the first to validate "
      "before any pricing move.\n")
    A("| Segment | Expected | Credibility Z | Hist losses |")
    A("|---|---:|---:|---:|")
    for _, r in thin_mat.iterrows():
        A(f"| {r['seg']} | {r['expected']:.1f} | {r['Z']:.2f} | {int(r['hist_large_losses'])} |")
    A("")

    A("## How to read this & caveats\n")
    A("- **Starter, not the last word.** These are four high-value cuts to get moving; each can "
      "go deeper (e.g. severity, sub-industry, per-policy).\n"
      "- **Frozen rates.** Expected = the shipped rate × that year's premium; it reflects the rates "
      "the business will actually use.\n"
      "- **Small segments are noisy.** O/E and single-year gaps swing hard on tiny expected counts; "
      "the drift view is limited to ≥5-loss segments, and 'structural' needs a multi-year pattern.\n"
      "- **Full detail** is in `segment_master.csv` (every segment, every column).\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
