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

# ---------------------------------------------------------------
print("\n" + "=" * 50)
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for f in failures:
        print(" -", f)
else:
    print("ALL CHECKS PASSED")
