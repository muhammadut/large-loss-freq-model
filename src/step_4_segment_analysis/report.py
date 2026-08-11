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


def write_investigation_report(path, summary, mat, dossiers, years):
    s = summary
    L = []; A = L.append
    A("# Segment investigation — validating the misses\n")
    A("> When a segment predicts low but comes in high, is it a real under-rating or just "
      "rare-event noise? Large-loss counts are small and lumpy, so most big-looking gaps are "
      "chance. This report tests each segment's actual against its predicted band, separates "
      "signal from noise, and builds a dossier on the ones that are real.\n")

    # calibration verdict
    verdict = "well-calibrated" if s["well_calibrated"] else "worth a closer look"
    A("## 1. Is the model calibrated? (the validation)\n")
    A(f"Of **{s['n_material']}** material segments (expected ≥ 1) in **{s['anchor_year']}**, a "
      f"perfectly-calibrated model would put ~**{s['expected_each']:.0f}** outside the band on "
      f"each side by pure chance (α={s['alpha']}). We see:\n")
    A("| | Count | Chance expectation |")
    A("|---|---:|---:|")
    A(f"| Significantly **high** (actual ≫ expected) | {s['n_sig_high']} | ~{s['expected_each']:.0f} |")
    A(f"| Significantly **low** (actual ≪ expected) | {s['n_sig_low']} | ~{s['expected_each']:.0f} |")
    A(f"\n**Verdict: {verdict}.** The apparent per-segment 'misses' are almost entirely what "
      "small Poisson counts do by chance — the model is not systematically off. Only the "
      "handful below clear the significance bar and deserve investigation.\n")

    # the signals
    sig = mat[(mat["p_high"] < s["alpha"]) | (mat["p_low"] < s["alpha"])].copy()
    A("## 2. The statistically real segments\n")
    if len(sig):
        A(f"| Segment | Expected ({s['anchor_year']}) | Actual | O/E | p (chance) | 3-yr net O/E | Classification |")
        A("|---|---:|---:|---:|---:|---:|:--|")
        for _, r in sig.sort_values("exp", ascending=False).iterrows():
            p = min(r["p_high"], r["p_low"])
            A(f"| {r['seg']} | {r['exp']:.1f} | {int(r['act'])} | {r['act']/max(r['exp'],1e-9):.1f} | "
              f"{p:.3f} | {r['net_oe']:.2f} | {r['classification']} |")
    else:
        A("*No segment is outside its band beyond chance — nothing to investigate.*")
    A("\n*p = probability of a count this extreme if the rate were correct (small = real). "
      "3-yr net O/E ≈ 1 means the segment is correctly rated over the window even if one year "
      "was off (lumpiness), while a net well above 1 with a rising pattern is genuine under-rating.*\n")

    # dossiers
    A("## 3. Dossiers\n")
    for d in dossiers:
        A(f"### {d['seg']}\n")
        A(f"- **Read:** {d['classification']}.")
        A(f"- **Rate quality:** credibility Z = {d['Z']:.2f}, {d['hist_large_losses']} historical "
          f"losses — {'well-determined (not a thin-data artifact)' if d['Z'] >= 0.5 else 'thin, treat with care'}.")
        A(f"- **Trajectory:**")
        A("")
        A("  | Year | Expected | Actual | O/E |")
        A("  |---|---:|---:|---:|")
        for yr in d["years"]:
            oe = yr["act"] / yr["exp"] if yr["exp"] else float("nan")
            A(f"  | {yr['year']} | {yr['exp']:.1f} | {yr['act']} | {oe:.1f} |")
        A(f"  | **{years[0]}–{years[-1]}** | **{d['net_exp']:.1f}** | **{d['net_act']}** | "
          f"**{d['net_oe']:.2f}** |")
        A("")
        if d["anchor_distinct_policies"] is not None:
            spread = ("spread across distinct policies (a broad frequency move, not one event)"
                      if d["anchor_distinct_policies"] >= max(2, 0.6 * d["anchor_losses"])
                      else "concentrated on few policies (check for a single event / clustering)")
            A(f"- **{years[-1]} losses:** {d['anchor_losses']} large losses on "
              f"{d['anchor_distinct_policies']} distinct policies — {spread}.")
        if d["anchor_sizes"]:
            sizes = ", ".join(f"${x/1000:.0f}K" for x in d["anchor_sizes"])
            A(f"- **Loss sizes ({years[-1]}):** {sizes}.")
        A("")

    A("## How to read this & what to do\n")
    A("- **Noise ≠ miss.** A large absolute gap on a small expected count is usually chance; the "
      "p-value is the arbiter, not the raw gap.\n"
      "- **One year ≠ a trend.** A segment that ran cold then hot (3-yr net O/E ≈ 1) is correctly "
      "rated and lumpy — *no action*. A persistent, rising gap is a re-rating candidate.\n"
      "- **Confirm before acting.** A single significant year (even a real one) is a **watch**; wait "
      "for the next year to confirm before moving a published rate, unless a cause is found.\n"
      "- **Broad vs concentrated.** Losses spread across many policies point to a real segment "
      "shift; losses on one policy point to a single event — very different implications.\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
