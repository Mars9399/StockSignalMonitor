import unittest

from signal_monitor import estimate_action_probabilities


class ActionProbabilityTests(unittest.TestCase):
    @staticmethod
    def values(**overrides):
        values = {
            "signal_ready": True,
            "status": "WATCH",
            "price": 99.0,
            "buy_point": 100.0,
            "stop_point": 90.0,
            "atr14": 2.0,
            "trend_fast": 97.0,
            "trend_slow": 95.0,
            "momentum_5d_pct": 3.0,
            "momentum_10d_pct": 5.0,
            "rsi14": 60.0,
            "volume_ratio": 1.3,
        }
        values.update(overrides)
        return values

    def test_strong_breakout_scores_above_weak_downtrend(self):
        strong = estimate_action_probabilities(
            self.values(status="BUY_ALERT", price=101.0), {}, 100_000, 10, 20_000, 50_000
        )
        weak = estimate_action_probabilities(
            self.values(
                price=91.0,
                trend_fast=98.0,
                trend_slow=100.0,
                momentum_5d_pct=-5.0,
                momentum_10d_pct=-8.0,
                rsi14=30.0,
                volume_ratio=0.4,
            ),
            {}, 100_000, 10, 20_000, 50_000,
        )
        self.assertGreater(strong["buy_probability"], weak["buy_probability"])
        self.assertEqual(strong["reduce_probability"], 0)

    def test_broken_stop_for_held_position_forces_high_reduction_score(self):
        result = estimate_action_probabilities(
            self.values(
                status="SELL_ALERT",
                price=88.0,
                trend_fast=96.0,
                trend_slow=99.0,
                momentum_5d_pct=-6.0,
                momentum_10d_pct=-9.0,
            ),
            {"quantity": 100, "avg_cost": 100, "initial_stop": 92},
            100_000,
            10,
            95_000,
            3_000,
        )
        self.assertGreaterEqual(result["reduce_probability"], 90)
        self.assertLessEqual(result["buy_probability"], 10)

    def test_account_allocation_reduces_buy_score_and_raises_reduce_score(self):
        values = self.values(status="BUY_ALERT", price=101.0)
        light = estimate_action_probabilities(
            values, {"quantity": 10, "avg_cost": 95}, 100_000, 10, 20_000, 50_000
        )
        heavy = estimate_action_probabilities(
            values, {"quantity": 150, "avg_cost": 95}, 100_000, 10, 95_000, 3_000
        )
        self.assertLess(heavy["buy_probability"], light["buy_probability"])
        self.assertGreater(heavy["reduce_probability"], light["reduce_probability"])

    def test_short_history_returns_zero_scores(self):
        result = estimate_action_probabilities(
            {"signal_ready": False}, {}, 100_000, 10
        )
        self.assertEqual(result["buy_probability"], 0)
        self.assertEqual(result["reduce_probability"], 0)


if __name__ == "__main__":
    unittest.main()
