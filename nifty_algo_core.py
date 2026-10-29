# ============================================================
# nifty_algo_core.py
# ============================================================
# Pure, side-effect-free functions shared by nifty_algo_live.py
# (the live/paper-trading engine) and nifty_algo_backtest.py
# (the offline validator).
#
# NOTHING in this file touches the network, the filesystem, global
# state, or threads. Every function takes explicit inputs and
# returns explicit outputs. That is the whole point of this split:
#
#   V47.2 computed indicators by reading module-level deques
#   directly inside technical_engine()/option_pressure(). That
#   makes it impossible to answer "what would this have signalled
#   on 14-Mar at 10:14?" without re-running the live process.
#   By moving the math here as pure functions, the EXACT SAME code
#   path can be fed live ticks or historical bars.
#
# Nothing here is a black box: every function is short enough to
# read top to bottom, and nifty_algo_backtest.py unit-checks the
# indicator math (calculate_ema/rsi/atr/adx) against hand-built
# synthetic series before you ever point it at real data.
# ============================================================

import math

# ------------------------------------------------------------------
# Basic indicators
# ------------------------------------------------------------------


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


def epm_score(volume_score, iv_skew, underlying_trend_score,
              weights=(0.40, 0.30, 0.30)):
    """
    PLACEHOLDER — confirm the real formula before trusting this.
    volume_score: same -100..100 scale as option_pressure's volume_score
                  (PE volume vs CE volume skew)
    iv_skew: (pe_iv - ce_iv) normalized to roughly -100..100
    underlying_trend_score: technical_score()['score'], -100..100
    """
    vol_w, iv_w, trend_w = weights
    score = volume_score * vol_w + iv_skew * iv_w + underlying_trend_score * trend_w
    if score >= 25:
        bias = "CALL"
    elif score <= -25:
        bias = "PUT"
    else:
        bias = "WAIT"
    return {
        "score": round(score, 2),
        "bias": bias,
        "volume_score": round(volume_score, 2),
        "iv_skew": round(iv_skew, 2),
        "underlying_trend_score": round(underlying_trend_score, 2),
        "weights": weights,
        "status": "Beta / formula pending confirmation",
    }


def regime_score(technical_score_value, momentum_score_value, option_score_value,
                  weights=(0.40, 0.35, 0.25)):
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
                     require_htf_agreement=True, htf_trend="NEUTRAL", epm=None):
    """
    Pure decision layer. Liveness/readiness checks (websocket connected,
    warmup elapsed, etc.) stay in the live engine since those depend on
    live process state -- this function only needs the three score dicts.
    epm: optional EPM score dict used as a confirming factor.
    """
    if not technical.get("ready"):
        return {"signal": "WAIT", "confidence": 0.0, "reason": "Technical history not ready", "epm": epm}

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
            "epm": epm,
        }

    regime = regime_score(technical["score"], momentum["score"], options["score"])
    technical_s, momentum_s, option_s = technical["score"], momentum["score"], options["score"]
    direction_score = technical_s * 0.40 + momentum_s * 0.35 + option_s * 0.25

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
        if abs(direction_score) >= 50:
            confidence += 15
        elif abs(direction_score) >= 35:
            confidence += 10
        else:
            confidence += 5

    # EPM confirming factor (treat as confirmation, not independent trigger)
    if epm and isinstance(epm, dict):
        epm_bias = epm.get("bias")
        if (epm_bias == "CALL" and options.get("bias") == "BULLISH") or \
           (epm_bias == "PUT" and options.get("bias") == "BEARISH"):
            confidence += 5

    confidence = min(100, confidence)

    if (bull_votes >= 2 and direction_score >= min_direction_score
            and confidence >= confidence_threshold):
        signal, reason = "BUY CALL", "Bullish multi-factor confirmation"
    elif (bear_votes >= 2 and direction_score <= -min_direction_score
          and confidence >= confidence_threshold):
        signal, reason = "BUY PUT", "Bearish multi-factor confirmation"
    else:
        signal, reason = "WAIT", f"Confidence {confidence:.0f}% < {confidence_threshold}% (direction: {direction_score:+.1f})"

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
        "epm": epm,
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
