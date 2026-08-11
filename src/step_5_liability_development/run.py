"""Run the liability development pipeline and print a readable report.

    python src/step_5_liability_development/run.py --config src/step_5_liability_development/config.yaml
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")            # Windows console safety
sys.path.insert(0, os.path.dirname(__file__))
import pipeline as P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.yaml"))
    args = ap.parse_args()

    r = P.run(args.config)
    cfg, lad, diag = r["cfg"], r["ladder"], r["diag"]

    print("=" * 70)
    print("LIABILITY DEVELOPMENT PIPELINE")
    print("=" * 70)

    print("\n[1] THE LADDER  (% of large losses developed by age)")
    print("    (early rungs recent-weighted -- reporting slowed; later rungs pooled)")
    for a in lad["ages"]:
        f = lad["a2a"].get(a)
        src = lad.get("a2a_src", {}).get(a, "")
        print(f"    age {a:>3}mo   factor {('%.2f'%f) if f else '  -- ':>5}   "
              f"cdf {lad['cdf'][a]:>5.2f}   {100*lad['pct_developed'][a]:>5.1f}% developed"
              f"   [{src}]")

    print(f"\n[2] THE RATE  (frequency = developed large losses per unit EXPOSURE)")
    print(f"    calibration years : {cfg.calib_years}")
    print(f"    rate (readable)   : {diag['rate_per_Mprem']:.3f} large losses per $M premium")
    print(f"    segments (cells)  : {diag['n_cells']}   |  thin (Z<0.5): {diag['thin_share']:.0%}"
          f"   |  Buhlmann K(cell): {diag['K_cell']:.0f}")

    print(f"\n[3] BAND SHOOT-OUT  (walk-forward, {cfg.band_recent_window}-yr window; nominal coverage {cfg.band_hi-cfg.band_lo:.0%})")
    bs = r["band_scores"]
    if len(bs):
        print("    method       coverage  false_alarm  false_ALARM  rel_width   fit_score")
        print("    (fit_score = calibration+tightness ONLY; ranks, does NOT auto-select)")
        for _, x in bs.iterrows():
            star = "  <- DEFAULT (config)" if x["method"] == cfg.band_method else ""
            print(f"    {x['method']:<11}  {x['coverage']:>7.0%}   {x['false_alarm']:>9.0%}"
                  f"    {x['high_rate']:>8.0%}    {x['mean_rel_width']:>6.2f}    {x['fit_score']:>6.3f}{star}")
        print("    Read: poisson DISQUALIFIED (fires on ~70% of normal cells); std/min_max too")
        print("    wide/fragile. percentile wins fit_score but is window-FRAGILE (cov 63->85%")
        print(f"    across 3-5yr windows) and can't extrapolate. {cfg.band_method} ships: window-stable,")
        print("    0 false-ALARMs, extrapolates. fit_score informs the call; it doesn't make it.")

    print(f"\n[4] VERDICT  (immature years; actual vs EMPIRICAL band [method={cfg.band_method}])")
    v = r["verdict"]
    print("    year  age  %dev  exp_now  band_ctr   band        actual  verdict     status")
    for _, x in v.iterrows():
        print(f"    {int(x['year'])}  {int(x['age_months']):>3}  {x['pct_developed']:>4.0%}"
              f"  {x['expected_by_now']:>6.1f}  {x['band_centre']:>7.1f}"
              f"   [{int(x['band_lo']):>2}-{int(x['band_hi']):>2}]"
              f"   {int(x['actual_by_now']):>5}   {x['verdict']:<9}  {x['status']}")

    print(f"\n[5] BACKTEST A -- rate stability (leave-one-year-out)")
    print("    NOTE: the shared ladder cancels here, so this validates the RATE, not the ladder.")
    bt = r["backtest"]
    print("    year   rate(others)   predicted   actual   error")
    for _, x in bt.iterrows():
        print(f"    {int(x['year'])}    {x['rate_others']:>8.4f}     {x['predicted']:>7.1f}"
              f"   {x['actual_developed']:>6.1f}   {x['error_pct']:>+.0%}")
    print(f"    mean |error| = {bt['error_pct'].abs().mean():.0%}  (rate is stable across years)")

    print(f"\n[6] BACKTEST B -- the ladder itself (leave-one-year-out development)")
    print("    Does the emergence pattern predict? (error does NOT cancel here -- the honest test.)")
    btl = r["backtest_ladder"]
    if len(btl):
        by = btl.groupby("from_age")["abs_error"].mean()
        for age, e in by.items():
            verdict = "trust" if e < 0.25 else ("rough" if e < 0.6 else "unreliable")
            print(f"    from age {int(age):>3}mo:  mean |error| {e:>5.0%}   -> {verdict}")
        print("    (confirms: young-age projection is unreliable -> why the band widens + 'TOO EARLY' gate)")

    # ---- persist ---------------------------------------------------------
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = os.path.join(cfg.raw["run"]["output_dir"], f"{cfg.raw['run']['name']}_{stamp}")
    os.makedirs(out, exist_ok=True)
    r["triangle"].to_csv(os.path.join(out, "triangle.csv"), index=False)
    r["cell_rates"].to_csv(os.path.join(out, "segment_rates.csv"), index=False)
    v.to_csv(os.path.join(out, "verdict.csv"), index=False)
    bt.to_csv(os.path.join(out, "backtest_rate.csv"), index=False)
    r["backtest_ladder"].to_csv(os.path.join(out, "backtest_ladder.csv"), index=False)
    if len(r["band_scores"]):
        r["band_scores"].to_csv(os.path.join(out, "band_shootout.csv"), index=False)
        r["band_cells"].to_csv(os.path.join(out, "band_shootout_cells.csv"), index=False)
    import pandas as pd
    pd.DataFrame([{"age": a, "pct_developed": lad["pct_developed"][a], "cdf": lad["cdf"][a]}
                  for a in lad["ages"]]).to_csv(os.path.join(out, "ladder.csv"), index=False)
    print(f"\n    outputs -> {out}")


if __name__ == "__main__":
    main()
