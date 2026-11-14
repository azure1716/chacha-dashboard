import random
import math
import nifty_algo_core as core

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
# 11. EPM score placeholder test
# ---------------------------------------------------------------
epm_bull = core.epm_score(volume_score=60.0, iv_skew=30.0, underlying_trend_score=80.0)
print("    epm_score (bullish):", epm_bull["score"], epm_bull["bias"])
check("epm_score returns CALL bias when positive", epm_bull["bias"] == "CALL")

epm_bear = core.epm_score(volume_score=-60.0, iv_skew=-30.0, underlying_trend_score=-80.0)
print("    epm_score (bearish):", epm_bear["score"], epm_bear["bias"])
check("epm_score returns PUT bias when negative", epm_bear["bias"] == "PUT")

epm_neutral = core.epm_score(volume_score=5.0, iv_skew=-5.0, underlying_trend_score=0.0)
check("epm_score returns WAIT bias when neutral", epm_neutral["bias"] == "WAIT")

# Verify signal_decision with EPM confirmation bumps confidence
sd_with_epm = core.signal_decision(ts, ms, ops, htf_trend="BULLISH", epm=epm_bull)
check("signal_decision includes epm and bumps confidence on confirmation", sd_with_epm["confidence"] >= sd["confidence"])

# ---------------------------------------------------------------
# 12. VWAP calculation & VWAP-stretch filter
# ---------------------------------------------------------------
vwap_flat = core.calculate_vwap([100.0] * 10, [100.0] * 10, [100.0] * 10, [500.0] * 10)
check("calculate_vwap on flat series == 100", math.isclose(vwap_flat, 100.0, abs_tol=1e-6))

# Hand-built synthetic series:
# Bar 1: H=10, L=10, C=10 (TP=10), Vol=100 -> TP*V = 1000
# Bar 2: H=20, L=20, C=20 (TP=20), Vol=300 -> TP*V = 6000
# Total TP*V = 7000, Total Vol = 400. VWAP = 7000 / 400 = 17.5
synth_h = [10.0, 20.0]
synth_l = [10.0, 20.0]
synth_c = [10.0, 20.0]
synth_v = [100.0, 300.0]
vwap_synth = core.calculate_vwap(synth_h, synth_l, synth_c, synth_v)
print("    calculate_vwap on synthetic 2-bar series:", vwap_synth)
check("calculate_vwap on synthetic series == 17.5", math.isclose(vwap_synth, 17.5, abs_tol=1e-6))

# Edge cases
check("calculate_vwap returns None on empty series", core.calculate_vwap([], [], [], []) is None)
check("calculate_vwap returns None on zero volume", core.calculate_vwap([10.0], [10.0], [10.0], [0.0]) is None)

# VWAP stretch check
stretched_no, diff_no = core.check_vwap_stretch(spot=24000.0, vwap=24000.0, atr=10.0, vwap_stretch_atr=2.5)
check("check_vwap_stretch returns False when within threshold", stretched_no is False)
stretched_yes, diff_yes = core.check_vwap_stretch(spot=24030.0, vwap=24000.0, atr=10.0, vwap_stretch_atr=2.5)
check("check_vwap_stretch returns True when diff (30) > 2.5 * ATR (25)", stretched_yes is True)

# ---------------------------------------------------------------
# 13. Spread cap check
# ---------------------------------------------------------------
check("is_spread_acceptable passes tight spread (3.0% <= 3.5%)",
      core.is_spread_acceptable(bid=100.0, ask=103.0, ltp=100.0, spread_pct_max=3.5) is True)
check("is_spread_acceptable blocks wide spread (4.0% > 3.5%)",
      core.is_spread_acceptable(bid=100.0, ask=104.0, ltp=100.0, spread_pct_max=3.5) is False)
check("is_spread_acceptable passes any spread when spread_pct_max is None",
      core.is_spread_acceptable(bid=100.0, ask=110.0, ltp=100.0, spread_pct_max=None) is True)

