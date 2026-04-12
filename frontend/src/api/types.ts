// ─── Raw OHLCV candle ─────────────────────────────────────────────────────────
export interface CandleData {
  time:   number; // Unix seconds
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
}

// ─── Swing / Internal pivot points (HH · HL · LH · LL) ───────────────────────
export interface SwingPoint {
  time:       number;
  level:      number;
  pivot_type: "high" | "low";
  label:      "HH" | "HL" | "LH" | "LL";
}

// ─── Structure breaks ─────────────────────────────────────────────────────────
export interface StructureBreak {
  time:       number;
  level:      number;
  break_type: "bos_up" | "bos_down" | "choch_up" | "choch_down";
  scope:      "swing" | "internal";
}

// ─── Order Blocks (LuxAlgo-style, with mitigation status) ────────────────────
export interface OrderBlock {
  time:   number;
  top:    number;
  bottom: number;
  bias:   1 | -1;   // 1 = bullish, -1 = bearish
  scope:  "swing" | "internal";
  active: boolean;
}

// ─── Fair Value Gaps (with mitigation status) ─────────────────────────────────
export interface FVGZone {
  time:   number;
  top:    number;
  bottom: number;
  bias:   1 | -1;
  active: boolean;
}

// ─── Equal Highs / Equal Lows ─────────────────────────────────────────────────
export interface EqualLevel {
  time1: number;
  time2: number;
  level: number;
  label: "EQH" | "EQL";
}

// ─── Strong / Weak High & Low ─────────────────────────────────────────────────
export interface StrongWeakLevel {
  time:  number;
  level: number;
  label: "Strong High" | "Weak High" | "Strong Low" | "Weak Low";
}

// ─── Premium / Equilibrium / Discount zones ───────────────────────────────────
export interface PremiumDiscountZone {
  zone_type: "premium" | "equilibrium" | "discount";
  top:       number;
  bottom:    number;
}

// ─── Consolidation range ──────────────────────────────────────────────────────
export interface RangeZone {
  start_time: number;
  end_time:   number;
  high:       number;
  low:        number;
  mid:        number;
}

// ─── ML signal item ───────────────────────────────────────────────────────────
export interface SignalItem {
  time:       number;
  side:       "LONG" | "SHORT";
  entry:      number;
  sl:         number;
  tp1:        number;
  tp2:        number;
  conviction: "low" | "normal" | "high";
  ml_bias:    number;
  reasons:    string;
}

// ─── Full analysis response ───────────────────────────────────────────────────
export interface AnalysisResponse {
  symbol:    string;
  timeframe: string;
  // Candles
  candles: CandleData[];
  // Swing structure (50-bar pivots)
  swing_highs:     SwingPoint[];
  swing_lows:      SwingPoint[];
  swing_structure: StructureBreak[];
  // Internal structure (5-bar pivots)
  internal_highs:     SwingPoint[];
  internal_lows:      SwingPoint[];
  internal_structure: StructureBreak[];
  // Order Blocks
  order_blocks: OrderBlock[];
  // Fair Value Gaps
  fvgs: FVGZone[];
  // Equal Highs / Lows
  equal_levels: EqualLevel[];
  // Strong / Weak
  strong_weak: StrongWeakLevel[];
  // Premium / Discount
  premium_discount: PremiumDiscountZone[];
  // Consolidation ranges
  ranges: RangeZone[];
  // ML signals
  signals: SignalItem[];
}

export type Asset     = "BTC" | "ETH";
export type Timeframe = "15m" | "1h" | "4h" | "1d";
