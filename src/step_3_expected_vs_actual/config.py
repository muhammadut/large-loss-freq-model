"""Load the Step-3 (Expected vs Actual) config.

Step 3 is an *orchestrator*: it does not re-declare business choices, it points
at the Step-1 and Step-2 configs and reuses them. That guarantees the "actual"
large-loss count is flagged with the SAME threshold / cat-scope / segment
definition that the rates were calibrated on — otherwise expected-vs-actual
would be apples-to-oranges.
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

    # ---- upstream configs (the single source of truth for each choice) ---
    @property
    def step1_config(self): return self.raw["upstream"]["step1_config"]
    @property
    def step2_config(self): return self.raw["upstream"]["step2_config"]
    @property
    def rate_table_glob(self): return self.raw["upstream"].get("rate_table_glob",
                                                                "outputs/**/rate_table_final.csv")

    # ---- the report window ----------------------------------------------
    @property
    def verdict_year(self): return int(self.raw["report"]["verdict_year"])
    @property
    def prior_year(self): return int(self.raw["report"]["prior_year"])
    @property
    def current_year(self):
        """The most recent, still-developing year — shown as a flagged watch,
        never as a verdict (it is not fully reported yet)."""
        c = self.raw["report"].get("current_year")
        return int(c) if c is not None else None
    @property
    def run_month(self):
        """Month the projection is 'run' at. 12 = full year known (isolates the
        rate model from premium-projection error) — the right basis for a
        retrospective verdict."""
        return int(self.raw["report"].get("run_month", 12))

    # ---- confidence bands + traffic light --------------------------------
    @property
    def overdispersion(self):
        """None -> auto (read from the rate table's run_report.json). A value
        >1 widens the Poisson band into a Negative-Binomial band."""
        return self.raw["report"].get("overdispersion")
    @property
    def green_band(self): return tuple(self.raw["report"].get("green_band", [25, 75]))
    @property
    def amber_band(self): return tuple(self.raw["report"].get("amber_band", [10, 90]))

    # ---- walk-forward backtest -------------------------------------------
    @property
    def bt_folds(self):
        """Mature years scored out-of-sample (rates + factors trained on < Y)."""
        return list(self.raw.get("backtest", {}).get("folds", [self.prior_year, self.verdict_year]))
    @property
    def bt_run_months(self):
        return list(self.raw.get("backtest", {}).get("run_months", [self.run_month]))
    @property
    def bt_immature(self):
        """Still-developing years shown for context, never scored (reporting lag)."""
        return list(self.raw.get("backtest", {}).get("immature_years", []) or [])


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        return Config(raw=yaml.safe_load(fh))