# ---------------------------------------------------------------
# 14. Trading window & lunch exclusion pure function
# ---------------------------------------------------------------
# Balanced: 09:25 to 14:50 (565 to 890 min), no lunch
ok_bal_pre, _ = core.is_within_trade_window(560, 565, 890) # 09:20
check("Balanced window blocks before 09:25", ok_bal_pre is False)
ok_bal_lunch, _ = core.is_within_trade_window(720, 565, 890) # 12:00
check("Balanced window allows 12:00 (no lunch gap)", ok_bal_lunch is True)
ok_bal_post, _ = core.is_within_trade_window(895, 565, 890) # 14:55
check("Balanced window blocks after 14:50", ok_bal_post is False)

# Scalp: 09:20 to 14:45 (560 to 885 min), lunch 11:30 to 13:30 (690 to 810 min)
ok_scalp_early, _ = core.is_within_trade_window(562, 560, 885, 690, 810) # 09:22
check("Scalp window allows 09:22 entry", ok_scalp_early is True)
ok_scalp_lunch, reason_lunch = core.is_within_trade_window(720, 560, 885, 690, 810) # 12:00
check("Scalp window blocks during lunch exclusion (12:00)", ok_scalp_lunch is False)
print("    Scalp lunch exclusion reason:", reason_lunch)
ok_scalp_afternoon, _ = core.is_within_trade_window(820, 560, 885, 690, 810) # 13:40
check("Scalp window allows after lunch (13:40)", ok_scalp_afternoon is True)
ok_scalp_late, _ = core.is_within_trade_window(886, 560, 885, 690, 810) # 14:46
check("Scalp window blocks after 14:45", ok_scalp_late is False)

# ---------------------------------------------------------------
# 15. Strategy Profile HTF Veto: Balanced (single 5m) vs Scalp (dual 3m+5m)
# ---------------------------------------------------------------
# Setup where technical, momentum, options scores produce a BUY CALL:
# Case 1: 5-min HTF trend is BEARISH, but 3-min HTF trend is BULLISH.
sd_bal = core.signal_decision(
    ts, ms, ops,
    confidence_threshold=65,
    min_adx_for_trend_signal=18,
    require_htf_agreement=True,
    htf_trend="BEARISH",
    htf_trend_3m="BULLISH",
    htf_veto_mode="single_tf",
)
check("Balanced profile blocks BUY CALL when 5m is BEARISH alone",
      sd_bal["signal"] == "WAIT" and "higher-timeframe (5-min) trend" in sd_bal["reason"])
print("    Balanced veto reason:", sd_bal["reason"])

sd_scalp = core.signal_decision(
    ts, ms, ops,
    confidence_threshold=70,
    min_adx_for_trend_signal=16,
    require_htf_agreement=True,
    htf_trend="BEARISH",
    htf_trend_3m="BULLISH",
    htf_veto_mode="both_tf",
)
check("Scalp profile allows BUY CALL when 5m is BEARISH but 3m is BULLISH (both don't oppose)",
      sd_scalp["signal"] == "BUY CALL")
print("    Scalp signal on relaxed HTF:", sd_scalp["signal"], sd_scalp["reason"])

# Case 2: BOTH 5-min and 3-min HTF trends are BEARISH
sd_scalp_both = core.signal_decision(
    ts, ms, ops,
    confidence_threshold=70,
    min_adx_for_trend_signal=16,
    require_htf_agreement=True,
    htf_trend="BEARISH",
    htf_trend_3m="BEARISH",
    htf_veto_mode="both_tf",
)
check("Scalp profile blocks BUY CALL when BOTH 3m and 5m are BEARISH",
      sd_scalp_both["signal"] == "WAIT" and "both higher-timeframe" in sd_scalp_both["reason"])
print("    Scalp dual-HTF veto reason:", sd_scalp_both["reason"])

# Case 3: 3-min higher_timeframe_trend check
htf_3m = core.higher_timeframe_trend(htf_trend_high, htf_trend_low, htf_trend_close, factor=3)
check("3-min higher_timeframe_trend runs with factor=3 and reads BULLISH on uptrend", htf_3m == "BULLISH")

# ---------------------------------------------------------------
print("\n" + "=" * 50)
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for f in failures:
        print(" -", f)
else:
    print("ALL CHECKS PASSED")
