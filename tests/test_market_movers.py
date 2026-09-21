import unittest
import queue
import time

from datetime import timezone

import pandas as pd

from market_movers import MarketMoverWorker, _latest_intraday, analyze_mover_opportunity


class MarketMoverAnalysisTests(unittest.TestCase):
    def values(self, status, price, buy=100):
        return {
            "signal_ready": True,
            "status": status,
            "price": price,
            "buy_point": buy,
            "stop_point": 90,
        }

    def test_direct_buy_near_wait_and_avoid_labels(self):
        self.assertEqual(analyze_mover_opportunity(self.values("BUY_ALERT", 101))[1], "BUY")
        self.assertEqual(analyze_mover_opportunity(self.values("BUY_ALERT", 104))[1], "EXTENDED")
        self.assertEqual(analyze_mover_opportunity(self.values("WATCH", 99))[1], "NEAR")
        self.assertEqual(analyze_mover_opportunity(self.values("WATCH", 90))[1], "WAIT")
        self.assertEqual(analyze_mover_opportunity(self.values("SELL_ALERT", 89))[1], "AVOID")

    def test_short_history_is_observation_only(self):
        text, tag = analyze_mover_opportunity({"signal_ready": False})
        self.assertEqual(tag, "OBSERVE")
        self.assertIn("历史不足", text)

    def test_latest_intraday_uses_newest_close_and_timestamp(self):
        index = pd.to_datetime(["2026-09-21T14:30:00Z", "2026-09-21T14:31:00Z"])
        columns = pd.MultiIndex.from_product([["AAPL"], ["Close", "High"]])
        data = pd.DataFrame([[100.0, 101.0], [102.5, 103.0]], index=index, columns=columns)
        price, stamp = _latest_intraday(data, "AAPL")
        self.assertEqual(price, 102.5)
        self.assertEqual(stamp.tzinfo, timezone.utc)

    def test_manual_refresh_wakes_worker_without_waiting_for_interval(self):
        events = queue.Queue()

        class Scanner:
            calls = 0

            def scan(self):
                self.calls += 1
                return [], []

        worker = MarketMoverWorker(events, interval_seconds=60)
        worker.scanner = Scanner()
        worker.start()

        def wait_for_result():
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                event = events.get(timeout=max(0.01, deadline - time.monotonic()))
                if event[0] == "mover_results":
                    return
            self.fail("没有收到涨跌榜刷新结果")

        try:
            wait_for_result()
            worker.refresh()
            wait_for_result()
            self.assertGreaterEqual(worker.scanner.calls, 2)
        finally:
            worker.stop()
            worker.join(2)


if __name__ == "__main__":
    unittest.main()
