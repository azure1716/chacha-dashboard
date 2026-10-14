import React, { useState, useEffect } from 'react';
import { BacktestJobResult } from '../types';
import { EquityCurveChart } from '../components/EquityCurveChart';
import { FlaskConical, Play, Upload, AlertTriangle, ShieldCheck, CheckCircle2, Loader2, Info } from 'lucide-react';
import { apiUrl } from '../api';

interface DatasetItem {
  id: string;
  name: string;
  path: string;
  size_bytes: number;
  is_synthetic: boolean;
  description?: string;
}

export const BacktestLabPage: React.FC = () => {
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>('synthetic');
  const [slMultiplier, setSlMultiplier] = useState<number>(1.2);
  const [targetMultiplier, setTargetMultiplier] = useState<number>(2.4);
  const [minAdx, setMinAdx] = useState<number>(18);
  const [minDirectionScore, setMinDirectionScore] = useState<number>(30);
  const [requireHtf, setRequireHtf] = useState<boolean>(true);
  const [htfFactor, setHtfFactor] = useState<number>(5);

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestJobResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch available datasets
  const fetchDatasets = async () => {
    try {
      const res = await fetch(apiUrl('/api/backtest/datasets'));
      if (res.ok) {
        const data = await res.json();
        setDatasets(data);
      }
    } catch (e) {
      console.error('Failed to fetch datasets:', e);
    }
  };

  useEffect(() => {
    fetchDatasets();
  }, []);

  // Poll active backtest job
  useEffect(() => {
    if (!activeJobId) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(apiUrl(`/api/backtest/jobs/${activeJobId}`));
        if (res.ok) {
          const job = await res.json();
          setJobStatus(job.status);
          if (job.status === 'COMPLETED') {
            setResult(job.result);
            setActiveJobId(null);
            clearInterval(interval);
          } else if (job.status === 'FAILED') {
            setError(job.error || 'Backtest job failed');
            setActiveJobId(null);
            clearInterval(interval);
          }
        }
      } catch (e: any) {
        console.error('Error polling backtest job:', e);
      }
    }, 500);

    return () => clearInterval(interval);
  }, [activeJobId]);

  const handleStartBacktest = async () => {
    setError(null);
    setJobStatus('PENDING');
    setResult(null);

    try {
      const res = await fetch(apiUrl('/api/backtest/run'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          csv_path: selectedDataset,
          sl_multiplier: slMultiplier,
          target_multiplier: targetMultiplier,
          min_adx: minAdx,
          min_direction_score: minDirectionScore,
          require_htf_agreement: requireHtf,
          htf_factor: htfFactor,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setActiveJobId(data.job_id);
      } else {
        const err = await res.json();
        setError(err.detail || 'Failed to start backtest');
        setJobStatus(null);
      }
    } catch (e: any) {
      setError(e.message || 'Error triggering backtest');
      setJobStatus(null);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(apiUrl('/api/backtest/upload'), {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const uploaded = await res.json();
        await fetchDatasets();
        setSelectedDataset(uploaded.path);
      }
    } catch (err: any) {
      alert('Upload failed: ' + err.message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner with Script Caveat */}
      <div className="p-4 rounded-xl bg-slate-900 border border-terminal-border flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-cyan-400" />
            <h2 className="text-base font-bold text-white uppercase tracking-wider">
              Offline Strategy Backtest Lab (nifty_algo_backtest.py)
            </h2>
          </div>
          <p className="text-xs text-terminal-muted mt-1">
            Replays 1-minute historical candles bar-by-bar with zero lookahead bias to validate the directional core.
          </p>
        </div>

        <div className="text-xs text-amber-300 font-mono bg-amber-950/40 border border-amber-800/60 px-3 py-1.5 rounded-lg flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
          <span>Index points simulation • No transaction costs</span>
        </div>
      </div>

      {/* Backtest Configuration Form */}
      <div className="glass-panel rounded-xl p-5 border border-terminal-border">
        <h3 className="text-xs font-mono uppercase tracking-wider text-white mb-4">
          Simulation Parameters
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono mb-4">
          {/* Dataset Selector */}
          <div className="sm:col-span-2 space-y-1">
            <label className="text-terminal-muted block">Historical OHLC Dataset:</label>
            <div className="flex gap-2">
              <select
                value={selectedDataset}
                onChange={(e) => setSelectedDataset(e.target.value)}
                className="flex-1 bg-terminal-bg border border-terminal-border rounded-lg px-3 py-2 text-white text-xs font-mono"
              >
                {datasets.map((d) => (
                  <option key={d.id} value={d.path}>
                    {d.name} {d.is_synthetic ? '(Harness Only)' : ''}
                  </option>
                ))}
              </select>

              <label className="cursor-pointer px-3 py-2 rounded-lg bg-terminal-hover text-terminal-subtext hover:text-white border border-terminal-border flex items-center gap-1.5">
                <Upload className="w-3.5 h-3.5" />
                <span>Upload CSV</span>
                <input type="file" accept=".csv" onChange={handleFileUpload} className="hidden" />
              </label>
            </div>
          </div>

          {/* SL Multiplier */}
          <div className="space-y-1">
            <label className="text-terminal-muted block">SL Multiplier (ATR):</label>
            <input
              type="number"
              step="0.1"
              value={slMultiplier}
              onChange={(e) => setSlMultiplier(parseFloat(e.target.value))}
              className="w-full bg-terminal-bg border border-terminal-border rounded-lg px-3 py-2 text-white font-mono text-xs"
            />
          </div>

          {/* Target Multiplier */}
          <div className="space-y-1">
            <label className="text-terminal-muted block">Target Multiplier (ATR):</label>
            <input
              type="number"
              step="0.1"
              value={targetMultiplier}
              onChange={(e) => setTargetMultiplier(parseFloat(e.target.value))}
              className="w-full bg-terminal-bg border border-terminal-border rounded-lg px-3 py-2 text-white font-mono text-xs"
            />
          </div>

          {/* Min ADX */}
          <div className="space-y-1">
            <label className="text-terminal-muted block">Min ADX (Chop Gate):</label>
            <input
              type="number"
              value={minAdx}
              onChange={(e) => setMinAdx(parseFloat(e.target.value))}
              className="w-full bg-terminal-bg border border-terminal-border rounded-lg px-3 py-2 text-white font-mono text-xs"
            />
          </div>

          {/* Min Direction Score */}
          <div className="space-y-1">
            <label className="text-terminal-muted block">Min Direction Score:</label>
            <input
              type="number"
              value={minDirectionScore}
              onChange={(e) => setMinDirectionScore(parseFloat(e.target.value))}
              className="w-full bg-terminal-bg border border-terminal-border rounded-lg px-3 py-2 text-white font-mono text-xs"
            />
          </div>

          {/* HTF Agreement */}
          <div className="space-y-1">
            <label className="text-terminal-muted block">HTF (5-min) Agreement:</label>
            <select
              value={requireHtf ? 'true' : 'false'}
              onChange={(e) => setRequireHtf(e.target.value === 'true')}
              className="w-full bg-terminal-bg border border-terminal-border rounded-lg px-3 py-2 text-white font-mono text-xs"
            >
              <option value="true">Required (Veto on)</option>
              <option value="false">Ignored (Veto off)</option>
            </select>
          </div>

          {/* HTF Factor */}
          <div className="space-y-1">
            <label className="text-terminal-muted block">HTF Resampling Factor:</label>
            <input
              type="number"
              value={htfFactor}
              onChange={(e) => setHtfFactor(parseInt(e.target.value, 10))}
              className="w-full bg-terminal-bg border border-terminal-border rounded-lg px-3 py-2 text-white font-mono text-xs"
            />
          </div>
        </div>

        {/* Action Button */}
        <div className="flex items-center justify-between pt-3 border-t border-terminal-border/60">
          <div className="text-xs text-terminal-muted font-mono">
            {selectedDataset === 'synthetic' && (
              <span className="text-amber-400">
                ⚠ Running on synthetic dataset — harness validation only.
              </span>
            )}
          </div>

          <button
            onClick={handleStartBacktest}
            disabled={activeJobId !== null}
            className="flex items-center gap-2 px-5 py-2 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 text-white font-medium text-xs hover:from-cyan-500 hover:to-blue-500 transition-all disabled:opacity-50 shadow-md shadow-cyan-500/20"
          >
            {activeJobId ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Running Simulation...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                <span>Execute Backtest</span>
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-xs font-mono">
          Backtest Error: {error}
        </div>
      )}

      {/* Results Section */}
      {result ? (
        <div className="space-y-6">
          {/* Prominent Caveats Alert Box */}
          <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/40 text-xs space-y-2">
            <div className="flex items-center gap-2 text-amber-300 font-bold uppercase tracking-wider">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>Backtest Methodology & Strategy Caveats (Preserved Verbatim)</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-amber-200/90 font-mono text-[11px] leading-relaxed">
              {result.caveats.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
            <div className="text-xs text-amber-300/80 pt-2 border-t border-amber-500/20">
              <strong>Header Reality Check:</strong> {result.header_warning}
            </div>
          </div>

          {/* Results Summary Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 font-mono">
            <div className="glass-panel rounded-xl p-3 border border-terminal-border">
              <span className="text-[10px] text-terminal-muted block">Total Trades</span>
              <span className="text-xl font-bold text-white">{result.stats.trades}</span>
            </div>

            <div className="glass-panel rounded-xl p-3 border border-terminal-border">
              <span className="text-[10px] text-terminal-muted block">Win Rate</span>
              <span className={`text-xl font-bold ${result.stats.win_rate_pct >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                {result.stats.win_rate_pct.toFixed(1)}%
              </span>
            </div>

            <div className="glass-panel rounded-xl p-3 border border-terminal-border">
              <span className="text-[10px] text-terminal-muted block">Profit Factor</span>
              <span className={`text-xl font-bold ${result.stats.profit_factor && result.stats.profit_factor >= 1.2 ? 'text-emerald-400' : 'text-white'}`}>
                {result.stats.profit_factor ? result.stats.profit_factor.toFixed(2) : '--'}
              </span>
            </div>

            <div className="glass-panel rounded-xl p-3 border border-terminal-border">
              <span className="text-[10px] text-terminal-muted block">Avg R</span>
              <span className="text-xl font-bold text-cyan-400">{result.stats.avg_R.toFixed(2)}R</span>
            </div>

            <div className="glass-panel rounded-xl p-3 border border-terminal-border">
              <span className="text-[10px] text-terminal-muted block">Total Index Pts</span>
              <span className={`text-xl font-bold ${result.stats.total_pnl_points >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {result.stats.total_pnl_points > 0 ? '+' : ''}{result.stats.total_pnl_points.toFixed(1)}
              </span>
            </div>

            <div className="glass-panel rounded-xl p-3 border border-terminal-border">
              <span className="text-[10px] text-terminal-muted block">Max Drawdown</span>
              <span className="text-xl font-bold text-rose-400">-{result.stats.max_drawdown_points.toFixed(1)} pts</span>
            </div>

            <div className="glass-panel rounded-xl p-3 border border-terminal-border">
              <span className="text-[10px] text-terminal-muted block">Exit Reasons</span>
              <span className="text-xs text-terminal-subtext block">
                Tgt: {result.exit_reasons.TARGET || 0} • SL: {result.exit_reasons.SL || 0}
              </span>
            </div>
          </div>

          {/* Equity Curve Line Chart */}
          <EquityCurveChart
            data={result.equity_curve}
            title={`Index Points Equity Curve (${result.dataset_name})`}
            unitLabel="Index Pts"
          />
        </div>
      ) : (
        <div className="glass-panel rounded-xl p-12 text-center border border-terminal-border">
          <FlaskConical className="w-10 h-10 text-terminal-muted mx-auto mb-3 opacity-50" />
          <h4 className="text-sm font-semibold text-white">No Backtest Results Yet</h4>
          <p className="text-xs text-terminal-muted mt-1 max-w-md mx-auto">
            Choose a dataset above (or leave Synthetic data selected for a quick harness sanity test) and click &quot;Execute Backtest&quot;.
          </p>
        </div>
      )}
    </div>
  );
};
