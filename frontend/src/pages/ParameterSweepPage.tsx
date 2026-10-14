import React, { useState, useEffect } from 'react';
import { SweepJobResult } from '../types';
import { Heatmap2D } from '../components/Heatmap2D';
import { SlidersHorizontal, Play, AlertOctagon, Loader2, ArrowUpDown, Info } from 'lucide-react';
import { apiUrl } from '../api';

export const ParameterSweepPage: React.FC = () => {
  const [datasets, setDatasets] = useState<any[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>('synthetic');
  const [minTrades, setMinTrades] = useState<number>(30);

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<string | null>(null);
  const [result, setResult] = useState<SweepJobResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'top' | 'all' | 'bottom'>('top');

  useEffect(() => {
    fetch(apiUrl('/api/backtest/datasets'))
      .then(res => res.json())
      .then(data => setDatasets(data))
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!activeJobId) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(apiUrl(`/api/sweep/jobs/${activeJobId}`));
        if (res.ok) {
          const job = await res.json();
          setJobProgress(job.progress || 'Computing...');
          if (job.status === 'COMPLETED') {
            setResult(job.result);
            setActiveJobId(null);
            clearInterval(interval);
          } else if (job.status === 'FAILED') {
            setError(job.error || 'Parameter sweep failed');
            setActiveJobId(null);
            clearInterval(interval);
          }
        }
      } catch (e: any) {
        console.error('Sweep polling error:', e);
      }
    }, 800);

    return () => clearInterval(interval);
  }, [activeJobId]);

  const handleStartSweep = async () => {
    setError(null);
    setResult(null);
    setJobProgress('Initializing sweep grid...');

    try {
      const res = await fetch(apiUrl('/api/sweep/run'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          csv_path: selectedDataset,
          min_trades_to_count: minTrades,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setActiveJobId(data.job_id);
      } else {
        const err = await res.json();
        setError(err.detail || 'Failed to start parameter sweep');
      }
    } catch (e: any) {
      setError(e.message || 'Error triggering sweep');
    }
  };

  const rowsToDisplay = result ? (
    viewMode === 'top' ? result.top_configs :
    viewMode === 'bottom' ? result.bottom_configs :
    result.all_results
  ) : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="p-4 rounded-xl bg-slate-900 border border-terminal-border flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-5 h-5 text-cyan-400" />
            <h2 className="text-base font-bold text-white uppercase tracking-wider">
              Parameter Sweep Explorer (parameter_sweep.py)
            </h2>
          </div>
          <p className="text-xs text-terminal-muted mt-1">
            Tests stop-multiplier, target-multiplier, ADX threshold, and direction score combinations against the same precomputed features.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={selectedDataset}
            onChange={(e) => setSelectedDataset(e.target.value)}
            className="bg-terminal-bg border border-terminal-border rounded-lg px-3 py-1.5 text-white text-xs font-mono"
          >
            {datasets.map((d) => (
              <option key={d.id} value={d.path}>
                {d.name}
              </option>
            ))}
          </select>

          <button
            onClick={handleStartSweep}
            disabled={activeJobId !== null}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 text-white font-medium text-xs hover:from-cyan-500 hover:to-blue-500 transition-all disabled:opacity-50 shadow-md shadow-cyan-500/20"
          >
            {activeJobId ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Scanning Grid...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                <span>Run Parameter Sweep</span>
              </>
            )}
          </button>
        </div>
      </div>

      {activeJobId && (
        <div className="p-4 rounded-xl bg-cyan-950/40 border border-cyan-800 text-cyan-300 text-xs font-mono flex items-center gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-cyan-400 shrink-0" />
          <div>
            <div className="font-bold">Replaying precomputed features across parameter grid...</div>
            <div className="text-[11px] text-cyan-400/80">{jobProgress}</div>
          </div>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-xs font-mono">
          Sweep Error: {error}
        </div>
      )}

      {result ? (
        <div className="space-y-6">
          {/* LOUD, PERMANENT MULTIPLE-TESTING CAUTION BANNER */}
          <div className="p-5 rounded-xl bg-rose-950/30 border-2 border-rose-600/70 text-rose-200 text-xs space-y-2">
            <div className="flex items-center gap-2 text-rose-300 font-bold uppercase tracking-wider text-sm">
              <AlertOctagon className="w-5 h-5 text-rose-400 shrink-0" />
              <span>CRITICAL MULTIPLE-TESTING WARNING (p-hacking risk)</span>
            </div>
            <p className="font-mono text-[11px] leading-relaxed text-rose-200/90">
              {result.multiple_testing_warning}
            </p>
            <div className="pt-2 text-[11px] text-rose-300/80 border-t border-rose-800/40 font-mono">
              Tested {result.total_combos_tested} combinations • {result.strong_configs_count} configs cleared PF &gt; 1.1 and actual win% &gt; breakeven line.
            </div>
          </div>

          {/* 2D Heatmap */}
          {result.heatmap && (
            <Heatmap2D heatmap={result.heatmap} />
          )}

          {/* Results Table Card */}
          <div className="glass-panel rounded-xl border border-terminal-border overflow-hidden">
            <div className="p-4 border-b border-terminal-border/60 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h4 className="text-xs font-semibold text-white uppercase tracking-wider">
                  Parameter Combinations Ranked by Profit Factor
                </h4>
                <p className="text-[11px] text-terminal-muted">
                  BEwin% = win rate required by this combo&apos;s R:R to break even. Edge = actual win% minus BEwin%.
                </p>
              </div>

              <div className="flex items-center gap-2 text-xs font-mono">
                <button
                  onClick={() => setViewMode('top')}
                  className={`px-3 py-1 rounded-lg ${viewMode === 'top' ? 'bg-cyan-600 text-white' : 'bg-terminal-bg text-terminal-muted hover:text-white'}`}
                >
                  Top 20 Configs
                </button>
                <button
                  onClick={() => setViewMode('all')}
                  className={`px-3 py-1 rounded-lg ${viewMode === 'all' ? 'bg-cyan-600 text-white' : 'bg-terminal-bg text-terminal-muted hover:text-white'}`}
                >
                  All ({result.combos_meeting_min_trades})
                </button>
                <button
                  onClick={() => setViewMode('bottom')}
                  className={`px-3 py-1 rounded-lg ${viewMode === 'bottom' ? 'bg-rose-900 text-white' : 'bg-terminal-bg text-terminal-muted hover:text-white'}`}
                >
                  Bottom 10 (Contrast)
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-terminal-surface text-terminal-muted border-b border-terminal-border/60">
                  <tr>
                    <th className="p-3">SL Mult</th>
                    <th className="p-3">Target Mult</th>
                    <th className="p-3">R:R</th>
                    <th className="p-3">Min ADX</th>
                    <th className="p-3">Min Dir</th>
                    <th className="p-3 text-right">Trades</th>
                    <th className="p-3 text-right">Actual Win%</th>
                    <th className="p-3 text-right">BE Win%</th>
                    <th className="p-3 text-right">Edge vs BE</th>
                    <th className="p-3 text-right">Profit Factor</th>
                    <th className="p-3 text-right">Avg R</th>
                    <th className="p-3 text-right">Max DD</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-terminal-border/40">
                  {rowsToDisplay.map((r, i) => {
                    const hasPositiveEdge = r.edge_vs_breakeven_pct > 0;
                    const pf = r.profit_factor || 0;
                    return (
                      <tr key={i} className="hover:bg-terminal-hover/40 transition-colors">
                        <td className="p-3 text-amber-400 font-bold">{r.sl_mult}x</td>
                        <td className="p-3 text-cyan-400 font-bold">{r.target_mult}x</td>
                        <td className="p-3 text-terminal-subtext">{r.rr_ratio}:1</td>
                        <td className="p-3 text-terminal-subtext">{r.adx_min}</td>
                        <td className="p-3 text-terminal-subtext">{r.dir_score_min}</td>
                        <td className="p-3 text-right text-white font-semibold">{r.trades}</td>
                        <td className="p-3 text-right text-terminal-text">{r.win_rate_pct.toFixed(1)}%</td>
                        <td className="p-3 text-right text-terminal-muted">{r.breakeven_win_rate_pct.toFixed(1)}%</td>
                        <td className={`p-3 text-right font-bold ${hasPositiveEdge ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {hasPositiveEdge ? '+' : ''}{r.edge_vs_breakeven_pct.toFixed(1)}%
                        </td>
                        <td className={`p-3 text-right font-black ${pf >= 1.2 ? 'text-emerald-400' : pf >= 1.0 ? 'text-cyan-400' : 'text-rose-400'}`}>
                          {pf.toFixed(3)}
                        </td>
                        <td className="p-3 text-right text-terminal-subtext">{r.avg_R.toFixed(3)}R</td>
                        <td className="p-3 text-right text-rose-400/80">-{r.max_drawdown_points.toFixed(1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        <div className="glass-panel rounded-xl p-12 text-center border border-terminal-border">
          <SlidersHorizontal className="w-10 h-10 text-terminal-muted mx-auto mb-3 opacity-50" />
          <h4 className="text-sm font-semibold text-white">No Parameter Sweep Evaluated Yet</h4>
          <p className="text-xs text-terminal-muted mt-1 max-w-md mx-auto">
            Click &quot;Run Parameter Sweep&quot; to test SL, Target, ADX, and Direction-Score combinations against historical data.
          </p>
        </div>
      )}
    </div>
  );
};
