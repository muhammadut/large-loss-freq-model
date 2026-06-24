"""Step 1-3: load the raw extract, clean it, flag large losses, action the
catastrophe-scope decision, and run data-quality gates. 'halt'-severity gates
stop the pipeline so we never publish a rate table on broken input.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd

from .config import Config


@dataclass
class QualityResult:
    name: str
    value: Any
    expectation: str
    ok: bool
    severity: str   # "halt" | "warn"
    message: str


def load_and_prepare(cfg: Config) -> pd.DataFrame:
    """Read only the needed columns, clean keys, action cat scope, and flag large
    losses. Order: fill null region -> drop null industry -> apply cat scope ->
    flag at threshold (mirrors the validated calibration logic)."""
    needed = set(cfg.seg_keys) | {cfg.year_col, cfg.loss_col} | set(cfg.all_lens_cols)
    if cfg.cat_flag_col:
        needed.add(cfg.cat_flag_col)
    if cfg.policy_period_col:
        needed.add(cfg.policy_period_col)

    df = pd.read_csv(cfg.data_path, usecols=lambda c: c in needed)

    # optional: collapse fine-grained regions (e.g. province codes in some extracts)
    # to the canonical grouped rating regions, so the segment definition is stable
    # whichever data file is used.
    if cfg.region_map and cfg.null_region_key in df.columns:
        rm = cfg.region_map
        df[cfg.null_region_key] = df[cfg.null_region_key].map(lambda v: rm.get(v, v))
    if cfg.null_region_key and cfg.null_region_key in df.columns:
        df[cfg.null_region_key] = df[cfg.null_region_key].fillna(cfg.null_region_fill)
    if cfg.drop_null_industry:
        df = df[df[cfg.industry_key].notna()].copy()

    # ---- catastrophe scope (a business decision, made explicit) -------------
    # exclude_flagged : drop rows whose cat flag is populated (needs a real flag)
    # assume_excluded : treat the book as already non-cat (disclose the assumption)
    # include_all     : large losses include catastrophes (disclose it)
    if cfg.cat_scope == "exclude_flagged" and cfg.cat_flag_col in df.columns:
        df = df[df[cfg.cat_flag_col].isna()].copy()

    df["is_large_loss"] = (df[cfg.loss_col] >= cfg.threshold).astype(int)
    return df


def exposure_integrity(df: pd.DataFrame, cfg: Config, lens_col: str,
                       lens_name: str) -> QualityResult:
    """Per-lens check: how many large losses sit on rows whose exposure under THIS
    lens is non-positive/missing. Such losses enter the numerator while their own
    exposure is absent from the denominator -> they inflate the affected segment's
    rate. Run for EVERY lens used (primary and any alternate)."""
    window = df[df[cfg.year_col].isin(cfg.experience_years)]
    large = window[window["is_large_loss"] == 1]
    bad = large[~((large[lens_col] > 0) & large[lens_col].notna())]
    n_bad, n_large = len(bad), len(large)
    share = (n_bad / n_large * 100) if n_large else 0.0
    return QualityResult(
        f"exposure_integrity[{lens_name}]", f"{n_bad}/{n_large} ({share:.1f}%)", "<= 1%",
        share <= 1.0, "warn",
        f"Large losses on rows with non-positive/missing {lens_name} exposure; "
        f"these inflate affected-segment rates. Impute or drop before using this lens.")


def quality_gates(df: pd.DataFrame, cfg: Config) -> list[QualityResult]:
    """Pre-model data-quality checks. 'halt' failures stop the run."""
    out: list[QualityResult] = []
    window = df[df[cfg.year_col].isin(cfg.experience_years)]

    # 1. Every experience year present.
    present = set(window[cfg.year_col].unique())
    missing = [y for y in cfg.experience_years if y not in present]
    out.append(QualityResult("years_present", f"missing={missing}", "no missing years",
                             len(missing) == 0, "halt",
                             "Every configured experience year must appear in the data."))

    # 2. Enough large losses for a stable GLM.
    n_large = int(window["is_large_loss"].sum())
    out.append(QualityResult("min_large_losses", n_large, ">= 50",
                             n_large >= 50, "halt",
                             "Need enough large losses in the window for a stable fit."))

    # 3. Catastrophe scope — honest about what we did.
    if cfg.cat_scope == "exclude_flagged":
        n_catflag = int(df[cfg.cat_flag_col].notna().sum()) if cfg.cat_flag_col in df.columns else 0
        out.append(QualityResult("cat_scope", f"exclude_flagged (flagged rows present={n_catflag})",
                                 "flag usable", n_catflag > 0, "halt",
                                 "cat_scope=exclude_flagged requires a populated cat flag; none found."))
    else:
        out.append(QualityResult("cat_scope", cfg.cat_scope, "disclosed", True, "warn",
                                 f"Large-loss frequency is reported on a '{cfg.cat_scope}' basis "
                                 f"(book assumed non-catastrophe; cat flag empty in this extract)."))

    # 4. Active-lens exposure integrity.
    out.append(exposure_integrity(df, cfg, cfg.lens_col, cfg.lens))

    # 5. Count-grain diagnostic (informational): row count vs distinct policy-period.
    if cfg.policy_period_col and cfg.policy_period_col in df.columns:
        large = window[window["is_large_loss"] == 1]
        rows = len(large)
        uniq = large[cfg.policy_period_col].nunique()
        dup_groups = int((large.groupby(cfg.policy_period_col).size() > 1).sum())
        out.append(QualityResult("count_grain", f"{rows} rows -> {uniq} policy-periods "
                                 f"({dup_groups} multi-row)", "informational", True, "warn",
                                 "Count unit is the coverage-row over threshold; it differs from "
                                 "distinct claim/event count by the multi-row groups shown."))

    return out


def assert_quality(results: list[QualityResult]) -> None:
    """Raise if any 'halt'-severity quality gate failed."""
    fatal = [r for r in results if (not r.ok and r.severity == "halt")]
    if fatal:
        lines = "\n".join(f"  [HALT] {r.name}: {r.message} (got {r.value}, expected {r.expectation})"
                          for r in fatal)
        raise SystemExit("Data-quality gate(s) failed; halting before modeling:\n" + lines)
