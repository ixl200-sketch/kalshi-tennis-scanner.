"""Tests for tournament/match display labels; API calls are mocked."""
import unittest
from unittest.mock import Mock

from match_labels import event_labels, fetch_event_metadata, player_name, ranked_event_volumes


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

    def test_volume_order_and_max_per_event(self):
        groups = {
            "LOW": [{"volume_24h": 125}, {"volume_24h": 100}],
            "HIGH": [{"volume_24h": 500}, {"volume_24h": 480}],
            "MID": [{"volume_24h": 250}],
        }
        # HIGH is 500, not 980 (two separate player contracts).
        self.assertEqual(ranked_event_volumes(groups),
                         [("HIGH", 500.0), ("MID", 250.0), ("LOW", 125.0)])

    def test_volume_missing_invalid_and_tie_order(self):
        groups = {
            "B": [{"volume_24h": None}],
            "A": [{"volume_24h": "nan"}, {"volume_24h": -5}],
            "C": [{"volume_24h": "bad"}],
        }
        self.assertEqual(ranked_event_volumes(groups),
                         [("A", 0.0), ("B", 0.0), ("C", 0.0)])

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
