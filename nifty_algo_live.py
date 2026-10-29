# ============================================================
# V48 - LIVE / PAPER-TRADING ENGINE
# Builds on V47.2's plumbing (WebSocket handling, candle
# reconstruction, gap detection, reconnection) which was solid.
# ============================================================
# WHAT CHANGED VS V47.2 (see the accompanying writeup for why):
#
#  1. Indicator/signal math moved to nifty_algo_core.py as pure
#     functions -> the exact same code can be backtested
#     (see nifty_algo_backtest.py) instead of only ever running live.
#  2. Added ADX trend-strength filter (chop protection) and a
#     5-minute higher-timeframe agreement filter, both computed
#     from the SAME 1-min history you already collect.
#  3. Option stop/target now delta-adjusted (uses the option's own
#     streamed delta) instead of a flat spot_atr * 0.55 guess.
#  4. Added an IV-percentile filter: skip entries when the chosen
#     option's IV is near the top of its own recent range.
#  5. Paper-trade entry/exit now price off ask/bid (falls back to
#     LTP with a flag) instead of always using LTP.
#  6. Added an approximate Indian-retail cost model subtracted from
#     paper P&L (brokerage/STT/exchange/SEBI/stamp-duty/GST) -- see
#     nifty_algo_core.DEFAULT_COST_MODEL, rates are placeholders,
#     VERIFY against your current Upstox contract note.
#  7. Added a real risk-management layer: daily max-loss circuit
#     breaker, optional daily profit lock, max trades/day,
#     consecutive-loss cooldown, and capital-based position sizing
#     (lots, not a single implicit unit). V47.2 had none of this.
#  8. Strikes are now periodically re-centered on ATM as spot moves
#     (V47.2 selected strikes once at startup and never revisited).
#  9. Removed the duplicated OI/volume delta-tracking system
#     (V47.2 had both an inline tracker AND a separate "V31" tracker
#     whose output silently overrode the first one -- dead code).
# 10. Every generated signal and every closed trade is appended to
#     a CSV so you can actually build the backtest/analysis loop
#     this strategy needs before real money touches it.
# 11. ATR low-volatility filter now uses ATR as a % of spot instead
#     of a fixed point value, so it doesn't quietly stop making
#     sense if NIFTY's price level moves a lot over time.
# 12. `import upstox_client` is now deferred into main() so the rest
#     of this file -- all the actual decision logic -- can be
#     imported and unit-tested without the broker SDK installed.
#
# WHAT DID NOT CHANGE (deliberately):
#  - REAL_ORDER stays False. Real order placement is NOT implemented
#    here -- see place_real_order() below for why, and what needs to
#    happen before it should be.
#  - This is still fundamentally a rule-based heuristic combining
#    trend/momentum/option-pressure signals, not a statistically
#    validated model. Nothing in this file substitutes for the
#    backtest in nifty_algo_backtest.py -- run that first.
# ============================================================

import csv
import os
import threading
import time
import traceback
from collections import deque

import requests

import nifty_algo_core as core

# ============================================================
# CONFIG
# ============================================================

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ACCESS_TOKEN = os.environ.get("UPSTOX_ACCESS_TOKEN", "")

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

CONFIDENCE_THRESHOLD = int(os.environ.get("CONFIDENCE_THRESHOLD", "65"))
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
                              # ⚠ VERIFY current lot size before using this
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

