import os
import json
import joblib
import ccxt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import TimeSeriesSplit

from market_structure_analyzer import (
    load_price_df, attach_aggregated_oi_and_funding,
    compute_signals
)
from signals_core import build_features, FEATURE_COLS, label_tp_sl

SYMBOL_SPOT = os.getenv("SYMBOL_SPOT", "BTC/USDT")
SYMBOL_FUT  = os.getenv("SYMBOL_FUT",  "BTCUSDT")
OKX_UNDERLYING = os.getenv("OKX_UNDERLYING", "BTC-USDT")
TIMEFRAME   = os.getenv("TIMEFRAME", "1h")
CANDLES     = int(os.getenv("CANDLES", "1500"))
TZ          = os.getenv("TZ_NAME", "Europe/Madrid")

TP = float(os.getenv("LBL_TP", "0.005"))
SL = float(os.getenv("LBL_SL", "0.005"))
HZN = int(os.getenv("LBL_HZN", "6"))

N_SPLITS = int(os.getenv("CV_SPLITS", "5"))
N_EST    = int(os.getenv("RF_ESTIMATORS", "300"))
MAX_DEPTH= int(os.getenv("RF_MAX_DEPTH", "8"))

MODEL_DIR = os.getenv("MODEL_DIR", "models")
MODEL_PATH = os.path.join(MODEL_DIR, f"rf_{SYMBOL_FUT}_{TIMEFRAME}.pkl")
REPORT_PATH= os.path.join(MODEL_DIR, f"report_{SYMBOL_FUT}_{TIMEFRAME}.json")

def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    ex = ccxt.binance()

    # 1) Load & enrich
    df = load_price_df(ex, SYMBOL_SPOT, TIMEFRAME, CANDLES, TZ)
    df = attach_aggregated_oi_and_funding(df, SYMBOL_FUT, OKX_UNDERLYING, TIMEFRAME, CANDLES, TZ)
    df = compute_signals(df)

    # 2) Features & labels
    X = build_features(df)
    y = label_tp_sl(df, tp=TP, sl=SL, horizon=HZN)

    # Clean missing / inf values
    X = X.replace([np.inf, -np.inf], np.nan)
    for col in X.columns:
        if col in ("oi_pct_agg", "oi_z_agg", "fundingRate"):
            X[col] = X[col].fillna(0.0)
        elif col in ("rsi", "ret_1", "ret_3", "ret_6", "atr14"):
            X[col] = X[col].ffill().bfill()
        else:
            X[col] = X[col].fillna(0.0)

    data = X.copy()
    data["label"] = y
    data = data.dropna(subset=FEATURE_COLS + ["label"]).copy()

    Xf = data[FEATURE_COLS].values
    yf = data["label"].values

    # 3) Dynamic CV splits
    n_samples = len(yf)
    if n_samples < 50:
        raise SystemExit(f"Not enough samples after preprocessing: {n_samples}")

    splits = min(N_SPLITS, max(2, n_samples // 200))
    if splits >= n_samples:
        splits = 2

    tscv = TimeSeriesSplit(n_splits=splits)
    reports = []
    fold = 0

    for train_idx, test_idx in tscv.split(Xf):
        fold += 1
        Xtr, Xte = Xf[train_idx], Xf[test_idx]
        ytr, yte = yf[train_idx], yf[test_idx]

        clf = RandomForestClassifier(
            n_estimators=N_EST,
            max_depth=MAX_DEPTH,
            random_state=42,
            n_jobs=-1,
            class_weight='balanced_subsample'
        )
        clf.fit(Xtr, ytr)
        pred = clf.predict(Xte)

        rpt = classification_report(yte, pred, output_dict=True, zero_division=0)
        cm  = confusion_matrix(yte, pred).tolist()
        reports.append({"fold": fold, "report": rpt, "confusion_matrix": cm})

    # 4) Train final on all data & save
    final = RandomForestClassifier(
        n_estimators=N_EST,
        max_depth=MAX_DEPTH,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced_subsample'
    )
    final.fit(Xf, yf)
    joblib.dump({"model": final, "features": FEATURE_COLS}, MODEL_PATH)

    importances = dict(zip(FEATURE_COLS, final.feature_importances_.tolist()))

    # Save report
    out = {
        "symbol": SYMBOL_FUT,
        "timeframe": TIMEFRAME,
        "samples": int(len(yf)),
        "cv_splits": splits,
        "tp": TP, "sl": SL, "horizon": HZN,
        "reports": reports,
        "feature_importances": importances,
        "model_path": MODEL_PATH,
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Saved model -> {MODEL_PATH}")
    print(f"Saved report -> {REPORT_PATH}")
    print("Top importances:", sorted(importances.items(), key=lambda x: x[1], reverse=True)[:6])

if __name__ == "__main__":
    main()
