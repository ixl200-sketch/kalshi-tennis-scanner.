"""Tests for tournament/match display labels; API calls are mocked."""
import unittest
from unittest.mock import Mock

from match_labels import event_labels, fetch_event_metadata, player_name


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
