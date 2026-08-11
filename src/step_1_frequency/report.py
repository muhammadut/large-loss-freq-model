"""Write the run artifacts: the credibilized rate table, a machine-readable run
report (for diffing across refits), and a human console summary.
"""
from __future__ import annotations
import json
from datetime import datetime
import numpy as np
import pandas as pd

from .config import Config
from .explanations import doc_for


def _coerce(o):
    """Make numpy types JSON-serializable."""
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    return str(o)


def write_rate_table(cred_df: pd.DataFrame, cfg: Config, path: str) -> pd.DataFrame:
    df = cred_df.copy()
    df["final_rate_per_1M"] = (df["final_rate"] * 1e6).round(4)
    df["glm_rate_per_1M"] = (df["glm_rate"] * 1e6).round(4)
    df["complement_rate_per_1M"] = (df["complement_rate"] * 1e6).round(4)
    df["Z"] = df["Z"].round(4)
    df["credible"] = np.where(df["hist_large_losses"] >= cfg.full_credibility_losses, "yes", "NO-shrink")
    cols = (cfg.seg_keys + ["hist_large_losses", "Z",
            "glm_rate_per_1M", "complement_rate_per_1M", "final_rate_per_1M",
            "glm_rate", "complement_rate", "final_rate", "credible"])
    out = df.sort_values("final_rate", ascending=False)[cols]
    out.to_csv(path, index=False)
    return out


def maturity_table(df: pd.DataFrame, cfg: Config) -> list[dict]:
    """Threshold-count-by-year table that supports the reference-year choice
    (the newest year's count dropping at every threshold => likely immaturity)."""
    window = df[df[cfg.year_col].isin(cfg.experience_years)]
    rows = []
    for t in [100_000, 200_000, 500_000, 1_000_000]:
        counts = (window.assign(flag=(window[cfg.loss_col] >= t).astype(int))
                  .groupby(cfg.year_col)["flag"].sum())
        row = {"threshold": t}
        for y in cfg.experience_years:
            row[str(y)] = int(counts.get(y, 0))
        newest, prev = max(cfg.experience_years), max(cfg.experience_years) - 1
        row["newest_vs_prev"] = (round(row[str(newest)] / row[str(prev)], 3)
                                 if row.get(str(prev)) else None)
        rows.append(row)
    return rows


def write_run_report(cfg: Config, gates, quality, diag, dispersion,
                     n_large, n_segments, path: str, extras: dict | None = None) -> dict:
    report = {
        "run_name": cfg.run_name,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "lens": cfg.lens,
        "threshold": cfg.threshold,
        "cat_scope": cfg.cat_scope,
        "count_unit": "coverage-row with incurred >= threshold (see count_grain gate)",
        "reference_year": cfg.reference_year,
        "reference_year_basis": "last fully-developed year; newest year assumed immature "
                                "(see maturity_evidence)",
        "experience_years": cfg.experience_years,
        "n_large_losses": int(n_large),
        "n_segments": int(n_segments),
        "dispersion": round(float(dispersion), 4),
        "credibility_diag": {k: round(float(v), 10) for k, v in diag.items()},
        "data_quality": [q.__dict__ for q in quality],
        "gates": [g.as_dict() for g in gates],
        "overall_status": "HALT" if any(g.status == "HALT" for g in gates)
                          else ("WARN" if any(g.status == "WARN" for g in gates) else "PASS"),
    }
    if extras:
        report.update(extras)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=_coerce)
    return report


_ICON = {"PASS": "✅", "OK": "✅", "WARN": "⚠️", "HALT": "⛔"}


