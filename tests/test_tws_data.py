import unittest
from datetime import timezone

from tws_data import _bar_time, auxiliary_client_id


class TWSDataTests(unittest.TestCase):
    def test_auxiliary_client_ids_are_distinct_and_valid(self):
        self.assertEqual(auxiliary_client_id(17, 101), 118)
        self.assertNotEqual(auxiliary_client_id(17, 101), auxiliary_client_id(17, 201))
        self.assertGreaterEqual(auxiliary_client_id(-1, 1), 0)

    def test_epoch_bar_time_is_utc(self):
        parsed = _bar_time("1789999200")
        self.assertEqual(parsed.tzinfo, timezone.utc)
