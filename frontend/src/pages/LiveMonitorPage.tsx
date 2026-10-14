import React from 'react';
import { LiveStateSnapshot } from '../types';
import { ConnectionMode } from '../hooks/useLiveStream';
import { SignalCard } from '../components/SignalCard';
import { ScoreBreakdown } from '../components/ScoreBreakdown';
import { CandleChart } from '../components/CandleChart';
import { ConnectionStrip } from '../components/ConnectionStrip';
import { OpenPositionCard } from '../components/OpenPositionCard';

interface LiveMonitorPageProps {
  snapshot: LiveStateSnapshot | null;
  connectionStatus: ConnectionMode;
  lastUpdated: string | null;
  onRefresh: () => void;
  onOpenTokenModal?: () => void;
}

export const LiveMonitorPage: React.FC<LiveMonitorPageProps> = ({
  snapshot,
  connectionStatus,
  lastUpdated,
  onRefresh,
  onOpenTokenModal,
}) => {
  return (
    <div className="space-y-6">
      {/* Connection & Diagnostics Strip */}
      <ConnectionStrip
        snapshot={snapshot}
        connectionStatus={connectionStatus}
        lastUpdated={lastUpdated}
        onRefresh={onRefresh}
        onOpenTokenModal={onOpenTokenModal}
      />

      {/* Top Section: Signal Hero & Active Position */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <SignalCard
            spot={snapshot?.spot || 0}
            atm={snapshot?.atm || null}
            signal={snapshot?.signal || 'WAIT'}
            confidence={snapshot?.confidence || 0}
            confidenceThreshold={snapshot?.confidence_threshold || 75}
            reason={snapshot?.reason || 'Awaiting live engine snapshot...'}
          />
        </div>

        <div className="lg:col-span-1 flex flex-col justify-between">
          <OpenPositionCard position={snapshot?.paper_position || null} />

          {/* Quick Risk Counters Mini-Card */}
          <div className="glass-panel rounded-xl p-4 border border-terminal-border mt-4">
            <span className="text-[11px] font-mono uppercase tracking-wider text-terminal-muted block mb-2">
              Today's Risk Snapshot
            </span>
            <div className="grid grid-cols-3 gap-2 text-center font-mono">
              <div className="bg-terminal-bg/50 p-2 rounded border border-terminal-border/50">
                <span className="text-[10px] text-terminal-muted block">Daily P&L</span>
                <span className={`text-xs font-bold ${
                  (snapshot?.risk_state?.daily_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}>
                  ₹{(snapshot?.risk_state?.daily_pnl || 0).toFixed(0)}
                </span>
              </div>
              <div className="bg-terminal-bg/50 p-2 rounded border border-terminal-border/50">
                <span className="text-[10px] text-terminal-muted block">Trades</span>
                <span className="text-xs font-bold text-white">
                  {snapshot?.risk_state?.trades_today || 0}/{snapshot?.risk_state?.max_trades_per_day || 6}
                </span>
              </div>
              <div className="bg-terminal-bg/50 p-2 rounded border border-terminal-border/50">
                <span className="text-[10px] text-terminal-muted block">Cooldown</span>
                <span className={`text-xs font-bold ${snapshot?.risk_state?.cooldown_active ? 'text-rose-400 animate-pulse' : 'text-emerald-400'}`}>
                  {snapshot?.risk_state?.cooldown_active ? `${snapshot.risk_state.cooldown_remaining_seconds}s` : 'OFF'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Candlestick Chart (1-min with EMA20/EMA50) */}
      <div className="h-[400px]">
        <CandleChart
          candles={snapshot?.candles || []}
          spotPrice={snapshot?.spot}
        />
      </div>

      {/* Multi-Factor Score Breakdown */}
      <ScoreBreakdown
        technical={snapshot?.technical || {}}
        momentum={snapshot?.momentum || {}}
        options={snapshot?.options || {}}
        htfTrend={snapshot?.htf_trend || null}
        epm={snapshot?.epm || { score: 0, bias: 'WAIT', volume_score: 0, iv_skew: 0, underlying_trend_score: 0 }}
        weights={snapshot?.weights || { technical: 0.40, momentum: 0.25, options: 0.35 }}
      />
    </div>
  );
};