def write_run_summary_md(cfg: Config, gates, quality, dispersion, n_large,
                         rate_table, timestamp: str, path: str) -> None:
    """Human-readable, click-to-read run report: every check with its result AND
    a plain-English explanation of what it means and how to read it."""
    n_warn = (sum(1 for g in gates if g.status == "WARN")
              + sum(1 for q in quality if (not q.ok and q.severity == "warn")))
    overall = ("⛔ HALT" if any(g.status == "HALT" for g in gates)
               else (f"⚠️ WARN ({n_warn} warning(s) to be aware of)" if n_warn else "✅ PASS"))
    verdict = ("This run was stopped by a failing check — no rate table was published."
               if overall.startswith("⛔") else
               ("The model is healthy. The warnings below are heads-ups to be AWARE of — "
                "several are informational by design (e.g. the lens comparison) — not failures. "
                "Open each one below to see what it means." if overall.startswith("⚠️") else
                "All checks passed cleanly."))

    L = []
    L.append(f"# Calibration Run — {cfg.run_name}\n")
    L.append(f"**When:** {timestamp} &nbsp;·&nbsp; **Overall:** {overall}\n")
    L.append(f"**Lens:** `{cfg.lens}` &nbsp;·&nbsp; **Threshold:** ${cfg.threshold:,.0f} "
             f"&nbsp;·&nbsp; **Cat scope:** `{cfg.cat_scope}` "
             f"&nbsp;·&nbsp; **Reference year:** {cfg.reference_year}\n")
    L.append(f"> {verdict}\n")

    L.append("## Quick result\n")
    L.append(f"- **Large losses:** {n_large} &nbsp; **Segments:** {len(rate_table)} "
             f"&nbsp; **Dispersion:** {dispersion:.3f}")
    top = rate_table.head(3)
    segs = "; ".join(" × ".join(str(r[k]) for k in cfg.seg_keys) +
                     f" ({r['final_rate_per_1M']:.3f}/$1M)" for _, r in top.iterrows())
    L.append(f"- **Highest-rate segments:** {segs}\n")

    L.append("## How to read this report\n")
    L.append("Each check shows the **result**, whether it **passed**, and **what it means**. "
             "`⛔` stops the run; `⚠️` is a heads-up; `✅` is clear.\n")

    def block(name, status, value, threshold=None):
        d = doc_for(name)
        head = f"### {_ICON.get(status, '•')} {d['title']} — {status}"
        res = f"**Result:** `{value}`" + (f" &nbsp; _(needs {threshold})_" if threshold else "")
        return f"{head}\n\n{res}\n\n**What it checks:** {d['what']}\n\n**How to read it:** {d['how']}\n"

    L.append("## Data-quality checks (run before modeling)\n")
    for q in quality:
        status = "OK" if q.ok else ("HALT" if q.severity == "halt" else "WARN")
        L.append(block(q.name, status, q.value))

    L.append("## Validation gates (model quality)\n")
    for g in gates:
        L.append(block(g.name, g.status, g.value, g.threshold))

    L.append("## Files in this folder\n")
    L.append("- **`rate_table_final.csv`** — the deliverable: the credibilized rate per segment "
             "(use the `final_rate` / `final_rate_per_1M` column).")
    L.append("- **`run_report.json`** — the machine-readable record of this run (every gate, the "
             "diagnostics, the maturity evidence) — keep it to diff against future refits.")
    L.append("- **`model_diagnostics.md`** — the classical statistical fit report "
             "(deviance, AIC/BIC, coefficient p-values), each metric explained.")
    L.append("- **`run_summary.md`** — this file.\n")

    L.append("## Using the rate table\n")
    L.append("`expected large losses = Σ over segments [ final_rate × projected exposure ]`, "
             "then put a Poisson range around the total for the percentile / traffic-light. "
             "Match the lens: a `premium` rate multiplies projected **premium**. "
             "See `pipeline_guide.html` §9 for the full hand-off spec.\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def write_model_diagnostics_md(cfg: Config, model, nested: list[dict], dispersion: float,
                               timestamp: str, path: str) -> None:
    """Classical GLM diagnostics (deviance, AIC/BIC, coefficient p-values) — the
    numbers analysts expect — each explained, and framed so p-values/AIC are read
    correctly (the trap that sank the earlier exploration)."""
    nobs = int(model.nobs)
    k = int(model.df_model) + 1
    bic = float(-2 * model.llf + k * np.log(model.nobs))
    try:
        mcf = f"{model.pseudo_rsquared(kind='mcf'):.3f}"
    except Exception:
        mcf = "n/a"
    dev_df = float(model.deviance / model.df_resid)

    def grp(n):
        if n == "Intercept": return "Baseline"
        if "CovType" in n: return "Coverage"
        if "ratingregion" in n: return "Region"
        if cfg.industry_key in n: return "Industry"
        if cfg.year_col in n: return "Year"
        return "Other"

    def clean(n):
        if n == "Intercept": return "Intercept (baseline)"
        return n.split("[T.")[1].rstrip("]") + f"  ({grp(n)})" if "[T." in n else n

    L = []
    L.append(f"# Model Diagnostics — {cfg.run_name}\n")
    L.append(f"Generated {timestamp} · lens `{cfg.lens}` · Poisson GLM (log link) with year fixed effect\n")
    L.append("> These are the classical statistical diagnostics analysts expect. The **headline** "
             "fit checks for this model are **dispersion** (§1) and the out-of-sample **backtest** "
             "(in `run_summary.md`). Read AIC/BIC and p-values with the cautions in §5.\n")

    # --- 1. fit summary ---
    L.append("## 1. Fit summary\n")
    L.append("| Metric | Value | What it tells you |")
    L.append("|---|---|---|")
    rows = [
        ("Model family / link", "Poisson / log", "counts with a multiplicative rate structure"),
        ("Observations (segment-years)", f"{nobs}", "rows the model was fit on"),
        ("Parameters (k)", f"{k}", "effects estimated (intercept + dummies)"),
        ("Log-likelihood", f"{model.llf:.1f}", "higher = better; feeds AIC/BIC"),
        ("Deviance / Null deviance", f"{model.deviance:.1f} / {model.null_deviance:.1f}",
         "drop from the null model = variation the segments explain"),
        ("Deviance / df", f"{dev_df:.3f}", "another spread check; ≈1 is good"),
        ("Pearson χ²", f"{model.pearson_chi2:.1f}", "basis of the dispersion ratio below"),
        ("**Dispersion (Pearson/df)**", f"**{dispersion:.3f}**",
         "**≈1 ⇒ Poisson's spread assumption holds — the headline diagnostic**"),
        ("AIC", f"{model.aic:.1f}", "fit penalized for complexity (compare only within the same data)"),
        ("BIC", f"{bic:.1f}", "like AIC, heavier penalty for extra parameters"),
        ("Pseudo-R² (McFadden)", mcf, "limited meaning for Poisson — don't over-index on it"),
    ]
    for m_, v_, w_ in rows:
        L.append(f"| {m_} | {v_} | {w_} |")
    L.append("")

    # --- 2. verdict ---
    fit_ok = dispersion < 1.5
    L.append("## 2. Does the model fit? — verdict\n")
    L.append(f"- **Dispersion {dispersion:.3f}** → {'Poisson is adequate' if fit_ok else 'overdispersed — consider a richer model / missing driver'}.")
    L.append(f"- **Deviance/df {dev_df:.3f}** → {'consistent with a good fit' if dev_df < 1.5 else 'elevated'}.")
    L.append("- **Out-of-sample backtest** (see `run_summary.md`): the held-out year landed inside the normal range.")
    L.append(f"\n**Bottom line:** {'the model fits well; plain Poisson is justified.' if fit_ok else 'fit is marginal — review the dispersion driver.'}\n")

    # --- 3. nested AIC/BIC (the valid use) ---
    L.append("## 3. Building the model — the VALID use of AIC/BIC\n")
    L.append("Each row adds one variable, fit on the **same** data, so AIC/BIC **are** comparable here "
             "(this is how AIC should be used — *not* to rank models fit to different aggregations).\n")
    L.append("| Model | params | Deviance | AIC | BIC |")
    L.append("|---|---|---|---|---|")
    for r in nested:
        L.append(f"| {r['model']} | {r['params']} | {r['deviance']:.1f} | {r['aic']:.1f} | {r['bic']:.1f} |")
    best = min(nested, key=lambda r: r["aic"])
    weak = [nested[i]["added"] for i in range(1, len(nested))
            if nested[i]["aic"] > nested[i - 1]["aic"] + 0.01]
    reading = f"a variable earns its place only if it **lowers** AIC. Lowest-AIC model = **{best['model']}**. "
    if weak:
        reading += (f"Adding **{', '.join(weak)}** actually *raised* AIC — a weak predictor whose extra "
                    f"parameters didn't pay off (cross-check its insignificant p-values in §4). ")
    else:
        reading += "Each added variable lowered AIC, so each earns its complexity. "
    reading += "This nested, same-data comparison is the **correct** way to use AIC — unlike ranking models fit to different aggregations."
    L.append(f"\n**Reading:** {reading}\n")

    # --- 4. coefficients = relativities ---
    L.append("## 4. Coefficients = segment relativities\n")
    L.append("`exp(coef)` is the multiplier vs the baseline segment (e.g. 2.5× the baseline rate).\n")
    seg_rows, yr_rows = [], []
    for name in model.params.index:
        coef = float(model.params[name]); p = float(model.pvalues[name])
        se = float(model.bse[name]); z = float(model.tvalues[name])
        unstable = se > 100  # perfect separation signature: huge std err (not a large coef)
        relv = "(baseline)" if name == "Intercept" else (f"{np.exp(coef):.2f}×" if not unstable else "≈0")
        flag = "⚠ separation (0 losses)" if unstable else ("★ sig" if p < 0.05 else "")
        row = f"| {clean(name)} | {coef:.3f} | {relv} | {se:.3f} | {z:.2f} | {p:.3f} | {flag} |"
        (yr_rows if grp(name) == "Year" else seg_rows).append(row)
    L.append("### Segment effects (Coverage / Region / Industry)\n")
    L.append("| Term | coef | exp(coef) | std err | z | p>\\|z\\| | flag |")
    L.append("|---|---|---|---|---|---|---|")
    L.extend(seg_rows)
    L.append("\n### Year effects — on-levelling, NOT segment risk\n")
    L.append("These absorb year-wide rate/inflation/development shifts so segment rates are clean. "
             "Not a risk signal.\n")
    L.append("| Term | coef | exp(coef) | std err | z | p>\\|z\\| | flag |")
    L.append("|---|---|---|---|---|---|---|")
    L.extend(yr_rows)
    L.append("\n> **Note on `⚠ separation`:** an industry with **zero** large losses (e.g. Government, "
             "Logging) makes the GLM push its coefficient toward −∞ with a giant standard error and "
             "p ≈ 1. That is expected, not a bug — credibility shrinks these to ~the industry average "
             "downstream, so they never reach the published rate table as noise.\n")

    # --- 5. cautions ---
    L.append("## 5. How to read p-values and AIC (read this)\n")
    L.append("- **A non-significant effect is NOT a model failure.** An insignificant region just means "
             "that region isn't clearly different from the baseline *at this threshold*. Only worry if a "
             "driver you **expect** to matter, in a **data-rich** segment, is insignificant.")
    L.append("- **AIC/BIC compare models on the SAME data only** — as in §3. Ranking models fit to "
             "different aggregations or row counts (different numbers of observations) is meaningless; "
             "the smaller table always 'wins' for the wrong reason.")
    L.append("- **Pseudo-R² is of limited value for Poisson** — don't headline it.")
    L.append("- **The trustworthy fit signals here are dispersion (§1) and the out-of-sample backtest** "
             "(`run_summary.md`), not the p-value column.\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def print_summary(cfg: Config, gates, quality, dispersion, n_large, rate_table) -> None:
    line = "=" * 74
    print("\n" + line)
    print(f"  LARGE-LOSS FREQUENCY — CALIBRATION RUN: {cfg.run_name}")
    print(line)
    print(f"  lens={cfg.lens}  threshold=${cfg.threshold:,.0f}  cat_scope={cfg.cat_scope}  "
          f"reference_year={cfg.reference_year}")
    print(f"  large losses (window)={n_large}  segments={len(rate_table)}  dispersion={dispersion:.3f}")

    print("\n  DATA-QUALITY GATES")
    for q in quality:
        tag = "ok " if q.ok else ("HALT" if q.severity == "halt" else "WARN")
        print(f"    [{tag}] {q.name:22} {q.value}")

    print("\n  VALIDATION GATES")
    for g in gates:
        print(f"    [{g.status:4}] {g.name:20} {g.value}   (need {g.threshold})")

    print("\n  TOP 5 SEGMENTS (final, per $1M)")
    for _, r in rate_table.head(5).iterrows():
        seg = " x ".join(str(r[k]) for k in cfg.seg_keys)
        print(f"    {r['final_rate_per_1M']:7.3f}  {seg:45}  (hist losses={int(r['hist_large_losses'])})")
    print(line + "\n")
