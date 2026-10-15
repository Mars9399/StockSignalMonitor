"""Unit tests for P0–P3 optimization modules."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from explain import explain_suggestion
from monitor_settings import DEFAULT_MONITOR_SETTINGS, read_monitor_settings, write_monitor_settings
from portfolio_insights import build_portfolio_insight
from reliability import initialize_risk_baseline
from signal_filters import apply_signal_filters, feed_profile_label
from signal_replay import replay_alerts
from suggestion import build_suggestion


class MonitorSettingsTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monitor_settings.json"
            write_monitor_settings(path, {"filter_volume_enabled": True, "atr_stop_multiplier": 1.5})
            loaded = read_monitor_settings(path)
            self.assertTrue(loaded["filter_volume_enabled"])
            self.assertEqual(loaded["atr_stop_multiplier"], 1.5)
            self.assertFalse(loaded["filter_relative_strength_enabled"])


class SignalFilterTests(unittest.TestCase):
    def base(self, **overrides):
        values = {
            "signal_ready": True,
            "status": "BUY_ALERT",
            "price": 101.0,
            "buy_point": 100.0,
            "stop_point": 90.0,
            "volume_ratio": 0.8,
            "rsi14": 55,
        }
        values.update(overrides)
        return values

    def test_filters_off_keep_buy(self):
        result = apply_signal_filters(self.base(), DEFAULT_MONITOR_SETTINGS)
        self.assertEqual(result["status"], "BUY_ALERT")
        self.assertFalse(result["filter_suppressed"])

    def test_volume_filter_demotes(self):
        settings = dict(DEFAULT_MONITOR_SETTINGS, filter_volume_enabled=True, filter_volume_min_ratio=1.15)
        result = apply_signal_filters(self.base(), settings)
        self.assertEqual(result["status"], "WATCH")
        self.assertTrue(result["filter_suppressed"])
        self.assertEqual(result["raw_status"], "BUY_ALERT")

    def test_relative_strength_filter(self):
        settings = dict(DEFAULT_MONITOR_SETTINGS, filter_relative_strength_enabled=True)
        result = apply_signal_filters(
            self.base(volume_ratio=2.0),
            settings,
            symbol_change_pct=-1.0,
            benchmark_change_pct=0.5,
        )
        self.assertTrue(result["filter_suppressed"])

    def test_feed_profile(self):
        label = feed_profile_label("Alpaca IEX", 2.0)
        self.assertIn("IEX", label)


class SuggestionTests(unittest.TestCase):
    def test_primary_buy_suggestion(self):
        values = {
            "signal_ready": True,
            "status": "BUY_ALERT",
            "raw_status": "BUY_ALERT",
            "price": 101,
            "buy_point": 100,
            "stop_point": 90,
            "volume_ratio": 1.4,
            "rsi14": 60,
            "history_date": "2026-10-14",
            "filter_suppressed": False,
            "breakout_extension_pct": 1.0,
        }
        suggestion = build_suggestion(
            "AAPL",
            values,
            {"buy_probability": 72, "reduce_probability": 0, "buy_label": "中高", "reduce_label": "无持仓"},
            {"action": "买入提示：参考上限 10 股"},
            feed_profile="Alpaca IEX · 约 1s",
            quote_age_seconds=1,
            provider="Alpaca IEX",
        )
        self.assertEqual(suggestion.side, "buy")
        self.assertEqual(suggestion.alert_tier, "primary")
        self.assertIn("不构成投资建议", suggestion.disclaimer)
        text = explain_suggestion(suggestion, use_llm=False)
        self.assertIn("AAPL", text)


class PortfolioInsightTests(unittest.TestCase):
    def test_overweight_hint(self):
        insight = build_portfolio_insight(
            {"AAPL": {"quantity": 100, "avg_cost": 100}},
            {"AAPL": {"price": 200}},
            account_value=10_000,
            max_position_pct=10,
            available_funds=100,
        )
        self.assertTrue(insight.overweight)
        self.assertIn("超配", insight.rebalance_hints[0])


class ProtectionAndReplayTests(unittest.TestCase):
    def test_atr_multiplier(self):
        position = {"quantity": 10, "avg_cost": 100}
        updated = initialize_risk_baseline(position, 100, 5, True, atr_multiplier=1.5)
        self.assertAlmostEqual(updated["initial_stop"], 100 - 1.5 * 5)

    def test_replay_missing_file(self):
        summary = replay_alerts(Path("/tmp/does-not-exist-alerts.csv"))
        self.assertEqual(summary.total_alerts, 0)


if __name__ == "__main__":
    unittest.main()
