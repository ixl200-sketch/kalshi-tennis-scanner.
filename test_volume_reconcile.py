"""Contract-volume source checks without network requests."""
import unittest
from volume_reconcile import reconciliation_report, whole_dollars


class VolumeSourceTests(unittest.TestCase):
    def test_doubled_markets_must_not_be_called_website_volume(self):
        report = reconciliation_report({
            "event": {"event_ticker": "KXATPCHALLENGERMATCH-26NOV23HUESCH"},
            "markets": [
                {"ticker": "PINO", "volume_fp": "660000", "volume_24h_fp": "100"},
                {"ticker": "SCH", "volume_fp": "660000", "volume_24h_fp": "100"},
            ],
        }, 662768)
        self.assertEqual(report["reference"], 662768)
        self.assertEqual(report["sum"], 1320000)
        self.assertFalse(report["matches_sum"])
        self.assertIsNone(report["published_event_volume"])

    def test_missing_volume_is_unavailable(self):
        report = reconciliation_report({
            "event": {},
            "markets": [{"ticker": "PINO", "volume_fp": "100"},
                        {"ticker": "SCH", "volume_fp": None}],
        })
        self.assertIsNone(report["sum"])
        self.assertEqual(whole_dollars(report["sum"]), "N/A")

    def test_whole_dollars(self):
        self.assertEqual(whole_dollars(662768), "$662,768")


if __name__ == "__main__":
    unittest.main()
