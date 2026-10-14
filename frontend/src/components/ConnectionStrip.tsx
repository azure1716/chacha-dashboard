import React from 'react';
import { LiveStateSnapshot } from '../types';
import { ConnectionMode } from '../hooks/useLiveStream';
import { Server, Database, Radio, Flame, CheckCircle, AlertCircle, RefreshCw, Key } from 'lucide-react';

interface ConnectionStripProps {
  snapshot: LiveStateSnapshot | null;
  connectionStatus: ConnectionMode;
  lastUpdated: string | null;
  onRefresh?: () => void;
  onOpenTokenModal?: () => void;
}

export const ConnectionStrip: React.FC<ConnectionStripProps> = ({
  snapshot,
  connectionStatus,
  lastUpdated,
  onRefresh,
  onOpenTokenModal,
}) => {
  const quality = snapshot?.data_quality;
  const isGoodQuality = quality?.status === 'GOOD';
  const isPartialQuality = quality?.status === 'PARTIAL';

  return (
    <div className="glass-panel rounded-xl p-3 border border-terminal-border flex flex-wrap items-center justify-between gap-3 text-xs">
      <div className="flex flex-wrap items-center gap-4 sm:gap-6">
        {/* WebSocket */}
        <div className="flex items-center gap-2">
          <Radio className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-terminal-muted">Engine Feed:</span>
          <span className="font-mono font-medium text-white flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${
              connectionStatus === 'CONNECTED' ? 'bg-emerald-400' :
              connectionStatus === 'FALLBACK_POLLING' ? 'bg-amber-400' : 'bg-rose-400'
            }`} />
            {connectionStatus === 'CONNECTED' ? 'WebSocket Streaming' :
             connectionStatus === 'FALLBACK_POLLING' ? 'REST Polling (Fallback)' : 'Disconnected'}
          </span>
        </div>

        {/* Data Quality */}
        <div className="flex items-center gap-2">
          <Database className="w-3.5 h-3.5 text-purple-400" />
          <span className="text-terminal-muted">Data Quality:</span>
          <span className={`font-mono font-semibold flex items-center gap-1 ${
            isGoodQuality ? 'text-emerald-400' : isPartialQuality ? 'text-amber-400' : 'text-rose-400'
          }`}>
            {isGoodQuality ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
            {quality ? `${quality.status} (${quality.live_options}/${quality.total_options} options)` : '--'}
          </span>
        </div>

        {/* Candle Status */}
        <div className="flex items-center gap-2">
          <Flame className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-terminal-muted">Candle Status:</span>
          <span className="font-mono text-white">
            {snapshot?.candle_status || 'INITIALIZING'}
            {snapshot?.historical_last_minute ? ` (Last: ${snapshot.historical_last_minute})` : ''}
          </span>
        </div>

        {/* Upstox Broker Token */}
        <div className="flex items-center gap-2">
          <Key className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-terminal-muted">Upstox Auth:</span>
          <span className={`font-mono font-medium flex items-center gap-1.5 ${
            snapshot?.token_status?.has_token ? 'text-emerald-400' : 'text-amber-400'
          }`}>
            <span className={`w-2 h-2 rounded-full ${snapshot?.token_status?.has_token ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
            {snapshot?.token_status?.has_token ? snapshot.token_status.token_masked : 'Missing'}
          </span>
          {onOpenTokenModal && (
            <button
              onClick={onOpenTokenModal}
              className="text-[11px] underline text-cyan-400 hover:text-cyan-300 ml-1 font-mono"
            >
              Update
            </button>
          )}
        </div>

        {/* Server Time */}
        <div className="flex items-center gap-2 text-terminal-muted">
          <Server className="w-3.5 h-3.5" />
          <span>Snapshot:</span>
          <span className="font-mono text-terminal-text">{lastUpdated || '--'}</span>
        </div>
      </div>

      {onRefresh && (
        <button
          onClick={onRefresh}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-terminal-hover text-terminal-subtext hover:text-white transition-colors"
          title="Manual refresh from API"
        >
          <RefreshCw className="w-3 h-3" />
          <span>Refresh</span>
        </button>
      )}
    </div>
  );
};
