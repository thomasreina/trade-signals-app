import numpy as np
import pandas as pd


FEATURE_COLS = [
    "rsi",
    "oi_pct_agg",
    "oi_z_agg",
    "fundingRate",
    "fundingRate_z",
    "fundingRate_diff",
    "oi_agg_raw",
    "smc_BOS_up",
    "smc_BOS_down",
    "has_sweep_low",
    "has_sweep_high",
    "fvg_up_flag",
    "fvg_down_flag",
    "ret_1",
    "ret_3",
    "ret_6",
    "atr14",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Common feature builder used by:
    - ML training
    - live analyzer
    - SMC backtest

    Ensures consistent ML inputs everywhere.
    """

    out = pd.DataFrame(index=df.index)

    # --- Basic numeric features ---

    out["rsi"] = df.get("rsi", np.nan)
    out["oi_pct_agg"] = df.get("oi_pct_agg", np.nan)
    out["oi_z_agg"] = df.get("oi_z_agg", np.nan)

    # Funding
    out["fundingRate"] = df.get("fundingRate", 0.0)
    out["fundingRate_z"] = (
        out["fundingRate"] - out["fundingRate"].mean()
    ) / (out["fundingRate"].std(ddof=0) + 1e-9)
    out["fundingRate_diff"] = out["fundingRate"].diff().fillna(0.0)

    # OI
    out["oi_agg_raw"] = df.get("oi_agg", df.get("oi_bybit", np.nan))

    # --- SMC-related flags ---

    # sweep: ensure Series aligned to df.index
    if "sweep" in df:
        sweep = df["sweep"].fillna("")
    else:
        sweep = pd.Series("", index=df.index, dtype=object)

    # smc_signal: BOS up/down flags
    if "smc_signal" in df:
        smc_sig = df["smc_signal"].fillna("")
    else:
        smc_sig = pd.Series("", index=df.index, dtype=object)

    out["smc_BOS_up"] = (smc_sig == "BOS_up").astype(int)
    out["smc_BOS_down"] = (smc_sig == "BOS_down").astype(int)

    out["has_sweep_low"] = (sweep == "sweep_low").astype(int)
    out["has_sweep_high"] = (sweep == "sweep_high").astype(int)

    # FVG flags: handle missing columns safely
    if "fvg_up_flag" in df:
        fvg_up = df["fvg_up_flag"].fillna(0)
    else:
        fvg_up = pd.Series(0, index=df.index)
    out["fvg_up_flag"] = fvg_up.astype(int)

    if "fvg_down_flag" in df:
        fvg_down = df["fvg_down_flag"].fillna(0)
    else:
        fvg_down = pd.Series(0, index=df.index)
    out["fvg_down_flag"] = fvg_down.astype(int)

    # --- Returns ---

    close = df["close"]
    out["ret_1"] = close.pct_change(1).fillna(0.0)
    out["ret_3"] = close.pct_change(3).fillna(0.0)
    out["ret_6"] = close.pct_change(6).fillna(0.0)

    # ATR (already computed in analyzer)
    out["atr14"] = df.get("atr14", np.nan)

    # Keep only needed columns in the right order
    return out[FEATURE_COLS]
