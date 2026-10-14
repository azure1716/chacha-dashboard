import React, { useState } from 'react';

interface EquityPoint {
  trade_index?: number;
  trade_num?: number;
  timestamp?: string;
  time?: string;
  pnl_points?: number;
  net_pnl?: number;
  cumulative_points?: number;
  cumulative_net?: number;
  drawdown?: number;
}

interface EquityCurveChartProps {
  data: EquityPoint[];
  title?: string;
  unitLabel?: string;
}

export const EquityCurveChart: React.FC<EquityCurveChartProps> = ({
  data,
  title = "Cumulative Equity Curve",
  unitLabel = "INR",
}) => {
  const [hoveredPoint, setHoveredPoint] = useState<EquityPoint | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="w-full h-64 glass-panel rounded-xl flex items-center justify-center border border-terminal-border text-terminal-muted text-xs">
        No equity curve data available yet.
      </div>
    );
  }

  // Extract points
  const points = data.map((d, i) => {
    const val = d.cumulative_net !== undefined ? d.cumulative_net : (d.cumulative_points ?? 0);
    const pnl = d.net_pnl !== undefined ? d.net_pnl : (d.pnl_points ?? 0);
    const label = d.timestamp || d.time || `Trade ${i + 1}`;
    const dd = d.drawdown ?? 0;
    return { ...d, index: i, value: val, pnl, label, dd };
  });

  const values = points.map(p => p.value);
  const minVal = Math.min(0, ...values);
  const maxVal = Math.max(0.1, ...values);
  const range = (maxVal - minVal) || 1;

  const width = 800;
  const height = 240;
  const paddingX = 40;
  const paddingY = 30;
  const plotWidth = width - paddingX * 2;
  const plotHeight = height - paddingY * 2;

  // Convert points to SVG coordinates
  const svgCoords = points.map(p => {
    const x = paddingX + (p.index / Math.max(1, points.length - 1)) * plotWidth;
    const y = height - paddingY - ((p.value - minVal) / range) * plotHeight;
    return { x, y, point: p };
  });

  // Zero line coordinate
  const zeroY = height - paddingY - ((0 - minVal) / range) * plotHeight;

  // Build path string
  const pathD = svgCoords.reduce((acc, curr, idx) => {
    return `${acc} ${idx === 0 ? 'M' : 'L'} ${curr.x} ${curr.y}`;
  }, '');

  // Fill path string under curve
  const fillD = `${pathD} L ${svgCoords[svgCoords.length - 1].x} ${zeroY} L ${svgCoords[0].x} ${zeroY} Z`;

  const isNetPositive = (values[values.length - 1] || 0) >= 0;

  return (
    <div className="glass-panel rounded-xl p-4 border border-terminal-border flex flex-col">
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-terminal-border/60">
        <div>
          <span className="text-xs font-semibold text-white tracking-wide">{title}</span>
          <span className="text-[11px] font-mono text-terminal-muted ml-2">({points.length} trades plotted)</span>
        </div>
        <div className="text-right">
          <span className="text-[10px] font-mono uppercase text-terminal-muted block">Final Equity</span>
          <span className={`text-base font-bold font-mono ${isNetPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isNetPositive ? '+' : ''}{(values[values.length - 1] || 0).toFixed(2)} {unitLabel}
          </span>
        </div>
      </div>

      <div className="relative w-full aspect-[16/6] min-h-[220px]">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full overflow-visible">
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line x1={paddingX} y1={paddingY} x2={width - paddingX} y2={paddingY} stroke="rgba(255,255,255,0.05)" />
          <line x1={paddingX} y1={zeroY} x2={width - paddingX} y2={zeroY} stroke="rgba(255,255,255,0.2)" strokeDasharray="4 4" />
          <line x1={paddingX} y1={height - paddingY} x2={width - paddingX} y2={height - paddingY} stroke="rgba(255,255,255,0.05)" />

          {/* Zero label */}
          <text x={paddingX - 8} y={zeroY + 4} fill="#64748b" fontSize="10" textAnchor="end" fontFamily="monospace">
            0.0
          </text>
          {/* Max label */}
          <text x={paddingX - 8} y={paddingY + 4} fill="#64748b" fontSize="10" textAnchor="end" fontFamily="monospace">
            {maxVal.toFixed(0)}
          </text>
          {/* Min label */}
          <text x={paddingX - 8} y={height - paddingY + 4} fill="#64748b" fontSize="10" textAnchor="end" fontFamily="monospace">
            {minVal.toFixed(0)}
          </text>

          {/* Shaded Area */}
          <path d={fillD} fill="url(#equityGrad)" />

          {/* Equity Line */}
          <path d={pathD} fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

          {/* Interactive points */}
          {svgCoords.map((c, i) => (
            <circle
              key={i}
              cx={c.x}
              cy={c.y}
              r={hoveredPoint === c.point ? 5 : 3}
              fill={hoveredPoint === c.point ? "#38bdf8" : "#10b981"}
              stroke="#0a0d14"
              strokeWidth="1.5"
              className="cursor-pointer transition-all"
              onMouseEnter={() => setHoveredPoint(c.point)}
            />
          ))}
        </svg>

        {/* Hover Tooltip */}
        {hoveredPoint && (
          <div className="absolute top-2 right-4 bg-slate-900/95 border border-cyan-500/40 p-2.5 rounded-lg text-xs font-mono shadow-xl backdrop-blur-md">
            <div className="text-cyan-400 font-bold mb-1">
              Trade #{hoveredPoint.trade_index || hoveredPoint.trade_num} • {hoveredPoint.time || hoveredPoint.timestamp}
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-terminal-muted">Trade P&L:</span>
              <span className={(hoveredPoint.net_pnl || hoveredPoint.pnl_points || 0) >= 0 ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                {(hoveredPoint.net_pnl || hoveredPoint.pnl_points || 0) > 0 ? "+" : ""}
                {(hoveredPoint.net_pnl || hoveredPoint.pnl_points || 0).toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-terminal-muted">Cumulative:</span>
              <span className="text-white font-bold">
                {(hoveredPoint.cumulative_net || hoveredPoint.cumulative_points || 0).toFixed(2)} {unitLabel}
              </span>
            </div>
            {hoveredPoint.drawdown !== undefined && (
              <div className="flex justify-between gap-4 text-rose-400/80">
                <span>Drawdown:</span>
                <span>-{hoveredPoint.drawdown.toFixed(2)}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
