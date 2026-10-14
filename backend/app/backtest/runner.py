import concurrent.futures
import itertools
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

import nifty_algo_backtest as bt
import parameter_sweep as sweep_module

IST = timezone(timedelta(hours=5, minutes=30))

executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
jobs: Dict[str, Dict[str, Any]] = {}


def now_ist_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    return jobs.get(job_id)


def list_jobs() -> Dict[str, Dict[str, Any]]:
    return jobs


def _run_backtest_worker(job_id: str, params: Dict[str, Any]):
    jobs[job_id]["status"] = "RUNNING"
    jobs[job_id]["started_at"] = now_ist_str()
    try:
        csv_path = params.get("csv_path")
        is_synthetic = False
        if not csv_path or csv_path == "synthetic" or not os.path.exists(csv_path):
            is_synthetic = True
            data = bt.synthetic_ohlc_for_harness_test(n=1500)
            dataset_name = "Synthetic OHLC (Harness Test)"
        else:
            data = bt.load_ohlc_csv(csv_path)
            dataset_name = os.path.basename(csv_path)

        sl_mult = float(params.get("sl_multiplier", 1.2))
        tgt_mult = float(params.get("target_multiplier", 2.4))
        min_adx = float(params.get("min_adx", 18))
        min_dir_score = float(params.get("min_direction_score", 30))
        req_htf = bool(params.get("require_htf_agreement", True))
        htf_factor = int(params.get("htf_factor", 5))
        atr_pct_min = float(params.get("atr_pct_min", 0.015))
        max_hold = int(params.get("max_hold_bars", 60))

        trades = bt.simulate_index_signal_backtest(
            data["highs"],
            data["lows"],
            data["closes"],
            data["opens"],
            min_adx_for_trend_signal=min_adx,
            min_direction_score=min_dir_score,
            require_htf_agreement=req_htf,
            htf_factor=htf_factor,
            sl_multiplier=sl_mult,
            target_multiplier=tgt_mult,
            max_hold_bars=max_hold,
            atr_pct_min=atr_pct_min,
            progress_every=0,
        )

        stats = bt.summarize_trades(trades)
        exit_reasons = bt.summarize_by_exit_reason(trades)

        # Build equity curve points
        equity_curve = []
        cum_points = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for idx, t in enumerate(trades):
            cum_points += t["pnl_points"]
            peak = max(peak, cum_points)
            dd = peak - cum_points
            max_drawdown = max(max_drawdown, dd)
            ts = data["timestamps"][t["entry_idx"]] if data.get("timestamps") and t["entry_idx"] < len(data["timestamps"]) else None
            equity_curve.append({
                "trade_index": idx + 1,
                "timestamp": ts or f"Bar {t['entry_idx']}",
                "pnl_points": round(t["pnl_points"], 2),
                "cumulative_points": round(cum_points, 2),
                "drawdown": round(dd, 2),
                "signal": t["signal"],
                "exit_reason": t["exit_reason"],
            })

        caveats = [
            "This backtest validates ONLY the directional core (technical + momentum + ADX + HTF trend: ~65% of live weight).",
            "Does NOT validate the option-pressure leg (35% of weight) or EPM — historical OI/IV feeds are not available offline.",
            "No transaction costs or slippage modeled — index points only. It is a floor check on direction-calling ability, not a P&L projection.",
        ]
        if is_synthetic:
            caveats.insert(0, "HARNESS TEST ONLY — proves the code runs, proves nothing about edge.")

        jobs[job_id]["status"] = "COMPLETED"
        jobs[job_id]["completed_at"] = now_ist_str()
        jobs[job_id]["result"] = {
            "dataset_name": dataset_name,
            "total_bars": len(data["closes"]),
            "is_synthetic": is_synthetic,
            "params": {
                "sl_multiplier": sl_mult,
                "target_multiplier": tgt_mult,
                "min_adx": min_adx,
                "min_direction_score": min_dir_score,
                "require_htf_agreement": req_htf,
                "htf_factor": htf_factor,
                "atr_pct_min": atr_pct_min,
                "max_hold_bars": max_hold,
            },
            "stats": stats,
            "exit_reasons": exit_reasons,
            "trades": trades[:500],  # Return up to 500 recent trades for inspectability
            "total_trades_count": len(trades),
            "equity_curve": equity_curve,
            "caveats": caveats,
            "header_warning": "From nifty_algo.py header: 1-minute EMA/RSI/ADX logic showed NO edge after costs on ~90 days of real data. Treat backtest as an initial sanity test only.",
        }
    except Exception as e:
        jobs[job_id]["status"] = "FAILED"
        jobs[job_id]["completed_at"] = now_ist_str()
        jobs[job_id]["error"] = str(e)


def start_backtest_job(params: Dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id": job_id,
        "type": "backtest",
        "status": "PENDING",
        "created_at": now_ist_str(),
        "params": params,
        "result": None,
        "error": None,
    }
    executor.submit(_run_backtest_worker, job_id, params)
    return job_id


