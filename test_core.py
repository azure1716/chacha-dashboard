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
print("\n" + "=" * 50)
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for f in failures:
        print(" -", f)
else:
    print("ALL CHECKS PASSED")
