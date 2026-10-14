import asyncio
import time
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import nifty_algo_live as live

router = APIRouter()

active_websockets: Set[WebSocket] = set()


@router.get("/live/state")
def get_live_state():
    """
    Returns the current in-memory state snapshot of the live trading engine.
    """
    return live.get_state_snapshot()


@router.get("/live/health")
def get_live_health():
    """
    Connection and data pipeline health diagnostics.
    """
    with live.data_lock:
        ws_conn = live.ws_connected
        ws_sub = live.ws_subscribed
        ws_attempts = live.ws_connect_attempts
        ws_reconnects = live.ws_reconnect_count
        ws_last_open = live.ws_last_open_time
        ws_last_err = live.ws_last_error
        c_status = live.candle_status
        hist_last_min = live.historical_last_minute
        forming = live.current_candle.copy()

    quality = live.data_quality()

    live_min = forming.get("minute")
    candle_gap = None
    if live_min is not None and hist_last_min is not None:
        candle_gap = int(live_min) - int(hist_last_min)

    return {
        "ws_connected": ws_conn,
        "ws_subscribed": ws_sub,
        "ws_connect_attempts": ws_attempts,
        "ws_reconnect_count": ws_reconnects,
        "ws_last_open_time": ws_last_open,
        "ws_last_error": str(ws_last_err) if ws_last_err else None,
        "candle_status": c_status,
        "historical_last_minute": hist_last_min,
        "live_current_minute": live_min,
        "candle_gap_minutes": candle_gap,
        "data_quality": quality,
        "market_session": "OPEN" if live.nse_market_open_now() else "CLOSED",
        "trade_window": "YES" if live.is_trade_time() else "NO",
        "recent_exceptions": live.get_recent_exceptions(),
    }


@router.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """
    Realtime WebSocket transport pushing state snapshots every DISPLAY_SECONDS (5s),
    with an immediate push upon connection.
    """
    await websocket.accept()
    active_websockets.add(websocket)
    try:
        # Push immediate snapshot upon connection
        initial_snap = live.get_state_snapshot()
        await websocket.send_json(initial_snap)

        while True:
            await asyncio.sleep(live.DISPLAY_SECONDS)
            snap = live.get_state_snapshot()
            await websocket.send_json(snap)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        active_websockets.discard(websocket)