def _run_sweep_worker(job_id: str, params: Dict[str, Any]):
    jobs[job_id]["status"] = "RUNNING"
    jobs[job_id]["started_at"] = now_ist_str()
    try:
        csv_path = params.get("csv_path")
        if not csv_path or not os.path.exists(csv_path):
            data = bt.synthetic_ohlc_for_harness_test(n=1500)
            dataset_name = "Synthetic OHLC (Harness Test Only)"
            is_synthetic = True
        else:
            data = bt.load_ohlc_csv(csv_path)
            dataset_name = os.path.basename(csv_path)
            is_synthetic = False

        jobs[job_id]["progress"] = "Precomputing bar features..."
        features = bt.precompute_bar_features(data["highs"], data["lows"], data["closes"], progress_every=0)

        sl_mults = params.get("sl_multipliers") or sweep_module.SL_MULTIPLIERS
        tgt_mults = params.get("target_multipliers") or sweep_module.TARGET_MULTIPLIERS
        adx_thresh = params.get("adx_thresholds") or sweep_module.ADX_THRESHOLDS
        dir_thresh = params.get("direction_score_thresholds") or sweep_module.DIRECTION_SCORE_THRESHOLDS
        min_trades = int(params.get("min_trades_to_count", 30))

        combos = [
            (sl, tgt, adx, dirscore)
            for sl, tgt, adx, dirscore in itertools.product(sl_mults, tgt_mults, adx_thresh, dir_thresh)
            if tgt > sl
        ]
        total_combos = len(combos)
        jobs[job_id]["total_combos"] = total_combos

        results = []
        for idx, (sl_m, tgt_m, adx_t, dir_t) in enumerate(combos):
            if idx % 10 == 0:
                jobs[job_id]["progress"] = f"Tested {idx}/{total_combos} combinations..."
            trades = bt.simulate_from_features(
                features,
                data["highs"],
                data["lows"],
                data["closes"],
                data["opens"],
                min_adx_for_trend_signal=adx_t,
                min_direction_score=dir_t,
                sl_multiplier=sl_m,
                target_multiplier=tgt_m,
            )
            stats = bt.summarize_trades(trades)
            if stats.get("trades", 0) < min_trades:
                continue

            rr = tgt_m / sl_m
            breakeven_wr = 100.0 / (1 + rr)
            stats.update({
                "sl_mult": sl_m,
                "target_mult": tgt_m,
                "adx_min": adx_t,
                "dir_score_min": dir_t,
                "rr_ratio": round(rr, 2),
                "breakeven_win_rate_pct": round(breakeven_wr, 2),
                "edge_vs_breakeven_pct": round(stats["win_rate_pct"] - breakeven_wr, 2),
            })
            results.append(stats)

        results.sort(key=lambda r: (r["profit_factor"] or 0), reverse=True)

        # Build 2D heatmap matrix (SL Multiplier vs Target Multiplier)
        heatmap_matrix = {}
        for sl in sl_mults:
            heatmap_matrix[str(sl)] = {}
            for tgt in tgt_mults:
                matching = [r for r in results if r["sl_mult"] == sl and r["target_mult"] == tgt]
                if matching:
                    avg_pf = sum((m["profit_factor"] or 0) for m in matching) / len(matching)
                    avg_edge = sum(m["edge_vs_breakeven_pct"] for m in matching) / len(matching)
                    heatmap_matrix[str(sl)][str(tgt)] = {
                        "avg_pf": round(avg_pf, 3),
                        "avg_edge": round(avg_edge, 2),
                        "combos_count": len(matching),
                        "best_pf": max((m["profit_factor"] or 0) for m in matching),
                    }
                else:
                    heatmap_matrix[str(sl)][str(tgt)] = None

        strong_configs = [
            r for r in results if r["edge_vs_breakeven_pct"] > 0 and r["profit_factor"] and r["profit_factor"] > 1.1
        ]

        jobs[job_id]["status"] = "COMPLETED"
        jobs[job_id]["completed_at"] = now_ist_str()
        jobs[job_id]["result"] = {
            "dataset_name": dataset_name,
            "is_synthetic": is_synthetic,
            "total_bars": len(data["closes"]),
            "total_combos_tested": total_combos,
            "combos_meeting_min_trades": len(results),
            "min_trades_threshold": min_trades,
            "strong_configs_count": len(strong_configs),
            "top_configs": results[:20],
            "bottom_configs": results[-10:] if len(results) >= 10 else results,
            "all_results": results,
            "heatmap": {
                "sl_multipliers": sl_mults,
                "target_multipliers": tgt_mults,
                "matrix": heatmap_matrix,
            },
            "multiple_testing_warning": (
                "CRITICAL WARNING — MULTIPLE TESTING RISK: "
                "Trying dozens of combinations on ONE dataset will produce a few lucky-looking rows by chance alone "
                "(p-hacking). Do NOT simply pick the single highest profit factor row. Look for a CLUSTER of nearby "
                "parameters that all perform reasonably well, and test leading candidates on a non-overlapping date range "
                "before trusting them."
            ),
        }
    except Exception as e:
        jobs[job_id]["status"] = "FAILED"
        jobs[job_id]["completed_at"] = now_ist_str()
        jobs[job_id]["error"] = str(e)


def start_sweep_job(params: Dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id": job_id,
        "type": "sweep",
        "status": "PENDING",
        "created_at": now_ist_str(),
        "params": params,
        "result": None,
        "error": None,
    }
    executor.submit(_run_sweep_worker, job_id, params)
    return job_id
