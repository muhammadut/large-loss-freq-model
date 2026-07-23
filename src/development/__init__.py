"""Claim-count development (IBNR) engine.

Turns a large-loss COUNT development triangle into a per-coverage development
pattern (% of the ultimate count reported by each age), so the immature current
accident year can be developed to ultimate before it is scored.

The key finding this exists to handle: commercial property develops within ~12
months (factor ~1.0, no adjustment needed) while commercial liability has a long
tail (only ~40% reported at 12 months). So the two coverages get separate
patterns, and only liability is materially adjusted.
"""
