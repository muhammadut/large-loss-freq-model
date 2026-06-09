#!/usr/bin/env python3
"""Entry point so the package runs without installation.

Usage (from the repo root):
    python src/run.py --config src/config/config.yaml
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from large_loss_freq.pipeline import main

if __name__ == "__main__":
    main()
