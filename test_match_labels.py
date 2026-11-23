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

    def test_lifetime_volume_matches_kalshi_style(self):
        groups = {
            "ONOJON": [
                {"ticker": "ONO", "volume_total": 517350},
                {"ticker": "JONES", "volume_total": 517351},
            ],
            "LOW": [{"ticker": "L1", "volume_total": 15000}],
        }
        self.assertEqual(ranked_event_volumes(groups),
                         [("ONOJON", 1034701.0), ("LOW", 15000.0)])
        self.assertEqual(format_notional_volume(1034701), "$1,034,701")

    def test_24h_volume_does_not_drive_lifetime_ranking(self):
        groups = {
            "A": [{"ticker": "A1", "volume_total": 100000, "volume_24h": 20}],
            "B": [{"ticker": "B1", "volume_total": 1000, "volume_24h": 1000}],
        }
        self.assertEqual(ranked_event_volumes(groups), [("A", 100000.0), ("B", 1000.0)])

    def test_duplicate_market_ticker_does_not_inflate_total(self):
        groups = {"A": [
            {"ticker": "A1", "volume_total": 100},
            {"ticker": "A1", "volume_total": 100},
            {"ticker": "A2", "volume_total": 50},
        ]}
        self.assertEqual(ranked_event_volumes(groups), [("A", 150.0)])

    def test_missing_volume_unknown_and_sort_last(self):
        groups = {
            "UNKNOWN": [{"ticker": "A", "volume_total": None}],
            "PARTIAL": [{"ticker": "B1", "volume_total": 2}, {"ticker": "B2", "volume_total": None}],
            "KNOWN": [{"ticker": "C", "volume_total": 0}],
        }
        self.assertEqual(ranked_event_volumes(groups),
                         [("KNOWN", 0.0), ("PARTIAL", None), ("UNKNOWN", None)])
        self.assertEqual(format_notional_volume(None), "N/A")

    def test_volume_has_no_cents(self):
        self.assertEqual(format_notional_volume(1200.25), "$1,200")
        self.assertEqual(format_notional_volume(1200.0), "$1,200")

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
