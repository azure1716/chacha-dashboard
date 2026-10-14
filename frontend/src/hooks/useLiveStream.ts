import { useEffect, useRef, useState, useCallback } from 'react';
import { LiveStateSnapshot } from '../types';

export type ConnectionMode = 'CONNECTED' | 'RECONNECTING' | 'DISCONNECTED' | 'FALLBACK_POLLING';

export function useLiveStream() {
  const [snapshot, setSnapshot] = useState<LiveStateSnapshot | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionMode>('DISCONNECTED');
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const pollingIntervalRef = useRef<number | null>(null);
  const isComponentMounted = useRef<boolean>(true);

  // Fallback REST polling
  const pollRestState = useCallback(async () => {
    try {
      const res = await fetch('/api/live/state');
      if (res.ok) {
        const data: LiveStateSnapshot = await res.json();
        if (isComponentMounted.current) {
          setSnapshot(data);
          setLastUpdated(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' }) + ' IST');
        }
      }
    } catch (e: any) {
      if (isComponentMounted.current) {
        setError(e?.message || 'Polling error');
      }
    }
  }, []);

  const startPollingFallback = useCallback(() => {
    if (pollingIntervalRef.current) return;
    setConnectionStatus('FALLBACK_POLLING');
    pollRestState(); // immediate poll
    pollingIntervalRef.current = window.setInterval(pollRestState, 3000);
  }, [pollRestState]);

  const stopPollingFallback = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  const connectWebSocket = useCallback(() => {
    if (!isComponentMounted.current) return;

    // Determine WS URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/live`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isComponentMounted.current) return;
        setConnectionStatus('CONNECTED');
        setError(null);
        stopPollingFallback();
      };

      ws.onmessage = (event) => {
        if (!isComponentMounted.current) return;
        try {
          const data: LiveStateSnapshot = JSON.parse(event.data);
          setSnapshot(data);
          setLastUpdated(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' }) + ' IST');
        } catch (err: any) {
          console.error('Failed to parse WS snapshot:', err);
        }
      };

      ws.onerror = () => {
        if (!isComponentMounted.current) return;
        // On error, initiate fallback polling
        startPollingFallback();
      };

      ws.onclose = () => {
        if (!isComponentMounted.current) return;
        setConnectionStatus('RECONNECTING');
        startPollingFallback();

        // Attempt reconnect after delay
        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = window.setTimeout(() => {
          if (isComponentMounted.current) {
            connectWebSocket();
          }
        }, 5000);
      };
    } catch {
      startPollingFallback();
    }
  }, [startPollingFallback, stopPollingFallback]);

  useEffect(() => {
    isComponentMounted.current = true;
    connectWebSocket();

    return () => {
      isComponentMounted.current = false;
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      stopPollingFallback();
    };
  }, [connectWebSocket, stopPollingFallback]);

  return {
    snapshot,
    connectionStatus,
    lastUpdated,
    error,
    refreshState: pollRestState,
  };
}
