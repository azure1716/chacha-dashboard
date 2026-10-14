import csv
import os
import math
from typing import Optional
from fastapi import APIRouter, Query
import nifty_algo_live as live

router = APIRouter()


@router.get("/signals")
def get_signals_log(
    from_date: Optional[str] = Query(None, description="Start date/time (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)"),
    to_date: Optional[str] = Query(None, description="End date/time (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)"),
    signal: Optional[str] = Query(None, description="Signal filter: BUY CALL, BUY PUT, WAIT, or ALL"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
):
    """
    Paginated audit log of every engine tick from signals_log.csv.
    """
    csv_path = live.SIGNALS_LOG_PATH
    if not os.path.exists(csv_path):
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "items": [],
            "source": csv_path,
        }

    rows = []
    try:
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Date filtering
                ts = row.get("timestamp", "")
                if from_date and ts < from_date:
                    continue
                if to_date and ts > (to_date + " 23:59:59" if len(to_date) == 10 else to_date):
                    continue

                # Signal filtering
                sig = row.get("signal", "")
                if signal and signal.upper() != "ALL" and sig.upper() != signal.upper():
                    continue

                rows.append(row)
    except Exception as e:
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "items": [],
            "error": str(e),
        }

    # Reverse so most recent ticks are at the top
    rows.reverse()

    total = len(rows)
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    items = rows[start_idx:end_idx]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": items,
        "source": csv_path,
    }
