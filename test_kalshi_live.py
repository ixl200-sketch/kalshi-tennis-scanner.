"""Offline smoke tests for read-only Kalshi live ticker transformations."""
import time
import unittest
from unittest.mock import patch

from kalshi_live import LiveTicker, overlay_market_data, apply_exchange_dollar_volumes


class StreamingTests(unittest.TestCase):
    def test_live_volume_overrides_rest_snapshot(self):
        baseline = [{"ticker": "KXATPMATCH-TEST", "volume_total": 100,
                     "bid_c": 45, "ask_c": 53, "spread_c": 8}]
        updates = {"KXATPMATCH-TEST": {
            "seen_at": time.time(),
            "data": {"volume_fp": "140.00", "yes_bid_dollars": "0.4800",
                     "yes_ask_dollars": "0.5000"}
        }}
        out, count = overlay_market_data(baseline, updates, time.time())
        self.assertEqual(count, 1)
        self.assertEqual(out[0]["volume_total"], 140)
        self.assertEqual(out[0]["spread_c"], 2)
        self.assertEqual(baseline[0]["volume_total"], 100)

    def test_stale_market_update_is_ignored(self):
        baseline = [{"ticker": "T", "volume_total": 10}]
        updates = {"T": {"seen_at": time.time() - 200,
                         "data": {"volume_fp": "999"}}}
        out, count = overlay_market_data(baseline, updates, time.time())
        self.assertEqual(count, 0)
        self.assertEqual(out[0]["volume_total"], 10)

    def test_exchange_dollar_volume_uses_field_not_contract_count(self):
        baseline = [{"ticker": "KXATPMATCH-EXAMPLE", "volume_total": 800000}]
        updates = {"KXATPMATCH-EXAMPLE": {
            "seen_at": time.time(),
            "data": {"volume_fp": "800000.00", "dollar_volume": 400000},
        }}
        rows = apply_exchange_dollar_volumes(baseline, updates)
        self.assertEqual(rows[0]["exchange_dollar_volume"], 400000)
        self.assertEqual(rows[0]["volume_total"], 800000)

    def test_missing_or_stale_dollar_volume_is_not_guessed(self):
        baseline = [{"ticker": "X", "volume_total": 1000}]
        self.assertNotIn("exchange_dollar_volume", apply_exchange_dollar_volumes(baseline, {})[0])
        stale = {"X": {"seen_at": time.time() - 500, "data": {"dollar_volume": 500}}}
        self.assertNotIn("exchange_dollar_volume", apply_exchange_dollar_volumes(baseline, stale)[0])
        missing = {"X": {"seen_at": time.time(), "data": {"volume_fp": "1000"}}}
        self.assertNotIn("exchange_dollar_volume", apply_exchange_dollar_volumes(baseline, missing)[0])

    def test_rest_exchange_dollar_value_survives_without_stream_message(self):
        # If the public market response includes dollar_volume, use that actual
        # exchange value even when the WebSocket has not produced a ticker.
        baseline = [{"ticker": "X", "exchange_dollar_volume": 200.0,
                     "volume_total": 900.0}]
        out = apply_exchange_dollar_volumes(baseline, {})
        self.assertEqual(out[0]["exchange_dollar_volume"], 200.0)
        self.assertEqual(out[0]["volume_total"], 900.0)

    def test_recent_websocket_message_overrides_rest_dollars(self):
        baseline = [{"ticker": "X", "exchange_dollar_volume": 200.0}]
        updates = {"X": {"seen_at": time.time(), "data": {"dollar_volume": 250}}}
        out = apply_exchange_dollar_volumes(baseline, updates)
        self.assertEqual(out[0]["exchange_dollar_volume"], 250.0)

    def test_websocket_messages_store_only_tennis(self):
        feed = LiveTicker.__new__(LiveTicker)
        import threading
        feed._lock = threading.Lock()
        feed._latest = {}
        feed._last_message = None
        feed._status = "connecting"
        feed._error = None
        feed._on_message(None, '{"type":"ticker","msg":{"market_ticker":"KXATPMATCH-123","volume_fp":"220.00"}}')
        feed._on_message(None, '{"type":"ticker","msg":{"market_ticker":"OTHER-123","volume_fp":"400.00"}}')
        self.assertEqual(len(feed.snapshot()[0]), 1)
        self.assertEqual(feed.snapshot()[0]["KXATPMATCH-123"]["data"]["volume_fp"], "220.00")


if __name__ == "__main__":
    unittest.main()
