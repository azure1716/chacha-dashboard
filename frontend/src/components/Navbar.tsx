import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  BarChart3, 
  ShieldAlert, 
  FileText, 
  FlaskConical, 
  SlidersHorizontal, 
  Settings, 
  Wifi, 
  WifiOff, 
  Clock, 
  AlertTriangle,
  Key
} from 'lucide-react';
import { ConnectionMode } from '../hooks/useLiveStream';
import { LiveStateSnapshot } from '../types';

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  connectionStatus: ConnectionMode;
  snapshot: LiveStateSnapshot | null;
  onOpenTokenModal?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  connectionStatus,
  snapshot,
  onOpenTokenModal,
}) => {
  const [currentTimeIST, setCurrentTimeIST] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTimeIST(now.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }) + ' IST');
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const navItems = [
    { id: 'live', label: 'Live Monitor', icon: Activity },
    { id: 'trades', label: 'Trade History', icon: BarChart3 },
    { id: 'risk', label: 'Risk Manager', icon: ShieldAlert },
    { id: 'signals', label: 'Signals Log', icon: FileText },
    { id: 'backtest', label: 'Backtest Lab', icon: FlaskConical },
    { id: 'sweep', label: 'Param Sweep', icon: SlidersHorizontal },
    { id: 'config', label: 'System Config', icon: Settings },
  ];

  const isMarketOpen = snapshot?.market_session === 'OPEN';
  const isTradeWindow = snapshot?.trade_window === 'YES';

  return (
    <header className="sticky top-0 z-50 bg-terminal-bg/95 backdrop-blur-md border-b border-terminal-border">
      {/* Persistent Impossible-to-miss Safety Banner */}
      <div className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-1.5 flex items-center justify-between text-xs text-amber-300">
        <div className="flex items-center gap-2 font-medium">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span>
            <strong>PAPER TRADING ONLY</strong> — Real order execution is deliberately disabled (<code>REAL_ORDER = False</code>). No broker orders are placed.
          </span>
        </div>
        <div className="hidden sm:flex items-center gap-3 text-terminal-subtext">
          <span className="flex items-center gap-1 font-mono">
            <Clock className="w-3 h-3 text-cyan-400" />
            {currentTimeIST}
          </span>
        </div>
      </div>

      {/* Main Bar */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          {/* Logo / App Name */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white shadow-lg shadow-cyan-500/20">
              N
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base tracking-wide text-white">NIFTY OPTIONS</span>
                <span className="text-[10px] uppercase font-mono tracking-wider px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/50">
                  V48 Heuristic
                </span>
              </div>
              <p className="text-[10px] text-terminal-muted hidden sm:block">Heuristic Directional + Options Pressure Dashboard</p>
            </div>
          </div>

          {/* Status Indicators */}
          <div className="flex items-center gap-2 sm:gap-4">
            {/* Market Session */}
            <div className={`text-xs px-2.5 py-1 rounded-md border flex items-center gap-1.5 font-medium ${
              isMarketOpen 
                ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/50' 
                : 'bg-slate-900 text-slate-400 border-slate-800'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isMarketOpen ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
              <span className="hidden md:inline">Market:</span>
              <span className="font-mono uppercase">{snapshot?.market_session || 'CLOSED'}</span>
            </div>

            {/* Trade Window */}
            <div className={`text-xs px-2.5 py-1 rounded-md border flex items-center gap-1.5 font-medium ${
              isTradeWindow 
                ? 'bg-cyan-950/60 text-cyan-400 border-cyan-800/50' 
                : 'bg-slate-900 text-slate-400 border-slate-800'
            }`}>
              <span className="hidden lg:inline">Window (09:25–14:50):</span>
              <span className="font-mono">{isTradeWindow ? 'ACTIVE' : 'IDLE'}</span>
            </div>

            {/* Connection Status */}
            <div className={`text-xs px-2.5 py-1 rounded-md border flex items-center gap-1.5 font-medium ${
              connectionStatus === 'CONNECTED'
                ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800/50'
                : connectionStatus === 'FALLBACK_POLLING'
                ? 'bg-amber-950/40 text-amber-300 border-amber-800/50'
                : 'bg-rose-950/40 text-rose-300 border-rose-800/50'
            }`}>
              {connectionStatus === 'CONNECTED' ? (
                <Wifi className="w-3.5 h-3.5 text-emerald-400" />
              ) : connectionStatus === 'FALLBACK_POLLING' ? (
                <Wifi className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
              ) : (
                <WifiOff className="w-3.5 h-3.5 text-rose-400" />
              )}
              <span className="font-mono hidden sm:inline">
                {connectionStatus === 'CONNECTED' && 'LIVE WS'}
                {connectionStatus === 'FALLBACK_POLLING' && 'POLLING REST'}
                {connectionStatus === 'RECONNECTING' && 'RECONNECTING...'}
                {connectionStatus === 'DISCONNECTED' && 'OFFLINE'}
              </span>
            </div>

            {/* Upstox Token Button */}
            <button
              onClick={onOpenTokenModal}
              title="Click to view or update your daily Upstox broker token"
              className={`text-xs px-2.5 py-1 rounded-md border flex items-center gap-1.5 font-medium transition-colors ${
                snapshot?.token_status?.has_token
                  ? 'bg-cyan-950/40 text-cyan-300 border-cyan-800/50 hover:bg-cyan-900/40'
                  : 'bg-amber-950/60 text-amber-300 border-amber-700/60 hover:bg-amber-900/60 animate-pulse'
              }`}
            >
              <Key className="w-3.5 h-3.5 text-cyan-400" />
              <span className="font-mono hidden sm:inline">
                {snapshot?.token_status?.has_token ? 'TOKEN ACTIVE' : 'REPLACE TOKEN'}
              </span>
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex space-x-1 overflow-x-auto pb-2 scrollbar-none pt-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
                  isActive
                    ? 'bg-gradient-to-r from-cyan-600 to-blue-600 text-white shadow-sm shadow-cyan-500/20'
                    : 'text-terminal-subtext hover:text-white hover:bg-terminal-card/80'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-white' : 'text-terminal-muted'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
};
