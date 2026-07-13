"""Load the Step-4 (segment analysis) config.

Like Step 3, this is an orchestrator: it points at the Step-1 and Step-2 configs
(so the actual counts are flagged exactly as the rates were calibrated) rather
than re-declaring the threshold / segments / cat-scope.
"""
from __future__ import annotations
from dataclasses import dataclass
import yaml


@dataclass
class Config:
    raw: dict

    # ---- run -------------------------------------------------------------
    @property
    def run_name(self): return self.raw["run"]["name"]
    @property
    def output_dir(self): return self.raw["run"]["output_dir"]

    # ---- upstream --------------------------------------------------------
    @property
    def step1_config(self): return self.raw["upstream"]["step1_config"]
    @property
    def step2_config(self): return self.raw["upstream"]["step2_config"]
    @property
    def rate_table_glob(self):
        return self.raw["upstream"].get("rate_table_glob", "outputs/**/rate_table_final.csv")

    # ---- analysis params -------------------------------------------------
    @property
    def years(self):
        """Trend window; the LAST year is the anchor for concentration/accuracy."""
        return list(self.raw["analysis"]["years"])
    @property
    def top_segments(self): return int(self.raw["analysis"].get("top_segments", 12))
    @property
    def material_expected(self): return float(self.raw["analysis"].get("material_expected", 1.0))
    @property
    def drift_min_losses(self): return int(self.raw["analysis"].get("drift_min_losses", 5))
    @property
    def drift_hot(self): return float(self.raw["analysis"].get("drift_hot", 1.25))
    @property
    def drift_cold(self): return float(self.raw["analysis"].get("drift_cold", 0.75))
    @property
    def significance_alpha(self): return float(self.raw["analysis"].get("significance_alpha", 0.05))
    @property
    def n_dossiers(self): return int(self.raw["analysis"].get("dossiers", 6))


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        return Config(raw=yaml.safe_load(fh))
