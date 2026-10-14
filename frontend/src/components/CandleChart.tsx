import React, { useEffect, useRef } from 'react';
import { 
  createChart, 
  CandlestickSeries, 
  LineSeries, 
  ColorType, 
  type IChartApi, 
  type ISeriesApi, 
  type CandlestickData, 
  type LineData, 
  type Time 
} from 'lightweight-charts';
import type { CandleData } from '../types';

interface CandleChartProps {
  candles: CandleData[];
  spotPrice?: number;
}

export const CandleChart: React.FC<CandleChartProps> = ({ candles, spotPrice }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const ema20SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Initialize Lightweight Chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#111726' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: 'Inter, system-ui, sans-serif',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
      },
      crosshair: {
        vertLine: {
          color: '#38bdf8',
          width: 1,
          style: 3,
          labelBackgroundColor: '#0369a1',
        },
        horzLine: {
          color: '#38bdf8',
          width: 1,
          style: 3,
          labelBackgroundColor: '#0369a1',
        },
      },
      rightPriceScale: {
        borderColor: '#1f2d4a',
        autoScale: true,
      },
      timeScale: {
        borderColor: '#1f2d4a',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // Add Candlestick Series (v5 API)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#f43f5e',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#f43f5e',
    });
    candleSeriesRef.current = candleSeries;

    // Add EMA20 Line (Amber/Gold)
    const ema20Series = chart.addSeries(LineSeries, {
      color: '#fbbf24',
      lineWidth: 2,
      title: 'EMA20',
      priceLineVisible: false,
    });
    ema20SeriesRef.current = ema20Series;

    // Add EMA50 Line (Violet/Purple)
    const ema50Series = chart.addSeries(LineSeries, {
      color: '#a855f7',
      lineWidth: 2,
      title: 'EMA50',
      priceLineVisible: false,
    });
    ema50SeriesRef.current = ema50Series;

    // Responsive resize handler
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight || 360,
        });
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  // Update Data
  useEffect(() => {
    if (!candleSeriesRef.current || !ema20SeriesRef.current || !ema50SeriesRef.current || candles.length === 0) return;

    // Format and sort candles by time ascending
    const formattedCandles: CandlestickData<Time>[] = [];
    const formattedEma20: LineData<Time>[] = [];
    const formattedEma50: LineData<Time>[] = [];

    // Deduplicate and ensure ascending timestamps
    const sorted = [...candles].sort((a, b) => a.time - b.time);
    const seenTimes = new Set<number>();

    for (const c of sorted) {
      if (seenTimes.has(c.time)) continue;
      seenTimes.add(c.time);

      const timeVal = c.time as Time;
      formattedCandles.push({
        time: timeVal,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      });

      if (c.ema20 !== undefined && c.ema20 !== null) {
        formattedEma20.push({ time: timeVal, value: c.ema20 });
      }
      if (c.ema50 !== undefined && c.ema50 !== null) {
        formattedEma50.push({ time: timeVal, value: c.ema50 });
      }
    }

    try {
      candleSeriesRef.current.setData(formattedCandles);
      ema20SeriesRef.current.setData(formattedEma20);
      ema50SeriesRef.current.setData(formattedEma50);
      chartRef.current?.timeScale().fitContent();
    } catch (e) {
      console.warn("Chart data update skipped due to formatting:", e);
    }
  }, [candles]);

  return (
    <div className="w-full h-full flex flex-col bg-terminal-surface rounded-xl border border-terminal-border overflow-hidden p-3">
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-terminal-border/60">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-white tracking-wide">NIFTY 50 • 1-MIN CANDLES</span>
          <span className="text-[11px] font-mono text-cyan-400">
            {spotPrice ? `Spot: ${spotPrice.toFixed(2)}` : ''}
          </span>
        </div>
        <div className="flex items-center gap-4 text-[11px]">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-amber-400 rounded-full" />
            <span className="text-amber-300 font-mono">EMA20</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-purple-400 rounded-full" />
            <span className="text-purple-300 font-mono">EMA50</span>
          </div>
          <span className="text-terminal-muted hidden sm:inline">IST (UTC+5:30)</span>
        </div>
      </div>

      <div className="flex-1 w-full min-h-[340px] relative" ref={chartContainerRef}>
        {candles.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-terminal-muted">
            <span className="text-xs">Awaiting candle stream from live engine...</span>
          </div>
        )}
      </div>
    </div>
  );
};
