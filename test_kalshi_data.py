"""Unit tests for public Kalshi market-data helpers; no network required."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from kalshi_data import get_market, get_orderbook, get_trades, get_candlesticks, orderbook_rows, candle_rows


class TestPublicMarketData(unittest.TestCase):
    def make_session(self, payload):
        session = Mock()
        response = session.get.return_value
        response.json.return_value = payload
        return session

    def test_market_info(self):
        session = self.make_session({"market": {"ticker": "TEST"}})
        self.assertEqual(get_market("TEST", session=session)["ticker"], "TEST")
        session.get.assert_called_once()

    def test_orderbook_levels_and_inverse_ask(self):
        session = self.make_session({"orderbook_fp": {"yes_dollars": [["0.3200", "25.00"]], "no_dollars": [["0.6500", "8.00"]]}})
        book = get_orderbook("TEST", depth=5, session=session)
        levels = orderbook_rows(book)
        self.assertEqual(len(levels), 2)
        self.assertEqual(levels[0]["Bid (¢)"], 65.0)
        self.assertEqual(levels[0]["Implied opposite ask (¢)"], 35.0)
        self.assertEqual(levels[1]["Quantity"], 25.0)

    def test_trades_filtered_by_ticker(self):
        session = self.make_session({"trades": [{"ticker": "TEST", "count_fp": "2.00"}]})
        trades = get_trades("TEST", session=session)
        self.assertEqual(len(trades), 1)
        self.assertEqual(session.get.call_args.kwargs["params"]["ticker"], "TEST")

    def test_candles_from_known_series(self):
        session = self.make_session({"candlesticks": [{"end_period_ts": 1730000000, "volume_fp": "3.00",
                                                        "yes_bid": {"close_dollars": "0.4000"}}]})
        candles = get_candlesticks("TEST", "ATP", days=2, period_minutes=60, session=session,
                                  now=datetime(2026, 11, 23, tzinfo=timezone.utc))
        self.assertEqual(candle_rows(candles)[0]["YES bid close (¢)"], 40.0)
        self.assertEqual(session.get.call_args.kwargs["params"]["period_interval"], 60)

    def test_invalid_candle_window(self):
        with self.assertRaises(ValueError):
            get_candlesticks("TEST", "ATP", days=7, period_minutes=1)
        with self.assertRaises(ValueError):
            get_candlesticks("TEST", "unknown", days=1)


if __name__ == "__main__":
    unittest.main()
