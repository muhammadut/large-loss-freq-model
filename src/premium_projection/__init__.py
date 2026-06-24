"""
premium_projection — Part 2 of the Large-Loss Frequency Model.

Projects full-year earned premium PER SEGMENT for a target year, so it can be
multiplied by the Part-1 frequency rate to produce expected large-loss counts.

Method (validated by backtest): for each segment, take the premium visible by the
run-month and multiply by that segment's historical growth factor
(full-year / visible-by-month). Cancellations are baked into the historical factor.
"""
__version__ = "0.1.0"
