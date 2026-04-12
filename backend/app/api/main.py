from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import List
import numpy as np

from app.core.market_structure_analyzer import run_analyzer, analyze_symbol_smc

app = FastAPI(title="Trade Signals API — SMC Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Pydantic models — legacy endpoints
# ─────────────────────────────────────────────

class Signal(BaseModel):
    timestamp: datetime
    side: str
    close: float
    ml_bias: float
    ml_conviction: str
    sl: float
    tp1: float
    tp2: float
    reasons: str


class TradeBacktest(BaseModel):
    entry_time: datetime
    exit_time: datetime
    side: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    exit_price: float
    exit_reason: str
    R: float


# ─────────────────────────────────────────────
# Pydantic models — SMC analysis response
# ─────────────────────────────────────────────

class CandleData(BaseModel):
    time:   int     # Unix seconds
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float


class SwingPoint(BaseModel):
    time:       int
    level:      float
    pivot_type: str     # 'high' | 'low'
    label:      str     # 'HH' | 'HL' | 'LH' | 'LL'


class StructureBreak(BaseModel):
    time:       int
    level:      float
    break_type: str     # 'bos_up' | 'bos_down' | 'choch_up' | 'choch_down'
    scope:      str     # 'swing' | 'internal'


class OrderBlock(BaseModel):
    time:   int
    top:    float
    bottom: float
    bias:   int         # 1=bullish, -1=bearish
    scope:  str         # 'swing' | 'internal'
    active: bool


class FVG(BaseModel):
    time:   int
    top:    float
    bottom: float
    bias:   int         # 1=bullish, -1=bearish
    active: bool


class EqualLevel(BaseModel):
    time1: int
    time2: int
    level: float
    label: str          # 'EQH' | 'EQL'


class StrongWeakLevel(BaseModel):
    time:  int
    level: float
    label: str          # 'Strong High' | 'Weak High' | 'Strong Low' | 'Weak Low'


class PremiumDiscountZone(BaseModel):
    zone_type: str      # 'premium' | 'equilibrium' | 'discount'
    top:       float
    bottom:    float


class SignalItem(BaseModel):
    time:       int
    side:       str     # 'LONG' | 'SHORT'
    entry:      float
    sl:         float
    tp1:        float
    tp2:        float
    conviction: str
    ml_bias:    float
    reasons:    str


class RangeZone(BaseModel):
    start_time: int
    end_time:   int
    high:       float
    low:        float
    mid:        float


class AnalysisResponse(BaseModel):
    symbol:    str
    timeframe: str
    # Price data
    candles: List[CandleData]
    # Swing structure (50-bar pivots)
    swing_highs:      List[SwingPoint]
    swing_lows:       List[SwingPoint]
    swing_structure:  List[StructureBreak]
    # Internal structure (5-bar pivots)
    internal_highs:      List[SwingPoint]
    internal_lows:       List[SwingPoint]
    internal_structure:  List[StructureBreak]
    # Order Blocks (swing + internal, with active/mitigated status)
    order_blocks: List[OrderBlock]
    # Fair Value Gaps (with active/mitigated status)
    fvgs: List[FVG]
    # Equal Highs / Equal Lows
    equal_levels: List[EqualLevel]
    # Strong / Weak levels
    strong_weak: List[StrongWeakLevel]
    # Premium / Equilibrium / Discount zones
    premium_discount: List[PremiumDiscountZone]
    # Consolidation ranges (ATR-based)
    ranges: List[RangeZone]
    # ML-filtered signals
    signals: List[SignalItem]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _ts(ts_val) -> int:
    try:
        return int(ts_val.timestamp())
    except Exception:
        return 0


def _sf(v, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if np.isfinite(f) else default
    except Exception:
        return default


# ─────────────────────────────────────────────
# Legacy /signals/latest
# ─────────────────────────────────────────────

@app.get("/signals/latest", response_model=List[Signal])
def get_latest_signals():
    try:
        df = run_analyzer()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"run_analyzer failed: {e}")
    if df is None or df.empty:
        return []
    results = []
    for _, row in df.tail(25).iterrows():
        results.append(Signal(
            timestamp   = row.get("timestamp", datetime.utcnow()),
            side        = str(row.get("side", "")),
            close       = _sf(row.get("close")),
            ml_bias     = _sf(row.get("ml_bias")),
            ml_conviction = str(row.get("ml_conviction", "")),
            sl          = _sf(row.get("sl")),
            tp1         = _sf(row.get("tp1")),
            tp2         = _sf(row.get("tp2")),
            reasons     = str(row.get("reasons", "")),
        ))
    return results


@app.get("/backtest/smc", response_model=List[TradeBacktest])
def get_smc_backtest():
    try:
        from app.core.backtest_smc_sl_tp import run_smc_backtest
        trades = run_smc_backtest()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"run_smc_backtest failed: {e}")
    if trades is None or trades.empty:
        return []
    return [
        TradeBacktest(
            entry_time  = row.get("entry_time", datetime.utcnow()),
            exit_time   = row.get("exit_time", datetime.utcnow()),
            side        = str(row.get("side", "")),
            entry       = _sf(row.get("entry")),
            sl          = _sf(row.get("sl")),
            tp1         = _sf(row.get("tp1")),
            tp2         = _sf(row.get("tp2")),
            exit_price  = _sf(row.get("exit_price")),
            exit_reason = str(row.get("exit_reason", "")),
            R           = _sf(row.get("R")),
        )
        for _, row in trades.iterrows()
    ]


