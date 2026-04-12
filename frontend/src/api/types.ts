// ─── Raw OHLCV candle ─────────────────────────────────────────────────────────
export interface CandleData {
  time: number;   // Unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// ─── SMC overlay types ────────────────────────────────────────────────────────
export interface FVGZone {
  time: number;
  low: number;
  high: number;
  type: "bull" | "bear";
}

export interface OrderBlock {
  time: number;
  low: number;
  high: number;
  type: "bull" | "bear";
}

export interface StructureEvent {
  time: number;
  type: "bos_up" | "bos_down" | "choch_up" | "choch_down";
  level: number;
}

export interface RangeZone {
  start_time: number;
  end_time: number;
  high: number;
  low: number;
  mid: number;
}

export interface SwingPoint {
  time: number;
  level: number;
  type: "high" | "low";
}

export interface SweepEvent {
  time: number;
  type: "sweep_high" | "sweep_low";
  level: number;
}

export interface SignalItem {
  time: number;
  side: "LONG" | "SHORT";
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  conviction: "low" | "normal" | "high";
  ml_bias: number;
  reasons: string;
}

// ─── Full analysis response ───────────────────────────────────────────────────
export interface AnalysisResponse {
  symbol: string;
  timeframe: string;
  candles: CandleData[];
  fvg_zones: FVGZone[];
  order_blocks: OrderBlock[];
  structure_events: StructureEvent[];
  ranges: RangeZone[];
  swing_highs: SwingPoint[];
  swing_lows: SwingPoint[];
  sweeps: SweepEvent[];
  signals: SignalItem[];
}

export type Asset = "BTC" | "ETH";
export type Timeframe = "15m" | "1h" | "4h" | "1d";
