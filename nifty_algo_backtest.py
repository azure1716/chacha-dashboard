# ============================================================
# nifty_algo_backtest.py
# ============================================================
# Offline validator for the DIRECTIONAL core of the strategy
# (technical trend + momentum + ADX chop filter + 5-min HTF
# agreement -- the 65% of the live signal weight that depends only
# on NIFTY spot candles). Replays the exact same functions from
# nifty_algo_core.py bar-by-bar, using only data available up to
# and including each bar (no lookahead), and simulates hypothetical
# trades in INDEX POINTS with ATR-based stop/target.
#
# WHAT THIS DOES **NOT** VALIDATE
# --------------------------------
# The live engine's option-pressure signal (35% of the weight) needs
# historical OI / volume / buy-sell-quantity / bid-ask snapshots for
# each strike, at the same 1-min granularity, going back weeks or
# months. Most retail historical-data feeds don't offer that at all,
# and it isn't available here. So:
#   - This backtest tells you whether the trend/momentum/ADX/HTF
#     combination has genuine directional edge on NIFTY -- necessary
#     but NOT sufficient for the full live strategy.
#   - It does NOT simulate option premium behaviour (theta, IV
#     crush, delta), spread costs, or the option-pressure signal.
#   - If this backtest doesn't show a real edge after typical
#     transaction-cost assumptions, the option-pressure layer isn't
#     going to rescue the strategy -- fix or abandon the direction
#     call first.
#
# USAGE
# -----
#   python3 nifty_algo_backtest.py your_1min_ohlc.csv
#
# CSV must have columns (case-insensitive, any order):
#   timestamp/time/date, open, high, low, close   (volume optional)
#
# With no CSV argument, it runs on a synthetic series purely to prove
# the harness itself works -- NOT a real backtest of anything.
# ============================================================

import csv
import sys

import nifty_algo_core as core


# ------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------

def load_ohlc_csv(path):
    opens, highs, lows, closes, timestamps = [], [], [], [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        fieldmap = {name.lower(): name for name in reader.fieldnames or []}

        def col(*candidates):
            for c in candidates:
                if c in fieldmap:
                    return fieldmap[c]
            return None

        c_ts = col("timestamp", "time", "date", "datetime")
        c_o = col("open", "o")
        c_h = col("high", "h")
        c_l = col("low", "l")
        c_c = col("close", "c")
        if not all([c_o, c_h, c_l, c_c]):
            raise ValueError(f"CSV must have open/high/low/close columns, found: {reader.fieldnames}")

        for row in reader:
            try:
                o, h, l, c = float(row[c_o]), float(row[c_h]), float(row[c_l]), float(row[c_c])
            except (ValueError, TypeError):
                continue
            if c <= 0:
                continue
            opens.append(o); highs.append(h); lows.append(l); closes.append(c)
            timestamps.append(row.get(c_ts) if c_ts else None)

    return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "timestamps": timestamps}


def synthetic_ohlc_for_harness_test(n=1500, seed=11):
    """
    NOT a real market simulation -- only exists to prove the backtest
    harness itself runs correctly end-to-end. Do not draw any
    conclusions about strategy edge from this data.
    """
    import random
    random.seed(seed)
    price = 24000.0
    opens, highs, lows, closes = [], [], [], []
    regime_len = 0
    drift = 0.0
    for i in range(n):
        if regime_len <= 0:
            drift = random.choice([-1.2, -0.4, 0.0, 0.4, 1.2])
            regime_len = random.randint(40, 150)
        regime_len -= 1
        o = price
        price = price + drift + random.uniform(-2.5, 2.5)
        c = price
        h = max(o, c) + random.uniform(1.0, 3.5)
        l = min(o, c) - random.uniform(1.0, 3.5)
        opens.append(o); highs.append(h); lows.append(l); closes.append(c)
    return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "timestamps": [None] * n}


# ------------------------------------------------------------------
# Backtest engine
# ------------------------------------------------------------------

