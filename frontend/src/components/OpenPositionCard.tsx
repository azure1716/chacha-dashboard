import React from 'react';
import { PaperPosition } from '../types';
import { Shield, Target, Crosshair, ArrowUpRight, ArrowDownRight, CheckCircle2 } from 'lucide-react';

interface OpenPositionCardProps {
  position: PaperPosition | null;
}

export const OpenPositionCard: React.FC<OpenPositionCardProps> = ({ position }) => {
  if (!position) {
    return (
      <div className="glass-panel rounded-xl p-5 border border-terminal-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-slate-800/80 flex items-center justify-center text-terminal-muted">
            <Crosshair className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs font-semibold text-white">Active Paper Position</span>
            <p className="text-xs font-mono text-terminal-muted">None currently open — risk gates and filters active</p>
          </div>
        </div>
        <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-800/60 text-slate-400 border border-slate-700">
          IDLE / FLAT
        </span>
      </div>
    );
  }

  const isCall = position.type === 'CE';
  const isNetPositive = (position.unrealized_net_pnl || 0) >= 0;

  return (
    <div className="glass-panel rounded-xl p-5 border border-cyan-500/30 bg-gradient-to-r from-terminal-card to-cyan-950/20 shadow-lg shadow-cyan-950/20">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 mb-3 border-b border-terminal-border/60">
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold ${
            isCall ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
          }`}>
            {isCall ? <ArrowUpRight className="w-5 h-5" /> : <ArrowDownRight className="w-5 h-5" />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold font-mono text-white">
                {position.strike} {position.type}
              </span>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
                {position.lots} Lots ({position.lots * 65} units)
              </span>
            </div>
            <span className="text-[11px] text-terminal-muted">Paper Trading Simulation</span>
          </div>
        </div>

        {/* Live Unrealized P&L */}
        <div className="text-right">
          <span className="text-[10px] font-mono uppercase text-terminal-muted">Unrealized Net P&L</span>
          <div className={`text-xl font-bold font-mono ${isNetPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isNetPositive ? '+' : ''}{(position.unrealized_net_pnl || 0).toFixed(2)} INR
          </div>
          <span className="text-[10px] font-mono text-terminal-muted">
            Gross: {(position.unrealized_gross_pnl || 0).toFixed(2)} • Est Cost: {(position.unrealized_cost || 0).toFixed(2)}
          </span>
        </div>
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs font-mono">
        <div className="bg-terminal-bg/50 p-2.5 rounded-lg border border-terminal-border/60">
          <span className="text-[10px] text-terminal-muted block">ENTRY PRICE</span>
          <span className="font-bold text-white text-sm">₹{position.entry.toFixed(2)}</span>
          <span className="text-[10px] text-terminal-muted block">LTP: ₹{(position.current_ltp || position.entry).toFixed(2)}</span>
        </div>

        <div className="bg-terminal-bg/50 p-2.5 rounded-lg border border-terminal-border/60">
          <span className="text-[10px] text-terminal-muted block flex items-center gap-1">
            <Shield className="w-3 h-3 text-rose-400" /> STOP LOSS
          </span>
          <span className="font-bold text-rose-400 text-sm">₹{position.sl.toFixed(2)}</span>
          <span className="text-[10px] text-terminal-muted block">Dist: ₹{Math.abs(position.entry - position.sl).toFixed(2)}</span>
        </div>

        <div className="bg-terminal-bg/50 p-2.5 rounded-lg border border-terminal-border/60">
          <span className="text-[10px] text-terminal-muted block flex items-center gap-1">
            <Target className="w-3 h-3 text-emerald-400" /> TARGET
          </span>
          <span className="font-bold text-emerald-400 text-sm">₹{position.target.toFixed(2)}</span>
          <span className="text-[10px] text-terminal-muted block">Dist: ₹{Math.abs(position.target - position.entry).toFixed(2)}</span>
        </div>

        <div className="bg-terminal-bg/50 p-2.5 rounded-lg border border-terminal-border/60">
          <span className="text-[10px] text-terminal-muted block">TRAILING STOP</span>
          <span className={`font-semibold flex items-center gap-1 text-sm ${position.trail_active ? 'text-emerald-400' : 'text-slate-400'}`}>
            {position.trail_active ? <CheckCircle2 className="w-3.5 h-3.5" /> : null}
            {position.trail_active ? 'ACTIVE' : 'INACTIVE'}
          </span>
          <span className="text-[10px] text-terminal-muted block">Delta: {position.delta ? position.delta.toFixed(2) : '0.50'}</span>
        </div>
      </div>
    </div>
  );
};
