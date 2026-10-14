import glob
import os
import shutil
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.backtest.runner import start_backtest_job, get_job

router = APIRouter()


class BacktestRunRequest(BaseModel):
    csv_path: Optional[str] = "synthetic"
    sl_multiplier: float = 1.2
    target_multiplier: float = 2.4
    min_adx: float = 18.0
    min_direction_score: float = 30.0
    require_htf_agreement: bool = True
    htf_factor: int = 5
    atr_pct_min: float = 0.015
    max_hold_bars: int = 60


@router.get("/backtest/datasets")
def list_backtest_datasets():
    """
    List available CSV files for backtesting and parameter sweep.
    """
    datasets = [
        {
            "id": "synthetic",
            "name": "Synthetic OHLC (Harness Test Only)",
            "path": "synthetic",
            "size_bytes": 0,
            "description": "Proves the harness runs. Proves nothing about edge.",
            "is_synthetic": True,
        }
    ]

    # Search in data/ directory and root directory for CSVs
    search_dirs = [
        os.path.abspath("data"),
        os.path.abspath("."),
    ]

    seen_paths = set()
    for s_dir in search_dirs:
        if not os.path.exists(s_dir):
            continue
        for f in os.listdir(s_dir):
            if f.endswith(".csv") and not f.endswith("_log.csv"):
                full_p = os.path.join(s_dir, f)
                if full_p in seen_paths:
                    continue
                seen_paths.add(full_p)
                try:
                    stat = os.stat(full_p)
                    datasets.append({
                        "id": f,
                        "name": f,
                        "path": full_p,
                        "size_bytes": stat.st_size,
                        "modified": stat.st_mtime,
                        "is_synthetic": False,
                    })
                except Exception:
                    pass

    return datasets


@router.post("/backtest/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """
    Upload an OHLC CSV file for backtesting.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    os.makedirs("data", exist_ok=True)
    target_path = os.path.join("data", file.filename)
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "status": "success",
        "filename": file.filename,
        "path": os.path.abspath(target_path),
        "size_bytes": os.path.getsize(target_path),
    }


@router.post("/backtest/run")
def run_backtest(req: BacktestRunRequest):
    """
    Trigger backtest as a background job.
    """
    job_id = start_backtest_job(req.dict())
    return {"job_id": job_id, "status": "PENDING"}


@router.get("/backtest/jobs/{job_id}")
def get_backtest_job_status(job_id: str):
    """
    Check the status and get results of a backtest job.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job
