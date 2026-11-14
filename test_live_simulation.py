import os
import random
import time

import nifty_algo_live as live

random.seed(7)
failures = []


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
# 9. State snapshot verification
# ---------------------------------------------------------------
snapshot = live.get_state_snapshot()
check("get_state_snapshot returns valid dict", isinstance(snapshot, dict))
check("get_state_snapshot contains spot and atm", "spot" in snapshot and "atm" in snapshot)
check("get_state_snapshot contains epm dict", "epm" in snapshot and isinstance(snapshot["epm"], dict))
check("get_state_snapshot has candles list", isinstance(snapshot.get("candles"), list))
check("get_state_snapshot has strategy_profile", "strategy_profile" in snapshot and snapshot["strategy_profile"]["active"] == "BALANCED")

# ---------------------------------------------------------------
# 10. Strategy Profile switching and persistence tests
# ---------------------------------------------------------------
# 1. Switch to SCALP with no open position succeeds and persists
switch_res = live.set_strategy_profile("SCALP")
check("Switching to SCALP succeeds when no position open", switch_res["success"] is True)
check("ACTIVE_STRATEGY_PROFILE is updated to SCALP", live.ACTIVE_STRATEGY_PROFILE == "SCALP")
check("CONFIDENCE_THRESHOLD updated to 70", live.CONFIDENCE_THRESHOLD == 70)
check("MIN_ADX_FOR_TREND_SIGNAL updated to 16", live.MIN_ADX_FOR_TREND_SIGNAL == 16)
check("HTF_VETO_MODE updated to both_tf", live.HTF_VETO_MODE == "both_tf")
check("ATR_SL_MULTIPLIER updated to 1.0", live.ATR_SL_MULTIPLIER == 1.0)
check("ATR_TARGET_MULTIPLIER updated to 2.0", live.ATR_TARGET_MULTIPLIER == 2.0)
check("TRAIL_ACTIVATE_R updated to 0.8", live.TRAIL_ACTIVATE_R == 0.8)
check("TRAIL_DISTANCE_R updated to 0.6", live.TRAIL_DISTANCE_R == 0.6)
check("MAX_TRADES_PER_DAY updated to 8", live.MAX_TRADES_PER_DAY == 8)
check("IV_PERCENTILE_MAX updated to 75", live.IV_PERCENTILE_MAX == 75)
check("MAX_SPREAD_PCT updated to 3.5", live.MAX_SPREAD_PCT == 3.5)
check("VWAP_STRETCH_ATR updated to 2.5", live.VWAP_STRETCH_ATR == 2.5)

# Verify choice is persisted to .env
root_env_path = os.path.join(os.path.dirname(os.path.abspath(live.__file__)), ".env")
env_content = ""
if os.path.exists(root_env_path):
    with open(root_env_path, "r", encoding="utf-8") as f:
        env_content = f.read()
check("STRATEGY_PROFILE=SCALP persisted in .env", "STRATEGY_PROFILE=SCALP" in env_content)

# 2. Switching while paper_trade is open is REJECTED
live.paper_trade = {"signal": "BUY CALL", "strike": 24500.0, "lots": 2, "entry": 100.0}
rej_res = live.set_strategy_profile("BALANCED")
check("Switching while paper_trade is open is rejected", rej_res["success"] is False)
check("Rejection reason contains open position details",
      "Cannot switch profile with an open position (BUY CALL 24500.0)" in rej_res.get("reason", ""))
print("    Rejection message:", rej_res.get("reason"))
check("Profile remains SCALP after rejection", live.ACTIVE_STRATEGY_PROFILE == "SCALP")
live.paper_trade = None  # clean up

# 3. signals_log.csv rows after a switch carry the new profile name
sig_scalp = live.generate_signal(spot=far_spot)
check("generate_signal result contains strategy_profile='SCALP'", sig_scalp.get("strategy_profile") == "SCALP")

import csv
with open(live.SIGNALS_LOG_PATH, "r", encoding="utf-8") as f:
    sig_rows = list(csv.DictReader(f))
check("Last signals_log.csv row has strategy_profile='SCALP'",
      len(sig_rows) > 0 and sig_rows[-1].get("strategy_profile") == "SCALP")

# 4. Old-format CSV rows without the strategy_profile column still parse
from backend.app.api.signals import get_signals_log
from backend.app.api.trades import _read_trades_rows