HEADERS = {
    "Authorization": "Bearer " + ACCESS_TOKEN,
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def set_access_token(new_token: str) -> None:
    """Updates access token in-memory, in default API headers, and os.environ."""
    global ACCESS_TOKEN, HEADERS
    ACCESS_TOKEN = (new_token or "").strip()
    HEADERS["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    os.environ["UPSTOX_ACCESS_TOKEN"] = ACCESS_TOKEN


def verify_upstox_token(token: str) -> dict:
    """
    Validates token with Upstox API v2 /user/profile.
    Returns dict with {valid: bool, user_name: str, user_id: str, error: str}.
    """
    cleaned = (token or "").strip()
    if not cleaned or len(cleaned) < 8:
        return {"valid": False, "error": "Token is empty or too short."}
    url = "https://api.upstox.com/v2/user/profile"
    headers = {
        "Authorization": f"Bearer {cleaned}",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return {
                "valid": True,
                "user_name": data.get("user_name", "Authorized Upstox User"),
                "user_id": data.get("user_id", ""),
                "email": data.get("email", ""),
                "broker": "Upstox",
            }
        else:
            err_msg = f"HTTP {resp.status_code}"
            try:
                err_json = resp.json()
                errs = err_json.get("errors", [])
                if errs and isinstance(errs, list) and "message" in errs[0]:
                    err_msg += f": {errs[0]['message']}"
            except Exception:
                pass
            return {"valid": False, "error": err_msg}
    except requests.exceptions.RequestException as e:
        return {"valid": False, "error": f"Connection error: {str(e)}"}

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


recent_exceptions = deque(maxlen=50)


def log_exception(label, e):
    safe_print(f"{label}:", e)
    tb = traceback.format_exc()[-1200:]
    safe_print(tb)
    recent_exceptions.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "label": str(label),
        "error": str(e),
        "traceback": tb,
    })


def get_recent_exceptions():
    return list(recent_exceptions)


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


def get_ist_now():
    """Returns current datetime in Indian Standard Time (UTC+5:30) regardless of host system timezone."""
    import datetime
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(ist_tz)


def today_string():
    return get_ist_now().strftime("%Y-%m-%d")


def timestamp_minute(ts=None):
    if ts is None:
        ts = time.time()
    return int(ts // 60)


def nse_market_open_now():
    try:
        now_ist = get_ist_now()
        if now_ist.weekday() >= 5:
            return False
        minutes = now_ist.hour * 60 + now_ist.minute
        return 9 * 60 + 15 <= minutes < 15 * 60 + 30
    except Exception:
        return False


def is_trade_time():
    try:
        now_ist = get_ist_now()
        if now_ist.weekday() >= 5:
            return False
        minutes = now_ist.hour * 60 + now_ist.minute
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


def candle_epoch_seconds(value):
    """
    Converts any timestamp format (ISO string, epoch ms, epoch sec, or epoch minute)
    into standard Unix epoch seconds (integer) for lightweight-charts.
    """
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            x = float(value)
            if x > 10000000000:
                return int(x / 1000)
            if x < 100000000:
                return int(x * 60)
            return int(x)
        s = str(value).strip()
        if "T" in s:
            from datetime import datetime
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return int(dt.timestamp())
        x = float(s)
        if x > 10000000000:
            return int(x / 1000)
        if x < 100000000:
            return int(x * 60)
        return int(x)
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
    import datetime
    now_ist = get_ist_now()
    to_date = now_ist.strftime("%Y-%m-%d")
    from_date = (now_ist - datetime.timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
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
        if streamer is not None:
            streamer.connect()
            safe_print("WS CONNECT CALL RETURNED")
    except Exception as e:
        ws_last_error = str(e)
        log_exception("WS CONNECT THREAD ERROR", e)


def update_options_quotes_rest():
    """Fetches quotes for selected option strikes via REST when WebSocket is inactive or in fallback."""
    global selected_strikes
    if not selected_strikes:
        return
    keys = [s["key"] for s in selected_strikes if s.get("key")]
    if not keys:
        return
    url = "https://api.upstox.com/v3/market-quote/quotes"
    try:
        chunk = ",".join(keys[:100])
        r = requests.get(url, headers=HEADERS, params={"instrument_key": chunk}, timeout=8)
        if r.status_code == 200:
            data = r.json().get("data", {})
            for key, quote in data.items():
                if not isinstance(quote, dict):
                    continue
                norm_key = key.replace(":", "|")
                with data_lock:
                    old = live_data.get(norm_key, {}).copy()
                    ltp = num(quote.get("last_price", quote.get("ltp")))
                    if ltp > 0:
                        old["ltp"] = ltp
                    cp = num(quote.get("prev_close_price", quote.get("cp")))
                    if cp > 0:
                        old["cp"] = cp
                    vol = integer(quote.get("volume"))
                    if vol > 0:
                        old["volume"] = vol
                    oi = integer(quote.get("oi"))
                    if oi > 0:
                        old["oi"] = oi
                    depth = quote.get("depth", {})
                    if isinstance(depth, dict):
                        bids = depth.get("buy", [])
                        asks = depth.get("sell", [])
                        if bids and isinstance(bids, list) and isinstance(bids[0], dict):
                            old["bid"] = num(bids[0].get("price"))
                            old["bid_qty"] = integer(bids[0].get("quantity"))
                        if asks and isinstance(asks, list) and isinstance(asks[0], dict):
                            old["ask"] = num(asks[0].get("price"))
                            old["ask_qty"] = integer(asks[0].get("quantity"))
                    live_data[norm_key] = old
                    live_data[key] = old
    except Exception as e:
        log_exception("OPTION REST QUOTES ERROR", e)


def rest_loop():
    global selected_expiry, full_chain, selected_strikes, last_atm_used
    while running:
        try:
            # 1. Discover expiry / chain if not yet loaded
            if not selected_expiry:
                selected_expiry = get_expiry()
            if selected_expiry and not full_chain:
                full_chain = get_option_chain(selected_expiry)

            # 2. Query spot NIFTY quote
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

                # Form candles via REST ticks if WebSocket ticks are not active
                if not ws_connected or candle_status in ("WAITING", "GAP DETECTED"):
                    update_live_candle(data["ltp"], volume=data.get("volume"))

                # Initialize strikes if chain exists and strikes are empty
                if not selected_strikes and full_chain:
                    atm = get_atm(data["ltp"])
                    last_atm_used = atm
                    selected_strikes = select_options(full_chain, atm)

            # 3. If WebSocket is not connected or streaming, fetch option quotes via REST
            if not ws_connected and selected_strikes:
                update_options_quotes_rest()

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
    return core.technical_score(series["closes"], series["highs"], series["lows"],
                                 ema_fast=EMA_FAST, ema_slow=EMA_SLOW,
                                 rsi_length=RSI_LENGTH, atr_length=ATR_LENGTH,
                                 adx_length=ADX_LENGTH, min_adx=MIN_ADX_FOR_TREND_SIGNAL)


def compute_momentum():
    series = get_indicator_series()
    return core.momentum_score(series["closes"], rsi_length=RSI_LENGTH)


def compute_htf_trend():
    series = get_indicator_series()
    return core.higher_timeframe_trend(series["highs"], series["lows"], series["closes"],
                                        factor=HTF_FACTOR, ema_fast=EMA_FAST, ema_slow=EMA_SLOW)


def compute_option_pressure():
    """
    Aggregates CE/PE totals across selected_strikes, then delegates the
    scoring math to core.option_pressure_score(). This is the ONE OI/price
    delta tracker (option_prev_tick / option_session_baseline) -- V47.2
    had two of these (an inline one and a separate "V31" one) and only
    ever returned the second, leaving the first as dead code.
    """
    ce_oi = pe_oi = ce_volume = pe_volume = 0
    ce_buy = pe_buy = ce_sell = pe_sell = 0
    ce_price_change = pe_price_change = 0.0
    ce_ivs = []
    pe_ivs = []
    live_count = 0

    with data_lock:
        snapshot = [(item, live_data.get(item["key"], {}).copy()) for item in selected_strikes]

    for item, data in snapshot:
        key = item["key"]; typ = item["type"]
        ltp = num(data.get("ltp")); oi = integer(data.get("oi"))
        volume = integer(data.get("volume"))
        buy_qty = integer(data.get("buy_qty")); sell_qty = integer(data.get("sell_qty"))
        iv = num(data.get("iv"))
        if ltp > 0:
            live_count += 1
        if iv > 0:
            if typ == "CE":
                ce_ivs.append(iv)
            else:
                pe_ivs.append(iv)

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

    result = core.option_pressure_score(ce_oi, pe_oi, ce_volume, pe_volume,
                                         ce_buy, pe_buy, ce_sell, pe_sell,
                                         ce_price_change, pe_price_change)
    avg_ce_iv = (sum(ce_ivs) / len(ce_ivs)) if ce_ivs else 0.0
    avg_pe_iv = (sum(pe_ivs) / len(pe_ivs)) if pe_ivs else 0.0
    # Normalized IV skew (-100 to 100)
    iv_skew = max(-100.0, min(100.0, (avg_pe_iv - avg_ce_iv) * 10.0))
    result["iv_skew"] = round(iv_skew, 2)
    result["avg_ce_iv"] = round(avg_ce_iv, 2)
    result["avg_pe_iv"] = round(avg_pe_iv, 2)
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
    global last_signal_audit
    ready, readiness_reason = live_signal_ready()
    if not ready:
        tech = compute_technical()
        mom = compute_momentum()
        opts = compute_option_pressure()
        htf = compute_htf_trend()
        epm = core.epm_score(
            volume_score=opts.get("volume_score", 0.0),
            iv_skew=opts.get("iv_skew", 0.0),
            underlying_trend_score=tech.get("score", 0.0),
        )
        result = {
            "signal": "WAIT", "confidence": 0.0, "reason": readiness_reason,
            "technical": tech, "momentum": mom,
            "options": opts, "htf_trend": htf,
            "epm": epm,
        }
        last_signal_audit = {
            "signal": result["signal"], "confidence": 0.0,
            "reason": result.get("reason", ""), "timestamp": time.strftime("%H:%M:%S"),
            "epm": epm,
        }
        log_signal_to_csv(result, spot)
        return result

    technical = compute_technical()
    momentum = compute_momentum()
    options = compute_option_pressure()
    htf_trend = compute_htf_trend()
    epm = core.epm_score(
        volume_score=options.get("volume_score", 0.0),
        iv_skew=options.get("iv_skew", 0.0),
        underlying_trend_score=technical.get("score", 0.0),
    )

    if not technical.get("ready"):
        result = {
            "signal": "WAIT", "confidence": 0.0, "reason": "Technical history not ready",
            "technical": technical, "momentum": momentum, "options": options, "htf_trend": htf_trend,
            "epm": epm,
        }
        last_signal_audit = {
            "signal": result["signal"], "confidence": 0.0,
            "reason": result.get("reason", ""), "timestamp": time.strftime("%H:%M:%S"),
            "epm": epm,
        }
        log_signal_to_csv(result, spot)
        return result

    atr_pct = technical.get("atr_pct")
    if atr_pct is not None and atr_pct < ATR_PCT_MIN:
        result = {
            "signal": "WAIT", "confidence": 0.0,
            "reason": f"Low volatility filter (ATR {atr_pct:.4f}% of spot < {ATR_PCT_MIN}%)",
            "technical": technical, "momentum": momentum, "options": options, "htf_trend": htf_trend,
            "epm": epm,
        }
        last_signal_audit = {
            "signal": result["signal"], "confidence": 0.0,
            "reason": result.get("reason", ""), "timestamp": time.strftime("%H:%M:%S"),
            "epm": epm,
        }
        log_signal_to_csv(result, spot)
        return result

    decision = core.signal_decision(
        technical, momentum, options,
        min_direction_score=MIN_DIRECTION_SCORE,
        confidence_threshold=CONFIDENCE_THRESHOLD,
        min_adx_for_trend_signal=MIN_ADX_FOR_TREND_SIGNAL,
        require_htf_agreement=REQUIRE_HTF_AGREEMENT,
        htf_trend=htf_trend,
        epm=epm,
    )
    result = dict(decision)
    result.update({
        "technical": technical, "momentum": momentum,
        "options": options, "htf_trend": htf_trend,
        "epm": epm,
    })

    last_signal_audit = {
        "signal": result["signal"], "confidence": result.get("confidence", 0.0),
        "reason": result.get("reason", ""), "timestamp": time.strftime("%H:%M:%S"),
        "epm": epm,
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
                  "htf_trend", "atr_pct", "epm_score", "epm_bias"]


def log_signal_to_csv(result, spot):
    technical = result.get("technical", {}) or {}
    momentum = result.get("momentum", {}) or {}
    options = result.get("options", {}) or {}
    epm = result.get("epm", {}) or {}
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
        "epm_score": epm.get("score") if isinstance(epm, dict) else None,
        "epm_bias": epm.get("bias") if isinstance(epm, dict) else None,
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

    allowed, reason = core.should_trade_now(
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
    iv_pct = core.iv_percentile(iv_now, hist)
    if iv_pct is not None and iv_pct > IV_PERCENTILE_MAX:
        return None, f"Skipped: option IV percentile {iv_pct:.0f} > {IV_PERCENTILE_MAX} (premium looks rich right now)"

    atr = technical.get("atr")
    if atr is None or atr <= 0:
        atr = 8.0
    option_delta = num(data.get("delta"))
    stop_target = core.delta_adjusted_option_stop_target(
        atr, option_delta, sl_multiplier=ATR_SL_MULTIPLIER, target_multiplier=ATR_TARGET_MULTIPLIER,
    )
    sl = entry_price - stop_target["sl_distance"]
    target = entry_price + stop_target["target_distance"]
    if sl <= 0:
        sl = entry_price * 0.85

    lots = core.position_size(CAPITAL, RISK_PER_TRADE_PCT, entry_price, sl, LOT_SIZE, MAX_LOTS_PER_TRADE)
    if lots <= 0:
        if not REAL_ORDER:
            lots = 1
        else:
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
    cost, cost_breakdown = core.estimate_option_trade_cost(paper_trade["entry"], exit_price, LOT_SIZE, lots)
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


def get_state_snapshot():
    """
    Returns a plain dict snapshot mirroring what display() prints and what
    the API/WebSocket needs: spot, ATM, signal, confidence, reason,
    technical/momentum/option/HTF/EPM scores, candle status, ws status,
    risk state, open paper position, paper stats, recent candles.
    """
    with data_lock:
        nifty = live_data.get(NIFTY_KEY, {}).copy()
        forming = current_candle.copy()
        pt_copy = dict(paper_trade) if paper_trade else None
        stats_copy = dict(paper_trade_stats)
        closes_copy = list(close_history)[-300:]
        highs_copy = list(high_history)[-300:]
        lows_copy = list(low_history)[-300:]
        opens_copy = list(open_history)[-300:]
        times_copy = list(candle_time)[-300:]
        volumes_copy = list(volume_history)[-300:]
        last_sig = dict(last_signal_audit) if last_signal_audit else {}
        ws_conn = ws_connected
        ws_sub = ws_subscribed
        c_status = candle_status
        hist_last_min = historical_last_minute
        curr_daily_pnl = daily_pnl
        curr_trades_today = trades_today
        curr_consec_losses = consecutive_losses
        curr_cooldown = cooldown_until
        atm_used = last_atm_used

    spot = num(nifty.get("ltp"))
    quality = data_quality()
    technical = compute_technical()
    momentum = compute_momentum()
    options = compute_option_pressure()
    htf = compute_htf_trend()
    epm = core.epm_score(
        volume_score=options.get("volume_score", 0.0),
        iv_skew=options.get("iv_skew", 0.0),
        underlying_trend_score=technical.get("score", 0.0),
    )

    if last_sig:
        signal_name = last_sig.get("signal") or "WAIT"
        confidence = last_sig.get("confidence", 0.0)
        reason = last_sig.get("reason") or ("Waiting for engine tick" if spot > 0 else "No spot price")
    else:
        live_dec = core.signal_decision(
            technical, momentum, options,
            min_direction_score=MIN_DIRECTION_SCORE,
            confidence_threshold=CONFIDENCE_THRESHOLD,
            min_adx_for_trend_signal=MIN_ADX_FOR_TREND_SIGNAL,
            require_htf_agreement=REQUIRE_HTF_AGREEMENT,
            htf_trend=htf,
            epm=epm,
        )
        signal_name = live_dec.get("signal", "WAIT")
        confidence = live_dec.get("confidence", 0.0)
        reason = live_dec.get("reason") or ("Waiting for engine tick" if spot > 0 else "No spot price")

    # If open paper trade exists, calculate live unrealized P&L
    open_position = None
    if pt_copy:
        opt_key = pt_copy.get("key")
        with data_lock:
            opt_data = live_data.get(opt_key, {}).copy()
        current_ltp = num(opt_data.get("ltp"), default=pt_copy["entry"])
        current_bid = num(opt_data.get("bid"), default=current_ltp)
        current_ask = num(opt_data.get("ask"), default=current_ltp)
        exit_est_price = current_bid if current_bid > 0 else current_ltp
        gross_pnl = (exit_est_price - pt_copy["entry"]) * pt_copy["lots"] * LOT_SIZE
        cost_est, _ = core.estimate_option_trade_cost(pt_copy["entry"], exit_est_price, LOT_SIZE, pt_copy["lots"])
        net_pnl = gross_pnl - cost_est
        open_position = {
            **pt_copy,
            "current_ltp": current_ltp,
            "current_bid": current_bid,
            "current_ask": current_ask,
            "unrealized_gross_pnl": round(gross_pnl, 2),
            "unrealized_cost": round(cost_est, 2),
            "unrealized_net_pnl": round(net_pnl, 2),
        }

    # Format candles for lightweight-charts (guarantee unix seconds)
    candles_list = []
    base_fallback_time = int(time.time() - len(closes_copy) * 60)
    for idx in range(len(closes_copy)):
        sub_c = closes_copy[: idx + 1]
        e20 = core.calculate_ema(sub_c, EMA_FAST)
        e50 = core.calculate_ema(sub_c, EMA_SLOW)
        t_raw = times_copy[idx] if idx < len(times_copy) else (base_fallback_time + idx * 60)
        t_sec = candle_epoch_seconds(t_raw) or (base_fallback_time + idx * 60)
        candles_list.append({
            "time": t_sec,
            "open": round(opens_copy[idx], 2) if idx < len(opens_copy) else round(closes_copy[idx], 2),
            "high": round(highs_copy[idx], 2) if idx < len(highs_copy) else round(closes_copy[idx], 2),
            "low": round(lows_copy[idx], 2) if idx < len(lows_copy) else round(closes_copy[idx], 2),
            "close": round(closes_copy[idx], 2),
            "volume": volumes_copy[idx] if idx < len(volumes_copy) else 0,
            "ema20": round(e20, 2) if e20 is not None else None,
            "ema50": round(e50, 2) if e50 is not None else None,
        })

    now_sec = time.time()
    cooldown_active = bool(curr_cooldown and now_sec < curr_cooldown)
    cooldown_rem = max(0, int(curr_cooldown - now_sec)) if cooldown_active else 0

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S") + " IST",
        "timestamp_epoch": now_sec,
        "market_session": "OPEN" if nse_market_open_now() else "CLOSED",
        "trade_window": "YES" if is_trade_time() else "NO",
        "ws_subscribed": ws_sub,
        "ws_connected": ws_conn,
        "spot": round(spot, 2),
        "atm": atm_used,
        "data_quality": quality,
        "candle_status": c_status,
        "historical_last_minute": hist_last_min,
        "candles": candles_list,
        "technical": technical,
        "momentum": momentum,
        "options": options,
        "htf_trend": htf,
        "epm": epm,
        "signal": signal_name,
        "confidence": round(confidence, 1),
        "reason": reason,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "weights": {
            "technical": 0.40,
            "momentum": 0.25,
            "options": 0.35,
        },
        "risk_state": {
            "daily_pnl": round(curr_daily_pnl, 2),
            "max_daily_loss": MAX_DAILY_LOSS,
            "daily_profit_lock": DAILY_PROFIT_LOCK,
            "trades_today": curr_trades_today,
            "max_trades_per_day": MAX_TRADES_PER_DAY,
            "consecutive_losses": curr_consec_losses,
            "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES,
            "cooldown_active": cooldown_active,
            "cooldown_until": curr_cooldown,
            "cooldown_remaining_seconds": cooldown_rem,
            "capital": CAPITAL,
            "risk_per_trade_pct": RISK_PER_TRADE_PCT,
            "lot_size": LOT_SIZE,
            "max_lots_per_trade": MAX_LOTS_PER_TRADE,
        },
        "paper_stats": {
            "closed": stats_copy.get("closed", 0),
            "wins": stats_copy.get("wins", 0),
            "losses": stats_copy.get("losses", 0),
            "gross_pnl": round(stats_copy.get("gross_pnl", 0.0), 2),
            "total_cost": round(stats_copy.get("total_cost", 0.0), 2),
            "net_pnl": round(stats_copy.get("net_pnl", 0.0), 2),
            "win_rate_pct": round(100.0 * stats_copy.get("wins", 0) / max(1, stats_copy.get("closed", 0)), 2)
            if stats_copy.get("closed", 0) > 0 else 0.0,
        },
        "paper_position": open_position,
        "token_status": {
            "has_token": bool(ACCESS_TOKEN and len(ACCESS_TOKEN.strip()) > 10),
            "token_masked": f"••••••••{ACCESS_TOKEN.strip()[-4:]}" if (ACCESS_TOKEN and len(ACCESS_TOKEN.strip()) >= 8) else ("Not set"),
        },
        "real_order": REAL_ORDER,
        "banner": "PAPER TRADING ONLY — no real orders are placed by this system.",
    }


def display():
    with data_lock:
        nifty = live_data.get(NIFTY_KEY, {}).copy()
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
        tech = compute_technical()
        opts = compute_option_pressure()
        epm = core.epm_score(opts.get("volume_score", 0.0), opts.get("iv_skew", 0.0), tech.get("score", 0.0))
        signal_data = {
            "signal": "WAIT", "confidence": 0.0, "reason": "Signal engine error",
            "technical": tech, "momentum": compute_momentum(),
            "options": opts, "htf_trend": "NEUTRAL", "epm": epm,
        }

    technical = signal_data["technical"]
    if num(spot) > 0:
        try:
            paper_trade_engine(signal_data, spot, technical)
        except Exception as e:
            log_exception("PAPER ENGINE ERROR", e)

    momentum = signal_data["momentum"]
    options = signal_data["options"]
    epm = signal_data.get("epm") or {}
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
    safe_print("EPM SCORE (BETA)  :", round(epm.get("score", 0), 2), epm.get("bias"),
               "| Skew:", epm.get("iv_skew"), "| Vol:", epm.get("volume_score"))
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


_engine_lock = threading.Lock()
_engine_started = False
_rest_thread = None
_display_thread = None


def start_live_engine(token=None, force_restart=False):
    """
    Initializes and starts the live trading engine in background daemon threads.
    Thread-safe and idempotent.
    """
    global running, streamer, selected_expiry, full_chain, selected_strikes, last_atm_used
    global ws_connect_thread, _engine_started, _rest_thread, _display_thread

    with _engine_lock:
        if token:
            set_access_token(token)

        active_token = (ACCESS_TOKEN or os.environ.get("UPSTOX_ACCESS_TOKEN", "")).strip()
        if not active_token or active_token in ("PASTE_YOUR_ACCESS_TOKEN_HERE", "token"):
            safe_print("Live engine: Waiting for valid UPSTOX_ACCESS_TOKEN...")
            return False

        if _engine_started and not force_restart:
            safe_print("Live engine: Already running.")
            return True

        safe_print(f"Live engine: {'Restarting' if _engine_started else 'Starting'} with active token...")
        running = True

        # Stop old streamer if any
        if streamer is not None:
            try:
                if hasattr(streamer, "disconnect"):
                    streamer.disconnect()
            except Exception:
                pass
            streamer = None

        # 1. Discover Expiry
        try:
            selected_expiry = get_expiry()
        except Exception as e:
            log_exception("START ENGINE EXPIRY ERROR", e)
            selected_expiry = None

        # 2. Load Option Chain
        if selected_expiry:
            try:
                full_chain = get_option_chain(selected_expiry)
            except Exception as e:
                log_exception("START ENGINE CHAIN ERROR", e)
                full_chain = None

        # 3. Load initial spot & select strikes
        try:
            nifty = get_nifty_rest()
            if nifty and nifty.get("ltp", 0) > 0:
                spot = nifty["ltp"]
                with data_lock:
                    old = live_data.get(NIFTY_KEY, {}).copy()
                    old.update(nifty)
                    live_data[NIFTY_KEY] = old
                if full_chain:
                    atm = get_atm(spot)
                    last_atm_used = atm
                    selected_strikes = select_options(full_chain, atm)
        except Exception as e:
            log_exception("START ENGINE INITIAL SPOT ERROR", e)

        # 4. Load historical candles
        try:
            load_historical_data()
            refresh_today_intraday_history()
        except Exception as e:
            log_exception("START ENGINE HISTORY ERROR", e)

        # 5. Initialize Upstox WebSocket Streamer if upstox_client is available
        try:
            import upstox_client
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

            ws_connect_thread = threading.Thread(
                target=websocket_connect_worker,
                daemon=True,
                name="UpstoxWebSocketConnect",
            )
            ws_connect_thread.start()
        except ImportError:
            safe_print("NOTE: upstox_client module not found -- running in resilient REST polling fallback.")
        except Exception as e:
            log_exception("START ENGINE STREAMER INIT ERROR", e)

        # 6. Start REST and display loops if not already alive
        if _rest_thread is None or not _rest_thread.is_alive():
            _rest_thread = threading.Thread(target=rest_loop, daemon=True, name="RestLoopThread")
            _rest_thread.start()

        if _display_thread is None or not _display_thread.is_alive():
            _display_thread = threading.Thread(target=display_loop, daemon=True, name="DisplayLoopThread")
            _display_thread.start()

        _engine_started = True
        safe_print("Live engine started successfully.")
        return True


def stop_live_engine():
    global running, streamer, _engine_started
    running = False
    _engine_started = False
    if streamer is not None:
        try:
            if hasattr(streamer, "disconnect"):
                streamer.disconnect()
        except Exception:
            pass
        streamer = None


def main():
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

    def start_api_server():
        try:
            import uvicorn
            from backend.app.main import app
            uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
        except Exception as e:
            log_exception("API SERVER START ERROR", e)

    threading.Thread(target=start_api_server, daemon=True, name="FastAPIServer").start()
    safe_print("FastAPI dashboard API running at http://localhost:8000")

    start_live_engine()

    global running
    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        safe_print("\nStopping V48...")
        stop_live_engine()


if __name__ == "__main__":
    main()
