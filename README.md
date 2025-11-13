
# BTC Trade Setup Engine (OI + RSI + SMC) — with 4H Trend Filter & Webhooks

This project scans BTC perps for high‑probability setups by combining:
- **Open Interest dynamics** (pct & z‑score)
- **RSI level + divergences**
- **Smart Money Concepts** (BOS, sweeps, FVG)
- **Funding rate context**
- A **4H trend filter** gating 1H entries
- Optional **Telegram** alerts and **webhook** payloads (TradingView/Pine‑style)

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill TG_TOKEN/TG_CHAT/WEBHOOK_URL if needed
python market_structure_analyzer.py
```

Outputs:
- `signals_btcusdt_1h.csv` – last actionable signals
- `htf_snapshot.csv` – last 10 4H bars with score (for transparency)

## Docker

Build and run once:
```bash
docker build -t trade-signals .
docker run --rm --env-file .env -v $(pwd):/app trade-signals
```

### Schedule with host cron (recommended)

Use your host's crontab (Linux/macOS):
```bash
crontab -e
# then add:
3 * * * * cd /path/to/project && /usr/bin/docker run --rm --env-file .env -v $(pwd):/app trade-signals >> logs.txt 2>&1
```

This runs the analyzer shortly after the hour, once the latest 1H candle is typically available.

## Webhook payload (example)

If `WEBHOOK_URL` is set, the script will POST JSON like:

```json
{
  "event": "trade_setup",
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "side": "LONG",
  "price": 103500.12,
  "score": 0.41,
  "reasons": "BOS_up,sweep_low,OI+2.11%,funding-",
  "risk": {
    "entry": 103500.12,
    "sl_pct": 0.0075,
    "tp1_pct": 0.0075,
    "tp2_pct": 0.015
  }
}
```

You can wire this to TradingView/PineConnector or any automation layer.

## Tuning

- Increase `LONG_TH`/`SHORT_TH` or `REQ_CONSECUTIVE` to reduce noise.
- Adjust `W_*` weights to reflect your conviction.
- Change `HTF_TIMEFRAME` to `2h`/`6h`/`1d` for different gating behavior.

## Notes

- All times are localized to `Europe/Madrid` by default.
- Data sources: Binance spot OHLCV (via ccxt) + Binance Futures OI & funding.
- Extend to Bybit/OKX by adding additional OI endpoints and doing an OI‑weighted aggregate.