# Create a temporary legacy CSV without strategy_profile column
legacy_sig_path = "legacy_signals_test.csv"
legacy_headers = ["timestamp", "spot", "signal", "confidence", "reason",
                  "technical_score", "trend", "trend_strength", "adx",
                  "momentum_score", "option_score", "option_bias",
                  "htf_trend", "atr_pct", "epm_score", "epm_bias"]
with open(legacy_sig_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=legacy_headers)
    writer.writeheader()
    writer.writerow({
        "timestamp": "2026-11-14 10:00:00",
        "spot": "24300.0",
        "signal": "BUY CALL",
        "confidence": "85.0",
        "reason": "Legacy signal test",
    })

saved_sig_path = live.SIGNALS_LOG_PATH
live.SIGNALS_LOG_PATH = legacy_sig_path
try:
    parsed_res = get_signals_log()
    items = parsed_res.get("items", [])
    check("Legacy signal row without strategy_profile defaults to BALANCED",
          len(items) > 0 and items[0].get("strategy_profile") == "BALANCED")
finally:
    live.SIGNALS_LOG_PATH = saved_sig_path
    if os.path.exists(legacy_sig_path):
        os.remove(legacy_sig_path)

# Create a temporary legacy trades CSV without strategy_profile column
legacy_trade_path = "legacy_trades_test.csv"
legacy_trade_headers = ["entry_time", "exit_time", "signal", "direction", "strike", "type", "lots",
                        "entry", "exit", "sl", "target", "atr_used", "option_delta", "confidence",
                        "iv_percentile_at_entry", "gross_pnl", "cost", "net_pnl", "exit_reason",
                        "used_ltp_fallback_entry", "used_ltp_fallback_exit"]
with open(legacy_trade_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=legacy_trade_headers)
    writer.writeheader()
    writer.writerow({
        "entry_time": "10:00:00",
        "exit_time": "10:05:00",
        "signal": "BUY CALL",
        "direction": "CALL",
        "strike": "24300.0",
        "net_pnl": "500.0",
    })

saved_trade_path = live.TRADES_LOG_PATH
live.TRADES_LOG_PATH = legacy_trade_path
try:
    parsed_trades = _read_trades_rows()
    check("Legacy trade row without strategy_profile defaults to BALANCED",
          len(parsed_trades) > 0 and parsed_trades[0].get("strategy_profile") == "BALANCED")
finally:
    live.TRADES_LOG_PATH = saved_trade_path
    if os.path.exists(legacy_trade_path):
        os.remove(legacy_trade_path)

# ---------------------------------------------------------------
# 11. Differential behavior verification (BALANCED vs SCALP)
# ---------------------------------------------------------------
# Verify that switching back to BALANCED restores Balanced parameters
live.set_strategy_profile("BALANCED")
check("Switching back to BALANCED sets ACTIVE_STRATEGY_PROFILE to BALANCED", live.ACTIVE_STRATEGY_PROFILE == "BALANCED")
check("Restored CONFIDENCE_THRESHOLD to 65", live.CONFIDENCE_THRESHOLD == 65)
check("Restored MIN_ADX_FOR_TREND_SIGNAL to 18", live.MIN_ADX_FOR_TREND_SIGNAL == 18)
check("Restored HTF_VETO_MODE to single_tf", live.HTF_VETO_MODE == "single_tf")
check("Restored ATR_SL_MULTIPLIER to 1.2", live.ATR_SL_MULTIPLIER == 1.2)
check("Restored ATR_TARGET_MULTIPLIER to 2.4", live.ATR_TARGET_MULTIPLIER == 2.4)
check("Restored TRAIL_ACTIVATE_R to 1.0", live.TRAIL_ACTIVATE_R == 1.0)
check("Restored TRAIL_DISTANCE_R to 0.8", live.TRAIL_DISTANCE_R == 0.8)
check("Restored MAX_TRADES_PER_DAY to 6", live.MAX_TRADES_PER_DAY == 6)
check("Restored IV_PERCENTILE_MAX to 80", live.IV_PERCENTILE_MAX == 80)
check("Restored MAX_SPREAD_PCT to None", live.MAX_SPREAD_PCT is None)
check("Restored VWAP_STRETCH_ATR to None", live.VWAP_STRETCH_ATR is None)

# ---------------------------------------------------------------
print("\n" + "=" * 50)
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for f in failures:
        print(" -", f)
else:
    print("ALL CHECKS PASSED")
