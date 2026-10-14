from fastapi import APIRouter
from backend.app.api.live import router as live_router
from backend.app.api.signals import router as signals_router
from backend.app.api.trades import router as trades_router
from backend.app.api.backtest import router as backtest_router
from backend.app.api.sweep import router as sweep_router
from backend.app.api.config import router as config_router
from backend.app.api.tests import router as tests_router

api_router = APIRouter(prefix="/api")

api_router.include_router(live_router, tags=["Live Ops"])
api_router.include_router(signals_router, tags=["Signals"])
api_router.include_router(trades_router, tags=["Trades"])
api_router.include_router(backtest_router, tags=["Backtest Lab"])
api_router.include_router(sweep_router, tags=["Parameter Sweep"])
api_router.include_router(config_router, tags=["Config"])
api_router.include_router(tests_router, tags=["Self Tests"])