def precompute_bar_features(
    highs, lows, closes,
    ema_fast=20, ema_slow=50, rsi_length=14, atr_length=14, adx_length=14,
    htf_factor=5, max_lookback_bars=600, progress_every=2000,
):
    """
    Computes technical_score/momentum_score/higher_timeframe_trend ONCE
    per bar and caches them, keyed by bar index. This is what makes a
    parameter sweep (trying many sl/target/ADX/direction-score
    combinations) fast: those parameters only affect the ENTRY/EXIT
    decision and threshold comparisons, not the underlying indicator
    values, so there's no need to recompute EMA/RSI/ATR/ADX/HTF for
    every combination -- compute once, replay many times.
    min_adx isn't baked in here (passed as 0 to technical_score, which
    only affects its 'trend_strength' label, not the numeric ADX value
    or score) -- the actual ADX threshold is applied later, per
    parameter combination, in simulate_from_features().
    """
    n = len(closes)
    features = {}
    for i in range(ema_slow, n - 1):
        if progress_every and i % progress_every == 0:
            print(f"  ...precomputing {i}/{n} bars")
        lookback_start = max(0, i + 1 - max_lookback_bars)
        window_c = closes[lookback_start: i + 1]
        window_h = highs[lookback_start: i + 1]
        window_l = lows[lookback_start: i + 1]

        tech = core.technical_score(window_c, window_h, window_l, ema_fast, ema_slow,
                                     rsi_length, atr_length, adx_length, min_adx=0)
        if not tech.get("ready"):
            continue
        mom = core.momentum_score(window_c, rsi_length)
        htf = core.higher_timeframe_trend(window_h, window_l, window_c, htf_factor, ema_fast, ema_slow)
        features[i] = {"tech": tech, "mom": mom, "htf": htf}
    return features


def simulate_from_features(
    features, highs, lows, closes, opens=None,
    min_adx_for_trend_signal=18, min_direction_score=30,
    require_htf_agreement=True,
    sl_multiplier=1.2, target_multiplier=2.4, max_hold_bars=60,
    atr_pct_min=0.015,
):
    """
    Same decision + trade-simulation logic as simulate_index_signal_backtest,
    but reads tech/mom/htf from a precomputed `features` dict instead of
    recomputing them -- this is the cheap part, safe to call many times
    per precompute for a parameter sweep.
    """
    n = len(closes)
    trades = []
    i = min(features.keys()) if features else n

    while i < n - 1:
        f = features.get(i)
        if f is None:
            i += 1
            continue
        tech, mom, htf = f["tech"], f["mom"], f["htf"]

        atr_pct = tech.get("atr_pct")
        if atr_pct_min is not None and atr_pct is not None and atr_pct < atr_pct_min:
            i += 1
            continue

        adx_value = tech.get("adx")
        if adx_value is not None and adx_value < min_adx_for_trend_signal:
            i += 1
            continue

        htf_trend = htf if require_htf_agreement else "NEUTRAL"
        direction_score = tech["score"] * 0.40 + mom["score"] * 0.25

        signal = None
        if direction_score >= min_direction_score and htf_trend in ("NEUTRAL", "BULLISH"):
            signal = "LONG"
        elif direction_score <= -min_direction_score and htf_trend in ("NEUTRAL", "BEARISH"):
            signal = "SHORT"

        if not signal:
            i += 1
            continue

        atr = tech.get("atr")
        if not atr or atr <= 0:
            i += 1
            continue

        entry_idx = i + 1
        entry_price = opens[entry_idx] if opens else closes[entry_idx]
        sl_dist = atr * sl_multiplier
        tgt_dist = atr * target_multiplier
        if signal == "LONG":
            sl, target = entry_price - sl_dist, entry_price + tgt_dist
        else:
            sl, target = entry_price + sl_dist, entry_price - tgt_dist

        exit_price = exit_reason = exit_idx = None
        for j in range(entry_idx, min(n, entry_idx + max_hold_bars)):
            hi, lo = highs[j], lows[j]
            if signal == "LONG":
                if lo <= sl:
                    exit_price, exit_reason, exit_idx = sl, "SL", j
                    break
                if hi >= target:
                    exit_price, exit_reason, exit_idx = target, "TARGET", j
                    break
            else:
                if hi >= sl:
                    exit_price, exit_reason, exit_idx = sl, "SL", j
                    break
                if lo <= target:
                    exit_price, exit_reason, exit_idx = target, "TARGET", j
                    break

        if exit_price is None:
            exit_idx = min(n - 1, entry_idx + max_hold_bars - 1)
            exit_price, exit_reason = closes[exit_idx], "TIME"

        pnl_points = (exit_price - entry_price) if signal == "LONG" else (entry_price - exit_price)
        trades.append({
            "entry_idx": entry_idx, "exit_idx": exit_idx, "signal": signal,
            "entry": entry_price, "exit": exit_price, "pnl_points": pnl_points,
            "exit_reason": exit_reason, "risk_points": sl_dist,
        })
        i = exit_idx + 1

    return trades


