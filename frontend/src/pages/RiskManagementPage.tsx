import React, { useState, useEffect } from 'react';
import { RiskState } from '../types';
import { ShieldAlert, AlertTriangle, Lock, Clock, DollarSign, Scale, Percent, Zap } from 'lucide-react';

interface RiskManagementPageProps {
  riskState: RiskState | null;
}

export const RiskManagementPage: React.FC<RiskManagementPageProps> = ({ riskState }) => {
  const [cooldownRemaining, setCooldownRemaining] = useState<number>(0);

  useEffect(() => {
    if (!riskState) return;
    setCooldownRemaining(riskState.cooldown_remaining_seconds || 0);

    const timer = setInterval(() => {
      setCooldownRemaining(prev => Math.max(0, prev - 1));
    }, 1000);

    return () => clearInterval(timer);
  }, [riskState?.cooldown_remaining_seconds]);

  const dailyPnl = riskState?.daily_pnl || 0;
  const maxLoss = riskState?.max_daily_loss || 3000;
  const lossUsedPct = Math.min(100, Math.max(0, (Math.abs(Math.min(0, dailyPnl)) / maxLoss) * 100));

  const tradesToday = riskState?.trades_today || 0;
  const maxTrades = riskState?.max_trades_per_day || 6;
  const tradesPct = Math.min(100, (tradesToday / maxTrades) * 100);

  const consecLosses = riskState?.consecutive_losses || 0;
  const maxConsecLosses = riskState?.max_consecutive_losses || 3;

  return (
    <div className="space-y-6">
      {/* Risk Header */}
      <div className="glass-panel rounded-xl p-5 border border-terminal-border flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-rose-400" />
            <h2 className="text-base font-bold text-white uppercase tracking-wider">
              Central Risk Management & Circuit Breakers
            </h2>
          </div>
          <p className="text-xs text-terminal-muted mt-1">
            Hard constraints evaluated by <code>should_trade_now()</code> in <code>nifty_algo_core.py</code> before every paper entry.
          </p>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs px-3 py-1.5 rounded-lg bg-terminal-bg border border-terminal-border">
          <Lock className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-terminal-subtext">Parameters are read-only</span>
        </div>
      </div>

      {/* Progress Bars & Circuit Breakers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* 1. Daily Max Loss Limit */}
        <div className="glass-panel rounded-xl p-5 border border-terminal-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono uppercase tracking-wider text-terminal-muted">
                Daily Max Loss Limit
              </span>
              <span className="text-xs font-mono text-rose-400 font-bold">
                Cap: ₹{maxLoss.toLocaleString('en-IN')}
              </span>
            </div>

            <div className="flex items-baseline justify-between mb-2">
              <span className={`text-2xl font-bold font-mono ${dailyPnl < 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                {dailyPnl >= 0 ? '+' : ''}₹{dailyPnl.toFixed(2)}
              </span>
              <span className="text-xs font-mono text-terminal-subtext">
                {lossUsedPct.toFixed(1)}% of limit consumed
              </span>
            </div>

            {/* Progress Bar */}
            <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden p-0.5 border border-terminal-border">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  lossUsedPct >= 80 ? 'bg-rose-500 animate-pulse' :
                  lossUsedPct >= 50 ? 'bg-amber-500' : 'bg-emerald-500'
                }`}
                style={{ width: `${lossUsedPct}%` }}
              />
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-terminal-border/60 text-[11px] text-terminal-muted">
            Halts all new entries for the rest of the day if daily realized net P&L breaches -₹{maxLoss}.
          </div>
        </div>

        {/* 2. Trades Today Limit */}
        <div className="glass-panel rounded-xl p-5 border border-terminal-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono uppercase tracking-wider text-terminal-muted">
                Trades Today
              </span>
              <span className="text-xs font-mono text-cyan-400 font-bold">
                Cap: {maxTrades} trades
              </span>
            </div>

            <div className="flex items-baseline justify-between mb-2">
              <span className="text-2xl font-bold font-mono text-white">
                {tradesToday} <span className="text-xs text-terminal-muted">/ {maxTrades}</span>
              </span>
              <span className="text-xs font-mono text-terminal-subtext">
                {maxTrades - tradesToday} remaining
              </span>
            </div>

            {/* Progress Bar */}
            <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden p-0.5 border border-terminal-border">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  tradesToday >= maxTrades ? 'bg-rose-500' :
                  tradesToday >= maxTrades - 2 ? 'bg-amber-500' : 'bg-cyan-500'
                }`}
                style={{ width: `${tradesPct}%` }}
              />
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-terminal-border/60 text-[11px] text-terminal-muted">
            Anti-overtrading limit. Resets at start of each trading session.
          </div>
        </div>

        {/* 3. Consecutive Loss Cooldown */}
        <div className="glass-panel rounded-xl p-5 border border-terminal-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono uppercase tracking-wider text-terminal-muted">
                Consecutive Loss Streak
              </span>
              <span className="text-xs font-mono text-amber-400 font-bold">
                Trigger: {maxConsecLosses} losses
              </span>
            </div>

            <div className="flex items-baseline justify-between mb-2">
              <span className={`text-2xl font-bold font-mono ${consecLosses >= maxConsecLosses ? 'text-rose-400' : 'text-white'}`}>
                {consecLosses} <span className="text-xs text-terminal-muted">/ {maxConsecLosses}</span>
              </span>
              <span className={`text-xs font-mono px-2 py-0.5 rounded font-bold ${
                riskState?.cooldown_active ? 'bg-rose-950 text-rose-400 border border-rose-800' : 'bg-slate-800 text-slate-300'
              }`}>
                {riskState?.cooldown_active ? 'COOLDOWN ACTIVE' : 'NORMAL'}
              </span>
            </div>

            {riskState?.cooldown_active ? (
              <div className="flex items-center gap-2 p-2 rounded bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs font-mono">
                <Clock className="w-4 h-4 text-rose-400 animate-spin" />
                <span>Cooldown timer: <strong>{cooldownRemaining}s</strong> remaining</span>
              </div>
            ) : (
              <p className="text-xs font-mono text-terminal-muted">
                No cooldown streak active. Will trigger 30-min pause if 3 consecutive losses occur.
              </p>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-terminal-border/60 text-[11px] text-terminal-muted">
            Enforces a mandatory 30-minute cooling off period after {maxConsecLosses} consecutive stop-outs.
          </div>
        </div>
      </div>

      {/* Sizing & Capital Parameters with Verbatim Source Warnings */}
      <div className="glass-panel rounded-xl p-5 border border-terminal-border">
        <h3 className="text-xs font-mono uppercase tracking-wider text-white mb-4 flex items-center gap-2">
          <Scale className="w-4 h-4 text-cyan-400" />
          Capital & Position Sizing Engine (nifty_algo_core.py)
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 font-mono text-xs mb-4">
          <div className="bg-terminal-bg/70 p-3 rounded-lg border border-terminal-border">
            <span className="text-[10px] text-terminal-muted block">CONFIGURED CAPITAL</span>
            <span className="text-base font-bold text-white">₹{(riskState?.capital || 100000).toLocaleString('en-IN')}</span>
          </div>

          <div className="bg-terminal-bg/70 p-3 rounded-lg border border-terminal-border">
            <span className="text-[10px] text-terminal-muted block">RISK PER TRADE</span>
            <span className="text-base font-bold text-cyan-400">{((riskState?.risk_per_trade_pct || 0.01) * 100).toFixed(1)}%</span>
            <span className="text-[10px] text-terminal-muted block">
              Budget: ₹{((riskState?.capital || 100000) * (riskState?.risk_per_trade_pct || 0.01)).toFixed(0)}
            </span>
          </div>

          <div className="bg-terminal-bg/70 p-3 rounded-lg border border-terminal-border">
            <span className="text-[10px] text-terminal-muted block">NIFTY LOT SIZE</span>
            <span className="text-base font-bold text-amber-400">{riskState?.lot_size || 65} units</span>
            <span className="text-[10px] text-terminal-muted block">Jan-2026 revision</span>
          </div>

          <div className="bg-terminal-bg/70 p-3 rounded-lg border border-terminal-border">
            <span className="text-[10px] text-terminal-muted block">MAX LOTS PER TRADE</span>
            <span className="text-base font-bold text-white">{riskState?.max_lots_per_trade || 5} lots</span>
            <span className="text-[10px] text-terminal-muted block">Hard cap</span>
          </div>
        </div>

        {/* Source File Warning Verbatim */}
        <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <strong>Source Code Sizing Caution (preserved verbatim):</strong>
            <p className="font-mono text-[11px] leading-relaxed">
              &quot;⚠ VERIFY current lot size before using this for real sizing — NSE revises it periodically.&quot;
            </p>
            <p className="text-[11px] text-amber-300/80">
              <code>position_size()</code> calculates lots so that if price hits the stop, loss is at most 1% of capital.
              If even 1 lot exceeds the risk budget, sizing safely returns 0 lots (trade skipped).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
