# ============================================================
# fetch_historical_data.py
# ============================================================
# Pulls 1-minute NIFTY historical candles from Upstox and writes
# them to a CSV that nifty_algo_backtest.py can read directly:
#
#   python fetch_historical_data.py
#   python nifty_algo_backtest.py nifty_1min_history.csv
#
# WHY THIS IS CHUNKED
# --------------------
# Upstox's Historical Candle Data V3 API caps a single request at
# ~1 month of data for 1-15 minute intervals (documented limit).
# To pull several months of history, this script splits the
# requested range into <=25-day windows (a small safety margin
# under the 1-month cap), fetches each one, and stitches them
# together -- deduping by timestamp in case chunk edges overlap.
#
# 1-minute data on Upstox is only available from January 2022
# onward -- DAYS_BACK below can't reach further back than that.
# ============================================================

import csv
import sys
import time
from datetime import datetime, timedelta

import requests

# ============================================================
# CONFIG -- edit these before running
# ============================================================

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ACCESS_TOKEN = os.environ.get("UPSTOX_ACCESS_TOKEN", "")

INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"
INTERVAL = 1  # minutes

DAYS_BACK = 90       # how far back to fetch, in calendar days
CHUNK_DAYS = 25       # stay safely under Upstox's ~1-month-per-request cap
REQUEST_DELAY_SECONDS = 0.5   # small pause between chunk requests

OUTPUT_CSV = "nifty_1min_history.csv"

HEADERS = {
    "Authorization": "Bearer " + ACCESS_TOKEN,
    "Accept": "application/json",
}


# ============================================================
# Date chunking
# ============================================================

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


# ============================================================
# Main
# ============================================================

def main():
    if not ACCESS_TOKEN or ACCESS_TOKEN in ("PASTE_YOUR_ACCESS_TOKEN_HERE", "token", ""):
        print("ERROR: set UPSTOX_ACCESS_TOKEN environment variable or in .env first.")
        sys.exit(1)

    rows = fetch_all(INSTRUMENT_KEY, INTERVAL, DAYS_BACK, CHUNK_DAYS, REQUEST_DELAY_SECONDS)

    if not rows:
        print("\nNo data fetched. Check your ACCESS_TOKEN, instrument key, and DAYS_BACK "
              "(1-min data on Upstox only goes back to January 2022).")
        sys.exit(1)

    print(f"\nTotal unique candles fetched: {len(rows)}")
    write_csv(rows, OUTPUT_CSV)
    print(f"Wrote {OUTPUT_CSV}")
    print(f"\nNow run:  python nifty_algo_backtest.py {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
