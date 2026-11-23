"""Tests for tournament/match display labels; API calls are mocked."""
import unittest
from unittest.mock import Mock

from match_labels import event_labels, fetch_event_metadata, player_name, ranked_event_volumes, format_notional_volume


class MatchupLabelsTests(unittest.TestCase):
    def setUp(self):
        self.markets = [
            {"ticker": "MARKET-A", "event_ticker": "EVENT-1", "tour": "ATP",
             "title": "Alex Rivera wins", "yes_label": "Alex Rivera"},
            {"ticker": "MARKET-B", "event_ticker": "EVENT-1", "tour": "ATP",
             "title": "Jordan Chen wins", "yes_label": "Jordan Chen"},
        ]

    def test_tournament_and_two_players(self):
        events = {"EVENT-1": {"title": "Alex Rivera vs. Jordan Chen",
                              "sub_title": "Example Open"}}
        self.assertEqual(event_labels(self.markets, events)["EVENT-1"],
                         "Example Open | Alex Rivera vs. Jordan Chen")

    def test_fallback_when_tournament_missing(self):
        self.assertEqual(event_labels(self.markets)["EVENT-1"],
                         "ATP | Alex Rivera vs. Jordan Chen")

    def test_clean_outcome(self):
        self.assertEqual(player_name("Alex Rivera wins"), "Alex Rivera")

    def test_volume_aggregation_and_sort_order(self):
        groups = {
            "LOW": [{"ticker": "L1", "volume_24h": 125}, {"ticker": "L2", "volume_24h": 100}],
            "HIGH": [{"ticker": "H1", "volume_24h": 500}, {"ticker": "H2", "volume_24h": 480}],
            "MID": [{"ticker": "M1", "volume_24h": 250}],
        }
        self.assertEqual(ranked_event_volumes(groups),
                         [("HIGH", 980.0), ("MID", 250.0), ("LOW", 225.0)])

    def test_duplicate_tickers_not_double_counted(self):
        groups = {"X": [
            {"ticker": "ONE", "volume_24h": 100},
            {"ticker": "ONE", "volume_24h": 100},
            {"ticker": "TWO", "volume_24h": 50},
        ]}
        self.assertEqual(ranked_event_volumes(groups), [("X", 150.0)])

    def test_missing_volume_is_unknown_not_zero(self):
        groups = {
            "B": [{"ticker": "B1", "volume_24h": None}],
            "A": [{"ticker": "A1", "volume_24h": "nan"}],
            "C": [{"ticker": "C1", "volume_24h": 10}, {"ticker": "C2", "volume_24h": None}],
            "D": [{"ticker": "D1", "volume_24h": 0}],
        }
        self.assertEqual(ranked_event_volumes(groups),
                         [("D", 0.0), ("A", None), ("B", None), ("C", None)])

    def test_fractional_kalshi_volume_formatting(self):
        self.assertEqual(format_notional_volume(1200.25), "$1,200.25")
        self.assertEqual(format_notional_volume(1200), "$1,200")
        self.assertEqual(format_notional_volume(None), "N/A")

    def test_event_fetch(self):
        session = Mock()
        session.get.return_value.json.return_value = {
            "events": [{"event_ticker": "EVENT-1", "title": "Alex Rivera vs Jordan Chen"}],
            "cursor": None,
        }
        metadata = fetch_event_metadata(["ATP"], session=session)
        self.assertIn("EVENT-1", metadata)
        self.assertEqual(session.get.call_args.kwargs["params"]["series_ticker"], "KXATPMATCH")


if __name__ == "__main__":
    unittest.main()
