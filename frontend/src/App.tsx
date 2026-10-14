import React, { useState } from 'react';
import { useLiveStream } from './hooks/useLiveStream';
import { Navbar } from './components/Navbar';
import { LiveMonitorPage } from './pages/LiveMonitorPage';
import { TradeHistoryPage } from './pages/TradeHistoryPage';
import { RiskManagementPage } from './pages/RiskManagementPage';
import { SignalsAuditPage } from './pages/SignalsAuditPage';
import { BacktestLabPage } from './pages/BacktestLabPage';
import { ParameterSweepPage } from './pages/ParameterSweepPage';
import { SystemConfigPage } from './pages/SystemConfigPage';
import { TokenModal } from './components/TokenModal';

export function App() {
  const [activeTab, setActiveTab] = useState<string>('live');
  const [isTokenModalOpen, setIsTokenModalOpen] = useState<boolean>(false);
  const { snapshot, connectionStatus, lastUpdated, refreshState } = useLiveStream();

  return (
    <div className="min-h-screen bg-terminal-bg text-terminal-text flex flex-col font-sans selection:bg-cyan-500/30 selection:text-cyan-200">
      {/* Navbar with persistent safety banner */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        connectionStatus={connectionStatus}
        snapshot={snapshot}
        onOpenTokenModal={() => setIsTokenModalOpen(true)}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'live' && (
          <LiveMonitorPage
            snapshot={snapshot}
            connectionStatus={connectionStatus}
            lastUpdated={lastUpdated}
            onRefresh={refreshState}
            onOpenTokenModal={() => setIsTokenModalOpen(true)}
          />
        )}

        {activeTab === 'trades' && (
          <TradeHistoryPage
            currentPosition={snapshot?.paper_position || null}
          />
        )}

        {activeTab === 'risk' && (
          <RiskManagementPage
            riskState={snapshot?.risk_state || null}
          />
        )}

        {activeTab === 'signals' && (
          <SignalsAuditPage />
        )}

        {activeTab === 'backtest' && (
          <BacktestLabPage />
        )}

        {activeTab === 'sweep' && (
          <ParameterSweepPage />
        )}

        {activeTab === 'config' && (
          <SystemConfigPage
            onOpenTokenModal={() => setIsTokenModalOpen(true)}
          />
        )}
      </main>

      {/* Daily Upstox Token Management Modal */}
      <TokenModal
        isOpen={isTokenModalOpen}
        onClose={() => setIsTokenModalOpen(false)}
        onTokenUpdated={refreshState}
      />

      {/* Footer */}
      <footer className="border-t border-terminal-border/60 py-4 bg-terminal-surface/40 text-xs font-mono text-terminal-muted">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            <span>NIFTY Options Paper-Trading Heuristic Engine • Pure Python Strategy Core</span>
          </div>

          <div className="flex items-center gap-4">
            <span>REAL_ORDER = False (Strictly Enforced)</span>
            <span>All timestamps in Indian Standard Time (IST, UTC+5:30)</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
