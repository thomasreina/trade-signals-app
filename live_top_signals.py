import os
import time
import json
import requests

from market_structure_analyzer import (
    SYMBOL_FUT,
    TIMEFRAME,
    ML_BIAS_TH,
    generate_signals,
)

STATE_PATH = "live_state.json"

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "300"))  # default 5 minutes
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print("State save error:", e)


def format_signal_text(sig: dict) -> str:
    """Human-readable message for Discord / generic webhook."""
    ts = sig["timestamp"]
    side = sig["side"]
    price = sig["close"]
    ml_bias = sig["ml_bias"]
    conv = sig["ml_conviction"]
    sl = sig["sl"]
    tp1 = sig["tp1"]
    tp2 = sig["tp2"]
    reasons = sig["reasons"]

    lines = [
        f"**Top {side} signal on {SYMBOL_FUT} ({TIMEFRAME})**",
        f"Time: `{ts}`",
        f"Price: `{price:.2f}`",
        f"ML bias: `{ml_bias:+.3f}` ({conv})",
        f"SL: `{sl:.2f}`",
        f"TP1: `{tp1:.2f}`",
        f"TP2: `{tp2:.2f}`",
        "",
        f"Reasons: `{reasons}`",
    ]
    return "\n".join(lines)


def send_notification(sig: dict):
    """
    Send notification for a *top* signal via webhook.
    If WEBHOOK_URL looks like a Discord webhook, send `content` only.
    Otherwise send a structured JSON payload.
    """
    if not WEBHOOK_URL:
        print("WEBHOOK_URL not set, printing payload locally:")
        print(json.dumps(sig, indent=2, default=str))
        return

    # Discord webhook?
    is_discord = "discord.com/api/webhooks" in WEBHOOK_URL

    if is_discord:
        payload = {
            "content": format_signal_text(sig)
        }
    else:
        # generic JSON payload
        payload = {
            "event": "top_signal",
            "symbol": SYMBOL_FUT,
            "timeframe": TIMEFRAME,
            "side": sig["side"],
            "price": float(sig["close"]),
            "ml_bias": float(sig["ml_bias"]),
            "conviction": sig["ml_conviction"],
            "reasons": sig["reasons"],
            "risk": {
                "entry": float(sig["close"]),
                "sl": float(sig["sl"]),
                "tp1": float(sig["tp1"]),
                "tp2": float(sig["tp2"]),
            },
            "timestamp": str(sig["timestamp"]),
        }

    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        print("Sent top signal, status:", r.status_code)
        if not r.ok:
            print("Response text:", r.text)
    except Exception as e:
        print("Webhook error:", e)
        print("Payload was:")
        print(json.dumps(payload, indent=2, default=str))


def main_loop():
    state = load_state()
    if not state:
        # Warm-up flag so we don't alert on first historical bar
        state = {"initialized": False}

    print("Starting live top-signal watcher...")
    print(f"Polling every {POLL_SECONDS} seconds")
    print(f"Using ML_BIAS_TH = {ML_BIAS_TH}")
    print()

    while True:
        try:
            sig_df = generate_signals()
            if sig_df.empty:
                print("No signals produced this run.")
                time.sleep(POLL_SECONDS)
                continue

            last = sig_df.sort_values("timestamp").iloc[-1]
            ts = str(last["timestamp"])
            mb = float(last["ml_bias"])
            conv = last["ml_conviction"]

            print(f"[{ts}] side={last['side']} price={last['close']} "
                  f"ml_bias={mb:+.3f} conv={conv}")

            # Warm-up: first run, just record state and skip alert
            if not state.get("initialized", False):
                print("Warm-up: storing latest bar as baseline, no alert on first run.")
                state["initialized"] = True
                state["last_ts"] = ts
                state["last_mb"] = mb
                save_state(state)
                time.sleep(POLL_SECONDS)
                continue

            # Only treat as "top" if high conviction and above bias threshold
            if conv != "high" or abs(mb) < ML_BIAS_TH:
                # Update state but don't notify
                state["last_ts"] = ts
                state["last_mb"] = mb
                save_state(state)
                time.sleep(POLL_SECONDS)
                continue

            # Avoid duplicate alerts for same bar & same bias
            if state.get("last_ts") == ts and state.get("last_mb") == mb:
                print("No new top signal (same bar / same bias).")
                time.sleep(POLL_SECONDS)
                continue

            # Prepare clean dict for notification
            sig = {
                "timestamp": last["timestamp"],
                "side": last["side"],
                "close": float(last["close"]),
                "ml_bias": mb,
                "ml_conviction": conv,
                "sl": float(last["sl"]),
                "tp1": float(last["tp1"]),
                "tp2": float(last["tp2"]),
                "reasons": last["reasons"],
            }

            send_notification(sig)

            # Update state after sending
            state["last_ts"] = ts
            state["last_mb"] = mb
            save_state(state)

        except Exception as e:
            print("Error in main_loop:", e)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main_loop()
