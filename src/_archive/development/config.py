"""Load the claim-development config."""
from __future__ import annotations
from dataclasses import dataclass
import yaml


@dataclass
class Config:
    raw: dict

    @property
    def run_name(self): return self.raw["run"]["name"]
    @property
    def output_dir(self): return self.raw["run"]["output_dir"]

    @property
    def triangle_path(self): return self.raw["triangle"]["path"]
    @property
    def ay_col(self): return self.raw["triangle"].get("accident_year_col", "accident_year")
    @property
    def ct_col(self): return self.raw["triangle"].get("covtype_col", "covtype")

    @property
    def method(self): return self.raw["develop"].get("method", "chain_ladder")
    @property
    def tail_factor(self): return dict(self.raw["develop"].get("tail_factor", {}))
    @property
    def expected_prior_csv(self): return self.raw["develop"].get("expected_prior_csv")


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        return Config(raw=yaml.safe_load(fh))
