import os
import json
import numpy as np
import pandas as pd
import requests
import joblib
import ccxt
from ta.momentum import RSIIndicator

from signals_core import build_features

# =============================
# Env / Config
# =============================

SYMBOL_SPOT = os.getenv("SYMBOL_SPOT", "BTC/USDT")
SYMBOL_FUT  = os.getenv("SYMBOL_FUT", "BTCUSDT")
OKX_UNDERLYING = os.getenv("OKX_UNDERLYING", "BTC-USDT")
TIMEFRAME   = os.getenv("TIMEFRAME", "1h")
CANDLES     = int(os.getenv("CANDLES", "500"))
TZ          = os.getenv("TZ_NAME", "Europe/Madrid")

SAVE_SIGNALS_PATH = os.getenv("SAVE_SIGNALS_PATH", f"signals_{SYMBOL_FUT}_{TIMEFRAME}.csv")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# ML options
USE_ML   = os.getenv("USE_ML", "false").lower() == "true"
W_ML     = float(os.getenv("W_ML", "0.30"))
MODEL_PATH = os.getenv("MODEL_PATH", f"models/rf_{SYMBOL_FUT}_{TIMEFRAME}.pkl")

ML_BIAS_TH      = float(os.getenv("ML_BIAS_TH", "0.20"))   # entry filter
ML_BIAS_HIGH_TH = float(os.getenv("ML_BIAS_HIGH_TH", "0.25"))  # high conviction


# =============================
# Core helpers
# =============================

def _atr14(df: pd.DataFrame) -> pd.Series:
    """Simple ATR(14) based on high/low/close."""
    tr1 = (df["high"] - df["low"]).abs()
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"]  - df["close"].shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(14).mean()


# =============================
# Price loader (for training & live)
# =============================

def load_price_df(exchange, symbol, timeframe, candles, tz):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=candles)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(tz)
    return df


# =============================
# OI fetchers
# =============================

def oi_binance(symbol_fut, timeframe, candles, tz):
    """Binance futures OI history."""
    try:
        url = (
            "https://fapi.binance.com/futures/data/openInterestHist"
            f"?symbol={symbol_fut}&period={timeframe}&limit={candles}"
        )
        resp = requests.get(url, timeout=15).json()
        if isinstance(resp, list):
            df = pd.DataFrame.from_records(resp)
        elif isinstance(resp, dict):
            data = resp.get("data") or resp.get("list") or []
            df = pd.DataFrame.from_records(data)
        else:
            return pd.DataFrame(columns=["timestamp", "oi"])
        if df.empty or "timestamp" not in df.columns:
            return pd.DataFrame(columns=["timestamp", "oi"])

        if "sumOpenInterest" in df.columns:
            df["oi"] = pd.to_numeric(df["sumOpenInterest"], errors="coerce")
        elif "openInterest" in df.columns:
            df["oi"] = pd.to_numeric(df["openInterest"], errors="coerce")
        else:
            return pd.DataFrame(columns=["timestamp", "oi"])

        df["timestamp"] = pd.to_datetime(
            pd.to_numeric(df["timestamp"], errors="coerce"),
            unit="ms", utc=True
        ).dt.tz_convert(tz)
        return df[["timestamp", "oi"]].dropna()
    except Exception as e:
        print("Binance OI error:", e)
        return pd.DataFrame(columns=["timestamp", "oi"])