def simulate_index_signal_backtest(
    highs, lows, closes, opens=None,
    ema_fast=20, ema_slow=50, rsi_length=14, atr_length=14, adx_length=14,
    min_adx_for_trend_signal=18, min_direction_score=30,
    require_htf_agreement=True, htf_factor=5,
    sl_multiplier=1.2, target_multiplier=2.4, max_hold_bars=60,
    max_lookback_bars=600, progress_every=2000,
    atr_pct_min=0.015,
    precomputed_features=None,
):
    """
    Thin wrapper: precompute_bar_features() + simulate_from_features().
    Kept as a single call for the common case (one backtest run); pass
    precomputed_features explicitly (see nifty_algo_backtest.py's
    parameter_sweep helper, or build your own) to reuse one precompute
    across many parameter combinations instead of recomputing indicators
    every time -- that's the expensive part.

    atr_pct_min: mirrors nifty_algo_live.py's ATR_PCT_MIN low-volatility
    filter -- keep in sync with ATR_PCT_MIN in nifty_algo_live.py if you
    change one of them.

    max_lookback_bars: each bar's indicators are computed on only the
    last `max_lookback_bars` candles, not the entire history-to-date --
    matches nifty_algo_live.py's own bounded candle history (MAX_CANDLES
    =3000) and turns this from an O(n^2) loop into an O(n) one.
    """
    features = precomputed_features
    if features is None:
        features = precompute_bar_features(
            highs, lows, closes, ema_fast, ema_slow, rsi_length, atr_length,
            adx_length, htf_factor, max_lookback_bars, progress_every,
        )
    return simulate_from_features(
        features, highs, lows, closes, opens,
        min_adx_for_trend_signal, min_direction_score, require_htf_agreement,
        sl_multiplier, target_multiplier, max_hold_bars, atr_pct_min,
    )


def summarize_trades(trades):
    if not trades:
        return {"trades": 0}
    wins = [t for t in trades if t["pnl_points"] > 0]
    losses = [t for t in trades if t["pnl_points"] <= 0]
    total_pnl = sum(t["pnl_points"] for t in trades)
    avg_r = sum((t["pnl_points"] / t["risk_points"]) for t in trades if t["risk_points"] > 0) / len(trades)

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t["pnl_points"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    gross_win = sum(t["pnl_points"] for t in wins)
    gross_loss = abs(sum(t["pnl_points"] for t in losses))

    return {
        "trades": len(trades),
        "win_rate_pct": round(100 * len(wins) / len(trades), 2),
        "avg_pnl_points": round(total_pnl / len(trades), 2),
        "total_pnl_points": round(total_pnl, 2),
        "avg_R": round(avg_r, 3),
        "max_drawdown_points": round(max_dd, 2),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
    }


def summarize_by_exit_reason(trades):
    out = {}
    for t in trades:
        out.setdefault(t["exit_reason"], 0)
        out[t["exit_reason"]] += 1
    return out


def run(path=None):
    if path:
        print(f"Loading {path} ...")
        data = load_ohlc_csv(path)
        print(f"Loaded {len(data['closes'])} bars.")
    else:
        print("No CSV given -- running on SYNTHETIC data to sanity-check the harness only.")
        print("(This proves the code runs. It proves NOTHING about strategy edge.)")
        data = synthetic_ohlc_for_harness_test()

    trades = simulate_index_signal_backtest(
        data["highs"], data["lows"], data["closes"], data["opens"],
    )
    stats = summarize_trades(trades)
    by_reason = summarize_by_exit_reason(trades)

    print("\n" + "=" * 50)
    print("BACKTEST RESULTS (index-points, technical+momentum only)")
    print("=" * 50)
    for k, v in stats.items():
        print(f"{k:20s}: {v}")
    print("exit reasons        :", by_reason)
    print("=" * 50)
    print("Reminder: no transaction costs, no option premium mechanics,")
    print("no option-pressure signal. This is a floor check on direction-")
    print("calling ability only, not a projection of live P&L.")
    return trades, stats


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    run(csv_path)
