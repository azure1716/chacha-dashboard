import React from 'react';
import { TechnicalData, MomentumData, OptionPressureData, EpmData } from '../types';
import { Gauge, TrendingUp, Layers, HelpCircle, Activity, Sparkles } from 'lucide-react';

interface ScoreBreakdownProps {
  technical: TechnicalData;
  momentum: MomentumData;
  options: OptionPressureData;
  htfTrend: string | null;
  epm: EpmData;
  weights: {
    technical: number;
    momentum: number;
    options: number;
  };
}

export const ScoreBreakdown: React.FC<ScoreBreakdownProps> = ({
  technical,
  momentum,
  options,
  htfTrend,
  epm,
  weights,
}) => {
  const techScore = technical.score ?? 0;
  const momScore = momentum.score ?? 0;
  const optScore = options.score ?? 0;
  const epmScore = epm?.score ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-mono uppercase tracking-wider text-terminal-muted flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-cyan-400" />
          Multi-Factor Score Architecture
        </h3>
        <span className="text-[11px] text-terminal-muted font-mono">
          Weights: Tech {(weights.technical * 100).toFixed(0)}% • Mom {(weights.momentum * 100).toFixed(0)}% • Options {(weights.options * 100).toFixed(0)}%
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Technical Score Card */}
        <div className="glass-panel glass-panel-hover rounded-xl p-4 border border-terminal-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                <Gauge className="w-4 h-4 text-cyan-400" /> Technical Layer
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
                Weight 40%
              </span>
            </div>

            <div className="flex items-baseline justify-between mb-3">
              <div className="text-2xl font-bold font-mono text-white">
                {techScore > 0 ? `+${techScore.toFixed(0)}` : techScore.toFixed(0)}
              </div>
              <span className={`text-xs font-mono px-2 py-0.5 rounded font-bold ${
                technical.trend === 'BULLISH' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60' :
                technical.trend === 'BEARISH' ? 'bg-rose-950 text-rose-400 border border-rose-800/60' :
                'bg-slate-900 text-slate-400 border border-slate-800'
              }`}>
                {technical.trend || 'NEUTRAL'}
              </span>
            </div>

            <div className="space-y-1.5 text-[11px] font-mono text-terminal-subtext pt-2 border-t border-terminal-border/50">
              <div className="flex justify-between">
                <span>ADX (Chop Gate):</span>
                <span className={`font-semibold ${technical.adx && technical.adx >= 18 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {technical.adx ? technical.adx.toFixed(1) : '--'} ({technical.trend_strength || '?'})
                </span>
              </div>
              <div className="flex justify-between">
                <span>+DI / -DI:</span>
                <span>
                  {technical.plus_di ? technical.plus_di.toFixed(1) : '--'} / {technical.minus_di ? technical.minus_di.toFixed(1) : '--'}
                </span>
              </div>
              <div className="flex justify-between">
                <span>RSI (14):</span>
                <span>{technical.rsi ? technical.rsi.toFixed(1) : '--'}</span>
              </div>
              <div className="flex justify-between">
                <span>ATR%:</span>
                <span>{technical.atr_pct ? `${technical.atr_pct.toFixed(4)}%` : '--'}</span>
              </div>
            </div>
          </div>
          <div className="mt-3 text-[10px] text-terminal-muted border-t border-terminal-border/40 pt-1.5">
            EMA20 {technical.ema_fast ? technical.ema_fast.toFixed(1) : '--'} • EMA50 {technical.ema_slow ? technical.ema_slow.toFixed(1) : '--'}
          </div>
        </div>

        {/* 2. Momentum Score Card */}
        <div className="glass-panel glass-panel-hover rounded-xl p-4 border border-terminal-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-emerald-400" /> Momentum Layer
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800">
                Weight 25%
              </span>
            </div>

            <div className="flex items-baseline justify-between mb-3">
              <div className="text-2xl font-bold font-mono text-white">
                {momScore > 0 ? `+${momScore.toFixed(0)}` : momScore.toFixed(0)}
              </div>
              <span className={`text-xs font-mono px-2 py-0.5 rounded font-bold ${
                momScore > 0 ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60' :
                momScore < 0 ? 'bg-rose-950 text-rose-400 border border-rose-800/60' :
                'bg-slate-900 text-slate-400 border border-slate-800'
              }`}>
                {momScore > 0 ? 'POSITIVE' : momScore < 0 ? 'NEGATIVE' : 'NEUTRAL'}
              </span>
            </div>

            <div className="space-y-1.5 text-[11px] font-mono text-terminal-subtext pt-2 border-t border-terminal-border/50">
              <div className="flex justify-between">
                <span>10-Bar Delta:</span>
                <span className={momentum.momentum && momentum.momentum > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                  {momentum.momentum !== undefined ? `${momentum.momentum > 0 ? '+' : ''}${momentum.momentum.toFixed(2)} pts` : '--'}
                </span>
              </div>
              <div className="flex justify-between">
                <span>RSI (14):</span>
                <span>{momentum.rsi ? momentum.rsi.toFixed(1) : '--'}</span>
              </div>
              <div className="flex justify-between">
                <span>Momentum Gate:</span>
                <span className="text-terminal-text">{momScore !== 0 ? 'ACTIVE' : 'NEUTRAL'}</span>
              </div>
            </div>
          </div>
          <div className="mt-3 text-[10px] text-terminal-muted border-t border-terminal-border/40 pt-1.5">
            Lookback: 10 bars • Dual velocity & RSI confirm
          </div>
        </div>

        {/* 3. Option Pressure Score Card */}
        <div className="glass-panel glass-panel-hover rounded-xl p-4 border border-terminal-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                <Activity className="w-4 h-4 text-purple-400" /> Option Pressure
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
                Weight 35%
              </span>
            </div>

            <div className="flex items-baseline justify-between mb-3">
              <div className="text-2xl font-bold font-mono text-white">
                {optScore > 0 ? `+${optScore.toFixed(1)}` : optScore.toFixed(1)}
              </div>
              <span className={`text-xs font-mono px-2 py-0.5 rounded font-bold ${
                options.bias === 'BULLISH' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60' :
                options.bias === 'BEARISH' ? 'bg-rose-950 text-rose-400 border border-rose-800/60' :
                'bg-slate-900 text-slate-400 border border-slate-800'
              }`}>
                {options.bias || 'NEUTRAL'}
              </span>
            </div>

            <div className="space-y-1.5 text-[11px] font-mono text-terminal-subtext pt-2 border-t border-terminal-border/50">
              <div className="flex justify-between">
                <span>OI Score (PE vs CE):</span>
                <span className={options.oi_score && options.oi_score > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                  {options.oi_score !== undefined ? `${options.oi_score > 0 ? '+' : ''}${options.oi_score.toFixed(1)}` : '--'}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Volume Skew:</span>
                <span className={options.volume_score && options.volume_score > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                  {options.volume_score !== undefined ? `${options.volume_score > 0 ? '+' : ''}${options.volume_score.toFixed(1)}` : '--'}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Order Flow Score:</span>
                <span>{options.order_score !== undefined ? options.order_score.toFixed(1) : '--'}</span>
              </div>
              <div className="flex justify-between">
                <span>Active Option Keys:</span>
                <span>{options.live_count || 0} live</span>
              </div>
            </div>
          </div>
          <div className="mt-3 text-[10px] text-terminal-muted border-t border-terminal-border/40 pt-1.5">
            Realtime chain metrics aggregated across ATM +/- 5 strikes
          </div>
        </div>

        {/* 4. HTF (5-min) Trend Card */}
        <div className="glass-panel glass-panel-hover rounded-xl p-4 border border-terminal-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-cyan-400" /> HTF Trend (5-min)
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                Gatekeeper
              </span>
            </div>

            <div className="flex items-baseline justify-between mb-3">
              <div className="text-2xl font-bold font-mono text-white">
                {htfTrend || 'NEUTRAL'}
              </div>
              <span className={`text-xs font-mono px-2 py-0.5 rounded font-bold ${
                htfTrend === 'BULLISH' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60' :
                htfTrend === 'BEARISH' ? 'bg-rose-950 text-rose-400 border border-rose-800/60' :
                'bg-slate-900 text-slate-400 border border-slate-800'
              }`}>
                {htfTrend === 'BULLISH' ? 'LONGS ONLY' : htfTrend === 'BEARISH' ? 'SHORTS ONLY' : 'NO VETO'}
              </span>
            </div>

            <div className="space-y-1.5 text-[11px] font-mono text-terminal-subtext pt-2 border-t border-terminal-border/50">
              <div className="flex justify-between">
                <span>Resampling:</span>
                <span>5 x 1-min bars</span>
              </div>
              <div className="flex justify-between">
                <span>HTF Filter Gate:</span>
                <span className="text-emerald-400 font-semibold">Active</span>
              </div>
              <p className="text-[10px] text-terminal-muted mt-2 leading-relaxed">
                Blocks 1-minute signals trading counter to the larger 5-minute EMA20/EMA50 trend.
              </p>
            </div>
          </div>
          <div className="mt-3 text-[10px] text-terminal-muted border-t border-terminal-border/40 pt-1.5">
            Computed on existing 1-min candles (no extra API calls)
          </div>
        </div>
      </div>

      {/* 5. EPM Score Card (§6) — Clearly labeled as Beta / formula pending confirmation */}
      <div className="glass-panel rounded-xl p-4 border border-trade-epmBorder/40 bg-gradient-to-r from-terminal-card to-purple-950/20">
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2 mb-3 border-b border-terminal-border/60">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-trade-epm" />
            <span className="text-xs font-bold text-white uppercase tracking-wider">EPM Module</span>
            <span className="text-[10px] font-semibold font-mono px-2 py-0.5 rounded-full bg-purple-900/60 text-purple-300 border border-purple-600/50">
              Beta — formula pending confirmation
            </span>
          </div>
          <div className="text-[11px] font-mono text-purple-300 flex items-center gap-1">
            <HelpCircle className="w-3.5 h-3.5" />
            Confirming factor only (does not trigger trades alone)
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
          <div>
            <span className="text-[11px] font-mono uppercase text-terminal-muted">EPM Score</span>
            <div className="text-2xl font-bold font-mono text-purple-300 flex items-center gap-2">
              {epmScore > 0 ? `+${epmScore.toFixed(1)}` : epmScore.toFixed(1)}
              <span className={`text-xs px-2 py-0.5 rounded font-bold ${
                epm?.bias === 'CALL' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                epm?.bias === 'PUT' ? 'bg-rose-950 text-rose-400 border border-rose-800' :
                'bg-slate-900 text-slate-400 border border-slate-800'
              }`}>
                Bias: {epm?.bias || 'WAIT'}
              </span>
            </div>
          </div>

          <div>
            <span className="text-[11px] font-mono uppercase text-terminal-muted">Volume Skew (40%)</span>
            <div className="text-sm font-mono font-semibold text-white">
              {epm?.volume_score !== undefined ? `${epm.volume_score > 0 ? '+' : ''}${epm.volume_score.toFixed(1)}` : '--'}
            </div>
          </div>

          <div>
            <span className="text-[11px] font-mono uppercase text-terminal-muted">IV Skew (30%)</span>
            <div className="text-sm font-mono font-semibold text-white">
              {epm?.iv_skew !== undefined ? `${epm.iv_skew > 0 ? '+' : ''}${epm.iv_skew.toFixed(1)}` : '--'}
            </div>
          </div>

          <div>
            <span className="text-[11px] font-mono uppercase text-terminal-muted">Underlying Trend Score (30%)</span>
            <div className="text-sm font-mono font-semibold text-white">
              {epm?.underlying_trend_score !== undefined ? `${epm.underlying_trend_score > 0 ? '+' : ''}${epm.underlying_trend_score.toFixed(1)}` : '--'}
            </div>
          </div>
        </div>

        <div className="mt-3 pt-2 text-[10px] text-purple-300/80 border-t border-purple-900/30 flex items-center justify-between">
          <span>Placeholder specification matching Hinglish description: Combines option volume, IV skew, and underlying trend.</span>
          <span className="font-mono">Formula: 0.40 * Vol + 0.30 * IV_Skew + 0.30 * Trend</span>
        </div>
      </div>
    </div>
  );
};