def oi_bybit(symbol_fut, timeframe, candles, tz):
    """Bybit open interest."""
    try:
        url = (
            "https://api.bybit.com/v5/market/open-interest"
            f"?category=linear&symbol={symbol_fut}&interval={timeframe}&limit={candles}"
        )
        j = requests.get(url, timeout=15).json()
        data = j.get("result", {}).get("list", [])
        if not data:
            return pd.DataFrame(columns=["timestamp", "oi"])
        df = pd.DataFrame.from_records(data)
        tscol = "timestamp" if "timestamp" in df.columns else ("time" if "time" in df.columns else None)
        if tscol is None:
            return pd.DataFrame(columns=["timestamp", "oi"])
        df["timestamp"] = pd.to_datetime(
            pd.to_numeric(df[tscol], errors="coerce"),
            unit="ms", utc=True
        ).dt.tz_convert(tz)
        oicol = "openInterest" if "openInterest" in df.columns else ("oi" if "oi" in df.columns else None)
        if oicol is None:
            return pd.DataFrame(columns=["timestamp", "oi"])
        df["oi"] = pd.to_numeric(df[oicol], errors="coerce")
        return df[["timestamp", "oi"]].dropna()
    except Exception as e:
        print("Bybit OI error:", e)
        return pd.DataFrame(columns=["timestamp", "oi"])


def oi_okx(underlying, timeframe, candles, tz):
    """OKX swap OI (summed across contracts)."""
    try:
        url = f"https://www.okx.com/api/v5/public/open-interest?instType=SWAP&uly={underlying}"
        j = requests.get(url, timeout=15).json()
        data = j.get("data", [])
        if not data:
            return pd.DataFrame(columns=["timestamp", "oi"])
        oi_sum = 0.0
        for d in data:
            try:
                oi_sum += float(d.get("oi", 0.0))
            except Exception:
                pass
        now_ts = pd.Timestamp.now(tz="UTC").tz_convert(tz)
        return pd.DataFrame({"timestamp": [now_ts], "oi": [oi_sum]})
    except Exception as e:
        print("OKX OI error:", e)
        return pd.DataFrame(columns=["timestamp", "oi"])


# =============================
# Aggregator (OI + funding)
# =============================

def attach_aggregated_oi_and_funding(df, symbol_fut, okx_underlying, timeframe, candles, tz):
    """Merge Binance, Bybit, OKX OI + funding into main df."""
    def align(oi_df):
        base = df[["timestamp"]].sort_values("timestamp").copy()
        if oi_df is None or oi_df.empty:
            base["oi"] = np.nan
            return base
        return pd.merge_asof(
            base,
            oi_df.sort_values("timestamp"),
            on="timestamp",
            direction="backward"
        )

    bnb = oi_binance(symbol_fut, timeframe, candles, tz)
    byt = oi_bybit(symbol_fut, timeframe, candles, tz)
    okx = oi_okx(okx_underlying, timeframe, candles, tz)

    bnb_a = align(bnb).rename(columns={"oi": "oi_binance"})
    byt_a = align(byt).rename(columns={"oi": "oi_bybit"})
    okx_a = align(okx).rename(columns={"oi": "oi_okx"})

    out = df.merge(bnb_a, on="timestamp", how="left") \
            .merge(byt_a, on="timestamp", how="left") \
            .merge(okx_a, on="timestamp", how="left")

    out["oi_agg"] = out[["oi_binance", "oi_bybit", "oi_okx"]].mean(axis=1, skipna=True)
    out["oi_pct_agg"] = out["oi_agg"].pct_change(fill_method=None) * 100.0

    mu = out["oi_pct_agg"].mean()
    sigma = out["oi_pct_agg"].std(ddof=0)
    out["oi_z_agg"] = (out["oi_pct_agg"] - mu) / sigma if sigma else np.nan

    # Funding via Binance
    try:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol_fut}&limit=1000"
        fr = pd.DataFrame(requests.get(url, timeout=15).json())
        fr["timestamp"] = pd.to_datetime(fr["fundingTime"], unit="ms", utc=True).dt.tz_convert(tz)
        fr["fundingRate"] = pd.to_numeric(fr["fundingRate"], errors="coerce")
        out = pd.merge_asof(
            out.sort_values("timestamp"),
            fr[["timestamp", "fundingRate"]].sort_values("timestamp"),
            on="timestamp",
            direction="backward"
        )
        out["fundingRate"] = out["fundingRate"].fillna(0.0)
    except Exception as e:
        print("Funding error:", e)
        out["fundingRate"] = 0.0

    return out


# =============================
# SMC structure (swings, sweeps, FVG)
# =============================

