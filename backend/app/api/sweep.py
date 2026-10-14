from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.backtest.runner import start_sweep_job, get_job

router = APIRouter()


class SweepRunRequest(BaseModel):
    csv_path: Optional[str] = "synthetic"
    sl_multipliers: Optional[List[float]] = None
    target_multipliers: Optional[List[float]] = None
    adx_thresholds: Optional[List[float]] = None
    direction_score_thresholds: Optional[List[float]] = None
    min_trades_to_count: int = 30


@router.post("/sweep/run")
def run_parameter_sweep(req: SweepRunRequest):
    """
    Trigger parameter sweep grid search as a background job.
    """
    job_id = start_sweep_job(req.dict())
    return {"job_id": job_id, "status": "PENDING"}


@router.get("/sweep/jobs/{job_id}")
def get_sweep_job_status(job_id: str):
    """
    Check the status and results of a parameter sweep job.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job
