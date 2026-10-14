# NIFTY Options Algo — Paper-Trading Monitoring & Research Dashboard

> **IMPORTANT DISCLAIMER — PAPER TRADING ONLY**
> This software is strictly a read-first, paper-trading monitoring and research dashboard for an algorithmic NIFTY 50 options heuristic strategy. **No real orders are placed by this system.** The engine's `REAL_ORDER` flag is permanently set to `False`, `place_real_order()` raises `NotImplementedError`, and there is no order execution button or API route in this entire codebase. This tool exists solely for signal observation, risk monitoring, backtesting, and parameter exploration.

---

## ⚠️ Security Notice: Revoke Exposed Access Tokens

> [!CAUTION]
> **ACTION REQUIRED FOR OPERATORS:**
> Prior versions of the console scripts contained hardcoded Upstox `ACCESS_TOKEN` strings in plaintext files. If you or anyone committed, shared, or pasted those files previously, **that access token is compromised**.
>
> 1. Log in to the [Upstox Developer Portal](https://developer.upstox.com/) immediately.
> 2. **Revoke and regenerate your API credentials and access token.**
> 3. Store the new token exclusively in a local `.env` file (which is git-ignored) or pass it via system environment variables.
> 4. Never commit `.env` or send the token to the frontend client. All Upstox interactions remain strictly server-side.

---

## Architecture Overview

```
d:/chacha claude algo/
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI REST and WebSocket routers
│   │   │   ├── live.py           # GET /api/live/state, /health, WS /ws/live
│   │   │   ├── signals.py        # GET /api/signals (paginated signals_log.csv)
│   │   │   ├── trades.py         # GET /api/trades, /stats, /export CSV
│   │   │   ├── backtest.py       # POST /api/backtest/run, upload, datasets
│   │   │   ├── sweep.py          # POST /api/sweep/run, job polling
│   │   │   ├── config.py         # GET /api/config (read-only engine parameters)
│   │   │   └── tests.py          # POST /api/tests/run (self-tests harness)
│   │   ├── backtest/
│   │   │   └── runner.py         # ThreadPoolExecutor background job runner
│   │   ├── core/                 # Proxy to root nifty_algo_core.py
│   │   ├── live/                 # Proxy to root nifty_algo_live.py
│   │   └── main.py               # ASGI application entrypoint & SPA static server
│   ├── requirements.txt          # Python dependencies
│   └── .env.example              # Template environment variables
├── frontend/
│   ├── src/
│   │   ├── components/           # Navbar, Layout, Lightweight Candlestick Chart
│   │   ├── hooks/                # useLiveStream (WS with automatic HTTP fallback)
│   │   ├── pages/
│   │   │   ├── LiveMonitorPage.tsx     # 5.1 Realtime Signal, Scores & Chart
│   │   │   ├── TradeHistoryPage.tsx    # 5.2 Open Position, Closed Trades & Equity Curve
│   │   │   ├── RiskManagementPage.tsx  # 5.3 Daily Loss Progress & Sizing Limits
│   │   │   ├── SignalsAuditPage.tsx    # 5.4 Full tick-by-tick CSV Audit Explorer
│   │   │   ├── BacktestLabPage.tsx     # 5.5 Directional Core Replay Engine
│   │   │   ├── ParameterSweepPage.tsx  # 5.6 Grid Search & 2D Heatmap
│   │   │   └── SystemConfigPage.tsx    # 5.7 Active Config & Self-Tests Runner
│   │   ├── types.ts              # TypeScript type contracts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
├── nifty_algo_core.py            # Source of truth: Pure mathematical functions & EPM placeholder
├── nifty_algo_live.py            # Live trading engine (WebSocket, candle builder, risk state)
├── nifty_algo_backtest.py        # Directional core historical replay engine
├── parameter_sweep.py            # Grid search optimizer
├── test_core.py                  # Core unit tests
├── test_live_simulation.py       # Live engine mock integration tests
├── signals_log.csv               # Historical signal audit log
├── trades_log.csv                # Paper-trade execution log
└── .env.example
```

---

## Strategy Truths & Honest Caveats

All metrics presented in this dashboard reflect the unaltered math of the underlying Python scripts. We do not soften or conceal the mathematical limitations:

1. **No Real Edge on 1-Min Data (Console Header Caveat):**
   As noted in `nifty_algo.py`'s header:
   > *"The 1-min EMA/RSI/ADX directional logic showed no statistical edge after costs on ~90 days of historical data."*
   The system relies on chop filters (ADX threshold, HTF alignment) and option pressure to avoid overtrading.

2. **WAIT is the Normal, Healthy State:**
   The algorithm is designed to remain in `WAIT` most of the trading session (e.g., ADX < 18 indicating chop, or outside the 09:25–14:50 window). `WAIT` is an active risk gate, not an error.

3. **Backtest Lab Scope:**
   `nifty_algo_backtest.py` validates **only the directional technical/momentum core** (~65% of the live decision weight). It **does not model option-pressure, order book depth, or slippage/commissions**. It serves as a baseline floor check, not a profit projection.

4. **Multiple-Testing Risk in Parameter Sweeps:**
   Running a grid sweep over dozens of parameter combinations on a single historical CSV is guaranteed to produce outliers that appear profitable purely by chance. Always look for stable clusters of nearby parameters and validate candidates on out-of-sample data.

5. **EPM Module Status (Beta — Formula Pending):**
   `epm_score()` in `nifty_algo_core.py` is a placeholder implementing the conceptual behavior described in chat notes (combining option volume skew, IV skew, and technical trend). It acts solely as a confirming factor for direction score and does not generate trades independently.

---

## Setup & Installation

### Prerequisites
- Python 3.10+ (tested on Python 3.12 / 3.14)
- Node.js 18+ and `npm`

### 1. Environment Configuration
Copy the template `.env.example` to `.env` in the project root:
```bash
cp .env.example .env
```
Edit `.env` with your Upstox API credentials:
```env
UPSTOX_ACCESS_TOKEN=your_regenerated_token_here
UPSTOX_API_KEY=your_api_key_here
UPSTOX_API_SECRET=your_api_secret_here
```

### 2. Backend Setup
Install Python dependencies:
```bash
pip install -r backend/requirements.txt
```

Run unit and integration self-tests to verify strategy logic:
```bash
python test_core.py
python test_live_simulation.py
```
*(All 49 core tests and simulation checks should pass).*

### 3. Frontend Setup
Navigate to `/frontend` and install packages:
```bash
cd frontend
npm install
```

---

## Running the Application

### Option A: Unified Production Server (Recommended)
Build the frontend assets and run the FastAPI server, which serves both the REST/WebSocket API and the built React SPA on a single port:

```bash
# 1. Build the React frontend
cd frontend
npm run build
cd ..

# 2. Start the ASGI server
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

### Option B: Development Mode (Hot-Reloading)
For active dashboard development, run the backend and Vite dev server concurrently:

**Terminal 1 (Backend):**
```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 (Frontend):**
```bash
cd frontend
npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)**. The Vite dev server proxies API calls and WebSocket connections directly to `127.0.0.1:8000`.

---

## Key Dashboard Panels

| Panel | Description | Key Features |
|---|---|---|
| **Live Signal Monitor** | Real-time cockpit for the running engine | Spot & ATM strikes, signal badge (`BUY CALL`, `BUY PUT`, `WAIT`), confidence progress ring, verbatim reason string, score breakdown card with weights, TradingView lightweight candlestick chart (1-min + EMA20/50), session/connection status strip. |
| **Trade History** | Paper execution tracking | Active paper position card with live unrealized P&L, summary performance metrics (Win Rate, Profit Factor, Max Drawdown), cumulative net equity curve, sortable/filterable closed trades table with CSV download. |
| **Risk Management** | Capital protection guardrails | Daily P&L vs `MAX_DAILY_LOSS` progress bar, trade counters today, consecutive loss cooldown timer, read-only lot sizing with NSE revision caution. |
| **Signals Audit Log** | Tick-by-tick decision diagnostics | Full browsable view of `signals_log.csv` showing why the engine entered or passed on every single tick, with detailed parameter inspector modal. |
| **Backtest Lab** | Directional replay runner | Non-blocking background backtest executor on synthetic or uploaded historical 1-min CSVs, equity curve visualization, exit reason breakdown, and explicit methodology caveats. |
| **Parameter Sweep** | Strategy sensitivity explorer | Background grid search across SL, Target, and ADX filters with multiple-testing warning banner, 2D SL×Target heatmap, and sortable profit-factor table. |
| **System / Config** | Engine transparency & tests | Live read-only parameters pulled directly from engine memory, exception ring buffer, in-UI Upstox daily token renewal, and one-click "Run Self-Tests" harness. |

---

## Hosted Deployment & Daily Upstox Token Renewal

When hosting this dashboard on a cloud server (VPS, AWS, DigitalOcean, or private network), Upstox access tokens expire every morning around **03:30 AM IST**. 

You do **not** need to log into SSH or edit files on the server every morning. You can replace and verify the token directly from the web dashboard:

1. **Top Navbar Button**: Click the **`TOKEN ACTIVE`** / **`REPLACE TOKEN`** button in the header (or go to **System Config → Upstox API Authentication**).
2. **Paste Today's Token**: Paste your fresh Upstox access token generated from the [Upstox Developer Console](https://developer.upstox.com/).
3. **Test & Verify**: Click **"Test Connection"** to verify the token live against Upstox's `/v2/user/profile` API. It displays the authenticated client name and ID.
4. **Save & Apply**: Click **"Save & Apply Token"**:
   - The token is applied **in-memory immediately** to the running engine without rebooting the server.
   - The token is automatically persisted to the server's `.env` file so it survives future restarts.
   - The token remains strictly server-side and is never exposed in client bundles or network logs.

---

## Safety & Invariant Guarantees

- **`REAL_ORDER == False`**: Verified at application startup via FastAPI lifespan context manager. The server refuses to boot if `REAL_ORDER` is true.
- **Server-Side Math**: 100% of indicator math, weights, and decision logic resides in Python (`nifty_algo_core.py`). No logic is duplicated in TypeScript.
- **Resilient Transport**: The frontend connects via `/ws/live`. If WebSocket drops, it automatically falls back to polling `/api/live/state` every 5 seconds and notifies the operator on-screen.
- **IST Standard**: All times are explicitly displayed in Indian Standard Time (`UTC+5:30`).
