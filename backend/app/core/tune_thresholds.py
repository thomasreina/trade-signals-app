import os
import joblib
import numpy as np
import pandas as pd
import ccxt

from market_structure_analyzer import (
    load_price_df,
    attach_aggregated_oi_and_funding,
    compute_signals,
)
from signals_core import build_features, label_tp_sl

SYMBOL_SPOT = os.getenv("SYMBOL_SPOT", "BTC/USDT")
SYMBOL_FUT  = os.getenv("SYMBOL_FUT",  "BTCUSDT")
OKX_UNDERLYING = os.getenv("OKX_UNDERLYING", "BTC-USDT")
TIMEFRAME   = os.getenv("TIMEFRAME", "1h")
CANDLES     = int(os.getenv("CANDLES", "1500"))
TZ          = os.getenv("TZ_NAME", "Europe/Madrid")

TP  = float(os.getenv("LBL_TP", "0.006"))
SL  = float(os.getenv("LBL_SL", "0.005"))
HZN = int(os.getenv("LBL_HZN", "8"))

MODEL_PATH = os.getenv("MODEL_PATH", f"models/rf_{SYMBOL_FUT}_{TIMEFRAME}.pkl")


def load_model(path):
    blob = joblib.load(path)
    model = blob["model"]
    feats = blob.get("features", [])
    return model, feats


def compute_ml_bias(model, classes, X):
    """
    ML bias = P(long) - P(short) in [-1,1].
    """
    if not hasattr(model, "predict_proba"):
        preds = model.predict(X)
        return preds.astype(float)

    proba = model.predict_proba(X)
    classes = list(classes)
    long_idx  = classes.index(1) if 1 in classes else None
    short_idx = classes.index(-1) if -1 in classes else None

    pl = proba[:, long_idx]  if long_idx  is not None else np.zeros(len(X))
    ps = proba[:, short_idx] if short_idx is not None else np.zeros(len(X))
    return pl - ps


def evaluate_thresholds(bias, labels, thresholds):
    """
    For each |bias| > t:
      - long if bias > t
      - short if bias < -t
    Outcome in R: +1 = TP first, -1 = SL first, 0 = neither within horizon.
    """
    results = []
    y = labels.values

    for t in thresholds:
        long_mask  = bias >  t
        short_mask = bias < -t
        trade_mask = long_mask | short_mask

        trades = int(trade_mask.sum())
        if trades == 0:
            results.append({
                "threshold": t,
                "trades": 0,
                "winrate": np.nan,
                "expectancy_R": np.nan,
                "longs": 0,
                "shorts": 0,
            })
            continue

        outcomes = np.zeros_like(bias)

        # Longs: want label +1
        outcomes[long_mask & (y == 1)]  = 1.0
        outcomes[long_mask & (y == -1)] = -1.0

        # Shorts: want label -1
        outcomes[short_mask & (y == -1)] = 1.0
        outcomes[short_mask & (y == 1)]  = -1.0

        trade_outcomes = outcomes[trade_mask]
        wins   = (trade_outcomes > 0).sum()
        losses = (trade_outcomes < 0).sum()

        winrate    = wins / trades if trades > 0 else np.nan
        expectancy = trade_outcomes.mean() if trades > 0 else np.nan

        results.append({
            "threshold": t,
            "trades": trades,
            "winrate": float(winrate),
            "expectancy_R": float(expectancy),
            "longs": int(long_mask.sum()),
            "shorts": int(short_mask.sum()),
        })

    return pd.DataFrame(results)


def main():
    ex = ccxt.binance()

    # 1) Rebuild dataset like in backtest_ml
    df = load_price_df(ex, SYMBOL_SPOT, TIMEFRAME, CANDLES, TZ)
    df = attach_aggregated_oi_and_funding(df, SYMBOL_FUT, OKX_UNDERLYING, TIMEFRAME, CANDLES, TZ)
    df = compute_signals(df)

    # 2) Features + labels
    feats_df = build_features(df)
    y_all = label_tp_sl(df, tp=TP, sl=SL, horizon=HZN)

    # 3) Load model and use its feature list
    model, feats = load_model(MODEL_PATH)
    if not feats:
        raise SystemExit("Model file does not contain 'features' list.")

    missing = [f for f in feats if f not in feats_df.columns]
    if missing:
        print("Warning: the following model features are missing from current build_features():")
        print(missing)
        print("Cannot continue threshold tuning with inconsistent features.")
        raise SystemExit(1)

    X_df = feats_df[feats].copy()

    # --- IMPORTANT: use the SAME NA logic as backtest_ml.py ---
    X_df = X_df.replace([np.inf, -np.inf], np.nan)

    for col in X_df.columns:
        if col in ("oi_pct_agg", "oi_z_agg",
                   "fundingRate", "fundingRate_z", "fundingRate_diff",
                   "oi_agg_raw",
                   "smc_BOS_up", "smc_BOS_down",
                   "has_sweep_low", "has_sweep_high",
                   "fvg_up_flag", "fvg_down_flag"):
            X_df[col] = X_df[col].fillna(0.0)
        elif col in ("rsi", "ret_1", "ret_3", "ret_6", "atr14"):
            X_df[col] = X_df[col].ffill().bfill()
        else:
            X_df[col] = X_df[col].fillna(0.0)

    # Now drop any rows that *still* have NaNs
    X_df = X_df.dropna().copy()

    if X_df.empty:
        raise SystemExit(
            f"No rows left after NA handling for features {feats}. "
            "Try increasing CANDLES or check data availability."
        )

    # Align labels
    y = y_all.loc[X_df.index]
    X = X_df.values

    # 4) Compute ML bias
    bias = compute_ml_bias(model, model.classes_, X)

    # 5) Evaluate thresholds
    thresholds = np.round(np.linspace(0.05, 0.5, 10), 3)
    df_res = evaluate_thresholds(bias, y, thresholds)

    print("\n=== Threshold Scan (ML bias) ===")
    print(df_res.to_string(index=False, float_format=lambda v: f"{v:0.3f}"))

    out_path = f"threshold_scan_{SYMBOL_FUT}_{TIMEFRAME}.csv"
    df_res.to_csv(out_path, index=False)
    print(f"\nSaved threshold scan to {out_path}")


if __name__ == "__main__":
    main()
