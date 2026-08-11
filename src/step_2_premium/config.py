"""Load the premium-projection config into a small typed object."""
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
    def data_path(self): return self.raw["data"]["path"]
    @property
    def premium_col(self): return self.raw["data"]["premium_col"]
    @property
    def year_col(self): return self.raw["data"]["year_col"]
    @property
    def eff_col(self): return self.raw["data"]["eff_col"]
    @property
    def exp_col(self): return self.raw["data"]["exp_col"]
    @property
    def keys(self): return list(self.raw["segmentation"]["keys"])
    @property
    def null_region_key(self): return self.raw["segmentation"].get("null_region_key")
    @property
    def fill_value(self): return self.raw["segmentation"].get("fill_value", "Unknown")
    @property
    def region_map(self): return self.raw["segmentation"].get("region_map")
    @property
    def experience_years(self): return list(self.raw["calibration"]["experience_years"])
    @property
    def clip_max_factor(self): return float(self.raw["calibration"].get("clip_max_factor", 5.0))
    @property
    def min_visible_premium(self): return float(self.raw["calibration"].get("min_visible_premium", 1000))
    @property
    def holdout_years(self): return list(self.raw["backtest"]["holdout_years"])
    @property
    def run_months(self): return list(self.raw["backtest"]["run_months"])
    @property
    def within_pct(self): return float(self.raw["backtest"].get("within_pct", 10.0))
    @property
    def project_year(self): return int(self.raw["project"]["year"])
    @property
    def project_month(self): return int(self.raw["project"]["month"])
    @property
    def rate_table_glob(self): return self.raw.get("rate_table_glob")


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        return Config(raw=yaml.safe_load(fh))
