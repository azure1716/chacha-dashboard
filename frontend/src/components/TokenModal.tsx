import React, { useState, useEffect } from 'react';
import { 
  Key, 
  X, 
  CheckCircle2, 
  AlertCircle, 
  ExternalLink, 
  Eye, 
  EyeOff, 
  Loader2, 
  ShieldCheck, 
  HelpCircle 
} from 'lucide-react';

interface TokenModalProps {
  isOpen: boolean;
  onClose: () => void;
  onTokenUpdated?: () => void;
}

export const TokenModal: React.FC<TokenModalProps> = ({ isOpen, onClose, onTokenUpdated }) => {
  const [tokenInput, setTokenInput] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [currentStatus, setCurrentStatus] = useState<{ has_token: boolean; token_masked: string } | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ valid: boolean; user_name?: string; user_id?: string; error?: string } | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error' | 'warning'; text: string; canForce?: boolean } | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchStatus();
      setTestResult(null);
      setStatusMessage(null);
    }
  }, [isOpen]);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/config/token-status');
      if (res.ok) {
        const data = await res.json();
        setCurrentStatus(data);
      }
    } catch {
      // Ignore initial status fetch error
    }
  };

  if (!isOpen) return null;

  const handleTestToken = async () => {
    const trimmed = tokenInput.trim();
    if (!trimmed) {
      setStatusMessage({ type: 'error', text: 'Please enter a token to test.' });
      return;
    }

    setIsTesting(true);
    setTestResult(null);
    setStatusMessage(null);

    try {
      const res = await fetch('/api/config/test-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: trimmed }),
      });
      const data = await res.json();
      setTestResult(data);
      if (data.valid) {
        setStatusMessage({
          type: 'success',
          text: `Verified with Upstox API! User: ${data.user_name || 'Authorized'} (ID: ${data.user_id || 'Active'})`,
        });
      } else {
        setStatusMessage({
          type: 'error',
          text: `Upstox rejected token: ${data.error || 'Invalid credentials'}`,
          canForce: true,
        });
      }
    } catch (err: any) {
      setStatusMessage({
        type: 'error',
        text: `Network connection error: ${err.message || 'Could not reach server'}`,
        canForce: true,
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSaveToken = async (force = false) => {
    const trimmed = tokenInput.trim();
    if (!trimmed) {
      setStatusMessage({ type: 'error', text: 'Please enter a token before saving.' });
      return;
    }

    setIsSaving(true);
    setStatusMessage(null);

    try {
      const res = await fetch('/api/config/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: trimmed, force }),
      });
      const data = await res.json();

      if (data.success) {
        setStatusMessage({
          type: 'success',
          text: `Token updated and applied in-memory! Saved to server .env.`,
        });
        setTokenInput('');
        fetchStatus();
        onTokenUpdated?.();
        setTimeout(() => {
          onClose();
        }, 1200);
      } else {
        setStatusMessage({
          type: 'error',
          text: data.error || data.message || 'Failed to update token.',
          canForce: data.can_force || true,
        });
      }
    } catch (err: any) {
      setStatusMessage({
        type: 'error',
        text: `Error saving token: ${err.message || 'Server error'}`,
        canForce: true,
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-150">
      <div 
        className="w-full max-w-xl bg-terminal-card border border-terminal-border rounded-xl shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-terminal-border/80 bg-terminal-surface/60">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-cyan-950/80 border border-cyan-800/60 flex items-center justify-center text-cyan-400">
              <Key className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                Upstox Broker Access Token
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-900/50 text-cyan-300 border border-cyan-700/50">
                  Daily Auth
                </span>
              </h3>
              <p className="text-xs text-terminal-muted">
                Replace or renew your token directly from the hosted web interface.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-terminal-muted hover:text-white hover:bg-terminal-border/50 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-5 overflow-y-auto max-h-[75vh]">
          {/* Current Status Box */}
          <div className="flex items-center justify-between p-3.5 rounded-lg bg-terminal-surface border border-terminal-border">
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full ${currentStatus?.has_token ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
              <div>
                <div className="text-xs font-semibold text-terminal-muted">ACTIVE SERVER TOKEN</div>
                <div className="text-sm font-mono text-white">
                  {currentStatus?.has_token ? currentStatus.token_masked : 'Not Configured'}
                </div>
              </div>
            </div>
            <span className={`text-xs px-2.5 py-1 rounded font-mono font-medium ${
              currentStatus?.has_token 
                ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/60' 
                : 'bg-rose-950/60 text-rose-400 border border-rose-800/60'
            }`}>
              {currentStatus?.has_token ? 'TOKEN ACTIVE' : 'MISSING / EXPIRED'}
            </span>
          </div>

          {/* Daily Expiry Info Note */}
          <div className="p-3.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-200/90 space-y-1.5">
            <div className="font-semibold flex items-center gap-1.5 text-amber-300">
              <HelpCircle className="w-3.5 h-3.5" />
              Upstox Access Tokens Expire Daily
            </div>
            <p className="leading-relaxed">
              Upstox API tokens automatically expire every morning around <strong>03:30 AM IST</strong>. 
              When running this hosted site, you can paste today's renewed access token here without needing terminal access or a server reboot.
            </p>
            <div className="pt-1">
              <a
                href="https://developer.upstox.com/"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-cyan-400 hover:text-cyan-300 underline font-medium"
              >
                <span>Generate Token from Upstox Developer Console</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>

          {/* Input Area */}
          <div className="space-y-2">
            <label className="block text-xs font-semibold uppercase tracking-wider text-terminal-muted">
              Paste New Upstox Access Token
            </label>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                className="w-full px-3.5 py-2.5 pr-20 bg-terminal-surface border border-terminal-border rounded-lg text-sm font-mono text-white placeholder-terminal-muted/60 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-colors"
                autoComplete="off"
                spellCheck="false"
              />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setShowToken(!showToken)}
                  className="p-1.5 text-terminal-muted hover:text-white rounded hover:bg-terminal-border/40 transition-colors"
                  title={showToken ? 'Hide token' : 'Show token'}
                >
                  {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
                {tokenInput && (
                  <button
                    type="button"
                    onClick={() => setTokenInput('')}
                    className="p-1.5 text-terminal-muted hover:text-rose-400 rounded hover:bg-terminal-border/40 transition-colors"
                    title="Clear"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
            <p className="text-[11px] text-terminal-muted flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              Token stays server-side only in <code>.env</code> and engine memory. Never logged or leaked to clients.
            </p>
          </div>

          {/* Status Message / Test Feedback */}
          {statusMessage && (
            <div className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 animate-in fade-in duration-200 ${
              statusMessage.type === 'success'
                ? 'bg-emerald-950/50 border-emerald-800/60 text-emerald-300'
                : statusMessage.type === 'warning'
                ? 'bg-amber-950/50 border-amber-800/60 text-amber-300'
                : 'bg-rose-950/50 border-rose-800/60 text-rose-300'
            }`}>
              {statusMessage.type === 'success' ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              )}
              <div className="flex-1 space-y-1">
                <div className="font-medium leading-relaxed">{statusMessage.text}</div>
                {statusMessage.canForce && (
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => handleSaveToken(true)}
                      disabled={isSaving}
                      className="px-2.5 py-1 text-[11px] font-semibold rounded bg-rose-900/60 hover:bg-rose-800 text-rose-200 border border-rose-700/60 transition-colors"
                    >
                      {isSaving ? 'Saving...' : 'Bypass Validation & Force Save'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-terminal-border/80 bg-terminal-surface/40 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-terminal-muted hover:text-white rounded-lg hover:bg-terminal-border/50 transition-colors"
          >
            Cancel
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleTestToken}
              disabled={isTesting || isSaving || !tokenInput.trim()}
              className="px-4 py-2 text-xs font-semibold rounded-lg bg-terminal-surface border border-terminal-border hover:border-terminal-subtext text-terminal-text hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              {isTesting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                  <span>Testing with Upstox...</span>
                </>
              ) : (
                <span>Test Connection</span>
              )}
            </button>

            <button
              type="button"
              onClick={() => handleSaveToken(false)}
              disabled={isSaving || isTesting || !tokenInput.trim()}
              className="px-4 py-2 text-xs font-semibold rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Applying Token...</span>
                </>
              ) : (
                <span>Save & Apply Token</span>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
