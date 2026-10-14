import React from 'react';
import { ArrowUpRight, ArrowDownRight, PauseCircle, ShieldCheck, Info } from 'lucide-react';
import { SignalType } from '../types';

interface SignalCardProps {
  spot: number;
  atm: number | null;
  signal: SignalType;
  confidence: number;
  confidenceThreshold: number;
  reason: string;
}

export const SignalCard: React.FC<SignalCardProps> = ({
  spot,
  atm,
  signal,
  confidence,
  confidenceThreshold,
  reason,
}) => {
  const isBuyCall = signal === 'BUY CALL';
  const isBuyPut = signal === 'BUY PUT';
  const isWait = signal === 'WAIT';

  // Badge colors
  const badgeClasses = isBuyCall
    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50 shadow-emerald-500/20'
    : isBuyPut
    ? 'bg-rose-500/20 text-rose-400 border-rose-500/50 shadow-rose-500/20'
    : 'bg-slate-700/30 text-slate-300 border-slate-600/50 shadow-slate-500/10';

  const glowClasses = isBuyCall
    ? 'shadow-lg shadow-emerald-500/10 border-emerald-500/30'
    : isBuyPut
    ? 'shadow-lg shadow-rose-500/10 border-rose-500/30'
    : 'border-terminal-border';

  const meetsThreshold = confidence >= confidenceThreshold;

  return (
    <div className={`glass-panel rounded-xl p-5 border ${glowClasses} relative overflow-hidden transition-all duration-300`}>
      {/* Top row: Spot & ATM */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-terminal-border/60">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-terminal-muted">NIFTY 50 Spot</span>
          <div className="text-3xl sm:text-4xl font-extrabold font-mono tracking-tight text-white flex items-baseline gap-2">
            {spot > 0 ? spot.toFixed(2) : '--'}
            <span className="text-xs font-normal text-terminal-subtext">INR</span>
          </div>
        </div>

        <div className="text-right">
          <span className="text-[11px] font-mono uppercase tracking-wider text-terminal-muted">ATM Strike</span>
          <div className="text-xl sm:text-2xl font-bold font-mono text-cyan-400">
            {atm ? atm.toLocaleString('en-IN') : '--'}
          </div>
        </div>
      </div>

      {/* Middle row: Signal & Confidence Ring */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 py-4 items-center">
        {/* Signal Badge */}
        <div className="col-span-1 md:col-span-2 flex flex-col justify-center">
          <span className="text-[11px] font-mono uppercase tracking-wider text-terminal-muted mb-1.5">Strategy Signal</span>
          <div className={`inline-flex items-center gap-3 px-4 py-2.5 rounded-xl border text-xl sm:text-2xl font-black tracking-wide w-fit ${badgeClasses}`}>
            {isBuyCall && <ArrowUpRight className="w-7 h-7 text-emerald-400 animate-bounce" />}
            {isBuyPut && <ArrowDownRight className="w-7 h-7 text-rose-400 animate-bounce" />}
            {isWait && <PauseCircle className="w-7 h-7 text-slate-400" />}
            <span>{signal}</span>
          </div>
        </div>

        {/* Confidence Gauge */}
        <div className="flex flex-col items-center sm:items-end justify-center">
          <span className="text-[11px] font-mono uppercase tracking-wider text-terminal-muted mb-1">
            Confidence (Threshold {confidenceThreshold}%)
          </span>
          <div className="flex items-center gap-3">
            {/* Circular Gauge */}
            <div className="relative w-16 h-16 flex items-center justify-center">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                {/* Background Ring */}
                <path
                  className="text-slate-800"
                  strokeWidth="3.5"
                  stroke="currentColor"
                  fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
                {/* Progress Ring */}
                <path
                  className={meetsThreshold ? (isBuyCall ? 'text-emerald-500' : isBuyPut ? 'text-rose-500' : 'text-cyan-500') : 'text-slate-500'}
                  strokeDasharray={`${Math.min(100, Math.max(0, confidence))}, 100`}
                  strokeWidth="3.5"
                  strokeLinecap="round"
                  stroke="currentColor"
                  fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
              </svg>
              <div className="absolute font-mono font-bold text-sm text-white">
                {Math.round(confidence)}%
              </div>
            </div>

            <div className="text-left text-xs">
              <div className={`font-mono font-semibold ${meetsThreshold ? 'text-emerald-400' : 'text-terminal-muted'}`}>
                {meetsThreshold ? 'Threshold Met' : 'Below Threshold'}
              </div>
              <div className="text-[10px] text-terminal-muted">Req: ≥ {confidenceThreshold}%</div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom row: Verbatim Reason */}
      <div className="mt-2 pt-3 border-t border-terminal-border/60">
        <div className="flex items-start gap-2 bg-terminal-bg/70 p-3 rounded-lg border border-terminal-border/80">
          <Info className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-wider text-terminal-muted">Decision Rationale</span>
              {isWait && (
                <span className="text-[10px] text-amber-400/90 font-medium flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" /> WAIT is the healthy default state
                </span>
              )}
            </div>
            <p className="text-sm font-mono text-terminal-text mt-0.5 break-words">
              {reason || 'Awaiting live engine tick...'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
