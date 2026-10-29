import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure root directory is on sys.path
root_dir = str(Path(__file__).resolve().parent.parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.api import api_router
from backend.app.api.live import router as ws_router
import nifty_algo_live as live


import threading


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enforce paper trading safety invariant on startup
    if getattr(live, "REAL_ORDER", False):
        raise RuntimeError("FATAL: REAL_ORDER is True. Refusing to run live orders in paper dashboard build.")

    # Auto-start live engine in background thread if a valid Upstox token exists on server boot
    token = (getattr(live, "ACCESS_TOKEN", "") or os.environ.get("UPSTOX_ACCESS_TOKEN", "")).strip()
    if token and len(token) > 8 and token not in ("PASTE_YOUR_ACCESS_TOKEN_HERE", "token"):
        threading.Thread(
            target=live.start_live_engine,
            kwargs={"token": token},
            daemon=True,
            name="LiveEngineInit",
        ).start()

    yield

    # Clean shutdown
    live.stop_live_engine()


app = FastAPI(
    title="NIFTY Options Algo — Dashboard API",
    description="Read-first, paper-trading-only monitoring & research tooling for NIFTY options heuristic strategy.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST API router and WebSocket router
app.include_router(api_router)
app.include_router(ws_router)  # for /ws/live


@app.get("/api/info")
def api_info():
    return {
        "app": "NIFTY Options Algo Dashboard",
        "version": "1.0.0",
        "status": "online",
        "trading_mode": "PAPER TRADING ONLY",
        "real_orders_enabled": False,
        "banner": "PAPER TRADING ONLY — no real orders are placed by this system.",
    }


# Mount built frontend files if they exist (for unified production deployment)
frontend_dist = os.path.join(root_dir, "frontend", "dist")
if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static_assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return api_info()
else:
    @app.get("/")
    def fallback_root():
        return api_info()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port)
