"""Tests for exchange event volume reconciliation (no network requests)."""
import unittest
from unittest.mock import Mock

from volume_reconcile import get_event_snapshot, reconciliation_report, whole_dollars


class VolumeReconciliationTests(unittest.TestCase):
    def test_fetch_event_uses_official_endpoint(self):
        session = Mock()
        session.get.return_value.json.return_value = {
            "event": {"event_ticker": "KXATPCHALLENGERMATCH-26NOV22ONOJON",
                      "markets": [{"ticker": "ONO", "volume_fp": "120.00"}]}
        }
        snapshot = get_event_snapshot("KXATPCHALLENGERMATCH-26NOV22ONOJON", session=session)
        self.assertEqual(len(snapshot["markets"]), 1)
        self.assertIn("/events/KXATPCHALLENGERMATCH-26NOV22ONOJON",
                      session.get.call_args.args[0])
        self.assertEqual(session.get.call_args.kwargs["params"]["with_nested_markets"], "true")

    def test_distinct_market_totals_and_snapshot_comparison(self):
        snapshot = {
            "event": {"event_ticker": "EXAMPLE"},
            "retrieved_at": "2026-11-23T07:00:00+00:00",
            "markets": [
                {"ticker": "P1", "yes_sub_title": "Player 1",
                 "volume_fp": "500.00", "volume_24h_fp": "50.00"},
                {"ticker": "P2", "yes_sub_title": "Player 2",
                 "volume_fp": "600.00", "volume_24h_fp": "70.00"},
                {"ticker": "P2", "volume_fp": "600.00"},
            ]
        }
        report = reconciliation_report(snapshot, 1100)
        self.assertEqual(report["sum"], 1100)
        self.assertEqual(report["largest"], 600)
        self.assertEqual(report["count"], 2)
        self.assertTrue(report["matches_sum"])
        self.assertIsNone(report["published_event_volume"])

    def test_missing_volume_not_assumed_zero(self):
        report = reconciliation_report({
            "event": {}, "markets": [
                {"ticker": "P1", "volume_fp": "4.00"},
                {"ticker": "P2", "volume_fp": None},
            ]
        }, 4)
        self.assertIsNone(report["sum"])
        self.assertIsNone(report["difference"])
        self.assertEqual(whole_dollars(report["sum"]), "N/A")

    def test_published_event_total_if_present(self):
        report = reconciliation_report({
            "event": {"volume_fp": "125.00"},
            "markets": [{"ticker": "P1", "volume_fp": "250.00"}],
        })
        self.assertEqual(report["published_event_volume"], 125)
        self.assertEqual(report["sum"], 250)

    def test_whole_dollars(self):
        self.assertEqual(whole_dollars(1034701.25), "$1,034,701")
        self.assertEqual(whole_dollars(None), "N/A")


if __name__ == "__main__":
    unittest.main()
