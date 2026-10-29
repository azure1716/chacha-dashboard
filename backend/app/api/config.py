import os
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import nifty_algo_live as live
import nifty_algo_core as core

router = APIRouter()


@router.get("/config")
def get_system_config():
    """
    Read-only view of running engine constants and configuration parameters.
    No secret keys are exposed here.
    """
    return {
        "engine": {
            "real_order": live.REAL_ORDER,
            "display_seconds": live.DISPLAY_SECONDS,
            "rest_seconds": live.REST_SECONDS,
            "strike_step": live.STRIKE_STEP,
            "strike_range": live.STRIKE_RANGE,
            "rebalance_threshold_points": live.REBALANCE_THRESHOLD_POINTS,
            "rebalance_check_seconds": live.REBALANCE_CHECK_SECONDS,
        },
        "indicators": {
            "ema_fast": live.EMA_FAST,
            "ema_slow": live.EMA_SLOW,
            "rsi_length": live.RSI_LENGTH,
            "atr_length": live.ATR_LENGTH,
            "adx_length": live.ADX_LENGTH,
            "htf_factor": live.HTF_FACTOR,
        },
        "thresholds": {
            "confidence_threshold": live.CONFIDENCE_THRESHOLD,
            "min_direction_score": live.MIN_DIRECTION_SCORE,
            "min_adx_for_trend_signal": live.MIN_ADX_FOR_TREND_SIGNAL,
            "require_htf_agreement": live.REQUIRE_HTF_AGREEMENT,
            "atr_pct_min": live.ATR_PCT_MIN,
            "iv_percentile_max": live.IV_PERCENTILE_MAX,
            "iv_history_len": live.IV_HISTORY_LEN,
        },
        "exit_and_trailing": {
            "atr_sl_multiplier": live.ATR_SL_MULTIPLIER,
            "atr_target_multiplier": live.ATR_TARGET_MULTIPLIER,
            "trail_activate_r": live.TRAIL_ACTIVATE_R,
            "trail_distance_r": live.TRAIL_DISTANCE_R,
        },
        "session_times": {
            "trade_start_minutes": live.TRADE_START_MINUTES,
            "trade_start_str": "09:25 IST",
            "trade_end_minutes": live.TRADE_END_MINUTES,
            "trade_end_str": "14:50 IST",
        },
        "risk_management": {
            "capital": live.CAPITAL,
            "risk_per_trade_pct": live.RISK_PER_TRADE_PCT,
            "lot_size": live.LOT_SIZE,
            "max_lots_per_trade": live.MAX_LOTS_PER_TRADE,
            "max_daily_loss": live.MAX_DAILY_LOSS,
            "daily_profit_lock": live.DAILY_PROFIT_LOCK,
            "max_trades_per_day": live.MAX_TRADES_PER_DAY,
            "max_consecutive_losses": live.MAX_CONSECUTIVE_LOSSES,
            "cooldown_minutes_after_streak": live.COOLDOWN_MINUTES_AFTER_STREAK,
        },
        "cost_model": core.DEFAULT_COST_MODEL,
        "epm_module": {
            "status": "Beta — formula not yet confirmed",
            "weights": (0.40, 0.30, 0.30),
            "description": "Combine option volume, IV, and underlying NIFTY trend into one score. Treated as confirming factor only.",
        },
        "warnings": {
            "lot_size": "⚠ VERIFY current lot size before using this for real sizing — NSE revises it periodically.",
            "costs": "Cost rates are approximate retail placeholders — verify current brokerage, STT, and exchange charges from your Upstox contract note.",
            "strategy_edge": "STATUS OF THE STRATEGY (from nifty_algo.py header): 1-minute EMA/RSI/ADX logic showed NO edge after costs on ~90 days of data. Real orders are NOT implemented; live is paper trading only.",
            "paper_only": "PAPER TRADING ONLY — no real orders are placed by this system.",
        },
        "recent_exceptions": live.get_recent_exceptions(),
    }


def _update_env_file(key: str, value: str, filepath: str) -> None:
    lines = []
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"export {key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


class TokenPayload(BaseModel):
    token: str
    force: bool = False


@router.get("/config/token-status")
def get_token_status():
    token = (getattr(live, "ACCESS_TOKEN", "") or os.environ.get("UPSTOX_ACCESS_TOKEN", "")).strip()
    has_token = bool(token and len(token) > 8 and token not in ("PASTE_YOUR_ACCESS_TOKEN_HERE", "token"))
    masked = f"••••••••{token[-4:]}" if has_token else "Not configured"
    return {
        "has_token": has_token,
        "token_masked": masked,
        "broker": "Upstox",
        "status": "configured" if has_token else "missing",
        "description": "Upstox V2 Interactive API Access Token (expires daily around 03:30 AM IST)",
    }


@router.post("/config/test-token")
def test_upstox_token(payload: TokenPayload):
    token = (payload.token or "").strip()
    if not token:
        return {"valid": False, "error": "Token is empty."}
    return live.verify_upstox_token(token)


@router.post("/config/token")
def update_upstox_token(payload: TokenPayload):
    token = (payload.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token cannot be empty.")

    # Validate against Upstox unless force=True
    verification = live.verify_upstox_token(token)
    if not verification.get("valid", False) and not payload.force:
        return {
            "success": False,
            "valid": False,
            "error": verification.get("error", "Token verification failed with Upstox API."),
            "can_force": True,
            "message": "Upstox rejected this token. If you are confident it is correct or testing offline, click 'Save Anyway'.",
        }

    # Persist to root .env
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    root_env = os.path.join(str(root_dir), ".env")
    _update_env_file("UPSTOX_ACCESS_TOKEN", token, root_env)

    # Persist to backend/.env if it exists
    backend_env = os.path.join(str(root_dir), "backend", ".env")
    if os.path.exists(os.path.dirname(backend_env)):
        _update_env_file("UPSTOX_ACCESS_TOKEN", token, backend_env)

    # Apply in-memory to running engine immediately
    live.set_access_token(token)

    # Start or restart live engine immediately in background thread with new token
    import threading
    threading.Thread(
        target=live.start_live_engine,
        kwargs={"token": token, "force_restart": True},
        daemon=True,
        name="LiveEngineRestart",
    ).start()

    # Update fetch_historical_data if already imported in session
    if "fetch_historical_data" in sys.modules:
        try:
            import fetch_historical_data
            fetch_historical_data.ACCESS_TOKEN = token
            fetch_historical_data.HEADERS["Authorization"] = f"Bearer {token}"
        except Exception:
            pass

    return {
        "success": True,
        "valid": verification.get("valid", False),
        "user_name": verification.get("user_name"),
        "user_id": verification.get("user_id"),
        "token_masked": f"••••••••{token[-4:]}",
        "message": f"Token updated successfully and applied in-memory! Saved to .env.",
    }
