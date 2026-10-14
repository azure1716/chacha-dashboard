# ============================================================
# parameter_sweep.py
# ============================================================
# Tests many (stop-multiplier, target-multiplier, ADX threshold,
# direction-score threshold) combinations against the SAME data,
# using nifty_algo_backtest's precompute/replay split so the
# expensive part (indicator computation) happens only ONCE.
#
# USAGE
#   python parameter_sweep.py your_1min_ohlc.csv
#
# WHAT TO ACTUALLY DO WITH THE OUTPUT
# ------------------------------------
# For every combination, "breakeven_win_rate_pct" is the win rate
# that combination's own reward:risk ratio requires just to break
# even (1 / (1 + reward:risk) * 100). "edge_vs_breakeven_pct" is how
# far the ACTUAL win rate cleared (or missed) that line. That number,
# not raw win rate or raw P&L, is what tells you whether a
# configuration has genuine edge or just a favourable-looking R:R.
#
# IMPORTANT -- multiple-testing risk:
# Trying dozens of combinations on ONE dataset means a few will look
# good by chance alone, even with zero real edge (this is the same
# problem as p-hacking). Do NOT take the single best row here and
# assume it'll work live. Instead:
#   1. Look for combinations that cluster together with a consistent
#      edge (a whole neighbourhood of similar parameters doing well),
#      not one lucky outlier.
#   2. Re-fetch a DIFFERENT, non-overlapping date range
#      (fetch_historical_data.py, different DAYS_BACK / edit the
#      script to shift the window) and re-run the best candidates
#      there. A config that only worked on the data it was tuned on
#      is overfit, not edge.
# ============================================================

import itertools
import sys

import nifty_algo_backtest as bt

# Keep this grid modest -- it's meant to map out the neighbourhood,
# not exhaustively search. Widen it once you know which corner of the
# space looks interesting.
SL_MULTIPLIERS = [1.0, 1.2, 1.5, 2.0]
TARGET_MULTIPLIERS = [1.5, 2.0, 2.4, 3.0, 4.0]
ADX_THRESHOLDS = [15, 18, 22, 26]
DIRECTION_SCORE_THRESHOLDS = [20, 30, 40]

MIN_TRADES_TO_COUNT = 30   # ignore configs with too few trades to mean anything
TOP_N = 20


def run_sweep(csv_path):
    print(f"Loading {csv_path} ...")
    data = bt.load_ohlc_csv(csv_path)
    print(f"Loaded {len(data['closes'])} bars.\n")

    print("Precomputing indicators ONCE (this is the slow part; every combination below reuses it)...")
    features = bt.precompute_bar_features(data["highs"], data["lows"], data["closes"])
    print(f"Precompute done -- {len(features)} bars ready.\n")

    combos = [
        (sl, tgt, adx, dirscore)
        for sl, tgt, adx, dirscore in itertools.product(
            SL_MULTIPLIERS, TARGET_MULTIPLIERS, ADX_THRESHOLDS, DIRECTION_SCORE_THRESHOLDS)
        if tgt > sl  # skip nonsensical reward:risk <= 1 combinations
    ]
    print(f"Running {len(combos)} parameter combinations...\n")

    results = []
    for idx, (sl_m, tgt_m, adx_t, dir_t) in enumerate(combos):
        trades = bt.simulate_from_features(
            features, data["highs"], data["lows"], data["closes"], data["opens"],
            min_adx_for_trend_signal=adx_t, min_direction_score=dir_t,
            sl_multiplier=sl_m, target_multiplier=tgt_m,
        )
        stats = bt.summarize_trades(trades)
        if stats.get("trades", 0) < MIN_TRADES_TO_COUNT:
            continue

        rr = tgt_m / sl_m
        breakeven_wr = 100.0 / (1 + rr)
        stats.update({
            "sl_mult": sl_m, "target_mult": tgt_m, "adx_min": adx_t, "dir_score_min": dir_t,
            "rr_ratio": round(rr, 2), "breakeven_win_rate_pct": round(breakeven_wr, 2),
            "edge_vs_breakeven_pct": round(stats["win_rate_pct"] - breakeven_wr, 2),
        })
        results.append(stats)

        if (idx + 1) % 40 == 0:
            print(f"  ...{idx + 1}/{len(combos)} combos tested")

    if not results:
        print(f"\nNo configuration produced >= {MIN_TRADES_TO_COUNT} trades to evaluate. "
              "Try a longer history or a wider grid.")
        return

    results.sort(key=lambda r: (r["profit_factor"] or 0), reverse=True)

    header = (f"{'sl':>5}{'tgt':>6}{'adx':>5}{'dirsc':>7}{'trades':>8}{'win%':>7}"
              f"{'BEwin%':>8}{'edge':>7}{'PF':>7}{'avgR':>7}{'maxDD':>8}")

    print("\n" + "=" * 100)
    print(f"TOP {min(TOP_N, len(results))} CONFIGS BY PROFIT FACTOR")
    print("(sl/tgt = ATR multipliers, adx/dirsc = thresholds, BEwin% = breakeven win rate")
    print(" this combo's own R:R requires, edge = actual win% minus BEwin%)")
    print("=" * 100)
    print(header)
    for r in results[:TOP_N]:
        print(f"{r['sl_mult']:>5}{r['target_mult']:>6}{r['adx_min']:>5}{r['dir_score_min']:>7}"
              f"{r['trades']:>8}{r['win_rate_pct']:>7.1f}{r['breakeven_win_rate_pct']:>8.1f}"
              f"{r['edge_vs_breakeven_pct']:>7.1f}{(r['profit_factor'] or 0):>7.3f}"
              f"{r['avg_R']:>7.3f}{r['max_drawdown_points']:>8.1f}")

    print("\n" + "=" * 100)
    print(f"BOTTOM {min(10, len(results))} (for contrast)")
    print("=" * 100)
    print(header)
    for r in results[-10:]:
        print(f"{r['sl_mult']:>5}{r['target_mult']:>6}{r['adx_min']:>5}{r['dir_score_min']:>7}"
              f"{r['trades']:>8}{r['win_rate_pct']:>7.1f}{r['breakeven_win_rate_pct']:>8.1f}"
              f"{r['edge_vs_breakeven_pct']:>7.1f}{(r['profit_factor'] or 0):>7.3f}"
              f"{r['avg_R']:>7.3f}{r['max_drawdown_points']:>8.1f}")

    strong = [r for r in results if r["edge_vs_breakeven_pct"] > 0 and r["profit_factor"] and r["profit_factor"] > 1.1]
    print("\n" + "=" * 100)
    print(f"Configs with profit_factor > 1.1 AND win rate above their own breakeven line: "
          f"{len(strong)} / {len(results)} tested")
    print("=" * 100)
    if strong:
        print("Worth a closer look -- but see the multiple-testing warning at the top of this")
        print("file before trusting any single row. Look for a CLUSTER of nearby parameters")
        print("that all do reasonably well, not one isolated winner, and re-test the leading")
        print("candidates on a different, non-overlapping date range before believing them.")
    else:
        print("None cleared that bar anywhere in this grid. That's a real result: across this")
        print("whole neighbourhood of stop/target/ADX/direction-score combinations, nothing in")
        print("the technical+momentum logic alone shows a robust edge on this data. The")
        print("option-pressure component (not testable offline) may still add value live -- but")
        print("the direction-calling core doesn't look strong enough on its own yet.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parameter_sweep.py your_1min_ohlc.csv")
        sys.exit(1)
    run_sweep(sys.argv[1])
