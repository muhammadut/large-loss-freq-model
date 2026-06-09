"""
large_loss_freq — config-driven calibration pipeline for the Large-Loss
Frequency Model.

Scope: data -> panel -> Poisson GLM (year effect) -> hierarchical credibility
-> validation gates -> credibilized rate table.

This package ENDS at `rate_table_final.csv`. The forward step (project premium ->
expected counts -> actual-vs-expected -> waterfall) is a separate downstream
module that consumes the rate table.
"""
__version__ = "0.1.0"
