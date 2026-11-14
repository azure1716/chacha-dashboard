import React, { useState, useEffect } from 'react';
import { SystemConfig } from '../types';
import { Settings, Shield, Terminal, CheckCircle2, XCircle, AlertTriangle, RefreshCw, Play, Loader2, Bug, Key, ExternalLink, SlidersHorizontal, Lock, Check } from 'lucide-react';
import { apiUrl } from '../api';

interface SystemConfigPageProps {
  onOpenTokenModal?: () => void;
}

export const SystemConfigPage: React.FC<SystemConfigPageProps> = ({ onOpenTokenModal }) => {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [testResult, setTestResult] = useState<any>(null);
  const [runningTests, setRunningTests] = useState<boolean>(false);
  const [tokenStatus, setTokenStatus] = useState<{ has_token: boolean; token_masked: string } | null>(null);
  const [switchingProfile, setSwitchingProfile] = useState<boolean>(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState<string | null>(null);

  const fetchTokenStatus = async () => {
    try {
      const res = await fetch(apiUrl('/api/config/token-status'));
      if (res.ok) {
        const data = await res.json();
        setTokenStatus(data);
      }
    } catch {
      // ignore
    }
  };

  const fetchConfig = async () => {
    setLoading(true);
    try {
      fetchTokenStatus();
      const res = await fetch(apiUrl('/api/config'));
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
      }
    } catch (e) {
      console.error('Failed to load system config:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSwitchProfile = async (targetProfile: string) => {
    if (!config?.strategy_profile) return;
    if (config.strategy_profile.active === targetProfile) return;
    if (config.strategy_profile.locked) {
      setProfileError('Cannot switch profile while a position is open. Close the open position first.');
      return;
    }

    setSwitchingProfile(true);
    setProfileError(null);
    setProfileSuccess(null);

    try {
      const res = await fetch(apiUrl('/api/config/strategy-profile'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: targetProfile }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setProfileSuccess(data.message || `Switched to ${targetProfile} profile.`);
        await fetchConfig();
      } else {
        setProfileError(data.reason || data.error || data.message || 'Failed to switch strategy profile.');
      }
    } catch (err: any) {
      setProfileError('Network error while switching strategy profile: ' + err.message);
    } finally {
      setSwitchingProfile(false);
    }
  };

  const handleRunSelfTests = async () => {
    setRunningTests(true);
    try {
      const res = await fetch(apiUrl('/api/tests/run'), { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setTestResult(data);
      }
    } catch (e: any) {
      alert('Self-test error: ' + e.message);
    } finally {
      setRunningTests(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-panel rounded-xl p-5 border border-terminal-border flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-cyan-400" />
            <h2 className="text-base font-bold text-white uppercase tracking-wider">
              System Configuration & Diagnostics (§5.7)
            </h2>
          </div>
          <p className="text-xs text-terminal-muted mt-1">
            Read-only mirror of active engine parameters directly from <code>/api/config</code>. Guaranteed in sync with running Python process.
          </p>
        </div>

        <button
          onClick={fetchConfig}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-terminal-hover text-terminal-subtext hover:text-white border border-terminal-border text-xs font-mono"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Reload Config</span>
        </button>
      </div>

      {/* Upstox Authentication & Token Management Card */}
      <div className="glass-panel rounded-xl p-5 border border-cyan-800/40 bg-gradient-to-r from-cyan-950/20 to-slate-900/60">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-cyan-900/40 border border-cyan-700/50 flex items-center justify-center text-cyan-400 shrink-0">
              <Key className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white">Upstox API Authentication</h3>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-medium ${
                  tokenStatus?.has_token 
                    ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/60' 
                    : 'bg-amber-950/80 text-amber-300 border border-amber-800/60'
                }`}>
                  {tokenStatus?.has_token ? 'CONFIGURED & ACTIVE' : 'TOKEN MISSING / EXPIRED'}
                </span>
              </div>
              <p className="text-xs text-terminal-muted mt-1 max-w-xl">
                Upstox interactive access tokens expire daily at 03:30 AM IST. When this site is hosted, update your access token directly from this dashboard without server restarts or SSH.
              </p>
              <div className="mt-2 text-xs font-mono text-terminal-subtext flex items-center gap-3">
                <span>Active Server Token: <strong className="text-white">{tokenStatus?.has_token ? tokenStatus.token_masked : 'None'}</strong></span>
                <a 
                  href="https://developer.upstox.com/" 
                  target="_blank" 
                  rel="noreferrer" 
                  className="text-cyan-400 hover:text-cyan-300 underline inline-flex items-center gap-1"
                >
                  Developer Portal <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          </div>

          <button
            onClick={onOpenTokenModal}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/20 transition-all flex items-center gap-2 shrink-0"
          >
            <Key className="w-3.5 h-3.5" />
            <span>Replace / Renew Token</span>
          </button>
        </div>
      </div>

      {/* Strategy Profile Selection Card */}
      {config?.strategy_profile && (
        <div className="glass-panel rounded-xl p-5 border border-terminal-border bg-gradient-to-r from-slate-900/40 via-cyan-950/10 to-slate-900/40 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-terminal-border/60">
            <div className="flex items-start gap-3.5">
              <div className="w-10 h-10 rounded-xl bg-cyan-950/70 border border-cyan-800/60 flex items-center justify-center text-cyan-400 shrink-0 shadow-lg shadow-cyan-950/30">
                <SlidersHorizontal className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-white">Strategy Profile Engine</h3>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800/60">
                    CONFIGURED & ACTIVE: {config.strategy_profile.active === 'SCALP' ? 'Scalp' : 'Balanced'}
                  </span>
                  {config.strategy_profile.locked && (
                    <span 
                      title="Close the open position first"
                      className="text-[10px] font-mono px-2 py-0.5 rounded font-medium bg-amber-950/80 text-amber-300 border border-amber-800/60 flex items-center gap-1"
                    >
                      <Lock className="w-3 h-3" />
                      LOCKED (POSITION OPEN)
                    </span>
                  )}
                </div>
                <p className="text-xs text-terminal-muted mt-1 max-w-xl">
                  {config.strategy_profile.parameters?.description ||
                    'Select between Balanced (default multi-factor trend-following) and Scalp (intraday dual-HTF with tighter stops/targets, VWAP filter, spread cap, and lunch gap). Switches live without engine restart.'}
                </p>
              </div>
            </div>

            {/* Toggle Switch */}
            <div className="flex flex-col items-end gap-1.5 shrink-0">
              <div 
                className={`p-1 rounded-lg bg-terminal-bg border border-terminal-border flex items-center gap-1 ${
                  config.strategy_profile.locked ? 'opacity-70 cursor-not-allowed' : ''
                }`}
                title={config.strategy_profile.locked ? 'Close the open position first' : undefined}
              >
                <button
                  type="button"
                  onClick={() => handleSwitchProfile('BALANCED')}
                  disabled={config.strategy_profile.locked || switchingProfile}
                  title={config.strategy_profile.locked ? 'Close the open position first' : 'Switch to Balanced strategy profile'}
                  className={`px-4 py-2 rounded-md text-xs font-mono font-bold transition-all flex items-center gap-1.5 ${
                    config.strategy_profile.active === 'BALANCED'
                      ? 'bg-gradient-to-r from-cyan-600 to-blue-600 text-white shadow-md shadow-cyan-600/30'
                      : 'text-terminal-subtext hover:text-white hover:bg-terminal-hover/60'
                  } ${config.strategy_profile.locked ? 'cursor-not-allowed' : ''}`}
                >
                  {config.strategy_profile.active === 'BALANCED' && <Check className="w-3.5 h-3.5" />}
                  <span>Balanced</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleSwitchProfile('SCALP')}
                  disabled={config.strategy_profile.locked || switchingProfile}
                  title={config.strategy_profile.locked ? 'Close the open position first' : 'Switch to Scalp strategy profile'}
                  className={`px-4 py-2 rounded-md text-xs font-mono font-bold transition-all flex items-center gap-1.5 ${
                    config.strategy_profile.active === 'SCALP'
                      ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-emerald-600/30'
                      : 'text-terminal-subtext hover:text-white hover:bg-terminal-hover/60'
                  } ${config.strategy_profile.locked ? 'cursor-not-allowed' : ''}`}
                >
                  {config.strategy_profile.active === 'SCALP' && <Check className="w-3.5 h-3.5" />}
                  <span>Scalp</span>
                </button>
              </div>

              {config.strategy_profile.locked && (
                <span className="text-[10px] text-amber-400 font-mono">
                  Close the open position first to switch profile
                </span>
              )}
            </div>
          </div>

          {/* Feedback messages */}
          {profileError && (
            <div className="p-3 rounded-lg bg-rose-950/80 border border-rose-800 text-rose-300 text-xs font-mono flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{profileError}</span>
              </div>
              <button 
                onClick={() => setProfileError(null)}
                className="text-rose-400 hover:text-white text-xs px-2 py-0.5 rounded bg-rose-900/50"
              >
                Dismiss
              </button>
            </div>
          )}

          {profileSuccess && (
            <div className="p-3 rounded-lg bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs font-mono flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{profileSuccess}</span>
              </div>
              <button 
                onClick={() => setProfileSuccess(null)}
                className="text-emerald-400 hover:text-white text-xs px-2 py-0.5 rounded bg-emerald-900/50"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Active Profile Parameter Table */}
          <div className="space-y-2 pt-1 font-mono text-xs">
            <div className="flex items-center justify-between text-terminal-muted border-b border-terminal-border/40 pb-1">
              <span className="text-[11px] font-bold text-cyan-400 uppercase tracking-wider">
                Active Profile Parameters ({config.strategy_profile.active === 'SCALP' ? 'Scalp' : 'Balanced'})
              </span>
              <span className="text-[10px]">Survives server restart (persisted in .env)</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">Confidence Threshold:</span>
                <span className="text-white font-bold">{config.strategy_profile.parameters.confidence_threshold}%</span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">Min ADX Trend Floor:</span>
                <span className="text-white font-bold">{config.strategy_profile.parameters.min_adx_for_trend_signal}</span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">HTF Trend Veto:</span>
                <span className="text-cyan-300 font-bold">
                  {config.strategy_profile.parameters.htf_veto_mode === 'both_tf' 
                    ? 'Both 3m & 5m must oppose' 
                    : '5-min trend alone'}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">Stop-Loss (ATR Multiplier):</span>
                <span className="text-white font-bold">{config.strategy_profile.parameters.atr_sl_multiplier}x ATR</span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">Target (ATR Multiplier):</span>
                <span className="text-white font-bold">{config.strategy_profile.parameters.atr_target_multiplier}x ATR</span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">Trailing Stop (Activate / Dist):</span>
                <span className="text-white font-bold">{config.strategy_profile.parameters.trail_activate_r}R / {config.strategy_profile.parameters.trail_distance_r}R</span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">Max Trades / Day:</span>
                <span className="text-white font-bold">{config.strategy_profile.parameters.max_trades_per_day}</span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">IV Percentile Cap:</span>
                <span className="text-white font-bold">{config.strategy_profile.parameters.iv_percentile_max}%</span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">Max Quoted Spread:</span>
                <span className="text-white font-bold">
                  {config.strategy_profile.parameters.max_spread_pct != null
                    ? `${config.strategy_profile.parameters.max_spread_pct}%`
                    : 'None (Disabled)'}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">VWAP-Stretch Filter:</span>
                <span className="text-white font-bold">
                  {config.strategy_profile.parameters.vwap_stretch_atr != null
                    ? `${config.strategy_profile.parameters.vwap_stretch_atr}x ATR`
                    : 'None (Disabled)'}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">Trading Session Window:</span>
                <span className="text-white font-bold">
                  {config.strategy_profile.parameters.trade_start_str} - {config.strategy_profile.parameters.trade_end_str} IST
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-terminal-bg/60 border border-terminal-border/50 flex justify-between items-center">
                <span className="text-terminal-muted">Lunch-Hour Exclusion:</span>
                <span className="text-white font-bold">
                  {config.strategy_profile.parameters.lunch_start_str
                    ? `${config.strategy_profile.parameters.lunch_start_str} - ${config.strategy_profile.parameters.lunch_end_str} IST`
                    : 'None (Disabled)'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Self-Tests Section (§5.8) */}
      <div className="glass-panel rounded-xl p-5 border border-terminal-border">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 mb-3 border-b border-terminal-border/60">
          <div>
            <h4 className="text-xs font-bold text-white uppercase font-mono flex items-center gap-2">
              <Shield className="w-4 h-4 text-emerald-400" />
              Engine Unit & Simulation Self-Tests (test_core.py & test_live_simulation.py)
            </h4>
            <p className="text-[11px] text-terminal-muted">
              Executes internal validation suite to verify indicator math, risk gates, position sizing, and simulation logic.
            </p>
          </div>

          <button
            onClick={handleRunSelfTests}
            disabled={runningTests}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white font-medium text-xs hover:bg-emerald-500 transition-all disabled:opacity-50"
          >
            {runningTests ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Running Suite...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                <span>Run Self-Tests</span>
              </>
            )}
          </button>
        </div>

        {testResult && (
          <div className="space-y-3 font-mono text-xs">
            <div className="flex items-center gap-4">
              <span className={`px-2.5 py-1 rounded font-bold ${
                testResult.status === 'SUCCESS' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-rose-950 text-rose-400 border border-rose-800'
              }`}>
                {testResult.status === 'SUCCESS' ? 'ALL CHECKS PASSED' : 'FAILURES DETECTED'}
              </span>
              <span className="text-terminal-text">
                Passed: <strong className="text-emerald-400">{testResult.passed}</strong> • Failed: <strong className={testResult.failed > 0 ? "text-rose-400" : "text-terminal-muted"}>{testResult.failed}</strong> of {testResult.total}
              </span>
            </div>

            <pre className="bg-terminal-bg p-3 rounded-lg border border-terminal-border text-[11px] text-terminal-subtext max-h-48 overflow-y-auto scrollbar-thin">
              {testResult.output}
            </pre>
          </div>
        )}
      </div>

      {/* Engine Constants Grid */}
      {config && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 font-mono text-xs">
          {/* Indicators */}
          <div className="glass-panel rounded-xl p-4 border border-terminal-border space-y-2">
            <span className="text-[11px] font-bold text-cyan-400 uppercase tracking-wider block border-b border-terminal-border/60 pb-1.5">
              Indicator Periods
            </span>
            {Object.entries(config.indicators || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1 border-b border-terminal-border/30">
                <span className="text-terminal-muted">{k}:</span>
                <span className="text-white font-bold">{String(v)}</span>
              </div>
            ))}
          </div>

          {/* Thresholds */}
          <div className="glass-panel rounded-xl p-4 border border-terminal-border space-y-2">
            <span className="text-[11px] font-bold text-amber-400 uppercase tracking-wider block border-b border-terminal-border/60 pb-1.5">
              Signal Gates & Thresholds
            </span>
            {Object.entries(config.thresholds || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1 border-b border-terminal-border/30">
                <span className="text-terminal-muted">{k}:</span>
                <span className="text-white font-bold">{String(v)}</span>
              </div>
            ))}
          </div>

          {/* Risk Management */}
          <div className="glass-panel rounded-xl p-4 border border-terminal-border space-y-2">
            <span className="text-[11px] font-bold text-rose-400 uppercase tracking-wider block border-b border-terminal-border/60 pb-1.5">
              Risk & Sizing Parameters
            </span>
            {Object.entries(config.risk_management || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1 border-b border-terminal-border/30">
                <span className="text-terminal-muted">{k}:</span>
                <span className="text-white font-bold">{String(v)}</span>
              </div>
            ))}
          </div>

          {/* Retail Cost Model */}
          <div className="glass-panel rounded-xl p-4 border border-terminal-border space-y-2">
            <span className="text-[11px] font-bold text-purple-400 uppercase tracking-wider block border-b border-terminal-border/60 pb-1.5">
              Indian Retail F&O Cost Model
            </span>
            {Object.entries(config.cost_model || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1 border-b border-terminal-border/30">
                <span className="text-terminal-muted">{k}:</span>
                <span className="text-white font-bold">{String(v)}</span>
              </div>
            ))}
          </div>

          {/* EPM Module */}
          <div className="glass-panel rounded-xl p-4 border border-terminal-border space-y-2">
            <span className="text-[11px] font-bold text-purple-300 uppercase tracking-wider block border-b border-terminal-border/60 pb-1.5">
              EPM Module (Beta)
            </span>
            <div className="py-1">
              <span className="text-terminal-muted block">Status:</span>
              <span className="text-purple-300 font-bold">{config.epm_module.status}</span>
            </div>
            <div className="py-1">
              <span className="text-terminal-muted block">Weights:</span>
              <span className="text-white font-bold">{JSON.stringify(config.epm_module.weights)}</span>
            </div>
            <p className="text-[11px] text-terminal-muted leading-relaxed">
              {config.epm_module.description}
            </p>
          </div>

          {/* Session Timing */}
          <div className="glass-panel rounded-xl p-4 border border-terminal-border space-y-2">
            <span className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider block border-b border-terminal-border/60 pb-1.5">
              Trading Session Limits
            </span>
            {Object.entries(config.session_times || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1 border-b border-terminal-border/30">
                <span className="text-terminal-muted">{k}:</span>
                <span className="text-white font-bold">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Exceptions Ring Buffer */}
      <div className="glass-panel rounded-xl p-5 border border-terminal-border">
        <div className="flex items-center gap-2 mb-3">
          <Bug className="w-4 h-4 text-rose-400" />
          <h4 className="text-xs font-bold text-white uppercase font-mono">
            Recent Engine Exceptions (In-Memory Ring Buffer, max 50)
          </h4>
        </div>

        {config?.recent_exceptions && config.recent_exceptions.length > 0 ? (
          <div className="space-y-3 font-mono text-xs">
            {config.recent_exceptions.map((ex, i) => (
              <div key={i} className="p-3 rounded-lg bg-terminal-bg border border-rose-900/60">
                <div className="flex justify-between text-rose-400 font-bold mb-1">
                  <span>[{ex.label}] {ex.error}</span>
                  <span className="text-terminal-muted text-[10px]">{ex.timestamp}</span>
                </div>
                <pre className="text-[10px] text-terminal-subtext overflow-x-auto whitespace-pre-wrap">
                  {ex.traceback}
                </pre>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded-lg bg-terminal-bg/50 border border-terminal-border text-xs font-mono text-emerald-400 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            <span>Zero exceptions logged in current engine session.</span>
          </div>
        )}
      </div>
    </div>
  );
};
