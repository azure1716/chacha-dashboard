# ============================================================
# nifty_algo.py  --  EVERYTHING IN ONE FILE
# ============================================================
# Paste your Upstox token ONCE, on the ACCESS_TOKEN line below.
#
# HOW TO RUN (Command Prompt, in this file's folder):
#
#   python nifty_algo.py                 -> shows a menu, pick a number
#
# or run a step directly:
#
#   python nifty_algo.py test            self-tests (no internet, no token needed)
#   python nifty_algo.py fetch 1000      download ~1000 days of 1-min NIFTY data
#   python nifty_algo.py lab             strategy lab on the downloaded data
#   python nifty_algo.py lab nifty_1min_history.csv 2    (2 = cost in index points)
#   python nifty_algo.py backtest        1-min index backtest
#   python nifty_algo.py sweep           parameter sweep on the 1-min backtest
#   python nifty_algo.py research        fetch (if needed) + strategy lab, in one go
#   python nifty_algo.py live            live PAPER trading (weekdays 9:15-15:30 IST)
#
# STATUS OF THE STRATEGY (from your own backtest): the 1-minute
# EMA/RSI/ADX logic showed NO edge after costs on ~90 days of data.
# Use "research" or "lab" to test slower / different ideas on more
# data BEFORE trusting anything. Real orders are NOT implemented;
# "live" is paper trading only.
#
# Sections in this file: 1 core math | 2 live engine | 3 backtest |
# 4 fetch data | 5 sweep | 6 strategy lab | 7 self-tests | 8 menu
# ============================================================

import csv
import itertools
import math
import os
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    requests = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ACCESS_TOKEN = os.environ.get("UPSTOX_ACCESS_TOKEN", "")

HEADERS = {
    "Authorization": "Bearer " + ACCESS_TOKEN,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

DEFAULT_CSV = "nifty_1min_history.csv"


##############################################################################
# SECTION 1: CORE MATH (indicators, scoring, risk, costs)
##############################################################################

def calculate_ema(values, length):
    if len(values) < length:
        return None
    values = list(values)
    seed = sum(values[:length]) / length
    multiplier = 2 / (length + 1)
    result = seed
    for value in values[length:]:
        result = (value - result) * multiplier + result
    return result


def calculate_rsi(values, length):
    if len(values) < length + 1:
        return None
    values = list(values)
    gains, losses = [], []
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length
    for i in range(length, len(gains)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_atr(highs, lows, closes, length):
    if len(closes) < length + 1:
        return None
    highs, lows, closes = list(highs), list(lows), list(closes)
    true_ranges = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)
    if len(true_ranges) < length:
        return None
    return sum(true_ranges[-length:]) / length


def _wilder_sum_smooth(series, length):
    """Wilder's classic running-sum smoothing (used for TR/+DM/-DM)."""
    if len(series) < length:
        return []
    smoothed = [sum(series[:length])]
    for v in series[length:]:
        smoothed.append(smoothed[-1] - (smoothed[-1] / length) + v)
    return smoothed


def _wilder_avg_smooth(series, length):
    """Wilder's running-average smoothing (used for DX -> ADX)."""
    if len(series) < length:
        return []
    result = [sum(series[:length]) / length]
    for v in series[length:]:
        result.append((result[-1] * (length - 1) + v) / length)
    return result


def calculate_adx(highs, lows, closes, length=14):
    """
    Wilder's ADX / +DI / -DI. Measures TREND STRENGTH (not direction).
    This is what V47.2 was missing: EMA/RSI can flip signals rapidly in
    a range-bound market even though there's no real trend to trade.
    Returns None until there's enough history (roughly 2*length bars).
    """
    n = len(closes)
    if n < (length * 2) + 1:
        return None
    highs, lows, closes = list(highs), list(lows), list(closes)

    plus_dm, minus_dm, tr_list = [], [], []
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        tr_list.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        )

    smoothed_tr = _wilder_sum_smooth(tr_list, length)
    smoothed_pdm = _wilder_sum_smooth(plus_dm, length)
    smoothed_mdm = _wilder_sum_smooth(minus_dm, length)
    if not smoothed_tr or not smoothed_pdm or not smoothed_mdm:
        return None

    m = min(len(smoothed_tr), len(smoothed_pdm), len(smoothed_mdm))
    plus_di, minus_di = [], []
    for i in range(m):
        tr_s = smoothed_tr[i]
        if tr_s <= 0:
            plus_di.append(0.0)
            minus_di.append(0.0)
        else:
            plus_di.append(100.0 * smoothed_pdm[i] / tr_s)
            minus_di.append(100.0 * smoothed_mdm[i] / tr_s)

    dx_list = []
    for pdi, mdi in zip(plus_di, minus_di):
        s = pdi + mdi
        dx_list.append(100.0 * abs(pdi - mdi) / s if s > 0 else 0.0)

    adx_series = _wilder_avg_smooth(dx_list, length)
    if not adx_series:
        return None

    return {"adx": adx_series[-1], "plus_di": plus_di[-1], "minus_di": minus_di[-1]}


# ------------------------------------------------------------------
# Multi-timeframe confirmation (reuses the SAME 1-min history you
# already collect -- no extra API calls needed)
# ------------------------------------------------------------------


