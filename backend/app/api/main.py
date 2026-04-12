from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
import numpy as np

from app.core.market_structure_analyzer import run_analyzer, analyze_symbol

app = FastAPI(title="Trade Signals API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Pydantic models
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


# ── Analysis response models ──────────────────

class CandleData(BaseModel):
    time: int           # Unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float


class FVGZone(BaseModel):
    time: int
    low: float
    high: float
    type: str           # "bull" | "bear"


class OrderBlock(BaseModel):
    time: int
    low: float
    high: float
    type: str           # "bull" | "bear"


class StructureEvent(BaseModel):
    time: int
    type: str           # "bos_up" | "bos_down" | "choch_up" | "choch_down"
    level: float


class RangeZone(BaseModel):
    start_time: int
    end_time: int
    high: float
    low: float
    mid: float


class SwingPoint(BaseModel):
    time: int
    level: float
    type: str           # "high" | "low"


class SweepEvent(BaseModel):
    time: int
    type: str           # "sweep_high" | "sweep_low"
    level: float


class SignalItem(BaseModel):
    time: int
    side: str           # "LONG" | "SHORT"
    entry: float
    sl: float
    tp1: float
    tp2: float
    conviction: str
    ml_bias: float
    reasons: str


class AnalysisResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: List[CandleData]
    fvg_zones: List[FVGZone]
    order_blocks: List[OrderBlock]
    structure_events: List[StructureEvent]
    ranges: List[RangeZone]
    swing_highs: List[SwingPoint]
    swing_lows: List[SwingPoint]
    sweeps: List[SweepEvent]
    signals: List[SignalItem]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _ts_to_unix(ts) -> int:
    """Convert a pandas Timestamp (or datetime) to Unix seconds."""
    try:
        return int(ts.timestamp())
    except Exception:
        return 0


def _safe_float(v, default=0.0) -> float:
    try:
        f = float(v)
        return f if np.isfinite(f) else default
    except Exception:
        return default


# ─────────────────────────────────────────────
# Existing endpoints (kept for backward compat)
# ─────────────────────────────────────────────

@app.get("/signals/latest", response_model=List[Signal])
def get_latest_signals(
    symbol: str = Query("BTC", description="BTC or ETH"),
    timeframe: str = Query("1h"),
):
    try:
        df = run_analyzer()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"run_analyzer failed: {e}")

    if df is None or df.empty:
        return []

    last = df.tail(25)
    results: List[Signal] = []
    for _, row in last.iterrows():
        ts = row.get("timestamp", datetime.utcnow())
        results.append(Signal(
            timestamp=ts,
            side=str(row.get("side", "")),
            close=_safe_float(row.get("close")),
            ml_bias=_safe_float(row.get("ml_bias")),
            ml_conviction=str(row.get("ml_conviction", "")),
            sl=_safe_float(row.get("sl")),
            tp1=_safe_float(row.get("tp1")),
            tp2=_safe_float(row.get("tp2")),
            reasons=str(row.get("reasons", "")),
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
            entry_time=row.get("entry_time", datetime.utcnow()),
            exit_time=row.get("exit_time", datetime.utcnow()),
            side=str(row.get("side", "")),
            entry=_safe_float(row.get("entry")),
            sl=_safe_float(row.get("sl")),
            tp1=_safe_float(row.get("tp1")),
            tp2=_safe_float(row.get("tp2")),
            exit_price=_safe_float(row.get("exit_price")),
            exit_reason=str(row.get("exit_reason", "")),
            R=_safe_float(row.get("R")),
        )
        for _, row in trades.iterrows()
    ]


# ─────────────────────────────────────────────
# New analysis endpoint
# ─────────────────────────────────────────────

