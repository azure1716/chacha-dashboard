import React, { useState, useEffect, useCallback } from 'react';
import { SignalLogRow } from '../types';
import { Filter, RefreshCw, ArrowUpRight, ArrowDownRight, PauseCircle, Search, HelpCircle, Eye } from 'lucide-react';
import { apiUrl } from '../api';

export const SignalsAuditPage: React.FC = () => {
  const [signals, setSignals] = useState<SignalLogRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [signalFilter, setSignalFilter] = useState<string>('ALL');
  const [selectedRow, setSelectedRow] = useState<SignalLogRow | null>(null);

  const fetchSignals = useCallback(async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams({
        page: String(page),
        page_size: '30',
      });
      if (signalFilter !== 'ALL') query.set('signal', signalFilter);

      const res = await fetch(apiUrl(`/api/signals?${query.toString()}`));
      if (res.ok) {
        const data = await res.json();
        setSignals(data.items || []);
        setTotalPages(data.total_pages || 1);
        setTotalCount(data.total || 0);
      }
    } catch (e) {
      console.error('Failed to load signals:', e);
    } finally {
      setLoading(false);
    }
  }, [page, signalFilter]);

  useEffect(() => {
    fetchSignals();
  }, [fetchSignals]);

  return (
    <div className="space-y-6">
      {/* Header Info Banner */}
      <div className="glass-panel rounded-xl p-5 border border-terminal-border flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Search className="w-5 h-5 text-cyan-400" />
            <h2 className="text-base font-bold text-white uppercase tracking-wider">
              Signals Audit Log (Tick-by-Tick Audit)
            </h2>
          </div>
          <p className="text-xs text-terminal-muted mt-1">
            Complete record from <code>signals_log.csv</code>. Every tick is preserved to explain exactly why a trade was taken or blocked.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-terminal-muted">
            <Filter className="w-3.5 h-3.5 text-cyan-400" />
            <span>Signal:</span>
            <select
              value={signalFilter}
              onChange={(e) => { setSignalFilter(e.target.value); setPage(1); }}
              className="bg-terminal-bg border border-terminal-border rounded px-2.5 py-1 text-white text-xs font-mono"
            >
              <option value="ALL">All Signals</option>
              <option value="BUY CALL">BUY CALL</option>
              <option value="BUY PUT">BUY PUT</option>
              <option value="WAIT">WAIT</option>
            </select>
          </div>

          <button
            onClick={fetchSignals}
            className="p-1.5 rounded-lg bg-terminal-hover text-terminal-subtext hover:text-white"
            title="Refresh signals log"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Table Card */}
      <div className="glass-panel rounded-xl border border-terminal-border overflow-hidden">
        <div className="p-3 border-b border-terminal-border/60 flex items-center justify-between text-xs text-terminal-muted">
          <span>Total records logged: <strong>{totalCount}</strong></span>
          <span>Showing page {page} of {totalPages}</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-terminal-surface text-terminal-muted border-b border-terminal-border/60">
              <tr>
                <th className="p-3">Timestamp (IST)</th>
                <th className="p-3 text-right">Spot</th>
                <th className="p-3">Signal</th>
                <th className="p-3 text-right">Conf.</th>
                <th className="p-3 text-right">Tech Score</th>
                <th className="p-3">Trend (ADX)</th>
                <th className="p-3 text-right">Mom.</th>
                <th className="p-3 text-right">Opt. Press</th>
                <th className="p-3">HTF</th>
                <th className="p-3">EPM (Beta)</th>
                <th className="p-3">Reason (Decision Rationale)</th>
                <th className="p-3 text-center">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-terminal-border/40">
              {loading ? (
                <tr>
                  <td colSpan={12} className="p-8 text-center text-terminal-muted">
                    Loading tick signals from signals_log.csv...
                  </td>
                </tr>
              ) : signals.length === 0 ? (
                <tr>
                  <td colSpan={12} className="p-8 text-center text-terminal-muted">
                    No signals found matching the current filter.
                  </td>
                </tr>
              ) : (
                signals.map((s, idx) => {
                  const isCall = s.signal === 'BUY CALL';
                  const isPut = s.signal === 'BUY PUT';
                  const isWait = s.signal === 'WAIT';

                  return (
                    <tr key={idx} className="hover:bg-terminal-hover/40 transition-colors">
                      <td className="p-3 whitespace-nowrap text-terminal-subtext">
                        {s.timestamp}
                      </td>

                      <td className="p-3 whitespace-nowrap text-right font-bold text-white">
                        {parseFloat(s.spot || '0').toFixed(2)}
                      </td>

                      <td className="p-3 whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
                          isCall ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                          isPut ? 'bg-rose-950 text-rose-400 border border-rose-800' :
                          'bg-slate-900 text-slate-300 border border-slate-700'
                        }`}>
                          {isCall && <ArrowUpRight className="w-3 h-3" />}
                          {isPut && <ArrowDownRight className="w-3 h-3" />}
                          {isWait && <PauseCircle className="w-3 h-3 text-slate-400" />}
                          {s.signal}
                        </span>
                      </td>

                      <td className="p-3 whitespace-nowrap text-right font-semibold text-white">
                        {parseFloat(s.confidence || '0').toFixed(1)}%
                      </td>

                      <td className="p-3 whitespace-nowrap text-right text-terminal-subtext">
                        {s.technical_score || '--'}
                      </td>

                      <td className="p-3 whitespace-nowrap text-terminal-subtext">
                        <span>{s.trend || '--'}</span>
                        {s.adx && <span className="text-terminal-muted text-[10px] ml-1">({parseFloat(s.adx).toFixed(1)})</span>}
                      </td>

                      <td className="p-3 whitespace-nowrap text-right text-terminal-subtext">
                        {s.momentum_score || '--'}
                      </td>

                      <td className="p-3 whitespace-nowrap text-right text-terminal-subtext">
                        <span>{s.option_score ? parseFloat(s.option_score).toFixed(1) : '--'}</span>
                        <span className="text-[10px] text-terminal-muted ml-1">({s.option_bias || '?'})</span>
                      </td>

                      <td className="p-3 whitespace-nowrap">
                        <span className={`text-[10px] font-bold ${
                          s.htf_trend === 'BULLISH' ? 'text-emerald-400' :
                          s.htf_trend === 'BEARISH' ? 'text-rose-400' : 'text-slate-400'
                        }`}>
                          {s.htf_trend || '--'}
                        </span>
                      </td>

                      <td className="p-3 whitespace-nowrap">
                        {s.epm_score ? (
                          <span className="text-purple-300 font-bold">
                            {parseFloat(s.epm_score).toFixed(1)} <span className="text-[10px] font-normal text-purple-400">({s.epm_bias})</span>
                          </span>
                        ) : (
                          <span className="text-terminal-muted">--</span>
                        )}
                      </td>

                      <td className="p-3 max-w-[280px] truncate text-terminal-muted" title={s.reason}>
                        {s.reason}
                      </td>

                      <td className="p-3 text-center">
                        <button
                          onClick={() => setSelectedRow(s)}
                          className="p-1 rounded bg-terminal-hover text-terminal-subtext hover:text-cyan-400 transition-colors"
                          title="Inspect tick parameters"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Toolbar */}
        {totalPages > 1 && (
          <div className="p-3 border-t border-terminal-border/60 flex items-center justify-between text-xs text-terminal-muted">
            <span>Page {page} of {totalPages}</span>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
                className="px-2.5 py-1 rounded bg-terminal-hover text-terminal-text disabled:opacity-40"
              >
                Previous
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                className="px-2.5 py-1 rounded bg-terminal-hover text-terminal-text disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Row Inspector Modal */}
      {selectedRow && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-panel rounded-xl max-w-lg w-full border border-cyan-500/40 p-5 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-terminal-border">
              <h4 className="text-xs font-bold text-white uppercase font-mono">
                Tick Audit Inspector • {selectedRow.timestamp}
              </h4>
              <button
                onClick={() => setSelectedRow(null)}
                className="text-terminal-muted hover:text-white text-xs font-mono"
              >
                ✕ Close
              </button>
            </div>

            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between py-1 border-b border-terminal-border/40">
                <span className="text-terminal-muted">Signal / Confidence:</span>
                <span className="font-bold text-white">{selectedRow.signal} ({selectedRow.confidence}%)</span>
              </div>
              <div className="flex justify-between py-1 border-b border-terminal-border/40">
                <span className="text-terminal-muted">NIFTY Spot:</span>
                <span className="font-bold text-white">₹{selectedRow.spot}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-terminal-border/40">
                <span className="text-terminal-muted">Reason:</span>
                <span className="text-amber-300 font-semibold">{selectedRow.reason}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-terminal-border/40">
                <span className="text-terminal-muted">Technical Trend / ADX:</span>
                <span className="text-white">{selectedRow.trend} ({selectedRow.trend_strength}) • ADX {selectedRow.adx}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-terminal-border/40">
                <span className="text-terminal-muted">Momentum Score:</span>
                <span className="text-white">{selectedRow.momentum_score}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-terminal-border/40">
                <span className="text-terminal-muted">Option Pressure Score:</span>
                <span className="text-white">{selectedRow.option_score} ({selectedRow.option_bias})</span>
              </div>
              <div className="flex justify-between py-1 border-b border-terminal-border/40">
                <span className="text-terminal-muted">Higher Timeframe (5-min):</span>
                <span className="text-white">{selectedRow.htf_trend}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-terminal-border/40">
                <span className="text-terminal-muted">EPM (Beta):</span>
                <span className="text-purple-300">{selectedRow.epm_score || '--'} ({selectedRow.epm_bias || '--'})</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-terminal-muted">ATR% of Spot:</span>
                <span className="text-white">{selectedRow.atr_pct}%</span>
              </div>
            </div>

            <div className="pt-2 text-[11px] text-terminal-muted">
              Note: WAIT is the default, healthy state when ADX chop gate, multi-factor threshold, or HTF agreement blocks trading.
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
