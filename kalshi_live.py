"""Optional read-only Kalshi WebSocket ticker feed.

Authentication comes exclusively from server-side Streamlit secrets.
This client never sends orders or accesses a portfolio.
"""
from __future__ import annotations

import base64
import json
import logging
import threading
import time

import websocket
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

URL = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
PATH = "/trade-api/ws/v2"
LOG = logging.getLogger(__name__)


def auth_headers(api_key_id: str, private_key_pem: str, timestamp_ms=None):
    timestamp = str(timestamp_ms or int(time.time() * 1000))
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"), password=None
    )
    message = (timestamp + "GET" + PATH).encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
    }


class LiveTicker:
    """Daemon listener retaining only tennis quotes, with locked snapshots."""

    PREFIXES = ("KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH",
                "KXWTACHALLENGERMATCH", "KXITFMATCH")

    def __init__(self, api_key_id: str, private_key_pem: str):
        self._key_id = api_key_id
        self._private_key = private_key_pem
        self._lock = threading.Lock()
        self._latest = {}
        self._last_message = None
        self._status = "connecting"
        self._error = None
        self._worker = threading.Thread(target=self._run, name="kalshi-ticker", daemon=True)
        self._worker.start()

    def _on_open(self, ws):
        ws.send(json.dumps({"id": 1, "cmd": "subscribe", "params": {"channels": ["ticker"]}}))
        with self._lock:
            self._status = "connected"

    def _on_message(self, ws, raw):
        try:
            payload = json.loads(raw)
            if payload.get("type") == "error":
                with self._lock:
                    self._error = "Kalshi rejected the ticker subscription."
                    self._status = "error"
                return
            if payload.get("type") != "ticker":
                return
            msg = payload.get("msg") or {}
            ticker = msg.get("market_ticker", "")
            if not ticker.startswith(self.PREFIXES):
                return
            with self._lock:
                self._latest[ticker] = msg
                self._last_message = time.time()
                self._status = "live"
        except (TypeError, ValueError, AttributeError):
            LOG.warning("Ignored malformed Kalshi ticker message")

    def _run(self):
        delay = 2
        while True:
            try:
                headers = auth_headers(self._key_id, self._private_key)
                ws = websocket.WebSocketApp(
                    URL, header=[f"{k}: {v}" for k, v in headers.items()],
                    on_open=self._on_open, on_message=self._on_message,
                    on_error=self._on_error, on_close=self._on_close,
                )
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                LOG.exception("Kalshi ticker connection failed")
            with self._lock:
                self._status = "reconnecting"
            time.sleep(delay)
            delay = min(delay * 2, 60)

    def _on_error(self, ws, error):
        with self._lock:
            self._status = "error"
            # Never log or expose API credentials/signatures.
            self._error = type(error).__name__

    def _on_close(self, ws, code, message):
        with self._lock:
            self._status = "disconnected"

    def snapshot(self):
        with self._lock:
            return dict(self._latest), self._last_message, self._status, self._error


def overlay_market_data(rows, live_updates, last_message, max_age_seconds=20):
    """Apply streaming totals and prices to a fresh REST baseline.

    Ignore old WebSocket messages, and do not interpret absent values as zero.
    No modification to the caller's rows.
    """
    if last_message is None or time.time() - last_message > max_age_seconds:
        return rows, 0
    result = []
    count = 0
    for row in rows:
        updated = dict(row)
        tick = live_updates.get(row["ticker"])
        if tick:
            count += 1
            if tick.get("volume_fp") is not None:
                try:
                    updated["volume_total"] = float(tick["volume_fp"])
                except (ValueError, TypeError):
                    pass
            for src, dest in (("yes_bid_dollars", "bid_c"),
                              ("yes_ask_dollars", "ask_c"),
                              ("price_dollars", "last_c")):
                if tick.get(src) is not None:
                    try:
                        updated[dest] = round(float(tick[src]) * 100, 4)
                    except (ValueError, TypeError):
                        pass
            bid, ask = updated.get("bid_c"), updated.get("ask_c")
            updated["spread_c"] = (
                round(ask - bid, 4)
                if bid is not None and ask is not None and ask >= bid else None
            )
        result.append(updated)
    return result, count
