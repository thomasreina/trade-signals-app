import numpy as np
import pandas as pd

# Columns used for ML; keep stable between training and inference
FEATURE_COLS = [
    "rsi",
    "oi_pct_agg",
    "oi_z_agg",
    "fundingRate",
    "fundingRate_z",
    "fundingRate_diff",
    "oi_agg_raw",
    # SMC one-hots
    "smc_BOS_up",
    "smc_BOS_down",
    "has_sweep_low",
    "has_sweep_high",
    "fvg_up_flag",
    "fvg_down_flag",
    # Price dynamics
    "ret_1",
    "ret_3",
    "ret_6",
    "atr14",
]

def _safe_pct_change(s, periods=1):
    return s.pct_change(periods=periods).replace([np.inf, -np.inf], np.nan)

def _atr14(df):
    tr1 = (df['high'] - df['low']).abs()
    tr2 = (df['high'] - df['close'].shift(1)).abs()
    tr3 = (df['low']  - df['close'].shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(14).mean()

def _series_or_default(df: pd.DataFrame, col: str, default='', dtype=str) -> pd.Series:
    """Return df[col] if present, else a Series of 'default' aligned to df.index."""
    if col in df.columns:
        s = df[col]
    else:
        s = pd.Series([default] * len(df), index=df.index)
    try:
        return s.astype(dtype)
    except Exception:
        return pd.Series([default] * len(df), index=df.index).astype(dtype)

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a new DF with ML feature columns.
    Expects price columns: close, high, low.
    Uses (if present): rsi, oi_pct_agg, oi_z_agg, oi_agg, fundingRate, smc_signal, sweep, fvg_up, fvg_down.
    Missing columns are handled gracefully with defaults.
    """
    out = pd.DataFrame(index=df.index.copy())

    # Base numeric inputs
    out["rsi"]         = df["rsi"] if "rsi" in df.columns else pd.Series(np.nan, index=df.index)
    out["oi_pct_agg"]  = df["oi_pct_agg"] if "oi_pct_agg" in df.columns else pd.Series(0.0, index=df.index)
    out["oi_z_agg"]    = df["oi_z_agg"] if "oi_z_agg" in df.columns else pd.Series(0.0, index=df.index)
    out["fundingRate"] = df["fundingRate"] if "fundingRate" in df.columns else pd.Series(0.0, index=df.index)

    # Extra funding / OI derivatives
    fr = out["fundingRate"].copy()
    fr_mu = fr.mean()
    fr_sigma = fr.std(ddof=0)
    out["fundingRate_z"] = (fr - fr_mu) / fr_sigma if fr_sigma not in (0, np.nan, None) else pd.Series(0.0, index=df.index)
    out["fundingRate_diff"] = fr.diff().fillna(0.0)

    if "oi_agg" in df.columns:
        out["oi_agg_raw"] = df["oi_agg"]
    else:
        out["oi_agg_raw"] = pd.Series(0.0, index=df.index)

    # One-hots / flags
    smc   = _series_or_default(df, "smc_signal", default="", dtype=str).fillna("")
    sweep = _series_or_default(df, "sweep", default="", dtype=str).fillna("")
    fvg_u = _series_or_default(df, "fvg_up", default="", dtype=str).fillna("")
    fvg_d = _series_or_default(df, "fvg_down", default="", dtype=str).fillna("")

    out["smc_BOS_up"]   = (smc == "BOS_up").astype(int)
    out["smc_BOS_down"] = (smc == "BOS_down").astype(int)

    out["has_sweep_low"]  = sweep.str.contains("sweep_low", na=False).astype(int)
    out["has_sweep_high"] = sweep.str.contains("sweep_high", na=False).astype(int)

    out["fvg_up_flag"]   = (fvg_u == "fvg_up").astype(int)
    out["fvg_down_flag"] = (fvg_d == "fvg_down").astype(int)

    # Price-derived context
    if all(c in df.columns for c in ["close", "high", "low"]):
        out["ret_1"] = _safe_pct_change(df["close"], 1)
        out["ret_3"] = _safe_pct_change(df["close"], 3)
        out["ret_6"] = _safe_pct_change(df["close"], 6)
        out["atr14"] = _atr14(df)
    else:
        out["ret_1"] = np.nan
        out["ret_3"] = np.nan
        out["ret_6"] = np.nan
        out["atr14"] = np.nan

    return out

def label_tp_sl(df: pd.DataFrame, tp=0.005, sl=0.005, horizon=6) -> pd.Series:
    """
    Label each bar by whether future path hits +tp before -sl within 'horizon' bars.
    Returns: -1 (short bias), 0 (none), +1 (long bias).
    """
    if not all(c in df.columns for c in ["close","high","low"]):
        return pd.Series(np.zeros(len(df), dtype=int), index=df.index)

    close = df["close"].values
    highs = df["high"].values
    lows  = df["low"].values

    labels = np.zeros(len(df), dtype=int)
    for i in range(len(df)-horizon):
        entry = close[i]
        up_level   = entry * (1 + tp)
        down_level = entry * (1 - sl)
        hit = 0
        for f in range(1, horizon+1):
            hi = highs[i+f]
            lo = lows[i+f]
            if hi >= up_level and lo <= down_level:
                mid = (up_level + down_level) / 2.0
                hit = 1 if close[i+f] >= mid else -1
                break
            if hi >= up_level:
                hit = 1
                break
            if lo <= down_level:
                hit = -1
                break
        labels[i] = hit
    return pd.Series(labels, index=df.index)
