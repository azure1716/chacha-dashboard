export type SignalType = "BUY CALL" | "BUY PUT" | "WAIT";

export interface CandleData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20?: number | null;
  ema50?: number | null;
}

export interface TechnicalData {
  candles?: number;
  ready?: boolean;
  ema_fast?: number | null;
  ema_slow?: number | null;
  rsi?: number | null;
  atr?: number | null;
  atr_pct?: number | null;
  adx?: number | null;
  plus_di?: number | null;
  minus_di?: number | null;
  trend_strength?: string;
  trend?: string;
  score?: number;
}

export interface MomentumData {
  score?: number;
  momentum?: number;
  rsi?: number | null;
}

export interface OptionPressureData {
  score?: number;
  bias?: string;
  oi_score?: number;
  volume_score?: number;
  order_score?: number;
  price_score?: number;
  live_count?: number;
  iv_skew?: number;
  avg_ce_iv?: number;
  avg_pe_iv?: number;
}

export interface EpmData {
  score: number;
  bias: "CALL" | "PUT" | "WAIT";
  volume_score: number;
  iv_skew: number;
  underlying_trend_score: number;
  weights?: [number, number, number];
  status?: string;
}

export interface RiskState {
  daily_pnl: number;
  max_daily_loss: number;
  daily_profit_lock: number | null;
  trades_today: number;
  max_trades_per_day: number;
  consecutive_losses: number;
  max_consecutive_losses: number;
  cooldown_active: boolean;
  cooldown_until: number | null;
  cooldown_remaining_seconds: number;
  capital: number;
  risk_per_trade_pct: number;
  lot_size: number;
  max_lots_per_trade: number;
}

export interface PaperTradeStats {
  closed: number;
  wins: number;
  losses: number;
  gross_pnl: number;
  total_cost: number;
  net_pnl: number;
  win_rate_pct: number;
}

export interface PaperPosition {
  strike: number;
  type: "CE" | "PE";
  direction: "CALL" | "PUT";
  lots: number;
  entry: number;
  sl: number;
  target: number;
  delta?: number;
  atr_used?: number;
  confidence?: number;
  iv_percentile_at_entry?: number;
  trail_active?: boolean;
  key?: string;
  current_ltp?: number;
  current_bid?: number;
  current_ask?: number;
  unrealized_gross_pnl?: number;
  unrealized_cost?: number;
  unrealized_net_pnl?: number;
}

export interface LiveStateSnapshot {
  timestamp: string;
  timestamp_epoch: number;
  market_session: "OPEN" | "CLOSED";
  trade_window: "YES" | "NO";
  ws_subscribed: boolean;
  ws_connected: boolean;
  spot: number;
  atm: number | null;
  data_quality: {
    nifty_live: boolean;
    live_options: number;
    total_options: number;
    option_quality: number;
    status: "GOOD" | "PARTIAL" | "LOW";
  };
  candle_status: string;
  historical_last_minute: number | null;
  candles: CandleData[];
  technical: TechnicalData;
  momentum: MomentumData;
  options: OptionPressureData;
  htf_trend: "BULLISH" | "BEARISH" | "NEUTRAL" | null;
  epm: EpmData;
  signal: SignalType;
  confidence: number;
  reason: string;
  confidence_threshold: number;
  weights: {
    technical: number;
    momentum: number;
    options: number;
  };
  risk_state: RiskState;
  paper_stats: PaperTradeStats;
  paper_position: PaperPosition | null;
  token_status?: {
    has_token: boolean;
    token_masked: string;
  };
  real_order: boolean;
  banner: string;
}

export interface SignalLogRow {
  timestamp: string;
  spot: string;
  signal: string;
  confidence: string;
  reason: string;
  technical_score: string;
  trend: string;
  trend_strength: string;
  adx: string;
  momentum_score: string;
  option_score: string;
  option_bias: string;
  htf_trend: string;
  atr_pct: string;
  epm_score?: string;
  epm_bias?: string;
}

export interface TradeLogRow {
  entry_time: string;
  exit_time: string;
  signal: string;
  direction: string;
  strike: string;
  type: string;
  lots: string;
  entry: string;
  exit: string;
  sl: string;
  target: string;
  atr_used: string;
  option_delta: string;
  confidence: string;
  iv_percentile_at_entry: string;
  gross_pnl: string;
  cost: string;
  net_pnl: string;
  exit_reason: string;
  used_ltp_fallback_entry?: string;
  used_ltp_fallback_exit?: string;
}

export interface TradeStatsSummary {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  total_gross_pnl: number;
  total_cost: number;
  total_net_pnl: number;
  avg_trade_pnl: number;
  profit_factor: number | null;
  max_drawdown: number;
  by_exit_reason: Record<string, number>;
  equity_curve: Array<{
    trade_num: number;
    time: string;
    net_pnl: number;
    cumulative_net: number;
    drawdown: number;
    exit_reason: string;
    direction: string;
    strike: string;
  }>;
}

export interface BacktestJobResult {
  dataset_name: string;
  total_bars: number;
  is_synthetic: boolean;
  params: {
    sl_multiplier: number;
    target_multiplier: number;
    min_adx: number;
    min_direction_score: number;
    require_htf_agreement: boolean;
    htf_factor: number;
    atr_pct_min: number;
    max_hold_bars: number;
  };
  stats: {
    trades: number;
    win_rate_pct: number;
    avg_pnl_points: number;
    total_pnl_points: number;
    avg_R: number;
    max_drawdown_points: number;
    profit_factor: number | null;
  };
  exit_reasons: Record<string, number>;
  trades: Array<{
    entry_idx: number;
    exit_idx: number;
    signal: string;
    entry: number;
    exit: number;
    pnl_points: number;
    exit_reason: string;
    risk_points: number;
  }>;
  total_trades_count: number;
  equity_curve: Array<{
    trade_index: number;
    timestamp: string;
    pnl_points: number;
    cumulative_points: number;
    drawdown: number;
    signal: string;
    exit_reason: string;
  }>;
  caveats: string[];
  header_warning: string;
}

export interface SweepJobResult {
  dataset_name: string;
  is_synthetic: boolean;
  total_bars: number;
  total_combos_tested: number;
  combos_meeting_min_trades: number;
  min_trades_threshold: number;
  strong_configs_count: number;
  top_configs: Array<{
    sl_mult: number;
    target_mult: number;
    adx_min: number;
    dir_score_min: number;
    rr_ratio: number;
    trades: number;
    win_rate_pct: number;
    breakeven_win_rate_pct: number;
    edge_vs_breakeven_pct: number;
    profit_factor: number | null;
    avg_R: number;
    max_drawdown_points: number;
  }>;
  bottom_configs: Array<any>;
  all_results: Array<any>;
  heatmap: {
    sl_multipliers: number[];
    target_multipliers: number[];
    matrix: Record<string, Record<string, {
      avg_pf: number;
      avg_edge: number;
      combos_count: number;
      best_pf: number;
    } | null>>;
  };
  multiple_testing_warning: string;
}

export interface SystemConfig {
  engine: Record<string, any>;
  indicators: Record<string, any>;
  thresholds: Record<string, any>;
  exit_and_trailing: Record<string, any>;
  session_times: Record<string, any>;
  risk_management: Record<string, any>;
  cost_model: Record<string, any>;
  epm_module: {
    status: string;
    weights: [number, number, number];
    description: string;
  };
  warnings: Record<string, string>;
  recent_exceptions: Array<{
    timestamp: string;
    label: string;
    error: string;
    traceback: string;
  }>;
}
