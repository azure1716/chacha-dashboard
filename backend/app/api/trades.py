import csv
import math
import os
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
import nifty_algo_live as live

router = APIRouter()


def _read_trades_rows():
    csv_path = live.TRADES_LOG_PATH
    if not os.path.exists(csv_path):
        return []

    rows = []
    try:
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception:
        return []
    return rows


@router.get("/trades")
def get_trades_log(
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    exit_reason: Optional[str] = Query(None, description="Exit reason filter: TARGET, SL, TIME, TRAIL, or ALL"),
    direction: Optional[str] = Query(None, description="Direction filter: CALL, PUT, or ALL"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
):
    """
    Paginated closed trade log from trades_log.csv.
    """
    all_rows = _read_trades_rows()

    filtered = []
    for r in all_rows:
        entry_t = r.get("entry_time", "")
        if from_date and entry_t < from_date:
            continue
        if to_date and entry_t > (to_date + " 23:59:59" if len(to_date) == 10 else to_date):
            continue

        reason = r.get("exit_reason", "")
        if exit_reason and exit_reason.upper() != "ALL" and reason.upper() != exit_reason.upper():
            continue

        dir_val = r.get("direction", "")
        if direction and direction.upper() != "ALL" and dir_val.upper() != direction.upper():
            continue

        filtered.append(r)

    # Reverse so latest trades are at the top
    filtered.reverse()

    total = len(filtered)
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    items = filtered[start_idx:end_idx]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": items,
        "source": live.TRADES_LOG_PATH,
    }


@router.get("/trades/stats")
def get_trades_stats():
    """
    Calculates summary performance metrics and equity curve data from trades_log.csv.
    """
    rows = _read_trades_rows()
    if not rows:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "total_gross_pnl": 0.0,
            "total_cost": 0.0,
            "total_net_pnl": 0.0,
            "avg_trade_pnl": 0.0,
            "profit_factor": None,
            "max_drawdown": 0.0,
            "by_exit_reason": {},
            "equity_curve": [],
        }

    total_gross = 0.0
    total_cost = 0.0
    total_net = 0.0
    wins = 0
    losses = 0
    gross_wins = 0.0
    gross_losses = 0.0
    by_exit = {}

    equity_curve = []
    cum_net = 0.0
    peak = 0.0
    max_dd = 0.0

    for idx, r in enumerate(rows):
        try:
            g = float(r.get("gross_pnl") or 0.0)
            c = float(r.get("cost") or 0.0)
            n = float(r.get("net_pnl") or 0.0)
        except (ValueError, TypeError):
            continue

        total_gross += g
        total_cost += c
        total_net += n

        if n > 0:
            wins += 1
            gross_wins += n
        else:
            losses += 1
            gross_losses += abs(n)

        reason = r.get("exit_reason", "UNKNOWN")
        by_exit[reason] = by_exit.get(reason, 0) + 1

        cum_net += n
        peak = max(peak, cum_net)
        dd = peak - cum_net
        max_dd = max(max_dd, dd)

        equity_curve.append({
            "trade_num": idx + 1,
            "time": r.get("exit_time") or r.get("entry_time") or f"Trade {idx+1}",
            "net_pnl": round(n, 2),
            "cumulative_net": round(cum_net, 2),
            "drawdown": round(dd, 2),
            "exit_reason": reason,
            "direction": r.get("direction", ""),
            "strike": r.get("strike", ""),
        })

    n_trades = len(rows)
    win_rate = round(100.0 * wins / n_trades, 2) if n_trades > 0 else 0.0
    pf = round(gross_wins / gross_losses, 3) if gross_losses > 0 else (None if gross_wins == 0 else 999.0)

    return {
        "total_trades": n_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "total_gross_pnl": round(total_gross, 2),
        "total_cost": round(total_cost, 2),
        "total_net_pnl": round(total_net, 2),
        "avg_trade_pnl": round(total_net / n_trades, 2) if n_trades > 0 else 0.0,
        "profit_factor": pf,
        "max_drawdown": round(max_dd, 2),
        "by_exit_reason": by_exit,
        "equity_curve": equity_curve,
    }


@router.get("/trades/export")
def export_trades_csv():
    """
    Export the trades log CSV directly as a downloadable file.
    """
    csv_path = live.TRADES_LOG_PATH
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail="trades_log.csv does not exist yet.")
    return FileResponse(
        path=csv_path,
        filename="trades_log.csv",
        media_type="text/csv",
    )