@app.get("/analysis/{symbol}", response_model=AnalysisResponse)
def get_analysis(
    symbol: str,
    timeframe: str = Query("1h"),
    limit: int = Query(200, ge=50, le=500),
):
    """
    Full SMC analysis for BTC or ETH.

    Returns OHLCV candles plus all overlay data:
    FVG zones, Order Blocks, BOS/CHoCH events, consolidation ranges,
    swing highs/lows, liquidity sweeps, and ML-filtered signals.
    """
    sym = symbol.upper()
    if sym not in ("BTC", "ETH"):
        raise HTTPException(status_code=400, detail="symbol must be BTC or ETH")

    try:
        df = analyze_symbol(symbol=sym, timeframe=timeframe, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analyze_symbol failed: {e}")

    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="No data returned from exchange")

    # ── Candles ────────────────────────────────
    candles: List[CandleData] = []
    for _, row in df.iterrows():
        candles.append(CandleData(
            time=_ts_to_unix(row["timestamp"]),
            open=_safe_float(row.get("open")),
            high=_safe_float(row.get("high")),
            low=_safe_float(row.get("low")),
            close=_safe_float(row.get("close")),
            volume=_safe_float(row.get("volume")),
        ))

    # ── FVG zones ─────────────────────────────
    fvg_zones: List[FVGZone] = []
    for _, row in df.iterrows():
        t = _ts_to_unix(row["timestamp"])
        if str(row.get("fvg_up", "")) == "fvg_up":
            lo = _safe_float(row.get("fvg_up_low"))
            hi = _safe_float(row.get("fvg_up_high"))
            if lo and hi:
                fvg_zones.append(FVGZone(time=t, low=lo, high=hi, type="bull"))
        if str(row.get("fvg_down", "")) == "fvg_down":
            lo = _safe_float(row.get("fvg_down_low"))
            hi = _safe_float(row.get("fvg_down_high"))
            if lo and hi:
                fvg_zones.append(FVGZone(time=t, low=lo, high=hi, type="bear"))

    # ── Order Blocks ──────────────────────────
    order_blocks: List[OrderBlock] = []
    for _, row in df.iterrows():
        t = _ts_to_unix(row["timestamp"])
        bull_lo = _safe_float(row.get("ob_bull_low"), np.nan)
        bull_hi = _safe_float(row.get("ob_bull_high"), np.nan)
        bear_lo = _safe_float(row.get("ob_bear_low"), np.nan)
        bear_hi = _safe_float(row.get("ob_bear_high"), np.nan)

        if np.isfinite(bull_lo) and np.isfinite(bull_hi) and bull_lo > 0:
            order_blocks.append(OrderBlock(time=t, low=bull_lo, high=bull_hi, type="bull"))
        if np.isfinite(bear_lo) and np.isfinite(bear_hi) and bear_lo > 0:
            order_blocks.append(OrderBlock(time=t, low=bear_lo, high=bear_hi, type="bear"))

    # ── Structure events (BOS / CHoCH) ────────
    structure_events: List[StructureEvent] = []
    event_cols = {
        "bos_up_level":     "bos_up",
        "bos_down_level":   "bos_down",
        "choch_up_level":   "choch_up",
        "choch_down_level": "choch_down",
    }
    for col, evt_type in event_cols.items():
        if col not in df.columns:
            continue
        sub = df[df[col].notna() & (df[col] != 0)]
        for _, row in sub.iterrows():
            lvl = _safe_float(row[col])
            if lvl:
                structure_events.append(StructureEvent(
                    time=_ts_to_unix(row["timestamp"]),
                    type=evt_type,
                    level=lvl,
                ))
    structure_events.sort(key=lambda e: e.time)

    # ── Consolidation ranges ───────────────────
    ranges: List[RangeZone] = []
    if "in_range" in df.columns:
        in_range_mask = df["in_range"].astype(bool)
        in_r = False
        start_t = 0
        prev_rh = prev_rl = prev_rm = 0.0

        for _, row in df[in_range_mask | ~in_range_mask].iterrows():
            cur_in = bool(row.get("in_range", False))
            rh = _safe_float(row.get("range_high"), 0.0)
            rl = _safe_float(row.get("range_low"),  0.0)
            rm = _safe_float(row.get("range_mid"),  0.0)
            t  = _ts_to_unix(row["timestamp"])

            if cur_in and not in_r:
                in_r    = True
                start_t = t
                prev_rh, prev_rl, prev_rm = rh, rl, rm
            elif not cur_in and in_r:
                ranges.append(RangeZone(
                    start_time=start_t,
                    end_time=t,
                    high=prev_rh, low=prev_rl, mid=prev_rm,
                ))
                in_r = False
            elif cur_in:
                prev_rh, prev_rl, prev_rm = rh, rl, rm

        if in_r and prev_rh:
            last_t = _ts_to_unix(df.iloc[-1]["timestamp"])
            ranges.append(RangeZone(
                start_time=start_t, end_time=last_t,
                high=prev_rh, low=prev_rl, mid=prev_rm,
            ))

    # ── Swing highs / lows ────────────────────
    swing_highs: List[SwingPoint] = []
    swing_lows:  List[SwingPoint] = []
    if "swing_high" in df.columns:
        for _, row in df[df["swing_high"].astype(bool)].iterrows():
            swing_highs.append(SwingPoint(
                time=_ts_to_unix(row["timestamp"]),
                level=_safe_float(row.get("high")),
                type="high",
            ))
    if "swing_low" in df.columns:
        for _, row in df[df["swing_low"].astype(bool)].iterrows():
            swing_lows.append(SwingPoint(
                time=_ts_to_unix(row["timestamp"]),
                level=_safe_float(row.get("low")),
                type="low",
            ))

    # ── Sweeps ────────────────────────────────
    sweeps: List[SweepEvent] = []
    if "sweep" in df.columns:
        for _, row in df[df["sweep"] != ""].iterrows():
            lvl = _safe_float(row.get("sweep_level"), 0.0)
            if lvl:
                sweeps.append(SweepEvent(
                    time=_ts_to_unix(row["timestamp"]),
                    type=str(row["sweep"]),
                    level=lvl,
                ))

    # ── ML signals (last 50 bars with bias >= threshold) ──
    signals: List[SignalItem] = []
    if "ml_bias" in df.columns:
        ML_TH = 0.20
        sig_df = df[df["ml_bias"].abs() >= ML_TH].tail(50)
        for _, row in sig_df.iterrows():
            mb   = _safe_float(row.get("ml_bias"))
            side = "LONG" if mb > 0 else "SHORT"
            signals.append(SignalItem(
                time=_ts_to_unix(row["timestamp"]),
                side=side,
                entry=_safe_float(row.get("close")),
                sl=_safe_float(row.get("sl")),
                tp1=_safe_float(row.get("tp1")),
                tp2=_safe_float(row.get("tp2")),
                conviction=str(row.get("ml_conviction", "normal")),
                ml_bias=mb,
                reasons=str(row.get("reasons", "")),
            ))

    return AnalysisResponse(
        symbol=sym,
        timeframe=timeframe,
        candles=candles,
        fvg_zones=fvg_zones,
        order_blocks=order_blocks,
        structure_events=structure_events,
        ranges=ranges,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        sweeps=sweeps,
        signals=signals,
    )
