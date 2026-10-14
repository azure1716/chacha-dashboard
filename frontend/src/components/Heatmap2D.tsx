import React, { useState } from 'react';

interface HeatmapData {
  sl_multipliers: number[];
  target_multipliers: number[];
  matrix: Record<string, Record<string, {
    avg_pf: number;
    avg_edge: number;
    combos_count: number;
    best_pf: number;
  } | null>>;
}

interface Heatmap2DProps {
  heatmap: HeatmapData;
}

export const Heatmap2D: React.FC<Heatmap2DProps> = ({ heatmap }) => {
  const [selectedCell, setSelectedCell] = useState<{
    sl: number;
    target: number;
    data: any;
  } | null>(null);

  const { sl_multipliers, target_multipliers, matrix } = heatmap;

  if (!sl_multipliers || !target_multipliers || sl_multipliers.length === 0) {
    return (
      <div className="p-4 text-center text-xs text-terminal-muted">
        No parameter sweep heatmap data available.
      </div>
    );
  }

  const getCellColor = (data: any) => {
    if (!data) return 'bg-slate-900/60 border-slate-800 text-slate-600';
    const pf = data.avg_pf || 0;
    if (pf >= 1.5) return 'bg-emerald-600/40 border-emerald-500 text-emerald-300 font-bold';
    if (pf >= 1.2) return 'bg-emerald-800/40 border-emerald-700 text-emerald-400';
    if (pf >= 1.0) return 'bg-cyan-900/40 border-cyan-800 text-cyan-300';
    if (pf >= 0.8) return 'bg-amber-900/30 border-amber-800 text-amber-400';
    return 'bg-rose-950/40 border-rose-900 text-rose-400';
  };

  return (
    <div className="glass-panel rounded-xl p-4 border border-terminal-border flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-xs font-semibold text-white uppercase tracking-wider">
            Parameter Space Heatmap (SL Multiplier × Target Multiplier)
          </h4>
          <p className="text-[11px] text-terminal-muted">
            Cells colored by Average Profit Factor across tested ADX & Direction-Score combinations.
          </p>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-emerald-600/60" /> PF ≥ 1.2</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-cyan-900/60" /> PF 1.0–1.2</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-rose-950/60" /> PF &lt; 1.0</span>
        </div>
      </div>

      <div className="overflow-x-auto pb-2">
        <table className="w-full border-collapse text-xs font-mono">
          <thead>
            <tr>
              <th className="p-2 border border-terminal-border/60 text-left text-terminal-muted bg-terminal-surface">
                SL \ TGT
              </th>
              {target_multipliers.map((tgt) => (
                <th key={tgt} className="p-2 border border-terminal-border/60 text-center text-cyan-400 bg-terminal-surface">
                  {tgt}x ATR
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sl_multipliers.map((sl) => (
              <tr key={sl}>
                <th className="p-2 border border-terminal-border/60 text-left text-amber-400 bg-terminal-surface whitespace-nowrap">
                  {sl}x ATR
                </th>
                {target_multipliers.map((tgt) => {
                  const cell = matrix[String(sl)]?.[String(tgt)];
                  const isSelected = selectedCell?.sl === sl && selectedCell?.target === tgt;
                  return (
                    <td
                      key={tgt}
                      onClick={() => setSelectedCell({ sl, target: tgt, data: cell })}
                      className={`p-3 border text-center cursor-pointer transition-all ${getCellColor(cell)} ${
                        isSelected ? 'ring-2 ring-cyan-400 scale-[0.98]' : 'hover:scale-[0.98]'
                      }`}
                    >
                      {cell ? (
                        <div>
                          <div className="font-bold text-sm">
                            {cell.avg_pf.toFixed(2)}
                          </div>
                          <div className="text-[10px] opacity-80">
                            Edge: {cell.avg_edge > 0 ? '+' : ''}{cell.avg_edge.toFixed(1)}%
                          </div>
                        </div>
                      ) : (
                        <span className="text-slate-600 text-xs">--</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedCell && selectedCell.data && (
        <div className="bg-terminal-bg/80 border border-cyan-500/30 p-3 rounded-lg text-xs font-mono flex flex-wrap items-center justify-between gap-4 mt-1">
          <div>
            <span className="text-cyan-400 font-bold">
              Cell Inspector: SL {selectedCell.sl}x ATR • Target {selectedCell.target}x ATR
            </span>
            <span className="text-terminal-muted block text-[11px]">
              Reward:Risk Ratio: {(selectedCell.target / selectedCell.sl).toFixed(2)}:1 • Requires Win Rate &gt; {(100 / (1 + selectedCell.target / selectedCell.sl)).toFixed(1)}% to break even
            </span>
          </div>
          <div className="flex gap-4">
            <div>
              <span className="text-[10px] text-terminal-muted block">Avg Profit Factor</span>
              <span className="font-bold text-white text-sm">{selectedCell.data.avg_pf.toFixed(3)}</span>
            </div>
            <div>
              <span className="text-[10px] text-terminal-muted block">Best PF in Cell</span>
              <span className="font-bold text-emerald-400 text-sm">{selectedCell.data.best_pf.toFixed(3)}</span>
            </div>
            <div>
              <span className="text-[10px] text-terminal-muted block">Edge vs Breakeven</span>
              <span className={`font-bold text-sm ${selectedCell.data.avg_edge > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {selectedCell.data.avg_edge > 0 ? '+' : ''}{selectedCell.data.avg_edge.toFixed(2)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
