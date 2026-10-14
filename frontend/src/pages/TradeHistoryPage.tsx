import React, { useState, useEffect, useCallback } from 'react';
import { PaperPosition, TradeStatsSummary, TradeLogRow } from '../types';
import { OpenPositionCard } from '../components/OpenPositionCard';
import { EquityCurveChart } from '../components/EquityCurveChart';
import { Download, Filter, RefreshCw, ArrowUpRight, ArrowDownRight, Award, TrendingUp, TrendingDown, DollarSign } from 'lucide-react';

interface TradeHistoryPageProps {
  currentPosition: PaperPosition | null;
}

export const TradeHistoryPage: React.FC<TradeHistoryPageProps> = ({ currentPosition }) => {
  const [trades, setTrades] = useState<TradeLogRow[]>([]);
  const [stats, setStats] = useState<TradeStatsSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [exitReasonFilter, setExitReasonFilter] = useState<string>('ALL');
  const [directionFilter, setDirectionFilter] = useState<string>('ALL');

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch('/api/trades/stats');
      if (res.ok) {
        const data: TradeStatsSummary = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error('Failed to load trade stats:', e);
    }
  }, []);

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams({
        page: String(page),
        page_size: '25',
      });
      if (exitReasonFilter !== 'ALL') query.set('exit_reason', exitReasonFilter);
      if (directionFilter !== 'ALL') query.set('direction', directionFilter);

      const res = await fetch(`/api/trades?${query.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setTrades(data.items || []);
        setTotalPages(data.total_pages || 1);
        setTotalCount(data.total || 0);
      }
    } catch (e) {
      console.error('Failed to load trades:', e);
    } finally {
      setLoading(false);
    }
  }, [page, exitReasonFilter, directionFilter]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  const handleExport = () => {
    window.location.href = '/api/trades/export';
  };

  return (
    <div className="space-y-6">
      {/* Active Position Card */}
      <div>
        <h3 className="text-xs font-mono uppercase tracking-wider text-terminal-muted mb-2">
          Current Position
        </h3>
        <OpenPositionCard position={currentPosition} />
      </div>

      {/* Performance Stats Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="glass-panel rounded-xl p-3 border border-terminal-border">
          <span className="text-[10px] font-mono uppercase text-terminal-muted block">Closed Trades</span>
          <span className="text-xl font-bold font-mono text-white">{stats?.total_trades || 0}</span>
          <span className="text-[10px] text-terminal-muted block">
            {stats?.wins || 0} Wins • {stats?.losses || 0} Losses
          </span>
        </div>

        <div className="glass-panel rounded-xl p-3 border border-terminal-border">
          <span className="text-[10px] font-mono uppercase text-terminal-muted block">Win Rate</span>
          <span className={`text-xl font-bold font-mono ${
            (stats?.win_rate_pct || 0) >= 50 ? 'text-emerald-400' : 'text-amber-400'
          }`}>
            {(stats?.win_rate_pct || 0).toFixed(1)}%
          </span>
          <span className="text-[10px] text-terminal-muted block">Net P&L &gt; 0</span>
        </div>

        <div className="glass-panel rounded-xl p-3 border border-terminal-border">
          <span className="text-[10px] font-mono uppercase text-terminal-muted block">Profit Factor</span>
          <span className={`text-xl font-bold font-mono ${
            stats?.profit_factor && stats.profit_factor >= 1.2 ? 'text-emerald-400' : 'text-terminal-text'
          }`}>
            {stats?.profit_factor ? stats.profit_factor.toFixed(2) : '--'}
          </span>
          <span className="text-[10px] text-terminal-muted block">Gross Win / Gross Loss</span>
        </div>

        <div className="glass-panel rounded-xl p-3 border border-terminal-border">
          <span className="text-[10px] font-mono uppercase text-terminal-muted block">Total Gross P&L</span>
          <span className={`text-xl font-bold font-mono ${
            (stats?.total_gross_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
          }`}>
            ₹{(stats?.total_gross_pnl || 0).toFixed(0)}
          </span>
          <span className="text-[10px] text-terminal-muted block">Pre-cost execution</span>
        </div>

        <div className="glass-panel rounded-xl p-3 border border-terminal-border">
          <span className="text-[10px] font-mono uppercase text-terminal-muted block">F&O Costs Subtracted</span>
          <span className="text-xl font-bold font-mono text-rose-400">
            -₹{(stats?.total_cost || 0).toFixed(0)}
          </span>
          <span className="text-[10px] text-terminal-muted block">STT/Brokerage/GST model</span>
        </div>

        <div className="glass-panel rounded-xl p-3 border border-terminal-border">
          <span className="text-[10px] font-mono uppercase text-terminal-muted block">Net Realized P&L</span>
          <span className={`text-xl font-bold font-mono ${
            (stats?.total_net_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
          }`}>
            ₹{(stats?.total_net_pnl || 0).toFixed(0)}
          </span>
          <span className="text-[10px] text-terminal-muted block">
            Max DD: ₹{(stats?.max_drawdown || 0).toFixed(0)}
          </span>
        </div>
      </div>

      {/* Equity Curve Line Chart */}
      <EquityCurveChart
        data={stats?.equity_curve || []}
        title="Realized Paper P&L Equity Curve (trades_log.csv)"
        unitLabel="INR"
      />

      {/* Closed Trades Table Card */}
      <div className="glass-panel rounded-xl border border-terminal-border overflow-hidden">
        {/* Table Header / Action Toolbar */}
        <div className="p-4 border-b border-terminal-border/60 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h4 className="text-xs font-semibold text-white uppercase tracking-wider">
              Closed Trade Ledger
            </h4>
            <span className="text-[11px] font-mono text-terminal-muted">
              ({totalCount} records in trades_log.csv)
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Filter by exit reason */}
            <div className="flex items-center gap-1.5 text-xs text-terminal-muted">
              <Filter className="w-3.5 h-3.5 text-cyan-400" />
              <span>Exit:</span>
              <select
                value={exitReasonFilter}
                onChange={(e) => { setExitReasonFilter(e.target.value); setPage(1); }}
                className="bg-terminal-bg border border-terminal-border rounded px-2 py-1 text-white text-xs font-mono"
              >
                <option value="ALL">All Exits</option>
                <option value="TARGET">TARGET</option>
                <option value="SL">SL</option>
                <option value="TRAIL">TRAIL</option>
                <option value="TIME">TIME</option>
              </select>
            </div>

            {/* Filter by direction */}
            <div className="flex items-center gap-1.5 text-xs text-terminal-muted">
              <span>Dir:</span>
              <select
                value={directionFilter}
                onChange={(e) => { setDirectionFilter(e.target.value); setPage(1); }}
                className="bg-terminal-bg border border-terminal-border rounded px-2 py-1 text-white text-xs font-mono"
              >
                <option value="ALL">All Dirs</option>
                <option value="CALL">CALL</option>
                <option value="PUT">PUT</option>
              </select>
            </div>

            {/* Export CSV Button */}
            <button
              onClick={handleExport}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950 text-cyan-300 border border-cyan-800 hover:bg-cyan-900 transition-colors text-xs font-medium"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export CSV</span>
            </button>

            <button
              onClick={() => { fetchTrades(); fetchStats(); }}
              className="p-1.5 rounded-lg bg-terminal-hover text-terminal-subtext hover:text-white"
              title="Refresh trade log"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Table Content */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-terminal-surface text-terminal-muted border-b border-terminal-border/60">
              <tr>
                <th className="p-3">Time (Entry → Exit)</th>
                <th className="p-3">Signal</th>
                <th className="p-3">Contract</th>
                <th className="p-3 text-right">Lots</th>
                <th className="p-3 text-right">Entry / Exit</th>
                <th className="p-3 text-right">SL / Target</th>
                <th className="p-3 text-right">Gross P&L</th>
                <th className="p-3 text-right">Cost</th>
                <th className="p-3 text-right">Net P&L</th>
                <th className="p-3 text-center">Exit Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-terminal-border/40">
              {loading ? (
                <tr>
                  <td colSpan={10} className="p-6 text-center text-terminal-muted">
                    Loading trade records from trades_log.csv...
                  </td>
                </tr>
              ) : trades.length === 0 ? (
                <tr>
                  <td colSpan={10} className="p-8 text-center text-terminal-muted">
                    No closed paper trades match the selected criteria.
                  </td>
                </tr>
              ) : (
                trades.map((t, idx) => {
                  const net = parseFloat(t.net_pnl || '0');
                  const gross = parseFloat(t.gross_pnl || '0');
                  const cost = parseFloat(t.cost || '0');
                  const isPositive = net > 0;
                  const isCall = t.direction === 'CALL' || t.type === 'CE';

                  return (
                    <tr key={idx} className="hover:bg-terminal-hover/40 transition-colors">
                      <td className="p-3 whitespace-nowrap text-terminal-subtext">
                        <span>{t.entry_time || '--'}</span>
                        <span className="text-terminal-muted"> → </span>
                        <span>{t.exit_time || '--'}</span>
                      </td>

                      <td className="p-3 whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1 font-bold ${
                          isCall ? 'text-emerald-400' : 'text-rose-400'
                        }`}>
                          {isCall ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                          {t.direction || t.signal}
                        </span>
                      </td>

                      <td className="p-3 whitespace-nowrap text-white font-semibold">
                        {t.strike} {t.type}
                      </td>

                      <td className="p-3 whitespace-nowrap text-right text-terminal-subtext">
                        {t.lots}
                      </td>

                      <td className="p-3 whitespace-nowrap text-right">
                        <span>₹{parseFloat(t.entry || '0').toFixed(1)}</span>
                        <span className="text-terminal-muted"> / </span>
                        <span className="text-white font-semibold">₹{parseFloat(t.exit || '0').toFixed(1)}</span>
                      </td>

                      <td className="p-3 whitespace-nowrap text-right text-terminal-muted">
                        <span>₹{parseFloat(t.sl || '0').toFixed(1)}</span>
                        <span> / </span>
                        <span>₹{parseFloat(t.target || '0').toFixed(1)}</span>
                      </td>

                      <td className="p-3 whitespace-nowrap text-right font-medium text-terminal-subtext">
                        {gross > 0 ? '+' : ''}{gross.toFixed(2)}
                      </td>

                      <td className="p-3 whitespace-nowrap text-right text-rose-400/80">
                        -{cost.toFixed(2)}
                      </td>

                      <td className={`p-3 whitespace-nowrap text-right font-bold ${
                        isPositive ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {isPositive ? '+' : ''}{net.toFixed(2)} INR
                      </td>

                      <td className="p-3 whitespace-nowrap text-center">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                          t.exit_reason === 'TARGET' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                          t.exit_reason === 'SL' ? 'bg-rose-950 text-rose-400 border border-rose-800' :
                          t.exit_reason === 'TRAIL' ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' :
                          'bg-slate-800 text-slate-300'
                        }`}>
                          {t.exit_reason || 'MANUAL'}
                        </span>
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
            <span>
              Page {page} of {totalPages}
            </span>
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
    </div>
  );
};
