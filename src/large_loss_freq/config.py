"""Load + validate the YAML config into a typed Config object.

Philosophy: fail loudly at load time. A misconfigured run should never reach the
modeling stage and silently produce a wrong rate table.
"""
from __future__ import annotations
from dataclasses import dataclass
import yaml

ALLOWED_LENSES = {"premium", "tiv", "earned_exposure"}
ALLOWED_ON_FAIL = {"halt", "warn"}
ALLOWED_CAT_SCOPE = {"assume_excluded", "exclude_flagged", "include_all"}
IMPLEMENTED_FAMILIES = {"poisson"}        # NB not yet implemented (see model.py)
IMPLEMENTED_THRESHOLD_MODES = {"fixed"}   # percentile not yet implemented (see data.py)


@dataclass
class Config:
    raw: dict
    path: str

    # ---- run -------------------------------------------------------------
    @property
    def run_name(self) -> str: return self.raw["run"].get("name", "run")
    @property
    def output_dir(self) -> str: return self.raw["run"].get("output_dir", "src/outputs")

    # ---- data ------------------------------------------------------------
    @property
    def data_path(self) -> str: return self.raw["data"]["path"]
    @property
    def loss_col(self) -> str: return self.raw["data"]["loss_col"]
    @property
    def year_col(self) -> str: return self.raw["data"]["year_col"]
    @property
    def cat_flag_col(self): return self.raw["data"].get("cat_flag_col")
    @property
    def policy_period_col(self): return self.raw["data"].get("policy_period_col")

    # ---- large loss ------------------------------------------------------
    @property
    def threshold(self) -> float: return float(self.raw["large_loss"]["threshold"])
    @property
    def threshold_mode(self) -> str: return self.raw["large_loss"].get("mode", "fixed")
    @property
    def cat_scope(self) -> str: return self.raw["large_loss"].get("cat_scope", "assume_excluded")

    # ---- exposure / lens -------------------------------------------------
    @property
    def lens(self) -> str: return self.raw["exposure"]["lens"]
    @property
    def lens_col(self) -> str: return self.raw["exposure"]["columns"][self.lens]
    def col_for_lens(self, lens: str) -> str: return self.raw["exposure"]["columns"][lens]
    @property
    def all_lens_cols(self): return list(self.raw["exposure"]["columns"].values())

    # ---- segmentation ----------------------------------------------------
    @property
    def seg_keys(self): return list(self.raw["segmentation"]["keys"])
    @property
    def industry_key(self) -> str: return self.raw["segmentation"]["industry_key"]
    @property
    def null_region_key(self): return self.raw["segmentation"].get("null_region_key")
    @property
    def null_region_fill(self) -> str: return self.raw["segmentation"].get("null_region_fill", "Unknown")
    @property
    def drop_null_industry(self) -> bool: return bool(self.raw["segmentation"].get("drop_null_industry", True))

    # ---- calibration -----------------------------------------------------
    @property
    def experience_years(self): return list(self.raw["calibration"]["experience_years"])
    @property
    def reference_year(self) -> int: return int(self.raw["calibration"]["reference_year"])
    @property
    def family(self) -> str: return self.raw["calibration"].get("family", "poisson")
    @property
    def year_effect(self) -> bool: return bool(self.raw["calibration"].get("year_effect", True))

    # ---- credibility -----------------------------------------------------
    @property
    def level1_keys(self): return list(self.raw["credibility"]["level1_keys"])
    @property
    def full_credibility_losses(self) -> int:
        return int(self.raw["credibility"].get("full_credibility_losses", 5))

    # ---- validation ------------------------------------------------------
    @property
    def gates(self) -> dict: return self.raw["validation"]


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    cfg = Config(raw=raw, path=path)
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    e = []
    if cfg.threshold <= 0:
        e.append("large_loss.threshold must be > 0")
    if cfg.lens not in ALLOWED_LENSES:
        e.append(f"exposure.lens must be one of {sorted(ALLOWED_LENSES)} (got '{cfg.lens}')")
    if cfg.lens not in cfg.raw["exposure"]["columns"]:
        e.append(f"exposure.columns has no entry for chosen lens '{cfg.lens}'")
    if not cfg.seg_keys:
        e.append("segmentation.keys must be non-empty")
    if cfg.industry_key not in cfg.seg_keys:
        e.append(f"segmentation.industry_key '{cfg.industry_key}' must be in segmentation.keys")
    for k in cfg.level1_keys:
        if k not in cfg.seg_keys:
            e.append(f"credibility.level1_keys '{k}' must be in segmentation.keys")
    # The hard-shaped credibility hierarchy merges level-1 -> industry, so the
    # industry key MUST be in level1_keys or apply_credibility() crashes at runtime.
    if cfg.industry_key not in cfg.level1_keys:
        e.append(f"credibility.level1_keys must include segmentation.industry_key "
                 f"('{cfg.industry_key}') for the current hierarchy implementation")
    if cfg.reference_year not in cfg.experience_years:
        e.append(f"calibration.reference_year ({cfg.reference_year}) must be in experience_years")
    # Fail fast on config switches that are recognized but NOT yet implemented,
    # so a refit can never silently run a different model than the config states.
    if cfg.threshold_mode not in IMPLEMENTED_THRESHOLD_MODES:
        e.append(f"large_loss.mode='{cfg.threshold_mode}' is not implemented; "
                 f"only {sorted(IMPLEMENTED_THRESHOLD_MODES)} is supported")
    if cfg.family not in IMPLEMENTED_FAMILIES:
        e.append(f"calibration.family='{cfg.family}' is not implemented; "
                 f"only {sorted(IMPLEMENTED_FAMILIES)} is supported "
                 f"(the dispersion gate flags if NB is warranted)")
    if cfg.cat_scope not in ALLOWED_CAT_SCOPE:
        e.append(f"large_loss.cat_scope must be one of {sorted(ALLOWED_CAT_SCOPE)}")
    for gname, g in cfg.gates.items():
        if isinstance(g, dict) and g.get("on_fail") not in ALLOWED_ON_FAIL:
            e.append(f"validation.{gname}.on_fail must be 'halt' or 'warn'")
    if e:
        raise ValueError("Config invalid:\n  - " + "\n  - ".join(e))