def _compute_swings_sweeps(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """Detect swing highs/lows and sweeps."""
    df = df.copy()
    n = len(df)

    swing_high = np.zeros(n, dtype=bool)
    swing_low  = np.zeros(n, dtype=bool)

    highs = df["high"].values
    lows  = df["low"].values
    closes = df["close"].values

    for i in range(1, n - 1):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            swing_high[i] = True
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            swing_low[i] = True

    df["swing_high"] = swing_high
    df["swing_low"]  = swing_low
    df["swing_high_level"] = np.where(swing_high, df["high"], np.nan)
    df["swing_low_level"]  = np.where(swing_low, df["low"], np.nan)

    df["swing_high_level"] = df["swing_high_level"].ffill()
    df["swing_low_level"]  = df["swing_low_level"].ffill()

    sweep_type  = np.array([""] * n, dtype=object)
    sweep_level = np.full(n, np.nan)

    for i in range(lookback, n):
        window_high = highs[i - lookback:i]
        window_low  = lows[i - lookback:i]

        prev_hi = window_high.max()
        prev_lo = window_low.min()

        if highs[i] > prev_hi and closes[i] < prev_hi:
            sweep_type[i] = "sweep_high"
            sweep_level[i] = prev_hi
        elif lows[i] < prev_lo and closes[i] > prev_lo:
            sweep_type[i] = "sweep_low"
            sweep_level[i] = prev_lo

    df["sweep"] = sweep_type
    df["sweep_level"] = sweep_level

    df["swept_high_level"] = (
        pd.Series(
            np.where(df["sweep"] == "sweep_high", df["sweep_level"], np.nan),
            index=df.index
        ).ffill()
    )
    df["swept_low_level"] = (
        pd.Series(
            np.where(df["sweep"] == "sweep_low", df["sweep_level"], np.nan),
            index=df.index
        ).ffill()
    )

    return df


def _compute_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """
    Simple 3-candle Fair Value Gap:
    - Bullish FVG at bar i if low[i] > high[i-2]
    - Bearish FVG at bar i if high[i] < low[i-2]
    """
    df = df.copy()
    n = len(df)
    highs = df["high"].values
    lows  = df["low"].values

    fvg_up_flag   = np.array([""] * n, dtype=object)
    fvg_down_flag = np.array([""] * n, dtype=object)
    fvg_up_low  = np.full(n, np.nan)
    fvg_up_high = np.full(n, np.nan)
    fvg_dn_low  = np.full(n, np.nan)
    fvg_dn_high = np.full(n, np.nan)

    for i in range(2, n):
        if lows[i] > highs[i - 2]:
            fvg_up_flag[i] = "fvg_up"
            fvg_up_low[i]  = highs[i - 2]
            fvg_up_high[i] = lows[i]
        elif highs[i] < lows[i - 2]:
            fvg_down_flag[i] = "fvg_down"
            fvg_dn_high[i]   = lows[i - 2]
            fvg_dn_low[i]    = highs[i]

    df["fvg_up"]   = fvg_up_flag
    df["fvg_down"] = fvg_down_flag
    df["fvg_up_low"]   = fvg_up_low
    df["fvg_up_high"]  = fvg_up_high
    df["fvg_down_low"] = fvg_dn_low
    df["fvg_down_high"] = fvg_dn_high

    return df


# =============================
# Minimal SMC-ish signals (+ SMC features)
# =============================

def compute_signals(df):
    """
    - Compute RSI + simple BOS_up / BOS_down
    - Compute ATR14
    - Compute swings, sweeps, FVGs
    - Provide columns used by ML features.
    """
    df = df.copy()
    df["rsi"] = RSIIndicator(df["close"], 14).rsi()
    df["atr14"] = _atr14(df)

    df["smc_signal"] = np.where(
        df["rsi"] >= 60, "BOS_up",
        np.where(df["rsi"] <= 40, "BOS_down", "neutral")
    )

    df = _compute_swings_sweeps(df, lookback=5)
    df = _compute_fvg(df)

    if "sweep" not in df.columns:
        df["sweep"] = ""
    if "fvg_up" not in df.columns:
        df["fvg_up"] = ""
    if "fvg_down" not in df.columns:
        df["fvg_down"] = ""

    return df


# =============================
# ML helpers
# =============================

def _load_model(path):
    try:
        blob = joblib.load(path)
        return blob.get("model", None), blob.get("features", [])
    except Exception as e:
        print("ML load error:", e)
        return None, []


def ml_score_row(df_full, idx, build_features_func):
    """
    Return ML bias in [-1,1]: + means long bias, - means short bias.
    0 if ML disabled / unavailable.
    """
    if not USE_ML:
        return 0.0
    model, feats = _load_model(MODEL_PATH)
    if model is None or not feats:
        return 0.0

    X = build_features_func(df_full).reindex(df_full.index)
    missing = [f for f in feats if f not in X.columns]
    if missing:
        print("ML: missing features:", missing)
        return 0.0

    row = X.iloc[idx:idx+1][feats]
    if row.isna().any(axis=None):
        return 0.0

    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(row.values)[0]
        classes = list(getattr(model, "classes_", [-1, 0, 1]))
        pl = proba[classes.index(1)] if 1 in classes else 0.0
        ps = proba[classes.index(-1)] if -1 in classes else 0.0
        return float(pl - ps)

    pred = model.predict(row.values)[0]
    return float(pred)


# =============================
# SMC-based SL/TP helpers
# =============================

def _build_fvg_lists(df: pd.DataFrame):
    """Build bullish/bearish FVG lists with midpoints for targeting."""
    bull = []
    bear = []
    for _, row in df.iterrows():
        if row.get("fvg_up") == "fvg_up":
            low = row.get("fvg_up_low", np.nan)
            high = row.get("fvg_up_high", np.nan)
            if not np.isnan(low) and not np.isnan(high):
                mid = (low + high) / 2.0
                bull.append({"mid": float(mid), "low": float(low), "high": float(high)})
        if row.get("fvg_down") == "fvg_down":
            low = row.get("fvg_down_low", np.nan)
            high = row.get("fvg_down_high", np.nan)
            if not np.isnan(low) and not np.isnan(high):
                mid = (low + high) / 2.0
                bear.append({"mid": float(mid), "low": float(low), "high": float(high)})
    return bull, bear


def _smc_sl_tp(side: str, row: pd.Series, price: float, atr: float,
               fvg_bull: list, fvg_bear: list):
    """
    Compute SL / TP1 / TP2 using SMC:
    - SL from swept level or swing
    - TP1 from FVG mid (directional)
    - TP2 from extended target based on that mid
    Fallback: ATR-based if no clean SMC or sanity fails.
    """
    if np.isnan(atr) or atr <= 0:
        atr = price * 0.01  # fallback

    # --- Stop loss via sweeps / swings ---
    if side == "LONG":
        sl = row.get("swept_low_level", np.nan)
        if np.isnan(sl):
            sl = row.get("swing_low_level", np.nan)
        if np.isnan(sl):
            sl = price - 2.0 * atr
        # sanity: SL must be below price
        if sl >= price:
            sl = price - 2.0 * atr
    else:
        sl = row.get("swept_high_level", np.nan)
        if np.isnan(sl):
            sl = row.get("swing_high_level", np.nan)
        if np.isnan(sl):
            sl = price + 2.0 * atr
        # sanity: SL must be above price
        if sl <= price:
            sl = price + 2.0 * atr

    # --- TP via FVG mid ---
    tp1 = np.nan
    tp2 = np.nan

    if side == "LONG":
        cands = [f for f in fvg_bull if f["mid"] > price]
        if cands:
            chosen = min(cands, key=lambda f: f["mid"] - price)
            mid = chosen["mid"]
            tp1 = mid
            tp2 = mid + (mid - price)
    else:
        cands = [f for f in fvg_bear if f["mid"] < price]
        if cands:
            chosen = max(cands, key=lambda f: f["mid"])
            mid = chosen["mid"]
            tp1 = mid
            tp2 = mid - (price - mid)

    # Sanity: targets must be in the trade direction
    if side == "LONG":
        if np.isnan(tp1) or np.isnan(tp2) or tp1 <= price or tp2 <= price:
            tp1 = price + 2.0 * atr
            tp2 = price + 3.0 * atr
    else:
        if np.isnan(tp1) or np.isnan(tp2) or tp1 >= price or tp2 >= price:
            tp1 = price - 2.0 * atr
            tp2 = price - 3.0 * atr

    return float(sl), float(tp1), float(tp2)


# =============================
# Live signal generation
# =============================

def generate_signals():
    ex = ccxt.binance()

    df = load_price_df(ex, SYMBOL_SPOT, TIMEFRAME, CANDLES, TZ)
    df = attach_aggregated_oi_and_funding(df, SYMBOL_FUT, OKX_UNDERLYING, TIMEFRAME, CANDLES, TZ)
    df = compute_signals(df)

    ml_biases = []
    for i in range(len(df)):
        mb = ml_score_row(df, i, build_features)
        ml_biases.append(mb)
    df["ml_bias"] = ml_biases

    abs_mb = df["ml_bias"].abs()
    df["ml_conviction"] = np.where(
        abs_mb >= ML_BIAS_HIGH_TH, "high",
        np.where(abs_mb >= ML_BIAS_TH, "normal", "low")
    )

    fvg_bull, fvg_bear = _build_fvg_lists(df)

    signals = []

    for idx, row in df.iterrows():
        mb = row["ml_bias"]
        if abs(mb) < ML_BIAS_TH:
            continue  # ML override: ignore weak bias

        side = "LONG" if mb > 0 else "SHORT"
        conviction = row["ml_conviction"]
        price = float(row["close"])
        rsi = row.get("rsi", np.nan)
        oi_pct = row.get("oi_pct_agg", np.nan)
        funding = row.get("fundingRate", 0.0)
        smc_sig = row.get("smc_signal", "neutral")
        atr = row.get("atr14", np.nan)

        sl, tp1, tp2 = _smc_sl_tp(side, row, price, atr, fvg_bull, fvg_bear)

        reasons = []
        reasons.append(f"MLbias{mb:+.2f}")
        if not np.isnan(rsi):
            reasons.append(f"RSI{rsi:.1f}")
        if not np.isnan(oi_pct):
            reasons.append(f"OIagg{oi_pct:+.2f}%")
        if funding != 0:
            reasons.append("funding+" if funding > 0 else "funding-")
        if smc_sig and smc_sig != "neutral":
            reasons.append(smc_sig)
        if row.get("sweep", ""):
            reasons.append(row["sweep"])

        signals.append({
            "timestamp": row["timestamp"],
            "close": price,
            "rsi": rsi,
            "oi_pct_agg": oi_pct,
            "oi_z_agg": row.get("oi_z_agg", np.nan),
            "fundingRate": funding,
            "smc_signal": smc_sig,
            "ml_bias": mb,
            "ml_conviction": conviction,
            "side": side,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "reasons": ",".join(reasons),
        })

    sig_df = pd.DataFrame(signals)
    return sig_df


def send_webhook(last_signal: pd.Series):
    if not WEBHOOK_URL:
        return
    payload = {
        "event": "trade_setup",
        "symbol": SYMBOL_FUT,
        "timeframe": TIMEFRAME,
        "side": last_signal["side"],
        "price": float(last_signal["close"]),
        "ml_bias": float(last_signal["ml_bias"]),
        "conviction": last_signal["ml_conviction"],
        "reasons": last_signal["reasons"],
        "risk": {
            "entry": float(last_signal["close"]),
            "sl": float(last_signal["sl"]),
            "tp1": float(last_signal["tp1"]),
            "tp2": float(last_signal["tp2"]),
        },
    }
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        print("Webhook status:", r.status_code)
    except Exception as e:
        print("Webhook error:", e)


def main():
    sig_df = generate_signals()
    if sig_df.empty:
        print("No signals (ML bias below threshold on all bars).")
        return

    sig_df = sig_df.sort_values("timestamp")
    print(sig_df.tail(25))

    sig_df.to_csv(SAVE_SIGNALS_PATH, index=False)
    print(f"\nSaved signals -> {SAVE_SIGNALS_PATH}")

    last = sig_df.iloc[-1]
    print("\nLast signal payload:")
    print(json.dumps({
        "timestamp": str(last["timestamp"]),
        "side": last["side"],
        "price": float(last["close"]),
        "ml_bias": float(last["ml_bias"]),
        "conviction": last["ml_conviction"],
        "sl": float(last["sl"]),
        "tp1": float(last["tp1"]),
        "tp2": float(last["tp2"]),
        "reasons": last["reasons"],
    }, indent=2))
    send_webhook(last)


if __name__ == "__main__":
    main()


# =============================
# Alias for backend wrapper
# =============================

run_analyzer = generate_signals


# =============================
# Order Block detection
# =============================

def _compute_order_blocks(df: pd.DataFrame, atr_multiplier: float = 1.5) -> pd.DataFrame:
    """
    Detect Order Blocks (OBs).

    Bullish OB  = last bearish candle before a strong bullish impulse.
    Bearish OB  = last bullish candle before a strong bearish impulse.

    An impulse is a candle whose body (|close - open|) exceeds
    atr_multiplier * ATR(14).
    """
    df = df.copy()
    n = len(df)

    ob_bull_low  = np.full(n, np.nan)
    ob_bull_high = np.full(n, np.nan)
    ob_bear_low  = np.full(n, np.nan)
    ob_bear_high = np.full(n, np.nan)

    opens  = df["open"].values
    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values
    atr    = df["atr14"].values if "atr14" in df.columns else np.ones(n)

    for i in range(2, n):
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        body = abs(closes[i] - opens[i])
        if body <= atr_multiplier * atr[i]:
            continue

        if closes[i] > opens[i]:           # bullish impulse → find last bearish candle
            for j in range(i - 1, max(0, i - 5), -1):
                if closes[j] < opens[j]:
                    ob_bull_low[j]  = lows[j]
                    ob_bull_high[j] = highs[j]
                    break
        elif closes[i] < opens[i]:         # bearish impulse → find last bullish candle
            for j in range(i - 1, max(0, i - 5), -1):
                if closes[j] > opens[j]:
                    ob_bear_low[j]  = lows[j]
                    ob_bear_high[j] = highs[j]
                    break

    df["ob_bull_low"]  = ob_bull_low
    df["ob_bull_high"] = ob_bull_high
    df["ob_bear_low"]  = ob_bear_low
    df["ob_bear_high"] = ob_bear_high
    return df


# =============================
# CHoCH / BOS classification
# =============================

def _compute_choch_bos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classify structure breaks as BOS or CHoCH.

    Uses the rolling sequence of swing highs and lows to determine trend:
      - HH + HL  →  uptrend
      - LH + LL  →  downtrend

    BOS   = break in the direction of the current trend (continuation).
    CHoCH = break against the current trend (reversal signal).
    """
    df = df.copy()
    n = len(df)

    swing_high = df["swing_high"].values if "swing_high" in df.columns else np.zeros(n, dtype=bool)
    swing_low  = df["swing_low"].values  if "swing_low"  in df.columns else np.zeros(n, dtype=bool)

    highs = df["high"].values
    lows  = df["low"].values

    bos_up_level     = np.full(n, np.nan)
    bos_down_level   = np.full(n, np.nan)
    choch_up_level   = np.full(n, np.nan)
    choch_down_level = np.full(n, np.nan)

    sh_history: list = []   # (index, price)
    sl_history: list = []
    trend = "neutral"

    for i in range(n):
        if swing_high[i]:
            sh_history.append((i, highs[i]))
        if swing_low[i]:
            sl_history.append((i, lows[i]))

        # Update trend from last two swing points of each type
        if len(sh_history) >= 2 and len(sl_history) >= 2:
            hh = sh_history[-1][1] > sh_history[-2][1]
            hl = sl_history[-1][1] > sl_history[-2][1]
            lh = sh_history[-1][1] < sh_history[-2][1]
            ll = sl_history[-1][1] < sl_history[-2][1]
            if hh and hl:
                trend = "up"
            elif lh and ll:
                trend = "down"

        # Check breaks vs last known swing levels
        if sh_history:
            last_sh = sh_history[-1][1]
            if highs[i] > last_sh:
                if trend == "up":
                    bos_up_level[i] = last_sh
                elif trend == "down":
                    choch_up_level[i] = last_sh

        if sl_history:
            last_sl = sl_history[-1][1]
            if lows[i] < last_sl:
                if trend == "down":
                    bos_down_level[i] = last_sl
                elif trend == "up":
                    choch_down_level[i] = last_sl

    df["bos_up_level"]     = bos_up_level
    df["bos_down_level"]   = bos_down_level
    df["choch_up_level"]   = choch_up_level
    df["choch_down_level"] = choch_down_level
    return df


# =============================
# Range / consolidation detection
# =============================

def _compute_ranges(df: pd.DataFrame, lookback: int = 20, atr_multiplier: float = 2.5) -> pd.DataFrame:
    """
    Identify consolidation ranges.

    A bar is flagged 'in_range' when the rolling (lookback+1)-bar high-low
    spread is less than atr_multiplier * ATR(14).  Low spread = price is
    oscillating without meaningful directional progress.
    """
    df = df.copy()
    n = len(df)

    range_high = np.full(n, np.nan)
    range_low  = np.full(n, np.nan)
    range_mid  = np.full(n, np.nan)
    in_range   = np.zeros(n, dtype=bool)

    highs = df["high"].values
    lows  = df["low"].values
    atr   = df["atr14"].values if "atr14" in df.columns else np.ones(n)

    for i in range(lookback, n):
        w_hi  = highs[i - lookback:i + 1]
        w_lo  = lows[i - lookback:i + 1]
        w_atr = atr[i - lookback:i + 1]

        spread   = w_hi.max() - w_lo.min()
        avg_atr  = float(np.nanmean(w_atr))

        if avg_atr > 0 and spread < atr_multiplier * avg_atr:
            rh = float(w_hi.max())
            rl = float(w_lo.min())
            range_high[i] = rh
            range_low[i]  = rl
            range_mid[i]  = (rh + rl) / 2.0
            in_range[i]   = True

    df["range_high"] = range_high
    df["range_low"]  = range_low
    df["range_mid"]  = range_mid
    df["in_range"]   = in_range
    return df


# =============================
# Multi-symbol full analysis
# =============================

SYMBOL_MAP = {
    "BTC": {"spot": "BTC/USDT", "fut": "BTCUSDT",  "okx": "BTC-USDT"},
    "ETH": {"spot": "ETH/USDT", "fut": "ETHUSDT",  "okx": "ETH-USDT"},
}


def analyze_symbol(symbol: str = "BTC", timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
    """
    Full SMC analysis pipeline for BTC or ETH.

    Fetches OHLCV + OI + funding, then runs:
      RSI · ATR · swings · sweeps · FVGs · Order Blocks · CHoCH/BOS · ranges

    Returns an enriched DataFrame with every overlay column so the API
    can slice and serialise what the frontend needs.
    """
    sym = SYMBOL_MAP.get(symbol.upper(), SYMBOL_MAP["BTC"])
    tz  = TZ

    ex  = ccxt.binance()
    df  = load_price_df(ex, sym["spot"], timeframe, limit, tz)
    df  = attach_aggregated_oi_and_funding(df, sym["fut"], sym["okx"], timeframe, limit, tz)
    df  = compute_signals(df)           # RSI, ATR, swings, sweeps, FVGs
    df  = _compute_order_blocks(df)
    df  = _compute_choch_bos(df)
    df  = _compute_ranges(df)
    return df
