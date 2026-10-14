import React, { useState, useEffect } from 'react';
import { SystemConfig } from '../types';
import { Settings, Shield, Terminal, CheckCircle2, XCircle, AlertTriangle, RefreshCw, Play, Loader2, Bug, Key, ExternalLink } from 'lucide-react';
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