def resample_ohlc(highs, lows, closes, factor):
    """
    Groups the most recent bars into non-overlapping `factor`-bar windows,
    oldest-first, dropping any incomplete leading remainder so every
    output bar represents a FULL window (no partially-formed last bucket
    sneaking in and distorting the higher-timeframe read).
    """
    n = len(closes)
    usable = (n // factor) * factor
    if usable == 0:
        return [], [], []
    start = n - usable
    agg_h, agg_l, agg_c = [], [], []
    for i in range(start, n, factor):
        agg_h.append(max(highs[i:i + factor]))
        agg_l.append(min(lows[i:i + factor]))
        agg_c.append(closes[i:i + factor][-1])
    return agg_h, agg_l, agg_c


def higher_timeframe_trend(highs, lows, closes, factor=5, ema_fast=20, ema_slow=50):
    """
    BULLISH / BEARISH / NEUTRAL read on a resampled higher timeframe
    (default: 5-min, built from your existing 1-min candles). Used to
    veto 1-min signals that go against the larger trend.
    """
    h, l, c = resample_ohlc(highs, lows, closes, factor)
    if len(c) < ema_slow:
        return "NEUTRAL"
    ef = calculate_ema(c, ema_fast)
    es = calculate_ema(c, ema_slow)
    if ef is None or es is None:
        return "NEUTRAL"
    last = c[-1]
    if last > ef > es:
        return "BULLISH"
    if last < ef < es:
        return "BEARISH"
    return "NEUTRAL"


# ------------------------------------------------------------------
# Scoring layers (technical / momentum / option pressure / regime)
# ------------------------------------------------------------------


def technical_score(closes, highs, lows, ema_fast=20, ema_slow=50,
                     rsi_length=14, atr_length=14, adx_length=14, min_adx=18):
    if len(closes) < ema_slow:
        return {"ready": False, "candles": len(closes)}

    ema_f = calculate_ema(closes, ema_fast)
    ema_s = calculate_ema(closes, ema_slow)
    rsi_v = calculate_rsi(closes, rsi_length)
    atr_v = calculate_atr(highs, lows, closes, atr_length)
    adx_r = calculate_adx(highs, lows, closes, adx_length)
    last = closes[-1]

    score = 0
    if ema_f is not None and ema_s is not None:
        if last > ema_f and ema_f > ema_s:
            score += 60
        elif last < ema_f and ema_f < ema_s:
            score -= 60
        elif ema_f > ema_s:
            score += 30
        elif ema_f < ema_s:
            score -= 30
    if rsi_v is not None:
        if rsi_v >= 55:
            score += 20
        elif rsi_v <= 45:
            score -= 20

    if score >= 50:
        trend = "BULLISH"
    elif score <= -50:
        trend = "BEARISH"
    else:
        trend = "MIXED"

    adx_value = adx_r["adx"] if adx_r else None
    # ADX not ready yet (early in the day) is NOT the same as "no trend" --
    # treat unknown as neutral/unknown rather than silently blocking trades.
    if adx_value is None:
        trend_strength = "UNKNOWN"
    elif adx_value >= min_adx:
        trend_strength = "STRONG"
    else:
        trend_strength = "WEAK"

    atr_pct = (atr_v / last * 100.0) if (atr_v is not None and last > 0) else None

    return {
        "ready": True,
        "ema_fast": ema_f, "ema_slow": ema_s, "rsi": rsi_v,
        "atr": atr_v, "atr_pct": atr_pct,
        "adx": adx_value, "plus_di": adx_r["plus_di"] if adx_r else None,
        "minus_di": adx_r["minus_di"] if adx_r else None,
        "trend_strength": trend_strength,
        "trend": trend, "score": score, "candles": len(closes),
    }


def momentum_score(closes, rsi_length=14, lookback=10):
    if len(closes) < rsi_length + 1:
        return {"score": 0, "momentum": 0, "rsi": None}
    lb = min(lookback, len(closes) - 1)
    momentum = closes[-1] - closes[-1 - lb]
    rsi_v = calculate_rsi(closes, rsi_length)
    score = 0
    if momentum > 0:
        score += 50
    elif momentum < 0:
        score -= 50
    if rsi_v is not None:
        if rsi_v >= 55:
            score += 50
        elif rsi_v <= 45:
            score -= 50
    return {"score": score, "momentum": momentum, "rsi": rsi_v}


def option_pressure_score(ce_oi, pe_oi, ce_volume, pe_volume,
                           ce_buy, pe_buy, ce_sell, pe_sell,
                           ce_price_change, pe_price_change,
                           weights=(0.25, 0.15, 0.25, 0.35)):
    """
    weights = (oi_weight, volume_weight, order_weight, price_weight)
    Same aggregate-pressure math as V47.2's option_pressure(), pulled out
    as a pure function so it's testable and reusable in a backtest that
    has historical OI/volume snapshots.
    """
    oi_w, vol_w, ord_w, price_w = weights
    total_oi = ce_oi + pe_oi
    oi_score = ((pe_oi - ce_oi) / total_oi * 100) if total_oi > 0 else 0

    total_volume = ce_volume + pe_volume
    volume_score = ((pe_volume - ce_volume) / total_volume * 100) if total_volume > 0 else 0

    total_order = ce_buy + pe_buy + ce_sell + pe_sell
    order_score = ((pe_buy + ce_sell - ce_buy - pe_sell) / total_order * 100) if total_order > 0 else 0

    price_score = max(-100, min(100, pe_price_change - ce_price_change))

    score = oi_score * oi_w + volume_score * vol_w + order_score * ord_w + price_score * price_w

    if score >= 25:
        bias = "BULLISH"
    elif score <= -25:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    return {
        "score": score, "bias": bias,
        "oi_score": oi_score, "volume_score": volume_score,
        "order_score": order_score, "price_score": price_score,
    }


def regime_score(technical_score_value, momentum_score_value, option_score_value,
                  weights=(0.40, 0.25, 0.35)):
    tw, mw, ow = weights
    score = technical_score_value * tw + momentum_score_value * mw + option_score_value * ow
    if score >= 40:
        regime = "BULLISH TREND"
    elif score <= -40:
        regime = "BEARISH TREND"
    elif abs(score) <= 15:
        regime = "RANGE"
    else:
        regime = "MIXED"
    return {"score": score, "regime": regime}


# ------------------------------------------------------------------
# IV context (options-specific -- V47.2 had zero IV awareness)
# ------------------------------------------------------------------


def iv_percentile(current_iv, iv_history):
    """
    Where does the option's CURRENT IV sit relative to its own recent
    history? Buying options at the top of their own IV range means
    you're paying a premium that's expensive relative to how it's
    actually been trading -- a classic way to be "right on direction,
    wrong on P&L" because of IV mean-reversion / crush.
    Returns 0-100, or None if there isn't enough history yet.
    """
    if not iv_history or current_iv is None:
        return None
    hist = [v for v in iv_history if v is not None and v > 0]
    if len(hist) < 10:
        return None
    rank = sum(1 for v in hist if v <= current_iv)
    return 100.0 * rank / len(hist)


# ------------------------------------------------------------------
# Signal decision (direction + confidence + consistency check)
# ------------------------------------------------------------------


def validate_signal_consistency(signal, technical_score_value, momentum_score_value, option_score_value):
    ts, ms, os = technical_score_value, momentum_score_value, option_score_value
    if signal == "BUY CALL":
        if ts <= -50 and ms <= -50:
            return False, "CALL BLOCKED: technical + momentum strongly bearish"
        if ts <= -70 and os <= -15:
            return False, "CALL BLOCKED: technical + option pressure bearish"
    if signal == "BUY PUT":
        if ts >= 50 and ms >= 50:
            return False, "PUT BLOCKED: technical + momentum strongly bullish"
        if ts >= 70 and os >= 15:
            return False, "PUT BLOCKED: technical + option pressure bullish"
    return True, "SIGNAL CONSISTENT"


def signal_decision(technical, momentum, options, min_direction_score=30,
                     confidence_threshold=75, min_adx_for_trend_signal=18,
                     require_htf_agreement=True, htf_trend="NEUTRAL"):
    """
    Pure decision layer. Liveness/readiness checks (websocket connected,
    warmup elapsed, etc.) stay in the live engine since those depend on
    live process state -- this function only needs the three score dicts.
    """
    if not technical.get("ready"):
        return {"signal": "WAIT", "confidence": 0.0, "reason": "Technical history not ready"}

    # --- ADX trend-strength gate -----------------------------------
    # This is the single biggest anti-whipsaw filter added vs V47.2:
    # EMA/RSI crossovers in a range-bound market generate confident-
    # looking but low-quality signals. If ADX says there's no real
    # trend, don't trade the trend-following logic.
    adx_value = technical.get("adx")
    if adx_value is not None and adx_value < min_adx_for_trend_signal:
        return {
            "signal": "WAIT", "confidence": 0.0,
            "reason": f"ADX {adx_value:.1f} < {min_adx_for_trend_signal}: no real trend (chop filter)",
        }

    regime = regime_score(technical["score"], momentum["score"], options["score"])
    technical_s, momentum_s, option_s = technical["score"], momentum["score"], options["score"]
    direction_score = technical_s * 0.40 + momentum_s * 0.25 + option_s * 0.35

    bull_votes = bear_votes = 0
    if technical_s > 0: bull_votes += 1
    elif technical_s < 0: bear_votes += 1
    if momentum_s > 0: bull_votes += 1
    elif momentum_s < 0: bear_votes += 1
    if option_s > 0: bull_votes += 1
    elif option_s < 0: bear_votes += 1

    confidence = abs(direction_score)
    if bull_votes == 3 or bear_votes == 3:
        confidence += 15
    elif bull_votes >= 2 or bear_votes >= 2:
        confidence += 5
    confidence = min(100, confidence)

    if (bull_votes >= 2 and direction_score >= min_direction_score
            and confidence >= confidence_threshold):
        signal, reason = "BUY CALL", "Bullish multi-factor confirmation"
    elif (bear_votes >= 2 and direction_score <= -min_direction_score
          and confidence >= confidence_threshold):
        signal, reason = "BUY PUT", "Bearish multi-factor confirmation"
    else:
        signal, reason = "WAIT", "Multi-factor confirmation not strong enough"

    # --- Higher-timeframe agreement gate ----------------------------
    if require_htf_agreement and signal != "WAIT" and htf_trend != "NEUTRAL":
        if signal == "BUY CALL" and htf_trend == "BEARISH":
            signal, reason = "WAIT", "Blocked: against higher-timeframe (5-min) trend"
        elif signal == "BUY PUT" and htf_trend == "BULLISH":
            signal, reason = "WAIT", "Blocked: against higher-timeframe (5-min) trend"

    if signal != "WAIT":
        ok, why = validate_signal_consistency(signal, technical_s, momentum_s, option_s)
        if not ok:
            signal, reason = "WAIT", why

    return {
        "signal": signal, "confidence": confidence, "reason": reason,
        "direction_score": direction_score, "regime": regime,
        "bull_votes": bull_votes, "bear_votes": bear_votes,
    }


# ------------------------------------------------------------------
# Risk management (V47.2 had NONE of this -- added from scratch)
# ------------------------------------------------------------------


def position_size(capital, risk_pct, entry_price, stop_price, lot_size, max_lots=10):
    """
    Risk-based sizing: how many lots can we take such that if price hits
    the stop, we lose at most `risk_pct` of `capital`? Returns 0 (skip
    the trade) if even 1 lot risks more than the allowed amount.
    """
    if capital <= 0 or lot_size <= 0:
        return 0
    per_unit_risk = abs(entry_price - stop_price)
    if per_unit_risk <= 0:
        return 0
    risk_amount = capital * risk_pct
    per_lot_risk = per_unit_risk * lot_size
    if per_lot_risk <= 0:
        return 0
    lots = int(risk_amount // per_lot_risk)
    return max(0, min(lots, max_lots))


def delta_adjusted_option_stop_target(spot_atr, option_delta, sl_multiplier=1.2,
                                       target_multiplier=2.4, min_atr=1.0):
    """
    Replaces V47.2's flat `atr * 0.55` guess. An option's own expected
    move is roughly |delta| * (expected move in the underlying) -- so an
    ATM option (delta ~0.5) should get a materially different stop
    distance than a far OTM one (delta ~0.15), which V47.2 did not
    distinguish at all.
    """
    abs_delta = abs(option_delta) if option_delta else 0.5
    abs_delta = max(0.05, min(1.0, abs_delta))
    option_atr = max(min_atr, spot_atr * abs_delta)
    return {
        "option_atr": option_atr,
        "sl_distance": option_atr * sl_multiplier,
        "target_distance": option_atr * target_multiplier,
    }


# Approximate Indian retail options cost model. These constants are
# PLACEHOLDERS for modeling purposes -- brokerage/STT/exchange/SEBI/
# stamp-duty rates change periodically and vary by broker plan. Verify
# current figures from your Upstox contract note / tariff sheet before
# using this for anything beyond rough paper-P&L realism.
DEFAULT_COST_MODEL = {
    "brokerage_per_order": 20.0,     # flat Rs per executed order (verify)
    "exchange_txn_pct": 0.00053,     # NSE F&O txn charge on premium turnover (verify)
    "stt_sell_pct": 0.001,           # STT on sell-side options premium (verify)
    "sebi_fee_pct": 0.000001,        # SEBI turnover fee, negligible (verify)
    "stamp_duty_buy_pct": 0.00003,   # stamp duty on buy-side, state-dependent (verify)
    "gst_pct": 0.18,                 # GST on (brokerage + exchange txn charge)
}


def estimate_option_trade_cost(entry_price, exit_price, lot_size, lots, cost_model=None):
    """
    Rough round-trip cost estimate for one options trade (one buy order
    to open, one sell order to close). Returns (total_cost, breakdown).
    """
    cm = cost_model or DEFAULT_COST_MODEL
    buy_turnover = entry_price * lot_size * lots
    sell_turnover = exit_price * lot_size * lots

    brokerage = cm["brokerage_per_order"] * 2
    exchange_txn = (buy_turnover + sell_turnover) * cm["exchange_txn_pct"]
    stt = sell_turnover * cm["stt_sell_pct"]
    sebi_fee = (buy_turnover + sell_turnover) * cm["sebi_fee_pct"]
    stamp_duty = buy_turnover * cm["stamp_duty_buy_pct"]
    gst = (brokerage + exchange_txn) * cm["gst_pct"]

    total = brokerage + exchange_txn + stt + sebi_fee + stamp_duty + gst
    return total, {
        "brokerage": brokerage, "exchange_txn": exchange_txn, "stt": stt,
        "sebi_fee": sebi_fee, "stamp_duty": stamp_duty, "gst": gst, "total": total,
    }


def should_trade_now(daily_pnl, max_daily_loss=None, daily_profit_lock=None,
                      trades_today=0, max_trades_per_day=None,
                      consecutive_losses=0, max_consecutive_losses=None,
                      cooldown_until=None, now=None):
    """
    Central risk gate. Called before every new entry. Pure function --
    the live engine owns the actual daily_pnl/trades_today/etc state and
    passes it in; this just decides allowed/blocked.
    """
    if max_daily_loss is not None and daily_pnl <= -abs(max_daily_loss):
        return False, "Daily max loss hit -- trading halted for today"
    if daily_profit_lock is not None and daily_pnl >= abs(daily_profit_lock):
        return False, "Daily profit target reached -- trading halted for today"
    if max_trades_per_day is not None and trades_today >= max_trades_per_day:
        return False, "Max trades/day reached"
    if (max_consecutive_losses is not None
            and consecutive_losses >= max_consecutive_losses
            and cooldown_until is not None and now is not None
            and now < cooldown_until):
        return False, f"Cooldown after {consecutive_losses} consecutive losses"
    return True, "OK"


##############################################################################
# SECTION 2: LIVE PAPER-TRADING ENGINE
##############################################################################

# ============================================================
# CONFIG
# ============================================================


REAL_ORDER = False  # leave False. See place_real_order() below.

NIFTY_KEY = "NSE_INDEX|Nifty 50"

STRIKE_STEP = 50
STRIKE_RANGE = 5

DISPLAY_SECONDS = 5
REST_SECONDS = 3

HISTORY_INTERVAL = 1
HISTORY_DAYS = 7

EMA_FAST = 20
EMA_SLOW = 50
RSI_LENGTH = 14
ATR_LENGTH = 14
ADX_LENGTH = 14

CONFIDENCE_THRESHOLD = 75
MIN_DIRECTION_SCORE = 30

# Chop filter: below this ADX, EMA/RSI crossovers are treated as noise,
# not a real trend. 18-20 is a common starting point -- validate against
# your own backtest rather than trusting this number blindly.
MIN_ADX_FOR_TREND_SIGNAL = 18

# Multi-timeframe confirmation: built by resampling the SAME 1-min
# history into 5-min bars (no extra API calls). A 1-min signal against
# the 5-min trend is blocked.
REQUIRE_HTF_AGREEMENT = True
HTF_FACTOR = 5

# Low-volatility filter as % of spot instead of a fixed point value.
ATR_PCT_MIN = 0.015

# IV filter: skip an entry if the chosen option's IV sits above this
# percentile of ITS OWN recent IV history (i.e. don't buy premium that's
# already expensive relative to how it's been trading).
IV_PERCENTILE_MAX = 80
IV_HISTORY_LEN = 300

ATR_SL_MULTIPLIER = 1.2
ATR_TARGET_MULTIPLIER = 2.4
TRAIL_ACTIVATE_R = 1.0
TRAIL_DISTANCE_R = 0.8

TRADE_START_MINUTES = 9 * 60 + 25
TRADE_END_MINUTES = 14 * 60 + 50

# --- Risk management (V47.2 had none of this) ------------------
CAPITAL = 100000.0          # << SET THIS to your actual paper/real capital
RISK_PER_TRADE_PCT = 0.01   # risk 1% of capital per trade (via stop distance)
LOT_SIZE = 65                # NIFTY lot size effective Jan-2026 revision.
                              # WARNING: VERIFY current lot size before using this
                              # for real sizing -- NSE revises it periodically.
MAX_LOTS_PER_TRADE = 5
MAX_DAILY_LOSS = 3000.0      # halt new entries for the day past this loss
DAILY_PROFIT_LOCK = None     # e.g. 6000.0 to stop trading after hitting a
                              # daily profit target; None disables it
MAX_TRADES_PER_DAY = 6
MAX_CONSECUTIVE_LOSSES = 3
COOLDOWN_MINUTES_AFTER_STREAK = 30

# --- Strike rebalancing -----------------------------------------
REBALANCE_THRESHOLD_POINTS = 150
REBALANCE_CHECK_SECONDS = 30

# --- Persistence --------------------------------------------------
SIGNALS_LOG_PATH = "signals_log.csv"
TRADES_LOG_PATH = "trades_log.csv"


# ============================================================
# GLOBAL STATE
# ============================================================

running = True
ws_connected = False
streamer = None

ws_connect_attempts = 0
ws_reconnect_count = 0
ws_subscribed = False
ws_last_open_time = None
ws_last_error = None
ws_last_close_time = None
ws_last_reconnecting_time = None
ws_connect_thread = None

selected_expiry = None
selected_strikes = []
full_chain = None          # full option chain fetched once at startup,
                            # reused for strike rebalancing (no re-fetch)
last_atm_used = None
_last_rebalance_check = 0.0

live_data = {}
option_prev_tick = {}       # single OI/price delta tracker (replaces the
                             # two duplicated trackers in V47.2)
option_session_baseline = {}
option_iv_history = {}      # key -> deque of recent IV readings

paper_trade = None
paper_trades = []

data_lock = threading.Lock()
print_lock = threading.Lock()

history_loaded = False

MAX_CANDLES = 3000

candle_time = deque(maxlen=MAX_CANDLES)
open_history = deque(maxlen=MAX_CANDLES)
high_history = deque(maxlen=MAX_CANDLES)
low_history = deque(maxlen=MAX_CANDLES)
close_history = deque(maxlen=MAX_CANDLES)
volume_history = deque(maxlen=MAX_CANDLES)

current_candle = {
    "minute": None, "open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0, "volume": 0,
}

historical_last_minute = None
last_live_minute = None
candle_status = "WAITING"

LIVE_WARMUP_TICKS = 20
LIVE_WARMUP_SECONDS = 15
live_tick_count = 0
live_session_started = False
live_session_start_time = None
live_completed_candles = 0

historical_candle_count = 0

paper_trade_stats = {
    "closed": 0, "wins": 0, "losses": 0,
    "gross_pnl": 0.0, "net_pnl": 0.0, "total_cost": 0.0,
}

# --- Risk-state (mutated only from the single display-loop thread,
#     same threading assumption V47.2 made for its trading state) ---
daily_pnl = 0.0
trades_today = 0
consecutive_losses = 0
cooldown_until = None
current_trade_date = None

last_signal_audit = {}
V36_LAST_HISTORY_REFRESH = 0.0
V36_REFRESH_COOLDOWN = 10.0


# ============================================================
# HELPERS
# ============================================================

def safe_print(*args, **kwargs):
    with print_lock:
        try:
            print(*args, **kwargs)
        except UnicodeEncodeError:
            text = " ".join(str(x) for x in args)
            safe_text = text.encode("ascii", "replace").decode("ascii")
            print(safe_text, end=kwargs.get("end", "\n"),
                  file=kwargs.get("file", None), flush=kwargs.get("flush", False))


def log_exception(label, e):
    safe_print(f"{label}:", e)
    safe_print(traceback.format_exc()[-1200:])


def num(value, default=0.0):
    try:
        if value is None:
            return default
        x = float(value)
        if x != x or x in (float("inf"), float("-inf")):  # NaN/inf guard, no math import needed here
            return default
        return x
    except Exception:
        return default


def integer(value, default=0):
    try:
        return int(num(value, default))
    except Exception:
        return default


def today_string():
    return time.strftime("%Y-%m-%d")


def timestamp_minute(ts=None):
    if ts is None:
        ts = time.time()
    return int(ts // 60)


def nse_market_open_now():
    try:
        lt = time.localtime()
        if lt.tm_wday >= 5:
            return False
        minutes = lt.tm_hour * 60 + lt.tm_min
        return 9 * 60 + 15 <= minutes < 15 * 60 + 30
    except Exception:
        return False


def is_trade_time():
    try:
        lt = time.localtime()
        if lt.tm_wday >= 5:
            return False
        minutes = lt.tm_hour * 60 + lt.tm_min
        return TRADE_START_MINUTES <= minutes <= TRADE_END_MINUTES
    except Exception:
        return False


# ============================================================
# EXPIRY + CHAIN + REST  (unchanged from V47.2)
# ============================================================

def get_expiry():
    safe_print("\nFinding active NIFTY expiry...")
    url = "https://api.upstox.com/v2/option/contract"
    try:
        r = requests.get(url, headers=HEADERS, params={"instrument_key": NIFTY_KEY}, timeout=10)
        safe_print("Contract API:", r.status_code)
        if r.status_code != 200:
            safe_print(r.text[:500])
            return None
        contracts = r.json().get("data", [])
        today = today_string()
        expiries = sorted(set(c.get("expiry") for c in contracts if c.get("expiry") and c.get("expiry") >= today))
        if not expiries:
            return None
        expiry = expiries[0]
        safe_print("SELECTED EXPIRY:", expiry)
        return expiry
    except Exception as e:
        log_exception("EXPIRY ERROR", e)
        return None


def get_option_chain(expiry):
    safe_print("\nLoading option chain...")
    url = "https://api.upstox.com/v2/option/chain"
    try:
        r = requests.get(url, headers=HEADERS,
                          params={"instrument_key": NIFTY_KEY, "expiry_date": expiry}, timeout=10)
        safe_print("Option Chain API:", r.status_code)
        if r.status_code != 200:
            safe_print(r.text[:500])
            return None
        chain = r.json().get("data", [])
        safe_print("Option chain strikes:", len(chain))
        return chain
    except Exception as e:
        log_exception("OPTION CHAIN ERROR", e)
        return None


def get_nifty_rest():
    url = "https://api.upstox.com/v3/market-quote/quotes"
    try:
        r = requests.get(url, headers=HEADERS, params={"instrument_key": NIFTY_KEY}, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json().get("data", {})
        item = data.get(NIFTY_KEY)
        if item is None and data:
            item = list(data.values())[0]
        if not isinstance(item, dict):
            return None
        return {
            "ltp": num(item.get("last_price", item.get("ltp"))),
            "cp": num(item.get("prev_close_price", item.get("cp"))),
            "volume": integer(item.get("volume")),
            "oi": integer(item.get("oi")),
        }
    except Exception as e:
        log_exception("NIFTY REST ERROR", e)
        return None


# ============================================================
# CANDLE + HISTORY  (unchanged from V47.2)
# ============================================================

def candle_minute_from_timestamp(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            x = float(value)
            if x > 10000000000:
                x /= 1000
            return int(x // 60)
        s = str(value).strip()
        if "T" in s:
            from datetime import datetime
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return int(dt.timestamp() // 60)
        x = float(s)
        if x > 10000000000:
            x /= 1000
        return int(x // 60)
    except Exception:
        return None


def refresh_today_intraday_history():
    global historical_last_minute, historical_candle_count, history_loaded
    safe_print("\nRefreshing CURRENT-DAY 1-minute candles...")
    url = ("https://api.upstox.com/v3/historical-candle/intraday/" +
           NIFTY_KEY.replace("|", "%7C") + "/minutes/" + str(HISTORY_INTERVAL))
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        safe_print("Intraday API:", r.status_code)
        if r.status_code != 200:
            safe_print("INTRADAY ERROR:", r.text[:500])
            return False
        candles = r.json().get("data", {}).get("candles", [])
        if not candles:
            return False

        merged = {}
        with data_lock:
            n = min(len(candle_time), len(open_history), len(high_history),
                    len(low_history), len(close_history), len(volume_history))
            for i in range(n):
                minute = candle_minute_from_timestamp(candle_time[i])
                if minute is not None:
                    merged[minute] = (candle_time[i], open_history[i], high_history[i],
                                       low_history[i], close_history[i], volume_history[i])

        current_minute = timestamp_minute()
        for c in candles:
            if not isinstance(c, list) or len(c) < 6:
                continue
            ts = c[0]
            minute = candle_minute_from_timestamp(ts)
            if minute is None or minute >= current_minute:
                continue
            op, hi, lo, cl, vol = num(c[1]), num(c[2]), num(c[3]), num(c[4]), integer(c[5])
            if cl <= 0:
                continue
            merged[minute] = (ts, op, hi, lo, cl, vol)

        ordered = sorted(merged.items(), key=lambda x: x[0])
        with data_lock:
            candle_time.clear(); open_history.clear(); high_history.clear()
            low_history.clear(); close_history.clear(); volume_history.clear()
            for _, row in ordered[-MAX_CANDLES:]:
                ts, op, hi, lo, cl, vol = row
                candle_time.append(ts); open_history.append(op); high_history.append(hi)
                low_history.append(lo); close_history.append(cl); volume_history.append(vol)
            historical_candle_count = len(close_history)
            historical_last_minute = ordered[-1][0] if ordered else None
            history_loaded = historical_candle_count >= EMA_SLOW

        safe_print("Merged completed candles:", historical_candle_count)
        return historical_candle_count > 0
    except Exception as e:
        log_exception("INTRADAY REFRESH ERROR", e)
        return False


def load_historical_data():
    global history_loaded, historical_last_minute, historical_candle_count
    safe_print("\nLoading historical NIFTY 1-minute candles...")
    to_date = today_string()
    from_date = time.strftime("%Y-%m-%d", time.localtime(time.time() - HISTORY_DAYS * 86400))
    url = ("https://api.upstox.com/v3/historical-candle/" + NIFTY_KEY.replace("|", "%7C") +
           "/minutes/" + str(HISTORY_INTERVAL) + "/" + to_date + "/" + from_date)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        safe_print("Historical API:", r.status_code)
        if r.status_code != 200:
            safe_print(r.text[:500])
            return False
        candles = r.json().get("data", {}).get("candles", [])
        if not candles:
            return False
        try:
            candles = sorted(candles, key=lambda x: x[0])
        except Exception:
            pass
        loaded = 0
        last_minute = None
        for c in candles:
            if not isinstance(c, list) or len(c) < 6:
                continue
            op, hi, lo, cl, vol = num(c[1]), num(c[2]), num(c[3]), num(c[4]), integer(c[5])
            if cl <= 0:
                continue
            minute = candle_minute_from_timestamp(c[0])
            candle_time.append(c[0]); open_history.append(op); high_history.append(hi)
            low_history.append(lo); close_history.append(cl); volume_history.append(vol)
            if minute is not None:
                last_minute = minute
            loaded += 1
        historical_candle_count = loaded
        historical_last_minute = last_minute
        history_loaded = loaded >= EMA_SLOW
        safe_print("Historical candles loaded:", loaded)
        return loaded > 0
    except Exception as e:
        log_exception("HISTORICAL DATA ERROR", e)
        return False


def get_atm(spot):
    if num(spot) <= 0:
        return 0
    return round(spot / STRIKE_STEP) * STRIKE_STEP


def select_options(chain, atm):
    selected = []
    strikes = sorted(set(num(row.get("strike_price")) for row in chain if num(row.get("strike_price")) > 0))
    nearest = sorted(strikes, key=lambda x: abs(x - atm))[:STRIKE_RANGE]
    nearest = sorted(nearest)
    safe_print("\nSELECTED STRIKES")
    safe_print("--------------------------------")
    for row in chain:
        strike = num(row.get("strike_price"))
        if strike not in nearest:
            continue
        call = row.get("call_options", {})
        put = row.get("put_options", {})
        if isinstance(call, dict) and call.get("instrument_key"):
            selected.append({"strike": strike, "type": "CE", "key": call["instrument_key"]})
            safe_print(strike, "CE", call["instrument_key"])
        if isinstance(put, dict) and put.get("instrument_key"):
            selected.append({"strike": strike, "type": "PE", "key": put["instrument_key"]})
            safe_print(strike, "PE", put["instrument_key"])
    safe_print("--------------------------------")
    safe_print("OPTIONS:", len(selected))
    return selected


# ============================================================
# LIVE CANDLE  (unchanged from V47.2)
# ============================================================

def update_live_candle(ltp, volume=None, event_time=None):
    global historical_last_minute, last_live_minute, candle_status
    global live_tick_count, live_session_started, live_session_start_time, live_completed_candles

    if num(ltp) <= 0 or not nse_market_open_now():
        return

    live_tick_count += 1
    if not live_session_started:
        live_session_started = True
        live_session_start_time = time.time()

    minute = timestamp_minute(event_time) if event_time else timestamp_minute()

    with data_lock:
        c = current_candle
        if c["minute"] is None:
            if (historical_last_minute is not None and minute == historical_last_minute and close_history):
                c["minute"] = minute
                c["open"] = open_history[-1]
                c["high"] = max(high_history[-1], ltp)
                c["low"] = min(low_history[-1], ltp)
                c["close"] = ltp
                c["volume"] = max(volume_history[-1], integer(volume))
                open_history[-1] = c["open"]; high_history[-1] = c["high"]
                low_history[-1] = c["low"]; close_history[-1] = c["close"]; volume_history[-1] = c["volume"]
                last_live_minute = minute
                candle_status = "UPDATING HISTORICAL LAST CANDLE"
                return

            c["minute"] = minute
            c["open"] = c["high"] = c["low"] = c["close"] = ltp
            c["volume"] = integer(volume)
            last_live_minute = minute
            if historical_last_minute is None:
                candle_status = "LIVE CANDLE"
            elif minute == historical_last_minute + 1:
                candle_status = "CONTINUOUS"
            elif minute > historical_last_minute + 1:
                candle_status = "GAP DETECTED"
            else:
                candle_status = "OLDER LIVE DATA"
            return

        if minute == c["minute"]:
            c["high"] = max(c["high"], ltp); c["low"] = min(c["low"], ltp); c["close"] = ltp
            if volume is not None:
                c["volume"] = max(c["volume"], integer(volume))
            last_live_minute = minute
            candle_status = "LIVE CANDLE"
            return

        if c["close"] > 0:
            candle_time.append(c["minute"]); open_history.append(c["open"]); high_history.append(c["high"])
            low_history.append(c["low"]); close_history.append(c["close"]); volume_history.append(c["volume"])
            historical_last_minute = c["minute"]
            live_completed_candles += 1

        c["minute"] = minute
        c["open"] = c["high"] = c["low"] = c["close"] = ltp
        c["volume"] = integer(volume)
        last_live_minute = minute
        if minute == historical_last_minute + 1:
            candle_status = "CONTINUOUS"
        elif minute > historical_last_minute + 1:
            candle_status = "GAP DETECTED"
        else:
            candle_status = "OLDER LIVE DATA"


def get_indicator_series():
    with data_lock:
        closes = list(close_history); highs = list(high_history); lows = list(low_history)
        c = dict(current_candle); hist_last = historical_last_minute; status = candle_status

    if (c.get("minute") is not None and c.get("close", 0) > 0 and hist_last is not None and
            c["minute"] == hist_last + 1 and status in ("CONTINUOUS", "LIVE CANDLE")):
        closes.append(c["close"]); highs.append(c["high"]); lows.append(c["low"])
    return {"closes": closes, "highs": highs, "lows": lows}


def parse_message(message):
    if not isinstance(message, dict):
        return
    feeds = message.get("feeds")
    if not isinstance(feeds, dict):
        return
    for key, feed in feeds.items():
        if not isinstance(feed, dict):
            continue
        full = feed.get("fullFeed", {})
        if not isinstance(full, dict):
            continue
        index_feed = full.get("indexFF", {}); market_feed = full.get("marketFF", {})
        source = {}
        if isinstance(index_feed, dict):
            source.update(index_feed)
        if isinstance(market_feed, dict):
            source.update(market_feed)
        if not source:
            continue

        with data_lock:
            old = live_data.get(key, {}).copy()

        ltpc = source.get("ltpc", {})
        if not isinstance(ltpc, dict):
            ltpc = {}
        ltp = num(ltpc.get("ltp")); cp = num(ltpc.get("cp"))
        if ltp > 0:
            old["ltp"] = ltp
        if cp > 0:
            old["cp"] = cp

        market_level = source.get("marketLevel", {})
        if isinstance(market_level, dict):
            quotes = market_level.get("bidAskQuote", [])
            if isinstance(quotes, list) and quotes:
                q = quotes[0]
                if isinstance(q, dict):
                    if num(q.get("bidP")) > 0:
                        old["bid"] = num(q.get("bidP"))
                    if num(q.get("askP")) > 0:
                        old["ask"] = num(q.get("askP"))
                    if integer(q.get("bidQ")) > 0:
                        old["bid_qty"] = integer(q.get("bidQ"))
                    if integer(q.get("askQ")) > 0:
                        old["ask_qty"] = integer(q.get("askQ"))

        greeks = source.get("optionGreeks", {})
        iv_new = None
        if isinstance(greeks, dict):
            old["delta"] = num(greeks.get("delta"), old.get("delta", 0))
            old["gamma"] = num(greeks.get("gamma"), old.get("gamma", 0))
            old["theta"] = num(greeks.get("theta"), old.get("theta", 0))
            old["vega"] = num(greeks.get("vega"), old.get("vega", 0))
            iv_new = num(greeks.get("iv"), old.get("iv", 0))
            old["iv"] = iv_new

        oi = integer(source.get("oi")); volume = integer(source.get("vtt"))
        buy_qty = integer(source.get("tbq")); sell_qty = integer(source.get("tsq"))
        if oi > 0:
            old["oi"] = oi
        if volume > 0:
            old["volume"] = volume
        if buy_qty > 0:
            old["buy_qty"] = buy_qty
        if sell_qty > 0:
            old["sell_qty"] = sell_qty

        feed_time = ltpc.get("ltt") or source.get("ltt") or source.get("timestamp")
        if feed_time:
            old["timestamp"] = feed_time

        with data_lock:
            live_data[key] = old
            # IV history feeds the pre-entry IV-percentile filter. This
            # dict is written here (WebSocket thread) and read from the
            # display thread at trade entry, so it needs the same lock.
            if iv_new and iv_new > 0:
                option_iv_history.setdefault(key, deque(maxlen=IV_HISTORY_LEN)).append(iv_new)

        if key == NIFTY_KEY and ltp > 0:
            update_live_candle(
                ltp, volume=old.get("volume"),
                event_time=(num(feed_time) / 1000 if num(feed_time) > 10000000000
                            else num(feed_time) if num(feed_time) > 0 else None)
            )


# ============================================================
# WEBSOCKET  (unchanged from V47.2)
# ============================================================

def on_open(*args):
    global ws_connected, ws_subscribed, ws_last_open_time, ws_last_error
    ws_connected = True; ws_subscribed = False; ws_last_open_time = time.time(); ws_last_error = None
    safe_print("\n======================================"); safe_print("WEBSOCKET CONNECTED")
    keys = [NIFTY_KEY]
    for item in selected_strikes:
        if item["key"] not in keys:
            keys.append(item["key"])
    safe_print("SUBSCRIBING:", len(keys), "INSTRUMENTS")
    try:
        streamer.subscribe(keys, "full")
        ws_subscribed = True
        safe_print("SUBSCRIPTION SENT")
    except Exception as e:
        ws_subscribed = False
        ws_last_error = str(e)
        log_exception("SUBSCRIBE ERROR", e)


def on_message(message):
    try:
        parse_message(message)
    except Exception as e:
        log_exception("MESSAGE PARSER ERROR", e)


def on_error(error):
    global ws_last_error
    ws_last_error = str(error)
    safe_print("\nWEBSOCKET ERROR:", error)


def on_close(*args):
    global ws_connected, ws_subscribed, ws_last_close_time
    ws_connected = False; ws_subscribed = False; ws_last_close_time = time.time()
    safe_print("\nWEBSOCKET CLOSED")


def on_reconnecting(*args):
    global ws_reconnect_count, ws_last_reconnecting_time
    ws_reconnect_count += 1; ws_last_reconnecting_time = time.time()
    safe_print("\nWEBSOCKET RECONNECTING:", ws_reconnect_count)


def on_auto_reconnect_stopped(*args):
    safe_print("\nWEBSOCKET AUTO-RECONNECT STOPPED")


def websocket_connect_worker():
    global ws_connect_attempts, ws_last_error
    ws_connect_attempts += 1
    safe_print("WS CONNECT THREAD STARTED | ATTEMPT:", ws_connect_attempts)
    try:
        streamer.connect()
        safe_print("WS CONNECT CALL RETURNED")
    except Exception as e:
        ws_last_error = str(e)
        log_exception("WS CONNECT THREAD ERROR", e)


def rest_loop():
    while running:
        try:
            data = get_nifty_rest()
            if data and data["ltp"] > 0:
                with data_lock:
                    old = live_data.get(NIFTY_KEY, {}).copy()
                    old["ltp"] = data["ltp"]
                    if data["cp"] > 0:
                        old["cp"] = data["cp"]
                    if data["volume"] > 0:
                        old["volume"] = data["volume"]
                    if data["oi"] > 0:
                        old["oi"] = data["oi"]
                    live_data[NIFTY_KEY] = old
        except Exception as e:
            log_exception("REST LOOP ERROR", e)
        time.sleep(REST_SECONDS)


# ============================================================
# INDICATOR / SIGNAL WRAPPERS
# (thin glue: pull live state, hand off to nifty_algo_core's
#  pure functions, which is what makes the core testable/backtestable)
# ============================================================

def compute_technical():
    series = get_indicator_series()
    return technical_score(series["closes"], series["highs"], series["lows"],
                                 ema_fast=EMA_FAST, ema_slow=EMA_SLOW,
                                 rsi_length=RSI_LENGTH, atr_length=ATR_LENGTH,
                                 adx_length=ADX_LENGTH, min_adx=MIN_ADX_FOR_TREND_SIGNAL)


def compute_momentum():
    series = get_indicator_series()
    return momentum_score(series["closes"], rsi_length=RSI_LENGTH)


def compute_htf_trend():
    series = get_indicator_series()
    return higher_timeframe_trend(series["highs"], series["lows"], series["closes"],
                                        factor=HTF_FACTOR, ema_fast=EMA_FAST, ema_slow=EMA_SLOW)


def compute_option_pressure():
    """
    Aggregates CE/PE totals across selected_strikes, then delegates the
    scoring math to option_pressure_score(). This is the ONE OI/price
    delta tracker (option_prev_tick / option_session_baseline) -- V47.2
    had two of these (an inline one and a separate "V31" one) and only
    ever returned the second, leaving the first as dead code.
    """
    ce_oi = pe_oi = ce_volume = pe_volume = 0
    ce_buy = pe_buy = ce_sell = pe_sell = 0
    ce_price_change = pe_price_change = 0.0
    live_count = 0

    with data_lock:
        snapshot = [(item, live_data.get(item["key"], {}).copy()) for item in selected_strikes]

    for item, data in snapshot:
        key = item["key"]; typ = item["type"]
        ltp = num(data.get("ltp")); oi = integer(data.get("oi"))
        volume = integer(data.get("volume"))
        buy_qty = integer(data.get("buy_qty")); sell_qty = integer(data.get("sell_qty"))
        if ltp > 0:
            live_count += 1

        prev = option_prev_tick.get(key)
        price_delta = (ltp - num(prev.get("ltp"))) if prev and ltp > 0 and num(prev.get("ltp")) > 0 else 0.0

        if key not in option_session_baseline and oi > 0:
            option_session_baseline[key] = {"oi": oi, "volume": volume}

        if typ == "CE":
            ce_oi += oi; ce_volume += volume; ce_buy += buy_qty; ce_sell += sell_qty
            ce_price_change += price_delta
        else:
            pe_oi += oi; pe_volume += volume; pe_buy += buy_qty; pe_sell += sell_qty
            pe_price_change += price_delta

        option_prev_tick[key] = {"ltp": ltp, "oi": oi, "volume": volume}

    result = option_pressure_score(ce_oi, pe_oi, ce_volume, pe_volume,
                                         ce_buy, pe_buy, ce_sell, pe_sell,
                                         ce_price_change, pe_price_change)
    result["live_count"] = live_count
    return result


def live_signal_ready():
    with data_lock:
        c = dict(current_candle); status = candle_status
        ticks = live_tick_count; started = live_session_started
        started_at = live_session_start_time; hist_minute = historical_last_minute

    if not ws_connected:
        return False, "WAIT: WEBSOCKET DISCONNECTED"
    if not ws_subscribed:
        return False, "WAIT: WEBSOCKET NOT SUBSCRIBED"

    live_min = c.get("minute")
    if live_min is None or num(c.get("close", 0)) <= 0:
        return False, "NO LIVE CANDLE"
    if status == "OLDER LIVE DATA":
        return False, "LIVE TIMESTAMP OLDER THAN HISTORY"
    if hist_minute is None or live_min > hist_minute + 1:
        return False, "WAIT: HISTORICAL/LIVE CANDLE GAP"
    if not is_trade_time():
        return False, "OUTSIDE TRADE WINDOW (09:25-14:50)"

    elapsed = 0.0
    if started and started_at is not None:
        elapsed = max(0.0, time.time() - started_at)
    if ticks < LIVE_WARMUP_TICKS and elapsed < LIVE_WARMUP_SECONDS:
        return False, f"LIVE WARMUP {ticks}/{LIVE_WARMUP_TICKS}"

    return True, "LIVE DATA READY"


def generate_signal(spot=None):
    ready, readiness_reason = live_signal_ready()
    if not ready:
        result = {
            "signal": "WAIT", "confidence": 0.0, "reason": readiness_reason,
            "technical": compute_technical(), "momentum": compute_momentum(),
            "options": compute_option_pressure(), "htf_trend": compute_htf_trend(),
        }
        log_signal_to_csv(result, spot)
        return result

    technical = compute_technical()
    momentum = compute_momentum()
    options = compute_option_pressure()
    htf_trend = compute_htf_trend()

    if not technical.get("ready"):
        result = {
            "signal": "WAIT", "confidence": 0.0, "reason": "Technical history not ready",
            "technical": technical, "momentum": momentum, "options": options, "htf_trend": htf_trend,
        }
        log_signal_to_csv(result, spot)
        return result

    atr_pct = technical.get("atr_pct")
    if atr_pct is not None and atr_pct < ATR_PCT_MIN:
        result = {
            "signal": "WAIT", "confidence": 0.0,
            "reason": f"Low volatility filter (ATR {atr_pct:.4f}% of spot < {ATR_PCT_MIN}%)",
            "technical": technical, "momentum": momentum, "options": options, "htf_trend": htf_trend,
        }
        log_signal_to_csv(result, spot)
        return result

    decision = signal_decision(
        technical, momentum, options,
        min_direction_score=MIN_DIRECTION_SCORE,
        confidence_threshold=CONFIDENCE_THRESHOLD,
        min_adx_for_trend_signal=MIN_ADX_FOR_TREND_SIGNAL,
        require_htf_agreement=REQUIRE_HTF_AGREEMENT,
        htf_trend=htf_trend,
    )
    result = dict(decision)
    result.update({"technical": technical, "momentum": momentum, "options": options, "htf_trend": htf_trend})

    global last_signal_audit
    last_signal_audit = {
        "signal": result["signal"], "confidence": result.get("confidence", 0.0),
        "reason": result.get("reason", ""), "timestamp": time.strftime("%H:%M:%S"),
    }
    log_signal_to_csv(result, spot)
    return result


# ============================================================
# RISK STATE + CSV PERSISTENCE
# ============================================================

def reset_daily_state_if_new_day():
    global daily_pnl, trades_today, consecutive_losses, cooldown_until, current_trade_date
    today = today_string()
    if current_trade_date != today:
        current_trade_date = today
        daily_pnl = 0.0
        trades_today = 0
        consecutive_losses = 0
        cooldown_until = None
        safe_print("NEW TRADING DAY -- risk counters reset:", today)


def _append_csv(path, fieldnames, row):
    file_exists = os.path.isfile(path)
    try:
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        safe_print("CSV LOG ERROR:", path, e)


SIGNAL_FIELDS = ["timestamp", "spot", "signal", "confidence", "reason",
                  "technical_score", "trend", "trend_strength", "adx",
                  "momentum_score", "option_score", "option_bias",
                  "htf_trend", "atr_pct"]


def log_signal_to_csv(result, spot):
    technical = result.get("technical", {}) or {}
    momentum = result.get("momentum", {}) or {}
    options = result.get("options", {}) or {}
    row = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "spot": spot,
        "signal": result.get("signal"),
        "confidence": round(num(result.get("confidence")), 2),
        "reason": result.get("reason"),
        "technical_score": technical.get("score"),
        "trend": technical.get("trend"),
        "trend_strength": technical.get("trend_strength"),
        "adx": technical.get("adx"),
        "momentum_score": momentum.get("score"),
        "option_score": options.get("score"),
        "option_bias": options.get("bias"),
        "htf_trend": result.get("htf_trend"),
        "atr_pct": technical.get("atr_pct"),
    }
    _append_csv(SIGNALS_LOG_PATH, SIGNAL_FIELDS, row)


TRADE_FIELDS = ["entry_time", "exit_time", "signal", "direction", "strike", "type", "lots",
                 "entry", "exit", "sl", "target", "atr_used", "option_delta", "confidence",
                 "iv_percentile_at_entry", "gross_pnl", "cost", "net_pnl", "exit_reason",
                 "used_ltp_fallback_entry", "used_ltp_fallback_exit"]


def log_trade_to_csv(record):
    row = {k: record.get(k) for k in TRADE_FIELDS}
    _append_csv(TRADES_LOG_PATH, TRADE_FIELDS, row)


# ============================================================
# PAPER TRADE ENGINE
# ============================================================

def place_real_order(*args, **kwargs):
    """
    NOT IMPLEMENTED. Deliberately.

    Real order placement needs to be built and tested against Upstox's
    specific order-placement API, wired through the broker-approved,
    SEBI-compliant access path (static IP whitelisting, OAuth, mandatory
    2FA, daily session expiry, unique algo order-ID tagging -- see the
    retail algo-trading framework that took full effect 1 April 2026),
    and validated with tiny size in a monitored live setting before it's
    trusted with real capital. None of that can be responsibly written
    and shipped sight-unseen in this file. Wire this in only after the
    paper-trading numbers above look solid across many weeks and
    multiple market regimes -- and after you've built it against the
    actual current Upstox order API docs.
    """
    raise NotImplementedError("Real order placement is not implemented in this script.")


def select_trade_option(signal, spot):
    atm = get_atm(spot)
    desired_type = "CE" if signal == "BUY CALL" else "PE" if signal == "BUY PUT" else None
    if not desired_type:
        return None

    candidates = []
    for item in selected_strikes:
        if item["type"] != desired_type:
            continue
        with data_lock:
            data = live_data.get(item["key"], {}).copy()
        vol = integer(data.get("volume")); oi = integer(data.get("oi")); ltp = num(data.get("ltp"))
        bid = num(data.get("bid")); ask = num(data.get("ask"))
        if ltp <= 0:
            continue
        # Liquidity/spread check -- V47.2 never looked at spread at all.
        if bid > 0 and ask > 0:
            spread_pct = (ask - bid) / ltp * 100.0 if ltp > 0 else 999
            if spread_pct > 8.0:   # skip strikes with an unreasonably wide quoted spread
                continue
        distance = abs(item["strike"] - atm)
        score = (vol * 0.6 + oi * 0.3) - (distance * 2)
        candidates.append((score, distance, item))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2]


def open_paper_trade(signal, confidence, spot, technical):
    global paper_trade, trades_today

    allowed, reason = should_trade_now(
        daily_pnl=daily_pnl, max_daily_loss=MAX_DAILY_LOSS, daily_profit_lock=DAILY_PROFIT_LOCK,
        trades_today=trades_today, max_trades_per_day=MAX_TRADES_PER_DAY,
        consecutive_losses=consecutive_losses, max_consecutive_losses=MAX_CONSECUTIVE_LOSSES,
        cooldown_until=cooldown_until, now=time.time(),
    )
    if not allowed:
        return None, reason

    option = select_trade_option(signal, spot)
    if option is None:
        return None, "No liquid option candidate found"

    with data_lock:
        data = live_data.get(option["key"], {}).copy()

    ask = num(data.get("ask")); ltp = num(data.get("ltp"))
    entry_price = ask if ask > 0 else ltp
    if entry_price <= 0:
        return None, "No valid entry price (no ask/ltp)"
    used_ltp_fallback_entry = ask <= 0

    iv_now = num(data.get("iv"))
    with data_lock:
        hist = list(option_iv_history.get(option["key"], []))
    iv_pct = iv_percentile(iv_now, hist)
    if iv_pct is not None and iv_pct > IV_PERCENTILE_MAX:
        return None, f"Skipped: option IV percentile {iv_pct:.0f} > {IV_PERCENTILE_MAX} (premium looks rich right now)"

    atr = technical.get("atr")
    if atr is None or atr <= 0:
        atr = 8.0
    option_delta = num(data.get("delta"))
    stop_target = delta_adjusted_option_stop_target(
        atr, option_delta, sl_multiplier=ATR_SL_MULTIPLIER, target_multiplier=ATR_TARGET_MULTIPLIER,
    )
    sl = entry_price - stop_target["sl_distance"]
    target = entry_price + stop_target["target_distance"]
    if sl <= 0:
        sl = entry_price * 0.85

    lots = position_size(CAPITAL, RISK_PER_TRADE_PCT, entry_price, sl, LOT_SIZE, MAX_LOTS_PER_TRADE)
    if lots <= 0:
        return None, "Position sizing returned 0 lots (risk budget too small for this stop distance)"

    if REAL_ORDER:
        place_real_order(option, entry_price, lots)  # will raise -- see docstring

    paper_trade = {
        "signal": signal, "direction": "CALL" if signal == "BUY CALL" else "PUT",
        "strike": option["strike"], "type": option["type"], "key": option["key"],
        "entry": entry_price, "sl": sl, "target": target,
        "atr_used": stop_target["option_atr"], "option_delta": option_delta,
        "lots": lots, "highest": entry_price, "trail_active": False,
        "confidence": confidence, "iv_percentile_at_entry": iv_pct,
        "used_ltp_fallback_entry": used_ltp_fallback_entry,
        "entry_time": time.strftime("%H:%M:%S"),
    }
    trades_today += 1

    safe_print("\n======================================")
    safe_print("PAPER TRADE OPENED")
    safe_print("SIGNAL:", signal, "| CONFIDENCE:", round(confidence, 1), "%")
    safe_print("OPTION:", option["strike"], option["type"], "| LOTS:", lots)
    safe_print("ENTRY:", round(entry_price, 2), "(ask)" if not used_ltp_fallback_entry else "(ltp fallback)")
    safe_print("SL:", round(sl, 2), "TARGET:", round(target, 2), "| delta:", round(option_delta, 3))
    if iv_pct is not None:
        safe_print("IV PERCENTILE AT ENTRY:", round(iv_pct, 1))
    safe_print("======================================")
    return paper_trade, "OPENED"


def close_paper_trade(exit_price, exit_reason, used_ltp_fallback_exit):
    global paper_trade, daily_pnl, consecutive_losses, cooldown_until

    lots = paper_trade["lots"]
    gross_pnl = (exit_price - paper_trade["entry"]) * LOT_SIZE * lots
    cost, cost_breakdown = estimate_option_trade_cost(paper_trade["entry"], exit_price, LOT_SIZE, lots)
    net_pnl = gross_pnl - cost

    daily_pnl += net_pnl
    if net_pnl > 0:
        consecutive_losses = 0
        paper_trade_stats["wins"] += 1
    else:
        consecutive_losses += 1
        paper_trade_stats["losses"] += 1
        if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            cooldown_until = time.time() + COOLDOWN_MINUTES_AFTER_STREAK * 60
            safe_print(f"RISK: {consecutive_losses} consecutive losses -- "
                       f"cooldown for {COOLDOWN_MINUTES_AFTER_STREAK} min")

    paper_trade_stats["closed"] += 1
    paper_trade_stats["gross_pnl"] += gross_pnl
    paper_trade_stats["net_pnl"] += net_pnl
    paper_trade_stats["total_cost"] += cost

    record = dict(paper_trade)
    record.update({
        "exit": exit_price, "exit_reason": exit_reason, "gross_pnl": gross_pnl,
        "cost": cost, "net_pnl": net_pnl, "exit_time": time.strftime("%H:%M:%S"),
        "used_ltp_fallback_exit": used_ltp_fallback_exit,
    })
    paper_trades.append(record)
    log_trade_to_csv(record)

    safe_print("\n======================================")
    safe_print("PAPER TRADE CLOSED:", exit_reason)
    safe_print("ENTRY:", round(paper_trade["entry"], 2), "EXIT:", round(exit_price, 2), "LOTS:", lots)
    safe_print("GROSS P&L:", round(gross_pnl, 2), "| COST:", round(cost, 2), "| NET P&L:", round(net_pnl, 2))
    safe_print("DAILY P&L:", round(daily_pnl, 2), "| TRADES TODAY:", trades_today,
               "| CONSEC LOSSES:", consecutive_losses)
    safe_print("======================================")
    paper_trade = None


def paper_trade_engine(signal_data, spot, technical):
    reset_daily_state_if_new_day()

    signal = signal_data["signal"]
    confidence = signal_data.get("confidence", 0.0)
    ready, _ = live_signal_ready()

    if paper_trade is None and not ready:
        return

    if paper_trade is not None:
        key = paper_trade["key"]
        with data_lock:
            data = live_data.get(key, {}).copy()

        bid = num(data.get("bid")); ltp = num(data.get("ltp"))
        mark_price = ltp
        exit_price_if_closing = bid if bid > 0 else ltp
        used_ltp_fallback_exit = bid <= 0
        if mark_price <= 0:
            return

        entry = paper_trade["entry"]; sl = paper_trade["sl"]; target = paper_trade["target"]
        atr_used = paper_trade.get("atr_used", 8.0)
        highest = paper_trade.get("highest", entry)
        trail_active = paper_trade.get("trail_active", False)

        if mark_price > highest:
            paper_trade["highest"] = mark_price
            highest = mark_price

        r_value = atr_used * ATR_SL_MULTIPLIER
        if not trail_active and (mark_price - entry) >= (r_value * TRAIL_ACTIVATE_R):
            paper_trade["trail_active"] = True
            trail_active = True
            safe_print("TRAILING ACTIVATED")

        if trail_active:
            new_sl = highest - (atr_used * TRAIL_DISTANCE_R)
            if new_sl > sl:
                paper_trade["sl"] = new_sl
                sl = new_sl

        exit_reason = None
        if mark_price <= sl:
            exit_reason = "STOP LOSS" if not trail_active else "TRAILING STOP"
        elif mark_price >= target:
            exit_reason = "TARGET"

        if exit_reason:
            close_paper_trade(exit_price_if_closing, exit_reason, used_ltp_fallback_exit)
        return

    if signal not in ("BUY CALL", "BUY PUT") or confidence < CONFIDENCE_THRESHOLD:
        return

    _, reason = open_paper_trade(signal, confidence, spot, technical)
    if reason != "OPENED":
        safe_print("SIGNAL SEEN BUT NOT TAKEN:", reason)


# ============================================================
# STRIKE REBALANCING
# (V47.2 selected strikes once at startup and never revisited them)
# ============================================================

def rebalance_strikes_if_needed(spot):
    global selected_strikes, last_atm_used, _last_rebalance_check

    if full_chain is None or num(spot) <= 0:
        return

    now = time.time()
    if now - _last_rebalance_check < REBALANCE_CHECK_SECONDS:
        return
    _last_rebalance_check = now

    new_atm = get_atm(spot)
    if last_atm_used is not None and abs(new_atm - last_atm_used) < REBALANCE_THRESHOLD_POINTS:
        return

    safe_print(f"\nREBALANCING STRIKES: ATM {last_atm_used} -> {new_atm}")
    new_strikes = select_options(full_chain, new_atm)
    if not new_strikes:
        safe_print("REBALANCE ABORTED: could not select new strikes")
        return

    old_keys = {s["key"] for s in selected_strikes}
    new_keys = {s["key"] for s in new_strikes}
    protected_keys = {paper_trade["key"]} if paper_trade else set()

    to_add = new_keys - old_keys
    to_remove = (old_keys - new_keys) - protected_keys

    try:
        if to_add and streamer is not None:
            streamer.subscribe(list(to_add), "full")
        # NOTE: verify the exact unsubscribe method name/signature against
        # your installed upstox_client version -- this defends against it
        # not existing rather than assuming it does.
        if to_remove and streamer is not None and hasattr(streamer, "unsubscribe"):
            streamer.unsubscribe(list(to_remove), "full")
    except Exception as e:
        log_exception("REBALANCE SUBSCRIBE ERROR (keeping old strikes)", e)
        return

    kept_open_trade_strike = [s for s in selected_strikes if s["key"] in protected_keys and s["key"] not in new_keys]
    selected_strikes = new_strikes + kept_open_trade_strike
    last_atm_used = new_atm
    safe_print("REBALANCE DONE. Active instruments:", len(selected_strikes))


# ============================================================
# DISPLAY + LOOPS
# ============================================================

def data_quality():
    with data_lock:
        nifty = live_data.get(NIFTY_KEY, {}).copy()
        option_snapshot = [live_data.get(item["key"], {}).copy() for item in selected_strikes]
    nifty_live = num(nifty.get("ltp")) > 0
    live_options = sum(1 for d in option_snapshot if num(d.get("ltp")) > 0)
    total = max(1, len(selected_strikes))
    option_quality = (live_options / total) * 100
    if nifty_live and option_quality >= 80:
        status = "GOOD"
    elif nifty_live and option_quality >= 50:
        status = "PARTIAL"
    else:
        status = "LOW"
    return {"nifty_live": nifty_live, "live_options": live_options,
            "total_options": total, "option_quality": option_quality, "status": status}


def maybe_refresh_history_for_live_gap():
    global V36_LAST_HISTORY_REFRESH
    try:
        if current_candle is None or historical_last_minute is None:
            return False
        live_min = current_candle.get("minute")
        if live_min is None:
            return False
        gap = int(live_min) - int(historical_last_minute)
        if gap <= 1:
            return False
        now = time.time()
        if now - V36_LAST_HISTORY_REFRESH < V36_REFRESH_COOLDOWN:
            return False
        V36_LAST_HISTORY_REFRESH = now
        safe_print(f"HISTORY REFRESH: live/history gap = {gap} minute(s)")
        return refresh_today_intraday_history()
    except Exception as e:
        log_exception("HISTORY REFRESH ERROR", e)
        return False


def display():
    with data_lock:
        nifty = live_data.get(NIFTY_KEY, {}).copy()
        forming = current_candle.copy()
    spot = num(nifty.get("ltp"))

    maybe_refresh_history_for_live_gap()
    if num(spot) > 0:
        try:
            rebalance_strikes_if_needed(spot)
        except Exception as e:
            log_exception("REBALANCE ERROR", e)

    try:
        signal_data = generate_signal(spot=spot)
    except Exception as e:
        log_exception("SIGNAL ENGINE ERROR", e)
        signal_data = {
            "signal": "WAIT", "confidence": 0.0, "reason": "Signal engine error",
            "technical": compute_technical(), "momentum": compute_momentum(),
            "options": compute_option_pressure(), "htf_trend": "NEUTRAL",
        }

    technical = signal_data["technical"]
    if num(spot) > 0:
        try:
            paper_trade_engine(signal_data, spot, technical)
        except Exception as e:
            log_exception("PAPER ENGINE ERROR", e)

    momentum = signal_data["momentum"]
    options = signal_data["options"]
    quality = data_quality()

    safe_print("MARKET SESSION     :", "OPEN" if nse_market_open_now() else "CLOSED")
    safe_print("TRADE WINDOW       :", "YES" if is_trade_time() else "NO")
    safe_print("WS SUBSCRIBED      :", "YES" if ws_subscribed else "NO")
    safe_print("======================================================")
    safe_print("V48 IMPROVED SEMI-ALGO (ADX + HTF + IV + RISK LAYER)")
    safe_print("======================================================")
    safe_print("NIFTY             :", round(spot, 2), "| ATM:", last_atm_used)
    safe_print("WEBSOCKET         :", "CONNECTED" if ws_connected else "DISCONNECTED")
    safe_print("DATA QUALITY      :", quality["status"],
               f"({quality['live_options']}/{quality['total_options']} options live)")
    safe_print()
    safe_print("CANDLE STATUS     :", candle_status, "| HIST LAST MIN:", historical_last_minute)
    safe_print()
    safe_print("TECHNICAL")
    safe_print("CANDLES USED      :", technical.get("candles", 0))
    safe_print("EMA20/EMA50       :",
               "--" if technical.get("ema_fast") is None else round(technical["ema_fast"], 2),
               "/", "--" if technical.get("ema_slow") is None else round(technical["ema_slow"], 2))
    safe_print("RSI / ATR%        :",
               "--" if technical.get("rsi") is None else round(technical["rsi"], 2), "/",
               "--" if technical.get("atr_pct") is None else round(technical["atr_pct"], 4))
    safe_print("ADX / TREND       :",
               "--" if technical.get("adx") is None else round(technical["adx"], 1),
               "(" + technical.get("trend_strength", "?") + ")", "|", technical.get("trend", "?"))
    safe_print("TECHNICAL SCORE   :", round(technical.get("score", 0), 2))
    safe_print("HTF (5-min) TREND :", signal_data.get("htf_trend"))
    safe_print()
    safe_print("MOMENTUM SCORE    :", round(momentum.get("score", 0), 2))
    safe_print("OPTION PRESSURE   :", round(options.get("score", 0), 2), options.get("bias"))
    safe_print()
    safe_print("FINAL SIGNAL      :", signal_data["signal"])
    safe_print("CONFIDENCE        :", round(signal_data.get("confidence", 0), 1), "%")
    safe_print("REASON            :", signal_data.get("reason"))
    safe_print()
    safe_print("RISK STATE        : Daily P&L", round(daily_pnl, 2),
               "| Trades today", trades_today, "/", MAX_TRADES_PER_DAY,
               "| Consec losses", consecutive_losses,
               "| Cooldown", "ACTIVE" if (cooldown_until and time.time() < cooldown_until) else "off")
    safe_print("PAPER STATS       : Closed", paper_trade_stats["closed"],
               "| Wins", paper_trade_stats["wins"], "| Losses", paper_trade_stats["losses"],
               "| Gross", round(paper_trade_stats["gross_pnl"], 2),
               "| Costs", round(paper_trade_stats["total_cost"], 2),
               "| Net", round(paper_trade_stats["net_pnl"], 2))
    if paper_trade:
        safe_print("PAPER POSITION    : OPEN", paper_trade["strike"], paper_trade["type"],
                   "x", paper_trade["lots"], "lots")
        safe_print("ENTRY/SL/TARGET   :", round(paper_trade["entry"], 2),
                   round(paper_trade["sl"], 2), round(paper_trade["target"], 2))
        safe_print("TRAIL ACTIVE      :", paper_trade.get("trail_active", False))
    else:
        safe_print("PAPER POSITION    : NONE")
    safe_print("REAL ORDER        :", REAL_ORDER, "(order placement not implemented -- paper only)")
    safe_print("======================================================")


def display_loop():
    while running:
        try:
            display()
        except Exception as e:
            log_exception("DISPLAY ERROR", e)
        time.sleep(DISPLAY_SECONDS)


def cmd_live():
    global streamer, selected_expiry, selected_strikes, running, full_chain, last_atm_used

    # Deferred import: keeps the rest of this module importable/unit-
    # testable without the broker SDK installed.
    import upstox_client

    safe_print("\n==============================================")
    safe_print("V48 IMPROVED SEMI-ALGO")
    safe_print("ADX chop filter + 5-min HTF confirm + IV filter + risk layer")
    safe_print("==============================================")
    safe_print("REAL ORDER:", REAL_ORDER)

    if REAL_ORDER:
        safe_print("\nREAL_ORDER=True, but place_real_order() is intentionally NOT implemented.")
        safe_print("This build is PAPER-TRADING ONLY. Set REAL_ORDER=False, or implement and")
        safe_print("thoroughly test place_real_order() first. Refusing to start.")
        return

    if ACCESS_TOKEN == "PASTE_YOUR_ACCESS_TOKEN_HERE" or ACCESS_TOKEN == "token":
        safe_print("\nERROR: Put your Upstox access token in ACCESS_TOKEN.")
        return

    selected_expiry = get_expiry()
    if not selected_expiry:
        safe_print("EXPIRY DISCOVERY FAILED")
        return

    chain = get_option_chain(selected_expiry)
    if not chain:
        safe_print("OPTION CHAIN FAILED")
        return
    full_chain = chain

    nifty = get_nifty_rest()
    if not nifty or num(nifty["ltp"]) <= 0:
        safe_print("NIFTY REST DATA FAILED")
        return

    spot = nifty["ltp"]
    safe_print("\nNIFTY SPOT:", round(spot, 2))
    atm = get_atm(spot)
    safe_print("ATM STRIKE:", float(atm))
    last_atm_used = atm

    selected_strikes = select_options(chain, atm)
    if not selected_strikes:
        safe_print("OPTION SELECTION FAILED")
        return

    load_historical_data()
    refresh_today_intraday_history()

    safe_print("\nCOMPLETED CANDLES:", len(close_history))
    safe_print("TECHNICAL ENGINE:", "READY" if history_loaded else "NOT READY")

    configuration = upstox_client.Configuration()
    configuration.access_token = ACCESS_TOKEN
    api_client = upstox_client.ApiClient(configuration)

    streamer = upstox_client.MarketDataStreamerV3(api_client)
    try:
        streamer.auto_reconnect(True, 10, 20)
    except Exception:
        pass

    streamer.on("open", on_open)
    streamer.on("message", on_message)
    streamer.on("error", on_error)
    streamer.on("close", on_close)
    try:
        streamer.on("reconnecting", on_reconnecting)
    except Exception:
        pass
    try:
        streamer.on("autoReconnectStopped", on_auto_reconnect_stopped)
    except Exception:
        pass

    threading.Thread(target=rest_loop, daemon=True).start()
    threading.Thread(target=display_loop, daemon=True).start()

    safe_print("\nConnecting WebSocket...")
    global ws_connect_thread
    ws_connect_thread = threading.Thread(target=websocket_connect_worker, daemon=True,
                                          name="UpstoxWebSocketConnect")
    ws_connect_thread.start()

    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        safe_print("\nStopping V48...")
        running = False


##############################################################################
# SECTION 3: BACKTEST (1-minute, index points)
##############################################################################

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

        tech = technical_score(window_c, window_h, window_l, ema_fast, ema_slow,
                                     rsi_length, atr_length, adx_length, min_adx=0)
        if not tech.get("ready"):
            continue
        mom = momentum_score(window_c, rsi_length)
        htf = higher_timeframe_trend(window_h, window_l, window_c, htf_factor, ema_fast, ema_slow)
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


def cmd_backtest(path=None):
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


##############################################################################
# SECTION 4: FETCH HISTORICAL DATA
##############################################################################

INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"
INTERVAL = 1                    # minutes
DAYS_BACK = 1000                # default history length (1-min data exists from Jan 2022)
CHUNK_DAYS = 25                 # stay under Upstox's ~1-month-per-request cap
REQUEST_DELAY_SECONDS = 0.5
OUTPUT_CSV = DEFAULT_CSV


def daterange_chunks(days_back, chunk_days, today=None):
    """
    Returns a list of (from_date, to_date) date objects, most-recent
    chunk first, each at most `chunk_days` days wide, covering the
    last `days_back` days with no gaps and no overlap.
    """
    today = today or datetime.now().date()
    earliest = today - timedelta(days=days_back)
    chunks = []
    end = today
    while end >= earliest:
        start = max(earliest, end - timedelta(days=chunk_days - 1))
        chunks.append((start, end))
        end = start - timedelta(days=1)
    return chunks


# ============================================================
# Fetching
# ============================================================

def fetch_chunk(instrument_key, interval, from_date, to_date):
    """
    from_date/to_date: 'YYYY-MM-DD' strings. Returns a list of raw
    candle rows [timestamp, open, high, low, close, volume, oi] as
    given by the API, or [] on any failure (never raises -- a bad
    chunk shouldn't kill the whole multi-month pull).
    """
    url = (f"https://api.upstox.com/v3/historical-candle/{instrument_key}"
           f"/minutes/{interval}/{to_date}/{from_date}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        print(f"    REQUEST ERROR for {from_date}..{to_date}:", e)
        return []
    if r.status_code != 200:
        print(f"    HTTP {r.status_code} for {from_date}..{to_date}: {r.text[:300]}")
        return []
    try:
        return r.json().get("data", {}).get("candles", [])
    except Exception as e:
        print("    PARSE ERROR:", e)
        return []


def fetch_all(instrument_key, interval, days_back, chunk_days, delay_seconds, today=None):
    """
    Fetches every chunk and returns candles as a dict keyed by
    timestamp (deduping any overlap at chunk boundaries), sorted
    ascending. Pure w.r.t. network side effects going through
    fetch_chunk() only, so this is unit-testable by monkeypatching
    fetch_chunk.
    """
    chunks = daterange_chunks(days_back, chunk_days, today=today)
    print(f"Fetching {instrument_key} 1-min candles across {len(chunks)} chunk(s), "
          f"~{days_back} days back...")

    all_rows = {}
    for start, end in chunks:
        from_str, to_str = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        print(f"  {from_str} -> {to_str} ...", end=" ", flush=True)
        candles = fetch_chunk(instrument_key, interval, from_str, to_str)
        print(f"{len(candles)} candles")
        for c in candles:
            if not isinstance(c, list) or len(c) < 6:
                continue
            all_rows[c[0]] = c
        if delay_seconds:
            time.sleep(delay_seconds)

    return dict(sorted(all_rows.items(), key=lambda kv: kv[0]))


def write_csv(rows_by_ts, path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for ts, c in rows_by_ts.items():
            writer.writerow([ts, c[1], c[2], c[3], c[4], c[5]])




##############################################################################
# SECTION 5: PARAMETER SWEEP
##############################################################################

# Keep this grid modest -- it's meant to map out the neighbourhood,
# not exhaustively search. Widen it once you know which corner of the
# space looks interesting.
SL_MULTIPLIERS = [1.0, 1.2, 1.5, 2.0]
TARGET_MULTIPLIERS = [1.5, 2.0, 2.4, 3.0, 4.0]
ADX_THRESHOLDS = [15, 18, 22, 26]
DIRECTION_SCORE_THRESHOLDS = [20, 30, 40]

MIN_TRADES_TO_COUNT = 30   # ignore configs with too few trades to mean anything
TOP_N = 20


def cmd_sweep(csv_path=DEFAULT_CSV):
    print(f"Loading {csv_path} ...")
    data = load_ohlc_csv(csv_path)
    print(f"Loaded {len(data['closes'])} bars.\n")

    print("Precomputing indicators ONCE (this is the slow part; every combination below reuses it)...")
    features = precompute_bar_features(data["highs"], data["lows"], data["closes"])
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
        trades = simulate_from_features(
            features, data["highs"], data["lows"], data["closes"], data["opens"],
            min_adx_for_trend_signal=adx_t, min_direction_score=dir_t,
            sl_multiplier=sl_m, target_multiplier=tgt_m,
        )
        stats = summarize_trades(trades)
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


##############################################################################
# SECTION 6: STRATEGY LAB (costs, 5m/15m trend, opening-range breakout)
##############################################################################

SESSION_START = 9 * 60 + 15      # 09:15
SESSION_END = 15 * 60 + 30       # 15:30
FLAT_BY = 15 * 60 + 15           # force-exit by 15:15
ENTRY_CUTOFF_TREND = 14 * 60 + 45
ENTRY_CUTOFF_ORB = 13 * 60 + 30

TRAIN_FRACTION = 0.6
MIN_TRADES_SELECT = 30


# ------------------------------------------------------------------
# Data
# ------------------------------------------------------------------

def load(path):
    data = load_ohlc_csv(path)
    if not data["timestamps"] or data["timestamps"][0] is None:
        raise ValueError("CSV needs a timestamp column (ISO format, as fetch_historical_data.py writes).")
    O, H, L, C, D, M = [], [], [], [], [], []
    for i, t in enumerate(data["timestamps"]):
        dt = datetime.fromisoformat(str(t))
        m = dt.hour * 60 + dt.minute
        if SESSION_START <= m < SESSION_END:
            O.append(data["opens"][i]); H.append(data["highs"][i])
            L.append(data["lows"][i]); C.append(data["closes"][i])
            D.append(dt.date()); M.append(m)

    days, day_last = [], []
    s = 0
    for i in range(1, len(D) + 1):
        if i == len(D) or D[i] != D[s]:
            days.append((s, i))
            last = s
            for j in range(s, i):
                if M[j] < FLAT_BY:
                    last = j
            day_last.append(last)
            s = i
    return {"O": O, "H": H, "L": L, "C": C, "M": M, "days": days, "day_last": day_last}


def resample_days(d, n):
    O, H, L, C = d["O"], d["H"], d["L"], d["C"]
    R = {"O": [], "H": [], "L": [], "C": [], "S": [], "E": [], "D": []}
    for di, (s, e) in enumerate(d["days"]):
        k = s
        while k + n <= e:
            R["O"].append(O[k]); R["H"].append(max(H[k:k + n]))
            R["L"].append(min(L[k:k + n])); R["C"].append(C[k + n - 1])
            R["S"].append(k); R["E"].append(k + n - 1); R["D"].append(di)
            k += n
    return R


# ------------------------------------------------------------------
# Trade mechanics (shared)
# ------------------------------------------------------------------

def scan_exit(side, ei, sl, tgt, last_idx, H, L, C, max_hold):
    end = min(last_idx, ei + max_hold - 1)
    if end < ei:
        end = ei
    for j in range(ei, end + 1):
        if side > 0:
            if L[j] <= sl:
                return sl, j, "SL"
            if H[j] >= tgt:
                return tgt, j, "TARGET"
        else:
            if H[j] >= sl:
                return sl, j, "SL"
            if L[j] <= tgt:
                return tgt, j, "TARGET"
    return C[end], end, "TIME"


# ------------------------------------------------------------------
# Strategy A: trend on N-minute bars
# ------------------------------------------------------------------

def sim_trend(d, R, feats, adx_min, dir_min, sl_m, tgt_m, max_hold=120):
    O, H, L, C, M = d["O"], d["H"], d["L"], d["C"], d["M"]
    trades, blocked = [], -1
    for k in sorted(feats):
        if R["E"][k] <= blocked:
            continue
        f = feats[k]
        tech, mom, htf = f["tech"], f["mom"], f["htf"]
        adx = tech.get("adx")
        if adx is None or adx < adx_min:
            continue
        ds = tech["score"] * 0.40 + mom["score"] * 0.25
        side = 0
        if ds >= dir_min and htf in ("NEUTRAL", "BULLISH"):
            side = 1
        elif ds <= -dir_min and htf in ("NEUTRAL", "BEARISH"):
            side = -1
        if not side:
            continue
        atr = tech.get("atr")
        if not atr or atr <= 0:
            continue
        di = R["D"][k]
        ei = R["E"][k] + 1
        if ei >= d["days"][di][1] or M[ei] >= ENTRY_CUTOFF_TREND or ei > d["day_last"][di]:
            continue
        entry = O[ei]
        sl = entry - side * atr * sl_m
        tgt = entry + side * atr * tgt_m
        px, xj, why = scan_exit(side, ei, sl, tgt, d["day_last"][di], H, L, C, max_hold)
        trades.append({"day": di, "pnl": side * (px - entry), "why": why})
        blocked = xj
    return trades


# ------------------------------------------------------------------
# Strategy B: opening-range breakout
# ------------------------------------------------------------------

def sim_orb(d, or_min, tgt_m, sl_mode):
    O, H, L, C, M = d["O"], d["H"], d["L"], d["C"], d["M"]
    trades = []
    for di, (s, e) in enumerate(d["days"]):
        or_end = s + or_min
        last = d["day_last"][di]
        if e - s < or_min + 10 or M[s] != SESSION_START or M[or_end - 1] != SESSION_START + or_min - 1:
            continue  # incomplete day
        orh, orl = max(H[s:or_end]), min(L[s:or_end])
        w = orh - orl
        if w < 5:
            continue
        for j in range(or_end, last):
            if M[j] >= ENTRY_CUTOFF_ORB:
                break
            if C[j] > orh:
                side = 1
            elif C[j] < orl:
                side = -1
            else:
                continue
            ei = j + 1                       # enter at NEXT bar's open (no lookahead)
            entry = O[ei]
            if sl_mode == "edge":
                sl = orl if side > 0 else orh
            else:
                sl = (orh + orl) / 2.0
            if side * (entry - sl) <= 0:
                break
            tgt = entry + side * tgt_m * w
            px, xj, why = scan_exit(side, ei, sl, tgt, last, H, L, C, 10 ** 9)
            trades.append({"day": di, "pnl": side * (px - entry), "why": why})
            break
    return trades


# ------------------------------------------------------------------
# Evaluation
# ------------------------------------------------------------------

def evaluate(trades, cost):
    n = len(trades)
    if n == 0:
        return {"n": 0, "gross": 0.0, "net": 0.0, "win": 0.0, "pf": None, "t": 0.0, "dd": 0.0, "total": 0.0}
    net = [t["pnl"] - cost for t in trades]
    mean = sum(net) / n
    var = sum((x - mean) ** 2 for x in net) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    t_stat = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    wins = sum(x for x in net if x > 0)
    losses = -sum(x for x in net if x <= 0)
    eq = peak = dd = 0.0
    for x in net:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return {
        "n": n, "gross": sum(t["pnl"] for t in trades) / n, "net": mean,
        "win": 100.0 * sum(1 for x in net if x > 0) / n,
        "pf": (wins / losses) if losses > 0 else None,
        "t": t_stat, "dd": dd, "total": sum(net),
    }


def split(trades, split_day):
    return [t for t in trades if t["day"] < split_day], [t for t in trades if t["day"] >= split_day]


def fmt(s):
    pf = "  n/a" if s["pf"] is None else f"{s['pf']:5.2f}"
    return (f"n={s['n']:4d} gross={s['gross']:6.2f} net={s['net']:6.2f} "
            f"win={s['win']:4.1f}% PF={pf} t={s['t']:5.2f}")


def report(family, rows, split_day):
    """rows: list of (label, trades)."""
    cost = report.cost
    scored = []
    for label, trades in rows:
        tr, te = split(trades, split_day)
        scored.append((label, evaluate(tr, cost), evaluate(te, cost)))

    eligible = [r for r in scored if r[1]["n"] >= MIN_TRADES_SELECT or r[1]["n"] >= 15 and family.startswith("ORB")]
    pos_train = sum(1 for r in scored if r[1]["n"] and r[1]["net"] > 0)
    pos_test = sum(1 for r in scored if r[2]["n"] and r[2]["net"] > 0)

    print("\n" + "=" * 110)
    print(f"{family}: {len(scored)} configs tested | positive net on TRAIN: {pos_train} | on TEST: {pos_test}")
    print("(if positives on test are far fewer than on train, the 'edge' was noise fitted to train)")
    print("=" * 110)
    if not eligible:
        print("No config had enough training trades to select from.")
        return []

    eligible.sort(key=lambda r: r[1]["net"], reverse=True)
    for label, a, b in eligible[:5]:
        print(f"{label}")
        print(f"   TRAIN: {fmt(a)}")
        print(f"   TEST : {fmt(b)}")

    survivors = [r for r in eligible
                 if r[1]["net"] > 0 and r[2]["n"] >= 30 and r[2]["net"] > 0
                 and (r[2]["pf"] or 0) > 1.1 and r[2]["t"] > 2.0]
    return [(family, r[0], r[1], r[2]) for r in survivors]


report.cost = 4.0


def cmd_lab(path=DEFAULT_CSV, cost=4.0):
    report.cost = cost
    print(f"Loading {path} ...")
    d = load(path)
    n_days = len(d["days"])
    print(f"{len(d['C'])} bars over {n_days} trading days. Cost assumed: {cost} index points per round trip.")
    if n_days < 200:
        print(f"WARNING: only {n_days} days. Results below are NOT statistically meaningful --")
        print("run:  python nifty_algo.py fetch 1000   (about 4 years) for a real test.")
    split_day = int(n_days * TRAIN_FRACTION)
    print(f"Train = first {split_day} days, Test = last {n_days - split_day} days.\n")

    survivors = []

    # ---- A) trend on 5m / 15m -------------------------------------
    for tf, htf_factor in ((5, 3), (15, 4)):
        print(f"Precomputing {tf}-minute indicators ...")
        R = resample_days(d, tf)
        feats = precompute_bar_features(R["H"], R["L"], R["C"], htf_factor=htf_factor, progress_every=0)
        rows = []
        for adx_min, dir_min, sl_m, tgt_m in itertools.product((18, 26), (30, 40), (1.0, 1.5), (2.0, 3.0)):
            trades = sim_trend(d, R, feats, adx_min, dir_min, sl_m, tgt_m)
            rows.append((f"TREND {tf}m adx>={adx_min} dir>={dir_min} sl={sl_m}xATR tgt={tgt_m}xATR", trades))
        survivors += report(f"TREND on {tf}-min bars", rows, split_day)

    # ---- B) opening range breakout ---------------------------------
    rows = []
    for or_min, tgt_m, sl_mode in itertools.product((15, 30), (1.0, 1.5, 2.0), ("edge", "mid")):
        trades = sim_orb(d, or_min, tgt_m, sl_mode)
        rows.append((f"ORB or={or_min}min target={tgt_m}xrange stop={sl_mode}", trades))
    survivors += report("ORB (opening range breakout)", rows, split_day)

    print("\n" + "#" * 110)
    print("VERDICT (needs: train net>0, test net>0, test PF>1.1, test t-stat>2, >=30 test trades)")
    print("#" * 110)
    if survivors:
        for fam, label, a, b in survivors:
            print(f"SURVIVED: {label}\n   TRAIN: {fmt(a)}\n   TEST : {fmt(b)}")
        print("\nSurvivors are CANDIDATES, not proof: you still tested dozens of configs, so re-check them")
        print("on a further untouched period (or paper trade them) before trusting any of them.")
    else:
        print("Nothing survived out-of-sample after costs. No index-only strategy tested here has")
        print("demonstrated an edge on this data. Try cost_points=2 to see how sensitive that is.")


##############################################################################
# SECTION 7: SELF-TESTS
##############################################################################

def _selftest_core():
    import random
    core = sys.modules[__name__]
    random.seed(42)
    failures = []



    def check(name, cond):
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name}")
        if not cond:
            failures.append(name)


    # ---------------------------------------------------------------
    # 1. EMA / RSI / ATR basic sanity
    # ---------------------------------------------------------------
    flat = [100.0] * 60
    check("EMA on flat series == 100", math.isclose(core.calculate_ema(flat, 20), 100.0, abs_tol=1e-6))
    check("RSI on flat series == 100 (no losses)", core.calculate_rsi(flat, 14) == 100.0)

    uptrend = [100 + i * 0.5 for i in range(60)]
    rsi_up = core.calculate_rsi(uptrend, 14)
    check("RSI on steady uptrend is high (>70)", rsi_up > 70)

    downtrend = [100 - i * 0.5 for i in range(60)]
    rsi_down = core.calculate_rsi(downtrend, 14)
    check("RSI on steady downtrend is low (<30)", rsi_down < 30)

    # ---------------------------------------------------------------
    # 2. ADX: trending series should show high ADX with +DI > -DI;
    #    a sideways/choppy series should show low ADX
    # ---------------------------------------------------------------
    n = 80
    trend_high = [100 + i * 1.0 + random.uniform(-0.3, 0.3) for i in range(n)]
    trend_low = [x - random.uniform(0.5, 1.5) for x in trend_high]
    trend_close = [(h + l) / 2 for h, l in zip(trend_high, trend_low)]
    adx_trend = core.calculate_adx(trend_high, trend_low, trend_close, length=14)
    check("ADX exists for a clean uptrend", adx_trend is not None)
    if adx_trend:
        print("    trend ADX:", round(adx_trend["adx"], 2),
              "+DI:", round(adx_trend["plus_di"], 2), "-DI:", round(adx_trend["minus_di"], 2))
        check("Trending market: ADX > 20", adx_trend["adx"] > 20)
        check("Trending market: +DI > -DI on uptrend", adx_trend["plus_di"] > adx_trend["minus_di"])

    choppy_close = [100 + random.uniform(-1, 1) for _ in range(n)]
    choppy_high = [c + random.uniform(0.1, 0.5) for c in choppy_close]
    choppy_low = [c - random.uniform(0.1, 0.5) for c in choppy_close]
    adx_chop = core.calculate_adx(choppy_high, choppy_low, choppy_close, length=14)
    check("ADX exists for choppy series", adx_chop is not None)
    if adx_chop:
        print("    choppy ADX:", round(adx_chop["adx"], 2))
        check("Choppy market: ADX < trend ADX", adx_chop["adx"] < adx_trend["adx"])

    # ---------------------------------------------------------------
    # 3. Higher-timeframe resample + trend read
    #    (needs factor * ema_slow = 5*50 = 250+ 1-min bars to have an
    #    opinion at all -- that's realistic: ~4hrs of 1-min data before
    #    a 5-min EMA50 is even computable)
    # ---------------------------------------------------------------
    n_htf = 320
    htf_trend_high = [100 + i * 0.3 + random.uniform(-0.3, 0.3) for i in range(n_htf)]
    htf_trend_low = [x - random.uniform(0.5, 1.5) for x in htf_trend_high]
    htf_trend_close = [(h + l) / 2 for h, l in zip(htf_trend_high, htf_trend_low)]
    htf = core.higher_timeframe_trend(htf_trend_high, htf_trend_low, htf_trend_close, factor=5)
    check("HTF trend reads BULLISH on a long clean uptrend", htf == "BULLISH")

    flat_h = [100.0] * 320  # zero-noise flat series -- removes randomness from this check
    flat_l = [100.0] * 320
    flat_c = [100.0] * 320
    htf_flat = core.higher_timeframe_trend(flat_h, flat_l, flat_c, factor=5)
    check("HTF trend reads NEUTRAL on perfectly flat data", htf_flat == "NEUTRAL")

    # ---------------------------------------------------------------
    # 4. technical_score / momentum_score wiring
    # ---------------------------------------------------------------
    ts = core.technical_score(trend_close, trend_high, trend_low)
    check("technical_score ready == True with enough candles", ts["ready"] is True)
    check("technical_score trend == BULLISH on uptrend", ts["trend"] == "BULLISH")
    check("technical_score trend_strength == STRONG on clean trend", ts["trend_strength"] == "STRONG")

    ms = core.momentum_score(trend_close)
    check("momentum_score positive on uptrend", ms["score"] > 0)

    # ---------------------------------------------------------------
    # 5. option_pressure_score
    # ---------------------------------------------------------------
    ops = core.option_pressure_score(
        ce_oi=50000, pe_oi=200000, ce_volume=2000, pe_volume=12000,
        ce_buy=1000, pe_buy=6000, ce_sell=5000, pe_sell=500,
        ce_price_change=-5, pe_price_change=10,
    )
    print("    option_pressure_score (strong PE skew):", round(ops["score"], 2), ops["bias"])
    check("option_pressure bullish when PE side heavily heavier", ops["bias"] == "BULLISH")

    # ---------------------------------------------------------------
    # 6. signal_decision end-to-end (should not blow up, should WAIT
    #    when ADX is weak even if EMA/RSI look directional)
    # ---------------------------------------------------------------
    sd = core.signal_decision(ts, ms, ops, htf_trend="BULLISH")
    print("    signal_decision on clean uptrend + bullish options + bullish HTF:", sd["signal"], round(sd["confidence"], 1))
    check("signal_decision runs without error and returns a dict", isinstance(sd, dict))

    # weak-trend case: flat data should never produce a BUY signal via the ADX gate
    ts_flat = core.technical_score(flat_c, flat_h, flat_l)
    ms_flat = core.momentum_score(flat_c)
    sd_flat = core.signal_decision(ts_flat, ms_flat, ops, htf_trend="NEUTRAL")
    print("    signal_decision on flat/choppy technical:", sd_flat["signal"], "-", sd_flat["reason"])
    check("ADX chop filter blocks trades when trend_strength is weak/unknown-flat data",
          sd_flat["signal"] == "WAIT")

    # ---------------------------------------------------------------
    # 7. position sizing
    # ---------------------------------------------------------------
    lots = core.position_size(capital=100000, risk_pct=0.01, entry_price=120, stop_price=100, lot_size=65, max_lots=10)
    print("    position_size example -> lots:", lots, "(risking 1% of 100000 with Rs20/unit stop, lot=65)")
    check("position_size returns a sane integer >= 0", isinstance(lots, int) and lots >= 0)
    # risk_amount=1000, per_lot_risk=20*65=1300 -> should be 0 lots (can't afford even 1 lot within risk)
    check("position_size correctly returns 0 when 1 lot already exceeds risk budget", lots == 0)

    lots2 = core.position_size(capital=500000, risk_pct=0.01, entry_price=120, stop_price=100, lot_size=65, max_lots=10)
    print("    position_size example2 -> lots:", lots2, "(risking 1% of 500000)")
    check("position_size scales up with more capital", lots2 > lots)

    # ---------------------------------------------------------------
    # 8. cost model
    # ---------------------------------------------------------------
    total, breakdown = core.estimate_option_trade_cost(entry_price=120, exit_price=140, lot_size=65, lots=2)
    print("    estimated round-trip cost on a 2-lot 120->140 trade:", round(total, 2), breakdown)
    check("cost model returns positive total cost", total > 0)

    # ---------------------------------------------------------------
    # 9. delta-adjusted stop/target
    # ---------------------------------------------------------------
    res_atm = core.delta_adjusted_option_stop_target(spot_atr=20, option_delta=0.5)
    res_otm = core.delta_adjusted_option_stop_target(spot_atr=20, option_delta=0.15)
    print("    ATM (delta .5) option_atr:", round(res_atm["option_atr"], 2),
          "| OTM (delta .15) option_atr:", round(res_otm["option_atr"], 2))
    check("ATM option gets a wider stop/target distance than far-OTM option", res_atm["option_atr"] > res_otm["option_atr"])

    # ---------------------------------------------------------------
    # 10. risk gate (should_trade_now)
    # ---------------------------------------------------------------
    ok, reason = core.should_trade_now(daily_pnl=-5000, max_daily_loss=4000)
    check("should_trade_now blocks after daily max loss breached", ok is False)
    print("    ->", reason)

    ok2, reason2 = core.should_trade_now(daily_pnl=-1000, max_daily_loss=4000, trades_today=3, max_trades_per_day=10)
    check("should_trade_now allows trading when within all limits", ok2 is True)

    ok3, reason3 = core.should_trade_now(
        daily_pnl=0, consecutive_losses=3, max_consecutive_losses=3,
        cooldown_until=1000.0, now=500.0,
    )
    check("should_trade_now enforces cooldown after consecutive losses", ok3 is False)
    print("    ->", reason3)

    # ---------------------------------------------------------------
    print("\n" + "=" * 50)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for f in failures:
            print(" -", f)
    else:
        print("ALL CHECKS PASSED")

    return failures


def _selftest_live():
    import random, tempfile
    live = sys.modules[__name__]
    random.seed(7)
    failures = []
    saved = (live.is_trade_time, live.SIGNALS_LOG_PATH, live.TRADES_LOG_PATH)
    tmp = tempfile.mkdtemp()
    live.SIGNALS_LOG_PATH = os.path.join(tmp, 'signals_log.csv')
    live.TRADES_LOG_PATH = os.path.join(tmp, 'trades_log.csv')
    try:



        def check(name, cond, extra=""):
            status = "PASS" if cond else "FAIL"
            print(f"[{status}] {name}" + (f"  ({extra})" if extra else ""))
            if not cond:
                failures.append(name)


        # Deterministic: don't depend on the sandbox's actual wall-clock day/time.
        live.is_trade_time = lambda: True

        # Clean up any CSVs from a previous run so counts below are meaningful.
        for p in (live.SIGNALS_LOG_PATH, live.TRADES_LOG_PATH):
            if os.path.exists(p):
                os.remove(p)

        # ---------------------------------------------------------------
        # 1. Seed 320 synthetic 1-min NIFTY candles: a clean, low-noise uptrend
        #    (long enough for EMA50, ADX14, AND the 5-min HTF EMA50 to all be
        #    computable -- HTF needs factor(5) * ema_slow(50) = 250 bars).
        # ---------------------------------------------------------------
        n = 320
        base = 24000.0
        highs, lows, closes = [], [], []
        for i in range(n):
            # Wider high/low range than the core-module unit test so ATR%
            # clears ATR_PCT_MIN (this is closer to real NIFTY 1-min noise;
            # the earlier too-tight synthetic series correctly got blocked by
            # the low-volatility filter, which is itself a useful confirmation).
            c = base + i * 1.2 + random.uniform(-1.5, 1.5)
            h = c + random.uniform(2.0, 4.0)
            l = c - random.uniform(2.0, 4.0)
            highs.append(h); lows.append(l); closes.append(c)

        for i in range(n):
            live.candle_time.append(1_700_000_000 + i * 60)
            live.open_history.append(closes[i - 1] if i > 0 else closes[0])
            live.high_history.append(highs[i])
            live.low_history.append(lows[i])
            live.close_history.append(closes[i])
            live.volume_history.append(1000)

        live.historical_last_minute = live.timestamp_minute(1_700_000_000 + (n - 1) * 60)
        live.history_loaded = True

        spot = closes[-1] + 3.0  # forming candle continues the uptrend a bit further
        live.current_candle.update({
            "minute": live.historical_last_minute + 1,
            "open": closes[-1], "high": spot + 1, "low": closes[-1] - 0.5, "close": spot, "volume": 500,
        })
        live.candle_status = "CONTINUOUS"

        live.ws_connected = True
        live.ws_subscribed = True
        live.live_session_started = True
        live.live_session_start_time = time.time() - 100
        live.live_tick_count = 100

        # ---------------------------------------------------------------
        # 2. Fabricate a small option chain + live ticks around ATM
        # ---------------------------------------------------------------
        atm = live.get_atm(spot)
        print("SPOT:", round(spot, 2), "ATM:", atm)

        live.full_chain = []
        live.selected_strikes = []
        strike_defs = []
        for offset in (-100, -50, 0, 50, 100):
            strike = atm + offset
            ce_key = f"NSE_FO|CE{strike}"
            pe_key = f"NSE_FO|PE{strike}"
            strike_defs.append((strike, ce_key, pe_key))
            live.full_chain.append({
                "strike_price": strike,
                "call_options": {"instrument_key": ce_key},
                "put_options": {"instrument_key": pe_key},
            })
            live.selected_strikes.append({"strike": float(strike), "type": "CE", "key": ce_key})
            live.selected_strikes.append({"strike": float(strike), "type": "PE", "key": pe_key})

        for strike, ce_key, pe_key in strike_defs:
            distance = abs(strike - atm)
            ce_delta = max(0.1, 0.5 - distance / 400.0)
            pe_delta = -max(0.1, 0.5 - distance / 400.0)
            ce_price = max(5.0, 120 - distance * 0.8)
            pe_price = max(5.0, 80 - distance * 0.5)
            # Bullish tape: PE side heavier OI/volume/buying pressure than CE.
            live.live_data[ce_key] = {
                "ltp": ce_price, "bid": ce_price - 0.5, "ask": ce_price + 0.5,
                "oi": 40000 - distance * 50, "volume": 3000, "buy_qty": 1500, "sell_qty": 2500,
                "delta": ce_delta, "iv": 14.0,
            }
            live.live_data[pe_key] = {
                "ltp": pe_price, "bid": pe_price - 0.5, "ask": pe_price + 0.5,
                "oi": 90000 - distance * 50, "volume": 9000, "buy_qty": 6000, "sell_qty": 1500,
                "delta": pe_delta, "iv": 15.0,
            }
            # Pre-fill IV history so the IV-percentile filter has something to compare against
            # (current IV sits mid-range of its own recent history -> should not block entry).
            from collections import deque
            live.option_iv_history[ce_key] = deque([12, 13, 14, 15, 16, 14, 13, 15, 14, 14], maxlen=live.IV_HISTORY_LEN)
            live.option_iv_history[pe_key] = deque([13, 14, 15, 16, 17, 15, 14, 16, 15, 15], maxlen=live.IV_HISTORY_LEN)

        live.live_data[live.NIFTY_KEY] = {"ltp": spot}

        # ---------------------------------------------------------------
        # 3. Run the signal engine end-to-end
        # ---------------------------------------------------------------
        result = live.generate_signal(spot=spot)
        print("\nSIGNAL:", result["signal"], "| confidence:", round(result.get("confidence", 0), 1),
              "| reason:", result.get("reason"))
        print("technical:", {k: (round(v, 2) if isinstance(v, float) else v)
                              for k, v in result["technical"].items() if k not in ("candles",)})
        print("htf_trend:", result.get("htf_trend"))
        check("generate_signal runs without raising", True)
        check("signals_log.csv was created", os.path.exists(live.SIGNALS_LOG_PATH))

        # ---------------------------------------------------------------
        # 4. Try to open a paper trade off this signal
        # ---------------------------------------------------------------
        live.paper_trade_engine(result, spot, result["technical"])
        check("A paper trade opened on a strong bullish setup", live.paper_trade is not None,
              extra=f"signal={result['signal']}")

        if live.paper_trade:
            pt = live.paper_trade
            print("\nOPENED:", pt["strike"], pt["type"], "lots:", pt["lots"],
                  "entry:", round(pt["entry"], 2), "sl:", round(pt["sl"], 2), "target:", round(pt["target"], 2))
            check("Opened trade direction matches signal", pt["direction"] == ("CALL" if result["signal"] == "BUY CALL" else "PUT"))
            check("Position sizing produced at least 1 lot", pt["lots"] >= 1)
            check("trades_today incremented", live.trades_today == 1)

            # ---------------------------------------------------------------
            # 5. Walk the price to the target and confirm it closes with the
            #    cost model correctly reducing net P&L below gross P&L.
            # ---------------------------------------------------------------
            key = pt["key"]
            target = pt["target"]
            run_price = pt["entry"]
            steps = 0
            while live.paper_trade is not None and steps < 200:
                run_price = min(target + 1, run_price + 1.0)
                live.live_data[key]["ltp"] = run_price
                live.live_data[key]["bid"] = run_price - 0.5
                live.live_data[key]["ask"] = run_price + 0.5
                live.paper_trade_engine(result, spot, result["technical"])
                steps += 1

            check("Trade eventually closed (target/trail reached)", live.paper_trade is None, extra=f"steps={steps}")
            check("A trade record was appended", len(live.paper_trades) == 1)
            if live.paper_trades:
                rec = live.paper_trades[-1]
                print("CLOSED:", rec["exit_reason"], "gross:", round(rec["gross_pnl"], 2),
                      "cost:", round(rec["cost"], 2), "net:", round(rec["net_pnl"], 2))
                check("Cost model reduced net P&L below gross P&L", rec["net_pnl"] < rec["gross_pnl"])
                check("trades_log.csv was created", os.path.exists(live.TRADES_LOG_PATH))
                check("daily_pnl reflects the closed trade's net P&L",
                      abs(live.daily_pnl - rec["net_pnl"]) < 1e-6)
        else:
            print("(No trade opened -- inspect the signal/filters above; skipping close-cycle checks.)")

        # ---------------------------------------------------------------
        # 6. Risk gate: daily max loss should block a brand-new entry
        # ---------------------------------------------------------------
        live.daily_pnl = -(live.MAX_DAILY_LOSS + 1)
        trade, reason = live.open_paper_trade("BUY CALL", 90.0, spot, result["technical"])
        check("Daily max-loss circuit breaker blocks a new entry", trade is None)
        print("   ->", reason)
        live.daily_pnl = 0.0  # reset for next check

        # ---------------------------------------------------------------
        # 7. Risk gate: consecutive-loss cooldown
        # ---------------------------------------------------------------
        live.consecutive_losses = live.MAX_CONSECUTIVE_LOSSES
        live.cooldown_until = time.time() + 600
        trade2, reason2 = live.open_paper_trade("BUY CALL", 90.0, spot, result["technical"])
        check("Consecutive-loss cooldown blocks a new entry", trade2 is None)
        print("   ->", reason2)
        live.consecutive_losses = 0
        live.cooldown_until = None

        # ---------------------------------------------------------------
        # 8. Strike rebalancing: spot drifts far enough to force a re-center
        # ---------------------------------------------------------------
        live.last_atm_used = atm
        live._last_rebalance_check = 0.0


        class _StubStreamer:
            def subscribe(self, keys, mode):
                print("   stub subscribe:", len(keys), "keys")

            def unsubscribe(self, keys, mode):
                print("   stub unsubscribe:", len(keys), "keys")


        live.streamer = _StubStreamer()
        far_spot = spot + live.REBALANCE_THRESHOLD_POINTS + 10
        # extend the chain so a strike selection exists near the new ATM too
        new_atm_guess = live.get_atm(far_spot)
        for offset in (-100, -50, 0, 50, 100):
            strike = new_atm_guess + offset
            if not any(row["strike_price"] == strike for row in live.full_chain):
                ce_key = f"NSE_FO|CE{strike}"
                pe_key = f"NSE_FO|PE{strike}"
                live.full_chain.append({
                    "strike_price": strike,
                    "call_options": {"instrument_key": ce_key},
                    "put_options": {"instrument_key": pe_key},
                })

        before_count = len(live.selected_strikes)
        live.rebalance_strikes_if_needed(far_spot)
        check("Rebalance updated last_atm_used", live.last_atm_used == new_atm_guess,
              extra=f"{atm} -> {live.last_atm_used}")
        check("Rebalance kept selected_strikes non-empty", len(live.selected_strikes) > 0,
              extra=f"before={before_count} after={len(live.selected_strikes)}")

        # ---------------------------------------------------------------
        print("\n" + "=" * 50)
        if failures:
            print(f"{len(failures)} CHECK(S) FAILED:")
            for f in failures:
                print(" -", f)
        else:
            print("ALL CHECKS PASSED")

    finally:
        live.is_trade_time, live.SIGNALS_LOG_PATH, live.TRADES_LOG_PATH = saved
    return failures


##############################################################################
# SECTION 8: COMMANDS AND MENU
##############################################################################

def _token_ok():
    if ACCESS_TOKEN in ("PASTE_YOUR_ACCESS_TOKEN_HERE", "token", ""):
        print("\nERROR: paste your Upstox access token on the ACCESS_TOKEN line near the top of this file.")
        return False
    if requests is None:
        print("\nERROR: the 'requests' library is missing. Run:  pip install requests")
        return False
    return True


def _need_csv(path):
    if not os.path.exists(path):
        print(f"\nERROR: {path} not found. Run this first:  python nifty_algo.py fetch 1000")
        return False
    return True


def cmd_fetch(days_back=None, out_path=OUTPUT_CSV):
    if not _token_ok():
        return False
    days_back = int(days_back or DAYS_BACK)
    rows = fetch_all(INSTRUMENT_KEY, INTERVAL, days_back, CHUNK_DAYS, REQUEST_DELAY_SECONDS)
    if not rows:
        print("\nNo data fetched. Check the token, and remember 1-min data only goes back to Jan 2022.")
        return False
    write_csv(rows, out_path)
    approx_days = len(rows) / 375.0
    print(f"\nTotal unique candles: {len(rows)}  (~{approx_days:.0f} trading days)")
    print(f"Wrote {out_path}")
    if approx_days < days_back * 0.55:
        print("NOTE: fewer candles than expected - some chunks may have failed (see messages above).")
    return True


def cmd_test():
    print("=" * 60)
    print("SELF-TEST 1/2: core math")
    print("=" * 60)
    f1 = _selftest_core()
    print("\n" + "=" * 60)
    print("SELF-TEST 2/2: live engine simulation (synthetic data, no internet)")
    print("=" * 60)
    f2 = _selftest_live()
    print("\n" + "#" * 60)
    if f1 or f2:
        print("SELF-TESTS FAILED:", f1 + f2)
    else:
        print("ALL SELF-TESTS PASSED")
    print("#" * 60)
    return not (f1 or f2)


def cmd_research(days_back=1000, csv_path=DEFAULT_CSV, cost=4.0):
    if os.path.exists(csv_path):
        print(f"Using existing {csv_path} (delete it, or run 'fetch', to refresh).")
    else:
        if not cmd_fetch(days_back, csv_path):
            return
    cmd_lab(csv_path, cost)


def _ask(prompt, default):
    s = input(f"{prompt} [{default}]: ").strip()
    return s if s else str(default)


def _menu():
    print("\n" + "=" * 60)
    print(" NIFTY ALGO - all-in-one")
    print("=" * 60)
    print(" 1  Self-tests (no internet needed)")
    print(" 2  Fetch historical data from Upstox")
    print(" 3  Strategy lab (costs + 5m/15m trend + opening-range breakout)")
    print(" 4  Research = fetch (if needed) + strategy lab")
    print(" 5  1-minute backtest")
    print(" 6  Parameter sweep (1-minute backtest)")
    print(" 7  Live PAPER trading (weekdays 9:15-15:30 IST)")
    print(" 0  Exit")
    choice = input("\nChoose a number: ").strip()
    if choice == "1":
        cmd_test()
    elif choice == "2":
        cmd_fetch(_ask("How many days back", 1000))
    elif choice == "3":
        p = _ask("CSV file", DEFAULT_CSV)
        if _need_csv(p):
            cmd_lab(p, float(_ask("Round-trip cost in index points", 4.0)))
    elif choice == "4":
        cmd_research(int(_ask("Days of history to fetch", 1000)), DEFAULT_CSV,
                     float(_ask("Round-trip cost in index points", 4.0)))
    elif choice == "5":
        p = _ask("CSV file (blank line = synthetic demo)", DEFAULT_CSV)
        if _need_csv(p):
            cmd_backtest(p)
    elif choice == "6":
        p = _ask("CSV file", DEFAULT_CSV)
        if _need_csv(p):
            cmd_sweep(p)
    elif choice == "7":
        if _token_ok():
            cmd_live()
    else:
        print("Bye.")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _menu()
    cmd, args = argv[0].lower(), argv[1:]
    if cmd == "test":
        sys.exit(0 if cmd_test() else 1)
    elif cmd == "fetch":
        cmd_fetch(args[0] if args else None)
    elif cmd == "backtest":
        p = args[0] if args else None
        if p is None or _need_csv(p):
            cmd_backtest(p)
    elif cmd == "sweep":
        p = args[0] if args else DEFAULT_CSV
        if _need_csv(p):
            cmd_sweep(p)
    elif cmd == "lab":
        p = args[0] if args else DEFAULT_CSV
        if _need_csv(p):
            cmd_lab(p, float(args[1]) if len(args) > 1 else 4.0)
    elif cmd == "research":
        cmd_research(int(args[0]) if args else 1000)
    elif cmd == "live":
        if _token_ok():
            cmd_live()
    else:
        print(f"Unknown command '{cmd}'. Run with no arguments to see the menu.")


if __name__ == "__main__":
    main()