# ─────────────────────────────────────────────
# Main SMC analysis endpoint
# ─────────────────────────────────────────────

@app.get("/analysis/{symbol}", response_model=AnalysisResponse)
def get_analysis(
    symbol:   str,
    timeframe: str = Query("1h"),
    limit:     int = Query(200, ge=50, le=500),
):
    """
    Full LuxAlgo SMC analysis for BTC or ETH.

    Returns OHLCV candles plus all SMC overlay data:
    - Swing structure  (50-bar pivots): BOS / CHoCH, HH/HL/LH/LL labels
    - Internal structure (5-bar pivots): BOS / CHoCH
    - Order Blocks (swing + internal) with mitigation status
    - Fair Value Gaps with mitigation status
    - Equal Highs / Equal Lows
    - Strong / Weak High / Low
    - Premium / Equilibrium / Discount zones
    - Consolidation ranges
    - ML-filtered signals
    """
    sym = symbol.upper()
    if sym not in ("BTC", "ETH"):
        raise HTTPException(status_code=400, detail="symbol must be BTC or ETH")

    try:
        df, smc = analyze_symbol_smc(symbol=sym, timeframe=timeframe, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analyze_symbol_smc failed: {e}")

    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="No data from exchange")

    # ── Candles ────────────────────────────────────────────────────
    candles = [
        CandleData(
            time   = _ts(row["timestamp"]),
            open   = _sf(row.get("open")),
            high   = _sf(row.get("high")),
            low    = _sf(row.get("low")),
            close  = _sf(row.get("close")),
            volume = _sf(row.get("volume")),
        )
        for _, row in df.iterrows()
    ]

    # ── Swing structure ────────────────────────────────────────────
    swing_highs = [
        SwingPoint(time=p.time, level=p.level,
                   pivot_type=p.pivot_type, label=p.label)
        for p in smc.swing_highs
    ]
    swing_lows = [
        SwingPoint(time=p.time, level=p.level,
                   pivot_type=p.pivot_type, label=p.label)
        for p in smc.swing_lows
    ]
    swing_structure = [
        StructureBreak(time=b.time, level=b.level,
                       break_type=b.break_type, scope=b.scope)
        for b in smc.swing_structure
    ]

    # ── Internal structure ─────────────────────────────────────────
    internal_highs = [
        SwingPoint(time=p.time, level=p.level,
                   pivot_type=p.pivot_type, label=p.label)
        for p in smc.internal_highs
    ]
    internal_lows = [
        SwingPoint(time=p.time, level=p.level,
                   pivot_type=p.pivot_type, label=p.label)
        for p in smc.internal_lows
    ]
    internal_structure = [
        StructureBreak(time=b.time, level=b.level,
                       break_type=b.break_type, scope=b.scope)
        for b in smc.internal_structure
    ]

    # ── Order Blocks ───────────────────────────────────────────────
    order_blocks = [
        OrderBlock(time=ob.time, top=ob.top, bottom=ob.bottom,
                   bias=ob.bias, scope=ob.scope, active=ob.active)
        for ob in smc.order_blocks
    ]

    # ── Fair Value Gaps ────────────────────────────────────────────
    fvgs = [
        FVG(time=fvg.time, top=fvg.top, bottom=fvg.bottom,
            bias=fvg.bias, active=fvg.active)
        for fvg in smc.fvgs
    ]

    # ── Equal Highs / Lows ─────────────────────────────────────────
    equal_levels = [
        EqualLevel(time1=el.time1, time2=el.time2,
                   level=el.level, label=el.label)
        for el in smc.equal_levels
    ]

    # ── Strong / Weak ──────────────────────────────────────────────
    strong_weak = [
        StrongWeakLevel(time=sw.time, level=sw.level, label=sw.label)
        for sw in smc.strong_weak
    ]

    # ── Premium / Discount ─────────────────────────────────────────
    premium_discount = [
        PremiumDiscountZone(zone_type=z.zone_type, top=z.top, bottom=z.bottom)
        for z in smc.premium_discount
    ]

    # ── Consolidation ranges (from legacy pipeline) ────────────────
    ranges: List[RangeZone] = []
    if "in_range" in df.columns:
        in_r     = False
        start_t  = 0
        rh = rl = rm = 0.0
        for _, row in df.iterrows():
            cur_in = bool(row.get("in_range", False))
            t      = _ts(row["timestamp"])
            if cur_in and not in_r:
                in_r    = True
                start_t = t
                rh = _sf(row.get("range_high"))
                rl = _sf(row.get("range_low"))
                rm = _sf(row.get("range_mid"))
            elif not cur_in and in_r:
                ranges.append(RangeZone(start_time=start_t, end_time=t,
                                        high=rh, low=rl, mid=rm))
                in_r = False
            elif cur_in:
                rh = _sf(row.get("range_high"))
                rl = _sf(row.get("range_low"))
                rm = _sf(row.get("range_mid"))
        if in_r and rh:
            last_t = _ts(df.iloc[-1]["timestamp"])
            ranges.append(RangeZone(start_time=start_t, end_time=last_t,
                                    high=rh, low=rl, mid=rm))

    # ── ML signals ────────────────────────────────────────────────
    signals: List[SignalItem] = []
    if "ml_bias" in df.columns:
        ML_TH  = 0.20
        sig_df = df[df["ml_bias"].abs() >= ML_TH].tail(50)
        for _, row in sig_df.iterrows():
            mb   = _sf(row.get("ml_bias"))
            side = "LONG" if mb > 0 else "SHORT"
            signals.append(SignalItem(
                time       = _ts(row["timestamp"]),
                side       = side,
                entry      = _sf(row.get("close")),
                sl         = _sf(row.get("sl")),
                tp1        = _sf(row.get("tp1")),
                tp2        = _sf(row.get("tp2")),
                conviction = str(row.get("ml_conviction", "normal")),
                ml_bias    = mb,
                reasons    = str(row.get("reasons", "")),
            ))

    return AnalysisResponse(
        symbol             = sym,
        timeframe          = timeframe,
        candles            = candles,
        swing_highs        = swing_highs,
        swing_lows         = swing_lows,
        swing_structure    = swing_structure,
        internal_highs     = internal_highs,
        internal_lows      = internal_lows,
        internal_structure = internal_structure,
        order_blocks       = order_blocks,
        fvgs               = fvgs,
        equal_levels       = equal_levels,
        strong_weak        = strong_weak,
        premium_discount   = premium_discount,
        ranges             = ranges,
        signals            = signals,
    )
