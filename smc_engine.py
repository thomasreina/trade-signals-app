"""
Smart Money Concepts Engine
============================
Python port of the LuxAlgo Smart Money Concepts indicator (Pine Script v5).

Reference: https://www.tradingview.com/script/Hy4ARLOT/

Key concepts faithfully reproduced
-----------------------------------
- Swing structure  : pivot lookback = 50 bars  (``swing_size``)
- Internal structure : pivot lookback = 5 bars  (``internal_size``)
- Leg-based pivot detection   (matches ``ta.highest / ta.lowest`` logic)
- BOS vs CHoCH classification (requires correct trend state)
- Order Blocks via parsed-high/low window search
- Fair Value Gaps with cumulative auto-threshold
- Equal Highs / Equal Lows
- Strong / Weak High / Low
- Premium / Equilibrium / Discount zones
- OB and FVG mitigation
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ─── Constants ────────────────────────────────────────────────────────────────
BULLISH     =  1
BEARISH     = -1
NEUTRAL     =  0

BULLISH_LEG = 1
BEARISH_LEG = 0


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class SwingPoint:
    time:       int     # unix seconds
    level:      float
    bar_index:  int
    pivot_type: str     # 'high' | 'low'
    label:      str     # 'HH' | 'HL' | 'LH' | 'LL'


@dataclass
class StructureBreak:
    time:       int
    level:      float
    break_type: str     # 'bos_up' | 'bos_down' | 'choch_up' | 'choch_down'
    scope:      str     # 'swing' | 'internal'


@dataclass
class OrderBlock:
    time:   int
    top:    float
    bottom: float
    bias:   int         # BULLISH | BEARISH
    scope:  str         # 'swing' | 'internal'
    active: bool = True


@dataclass
class FVG:
    time:   int
    top:    float
    bottom: float
    bias:   int         # BULLISH | BEARISH
    active: bool = True


@dataclass
class EqualLevel:
    time1: int
    time2: int
    level: float
    label: str          # 'EQH' | 'EQL'


@dataclass
class StrongWeakLevel:
    time:  int
    level: float
    label: str          # 'Strong High' | 'Weak High' | 'Strong Low' | 'Weak Low'


@dataclass
class PremiumDiscountZone:
    zone_type: str      # 'premium' | 'equilibrium' | 'discount'
    top:       float
    bottom:    float


@dataclass
class SmcResult:
    """Complete SMC analysis result — all overlay layers."""
    swing_highs:       List[SwingPoint]          = field(default_factory=list)
    swing_lows:        List[SwingPoint]          = field(default_factory=list)
    internal_highs:    List[SwingPoint]          = field(default_factory=list)
    internal_lows:     List[SwingPoint]          = field(default_factory=list)
    swing_structure:   List[StructureBreak]      = field(default_factory=list)
    internal_structure:List[StructureBreak]      = field(default_factory=list)
    order_blocks:      List[OrderBlock]          = field(default_factory=list)
    fvgs:              List[FVG]                 = field(default_factory=list)
    equal_levels:      List[EqualLevel]          = field(default_factory=list)
    strong_weak:       List[StrongWeakLevel]     = field(default_factory=list)
    premium_discount:  List[PremiumDiscountZone] = field(default_factory=list)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _ts(ts_val) -> int:
    """Convert a pandas Timestamp (or int) to Unix seconds."""
    try:
        return int(ts_val.timestamp())
    except AttributeError:
        return int(ts_val)


def _safe_float(v, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if np.isfinite(f) else default
    except (TypeError, ValueError):
        return default


# ─── Step 1: Leg detection ────────────────────────────────────────────────────

def _compute_legs(highs: np.ndarray, lows: np.ndarray, size: int) -> np.ndarray:
    """
    Compute alternating BULLISH_LEG / BEARISH_LEG values per bar.

    Pine Script logic reproduced:
        newLegHigh = high[size] > ta.highest(size)   → BEARISH_LEG (pivot high confirmed)
        newLegLow  = low[size]  < ta.lowest(size)    → BULLISH_LEG (pivot low  confirmed)

    ``ta.highest(size)`` at bar ``i`` = max(high[i], …, high[i-size+1])
    — it does NOT include bar i-size (the pivot candidate).
    """
    n   = len(highs)
    leg = np.zeros(n, dtype=np.int8)

    for i in range(size, n):
        h_pivot = highs[i - size]
        l_pivot = lows[i - size]
        # Window: the `size` bars AFTER the pivot candidate up to current
        win_h = highs[i - size + 1 : i + 1]
        win_l = lows[i - size + 1 : i + 1]

        if h_pivot > win_h.max():
            leg[i] = BEARISH_LEG        # confirmed swing HIGH
        elif l_pivot < win_l.min():
            leg[i] = BULLISH_LEG        # confirmed swing LOW
        else:
            leg[i] = leg[i - 1]

    return leg


# ─── Step 2: Pivot extraction ─────────────────────────────────────────────────

def _extract_pivots(
    df: pd.DataFrame,
    legs: np.ndarray,
    size: int,
) -> Tuple[List[dict], List[dict]]:
    """
    Extract confirmed pivot highs and lows from leg transitions.

    A leg change at bar ``i`` means:
      BEARISH_LEG → pivot HIGH was confirmed at bar ``i - size``
      BULLISH_LEG → pivot LOW  was confirmed at bar ``i - size``
    """
    n   = len(df)
    ts  = df["timestamp"].values
    h   = df["high"].values
    lo  = df["low"].values

    pivot_highs: List[dict] = []
    pivot_lows:  List[dict] = []

    for i in range(1, n):
        if legs[i] == legs[i - 1]:
            continue                         # no leg change

        pbar = i - size
        if pbar < 0:
            continue

        rec = {"time": _ts(ts[pbar]), "level": None, "bar_index": pbar}

        if legs[i] == BEARISH_LEG:
            rec["level"] = float(h[pbar])
            pivot_highs.append(rec)
        else:
            rec["level"] = float(lo[pbar])
            pivot_lows.append(rec)

    return pivot_highs, pivot_lows


# ─── Step 3: Label swing points (HH / HL / LH / LL) ─────────────────────────

def _label_pivots(
    pivot_highs: List[dict],
    pivot_lows:  List[dict],
) -> Tuple[List[SwingPoint], List[SwingPoint]]:
    """Attach HH/LH and HL/LL labels to pivot lists."""

    labeled_h: List[SwingPoint] = []
    prev_h: Optional[dict] = None
    for p in sorted(pivot_highs, key=lambda x: x["bar_index"]):
        label = "HH" if (prev_h is None or p["level"] > prev_h["level"]) else "LH"
        labeled_h.append(SwingPoint(
            time=p["time"], level=p["level"],
            bar_index=p["bar_index"], pivot_type="high", label=label,
        ))
        prev_h = p

    labeled_l: List[SwingPoint] = []
    prev_l: Optional[dict] = None
    for p in sorted(pivot_lows, key=lambda x: x["bar_index"]):
        label = "HL" if (prev_l is None or p["level"] > prev_l["level"]) else "LL"
        labeled_l.append(SwingPoint(
            time=p["time"], level=p["level"],
            bar_index=p["bar_index"], pivot_type="low", label=label,
        ))
        prev_l = p

    return labeled_h, labeled_l


# ─── Step 4: BOS / CHoCH detection ───────────────────────────────────────────

def _detect_structure(
    df: pd.DataFrame,
    pivot_highs: List[dict],
    pivot_lows:  List[dict],
    scope: str,
) -> Tuple[List[StructureBreak], int]:
    """
    Detect BOS and CHoCH by scanning for close crossovers / crossunders.

    Pine Script equivalent of ``displayStructure()``:
      ta.crossover(close, pivot_high.level)  → BOS_up  (trend was BULLISH) or CHoCH_up  (was BEARISH)
      ta.crossunder(close, pivot_low.level)  → BOS_down (trend was BEARISH) or CHoCH_down (was BULLISH)

    Returns (breaks, final_swing_trend).
    """
    n      = len(df)
    closes = df["close"].values
    ts_arr = df["timestamp"].values

    sorted_ph = sorted(pivot_highs, key=lambda x: x["bar_index"])
    sorted_pl = sorted(pivot_lows,  key=lambda x: x["bar_index"])

    trend        = NEUTRAL
    cur_high: Optional[dict] = None
    cur_low:  Optional[dict] = None
    h_crossed    = False
    l_crossed    = False
    ph_idx       = 0
    pl_idx       = 0
    breaks: List[StructureBreak] = []

    for i in range(n):
        # Absorb all pivots confirmed up to this bar
        while ph_idx < len(sorted_ph) and sorted_ph[ph_idx]["bar_index"] <= i:
            cur_high  = sorted_ph[ph_idx]
            h_crossed = False
            ph_idx   += 1
        while pl_idx < len(sorted_pl) and sorted_pl[pl_idx]["bar_index"] <= i:
            cur_low   = sorted_pl[pl_idx]
            l_crossed = False
            pl_idx   += 1

        close = closes[i]
        t     = _ts(ts_arr[i])

        # Crossover: close breaks above last pivot high
        if cur_high and not h_crossed and close > cur_high["level"]:
            h_crossed  = True
            btype      = "choch_up" if trend == BEARISH else "bos_up"
            trend      = BULLISH
            breaks.append(StructureBreak(time=t, level=cur_high["level"],
                                         break_type=btype, scope=scope))

        # Crossunder: close breaks below last pivot low
        if cur_low and not l_crossed and close < cur_low["level"]:
            l_crossed  = True
            btype      = "choch_down" if trend == BULLISH else "bos_down"
            trend      = BEARISH
            breaks.append(StructureBreak(time=t, level=cur_low["level"],
                                         break_type=btype, scope=scope))

    return breaks, trend


# ─── Step 5: Order Block detection ───────────────────────────────────────────

def _compute_order_blocks(
    df: pd.DataFrame,
    structure_breaks: List[StructureBreak],
    pivot_highs: List[dict],
    pivot_lows:  List[dict],
    scope: str,
) -> List[OrderBlock]:
    """
    LuxAlgo-style Order Block detection.

    For each structure break, scan from the causal pivot bar to the break bar:
      Bullish BOS/CHoCH → bullish OB  = bar with MINIMUM parsedLow
      Bearish BOS/CHoCH → bearish OB  = bar with MAXIMUM parsedHigh

    parsedHigh = high-volatility bar ? low  : high   (LuxAlgo volatility filter)
    parsedLow  = high-volatility bar ? high : low

    High-volatility: candle range ≥ 2 × mean range (200-bar window).
    """
    n      = len(df)
    highs  = df["high"].values
    lows   = df["low"].values
    ts_arr = df["timestamp"].values

    # ── Volatility filter (ATR-200 equivalent) ────────────────────
    vol_win   = min(200, max(n // 4, 4))
    rng       = highs - lows
    cum_rng   = np.cumsum(rng)
    vol       = np.zeros(n)
    for i in range(n):
        s        = max(0, i - vol_win)
        vol[i]   = (cum_rng[i] - (cum_rng[s - 1] if s > 0 else 0.0)) / (i - s + 1)

    hi_vol_bar  = rng >= 2.0 * vol
    parsed_hi   = np.where(hi_vol_bar, lows,  highs)   # swapped for hi-vol candles
    parsed_lo   = np.where(hi_vol_bar, highs, lows)

    # ── Timestamp → bar-index map ─────────────────────────────────
    ts2idx: dict[int, int] = {_ts(ts_arr[i]): i for i in range(n)}

    sorted_ph = sorted(pivot_highs, key=lambda x: x["bar_index"])
    sorted_pl = sorted(pivot_lows,  key=lambda x: x["bar_index"])

    obs: List[OrderBlock] = []

    for sb in structure_breaks:
        break_bar = ts2idx.get(sb.time)
        if break_bar is None:
            continue

        is_bull = sb.break_type in ("bos_up", "choch_up")

        # Find the causal pivot (the one whose level was broken)
        pivot_bar: Optional[int] = None
        candidates = sorted_ph if is_bull else sorted_pl
        for p in reversed(candidates):
            if p["bar_index"] < break_bar:
                if abs(p["level"] - sb.level) < 1e-8 * max(sb.level, 1.0):
                    pivot_bar = p["bar_index"]
                    break
        if pivot_bar is None:
            # Fallback: most recent pivot before the break
            for p in reversed(candidates):
                if p["bar_index"] < break_bar:
                    pivot_bar = p["bar_index"]
                    break

        if pivot_bar is None or pivot_bar >= break_bar:
            continue

        # ── Find OB candle in [pivot_bar, break_bar) ─────────────
        if is_bull:
            window   = parsed_lo[pivot_bar:break_bar]
            ob_off   = int(np.argmin(window))
        else:
            window   = parsed_hi[pivot_bar:break_bar]
            ob_off   = int(np.argmax(window))

        ob_bar = pivot_bar + ob_off
        obs.append(OrderBlock(
            time   = _ts(ts_arr[ob_bar]),
            top    = float(parsed_hi[ob_bar]),
            bottom = float(parsed_lo[ob_bar]),
            bias   = BULLISH if is_bull else BEARISH,
            scope  = scope,
        ))

    return obs


def _apply_ob_mitigation(df: pd.DataFrame, obs: List[OrderBlock]) -> List[OrderBlock]:
    """
    Deactivate OBs once price trades through them.
      Bearish OB: mitigated when high > ob.top
      Bullish OB: mitigated when low  < ob.bottom
    """
    ts_arr = df["timestamp"].values
    highs  = df["high"].values
    lows   = df["low"].values
    ts2idx = {_ts(ts_arr[i]): i for i in range(len(df))}

    for ob in obs:
        start = ts2idx.get(ob.time, -1)
        if start < 0:
            continue
        for i in range(start + 1, len(df)):
            if ob.bias == BEARISH and highs[i] > ob.top:
                ob.active = False
                break
            if ob.bias == BULLISH and lows[i] < ob.bottom:
                ob.active = False
                break

    return obs


# ─── Step 6: Fair Value Gaps ──────────────────────────────────────────────────

def _compute_fvgs(df: pd.DataFrame, use_threshold: bool = True) -> List[FVG]:
    """
    LuxAlgo FVG with cumulative auto-threshold.

    At bar i (current TF, so ``newTimeframe`` is always True):
      Bullish FVG:  low[i] > high[i-2]  AND  close[i-1] > high[i-2]  AND  bar_delta_pct[i-1] > threshold
      Bearish FVG: high[i] < low[i-2]   AND  close[i-1] < low[i-2]   AND -bar_delta_pct[i-1] > threshold

    threshold = cumulative_mean(|bar_delta_pct|) × 2   (auto-threshold)
    """
    n      = len(df)
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    opens  = df["open"].values
    ts_arr = df["timestamp"].values

    # Bar delta %  (middle candle)
    bar_delta = np.where(opens > 0, (closes - opens) / opens * 100.0, 0.0)

    # Running threshold
    cum_abs   = np.cumsum(np.abs(bar_delta))
    threshold = np.zeros(n)
    for i in range(1, n):
        threshold[i] = (cum_abs[i] / i) * 2.0

    fvgs: List[FVG] = []

    for i in range(2, n):
        t   = _ts(ts_arr[i])
        mid = bar_delta[i - 1]
        th  = threshold[i] if use_threshold else 0.0

        if lows[i] > highs[i - 2] and closes[i - 1] > highs[i - 2] and mid > th:
            fvgs.append(FVG(time=t, top=float(lows[i]),
                            bottom=float(highs[i - 2]), bias=BULLISH))

        elif highs[i] < lows[i - 2] and closes[i - 1] < lows[i - 2] and -mid > th:
            fvgs.append(FVG(time=t, top=float(lows[i - 2]),
                            bottom=float(highs[i]), bias=BEARISH))

    return fvgs


def _apply_fvg_mitigation(df: pd.DataFrame, fvgs: List[FVG]) -> List[FVG]:
    """
    Deactivate FVGs when price retraces into them.
      Bullish FVG: mitigated when low  < fvg.bottom
      Bearish FVG: mitigated when high > fvg.top
    """
    ts_arr = df["timestamp"].values
    highs  = df["high"].values
    lows   = df["low"].values
    ts2idx = {_ts(ts_arr[i]): i for i in range(len(df))}

    for fvg in fvgs:
        start = ts2idx.get(fvg.time, -1)
        if start < 0:
            continue
        for i in range(start + 1, len(df)):
            if fvg.bias == BULLISH and lows[i] < fvg.bottom:
                fvg.active = False
                break
            if fvg.bias == BEARISH and highs[i] > fvg.top:
                fvg.active = False
                break

    return fvgs


# ─── Step 7: Equal Highs / Equal Lows ────────────────────────────────────────

def _compute_equal_levels(
    df: pd.DataFrame,
    swing_highs: List[SwingPoint],
    swing_lows:  List[SwingPoint],
    threshold:   float = 0.1,
) -> List[EqualLevel]:
    """
    EQH: two consecutive swing highs within ``threshold × ATR``
    EQL: two consecutive swing lows  within ``threshold × ATR``
    """
    atr = _safe_float(df["atr14"].iloc[-1]) if "atr14" in df.columns else \
          float((df["high"] - df["low"]).mean())

    equal: List[EqualLevel] = []

    for i in range(1, len(swing_highs)):
        p1, p2 = swing_highs[i - 1], swing_highs[i]
        if abs(p1.level - p2.level) < threshold * atr:
            equal.append(EqualLevel(time1=p1.time, time2=p2.time,
                                    level=(p1.level + p2.level) / 2, label="EQH"))

    for i in range(1, len(swing_lows)):
        p1, p2 = swing_lows[i - 1], swing_lows[i]
        if abs(p1.level - p2.level) < threshold * atr:
            equal.append(EqualLevel(time1=p1.time, time2=p2.time,
                                    level=(p1.level + p2.level) / 2, label="EQL"))

    return equal


# ─── Step 8: Strong / Weak High & Low ────────────────────────────────────────

def _compute_strong_weak(
    df: pd.DataFrame,
    swing_trend: int,
) -> List[StrongWeakLevel]:
    """
    Trailing high/low from the full window are labelled Strong/Weak.

    Strong High = trailing high when trend is BEARISH (it caused the sell-off)
    Weak   High = trailing high when trend is BULLISH (will likely be swept)
    Strong Low  = trailing low  when trend is BULLISH (it underpins the rally)
    Weak   Low  = trailing low  when trend is BEARISH (will likely be broken)
    """
    highs  = df["high"].values
    lows   = df["low"].values
    ts_arr = df["timestamp"].values

    idx_hi = int(np.argmax(highs))
    idx_lo = int(np.argmin(lows))

    return [
        StrongWeakLevel(
            time  = _ts(ts_arr[idx_hi]),
            level = float(highs[idx_hi]),
            label = "Strong High" if swing_trend == BEARISH else "Weak High",
        ),
        StrongWeakLevel(
            time  = _ts(ts_arr[idx_lo]),
            level = float(lows[idx_lo]),
            label = "Strong Low" if swing_trend == BULLISH else "Weak Low",
        ),
    ]


# ─── Step 9: Premium / Equilibrium / Discount ─────────────────────────────────

def _compute_premium_discount(df: pd.DataFrame) -> List[PremiumDiscountZone]:
    """
    Zones derived from the full-window swing range.

    Premium     : top 5 % of range  (above 95th percentile)
    Equilibrium : middle ± 2.5 %    (±5 % band around midpoint)
    Discount    : bottom 5 %        (below 5th percentile)
    """
    hi = float(df["high"].max())
    lo = float(df["low"].min())

    return [
        PremiumDiscountZone("premium",
                            top    = hi,
                            bottom = 0.95 * hi + 0.05 * lo),
        PremiumDiscountZone("equilibrium",
                            top    = 0.525 * hi + 0.475 * lo,
                            bottom = 0.475 * hi + 0.525 * lo),
        PremiumDiscountZone("discount",
                            top    = 0.05 * hi + 0.95 * lo,
                            bottom = lo),
    ]


# ─── Public entry point ───────────────────────────────────────────────────────

def analyze_smc(
    df: pd.DataFrame,
    swing_size:    int = 50,
    internal_size: int = 5,
) -> SmcResult:
    """
    Full LuxAlgo SMC analysis on a prepared OHLCV + ATR DataFrame.

    Parameters
    ----------
    df            : DataFrame with columns timestamp, open, high, low, close,
                    volume, atr14.  Must be sorted oldest-first.
    swing_size    : pivot lookback for swing   structure (default 50, matches LuxAlgo)
    internal_size : pivot lookback for internal structure (default  5, matches LuxAlgo)

    Returns
    -------
    SmcResult  — all overlay layers ready for API serialisation.
    """
    result = SmcResult()

    min_bars = max(swing_size, internal_size) * 2 + 10
    if len(df) < min_bars:
        return result

    highs = df["high"].values
    lows  = df["low"].values

    # ── 1. Legs ────────────────────────────────────────────────────
    swing_legs    = _compute_legs(highs, lows, swing_size)
    internal_legs = _compute_legs(highs, lows, internal_size)

    # ── 2. Pivots ──────────────────────────────────────────────────
    swing_ph, swing_pl       = _extract_pivots(df, swing_legs,    swing_size)
    internal_ph, internal_pl = _extract_pivots(df, internal_legs, internal_size)

    # ── 3. Labels (HH / HL / LH / LL) ────────────────────────────
    result.swing_highs,    result.swing_lows    = _label_pivots(swing_ph,    swing_pl)
    result.internal_highs, result.internal_lows = _label_pivots(internal_ph, internal_pl)

    # ── 4. Structure breaks (BOS / CHoCH) ─────────────────────────
    swing_breaks,    swing_trend    = _detect_structure(df, swing_ph,    swing_pl,    "swing")
    internal_breaks, _              = _detect_structure(df, internal_ph, internal_pl, "internal")

    result.swing_structure    = swing_breaks
    result.internal_structure = internal_breaks

    # ── 5. Order Blocks ────────────────────────────────────────────
    s_obs  = _compute_order_blocks(df, swing_breaks,    swing_ph,    swing_pl,    "swing")
    i_obs  = _compute_order_blocks(df, internal_breaks, internal_ph, internal_pl, "internal")
    result.order_blocks = _apply_ob_mitigation(df, s_obs + i_obs)

    # ── 6. Fair Value Gaps ─────────────────────────────────────────
    result.fvgs = _apply_fvg_mitigation(df, _compute_fvgs(df))

    # ── 7. Equal Highs / Lows ──────────────────────────────────────
    result.equal_levels = _compute_equal_levels(df, result.swing_highs, result.swing_lows)

    # ── 8. Strong / Weak levels ────────────────────────────────────
    result.strong_weak = _compute_strong_weak(df, swing_trend)

    # ── 9. Premium / Discount zones ────────────────────────────────
    result.premium_discount = _compute_premium_discount(df)

    return result
