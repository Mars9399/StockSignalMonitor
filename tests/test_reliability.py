import ast
import __future__
import json
import math
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reliability import observation_reason, initialize_risk_baseline
from tws_positions import merge_positions

ROOT = Path(__file__).resolve().parents[1]


def compile_position_planner():
    """Compile the extracted planner with the source file's annotation semantics."""
    module = ast.parse((ROOT / 'signal_monitor_gui.py').read_text(encoding='utf-8'))
    function = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == 'build_position_plan'
    )
    scope = {'math': math}
    code = compile(
        ast.Module(body=[function], type_ignores=[]),
        '<production planner>',
        'exec',
        flags=__future__.annotations.compiler_flag,
    )
    exec(code, scope)
    return scope['build_position_plan']


class ReliabilityTests(unittest.TestCase):
    def test_automatic_baseline_is_fixed_and_gated(self):
        for cost in (60, 150):
            position = dict(quantity=0.5, avg_cost=cost)
            self.assertEqual(initialize_risk_baseline(position, 100, 5, False), position)
            for atr in (0, -1, 60, float('nan')):
                self.assertEqual(initialize_risk_baseline(position, 100, atr, True), position)
            initialized = initialize_risk_baseline(position, 100, 5, True)
            self.assertEqual(initialized['initial_stop'], 90)
            self.assertEqual(initialized['risk_reference_price'], 100)
            restored = json.loads(json.dumps(initialized))
            self.assertEqual(initialize_risk_baseline(restored, 80, 10, True), initialized)
            planner = compile_position_planner()
            plan = planner(dict(signal_ready=True, price=80, atr14=10,
                buy_point=110, stop_point=70, sma50=70, status='NO_SIGNAL'), restored, 100000, 1, 10)
            self.assertEqual(plan['position_stop'], 90)
            self.assertEqual(plan['target_2r'], 0)
            self.assertEqual(plan['target_3r'], 0)
            self.assertIn('卖出提示', plan['action'])

    def test_incomplete_day_is_excluded(self):
        try:
            import pandas as pd
            from signal_monitor import calculate_levels
        except ImportError:
            self.skipTest('Market data dependencies installed on Windows CI')
        from reliability import NEW_YORK
        today = datetime.now(NEW_YORK).date()
        frame = pd.DataFrame(dict(high=[101.0]*40+[999.0], low=[99.0]*41, close=[100.0]*41),
                             index=pd.date_range(end=today, periods=41))
        levels = calculate_levels(frame, 100)
        self.assertEqual(levels['history_days'], 40)
        self.assertEqual(levels['buy_point'], 101)
        self.assertLess(levels['history_date'], today.isoformat())

    def test_same_scenarios_as_swift(self):
        # Compile the actual pure planner without importing Tk or starting a UI.
        planner = compile_position_planner()
        scenarios = json.loads((ROOT / 'apple/Tests/SharedTests/Fixtures/reliability.json').read_text())
        for s in scenarios:
            values = dict(signal_ready=True, price=s['price'], buy_point=110, stop_point=100,
                          atr14=5, sma50=70, status=s['status'])
            plan = planner(values, dict(quantity=s['quantity'], avg_cost=100,
                                        initial_stop=s['stop']), 100000, 1, 10)
            self.assertEqual(plan['position_stop'], s['riskLine'])
            self.assertEqual(plan['target_2r'], s['target2'])
            self.assertEqual(plan['target_3r'], s['target3'])
            text = {'sell':'卖出提示', 'buy':'买入提示', 'hold':'持有'}[s['action']]
            self.assertIn(text, plan['action'])

    def test_fresh_stale_missing_and_weekend(self):
        now = datetime(2026, 9, 11, 15, tzinfo=timezone.utc)
        self.assertIsNone(observation_reason(100, now, '2026-09-10', now))
        self.assertIsNotNone(observation_reason(100, now-timedelta(seconds=181), '2026-09-10', now))
        self.assertIsNotNone(observation_reason(100, None, '2026-09-10', now))
        self.assertIsNone(observation_reason(100, now, '2026-09-09', now))
        self.assertIsNotNone(observation_reason(100, now, '2026-09-06', now))
        weekend = now+timedelta(days=1)
        self.assertIsNotNone(observation_reason(100, weekend, '2026-09-11', weekend))

    def test_sync_preserves_or_invalidates_risk_baseline(self):
        current = {'TEST':dict(quantity=0.5, avg_cost=100, initial_stop=90, risk_reference_price=110)}
        snapshot = dict(symbol='TEST', quantity=0.5, avg_cost=100, account='test', security_type='STK', currency='USD')
        result, _, _ = merge_positions(current, [snapshot], ['TEST'])
        self.assertEqual(result['TEST']['initial_stop'], 90)
        self.assertEqual(result['TEST']['risk_reference_price'], 110)
        snapshot['quantity'] = 1
        result, _, _ = merge_positions(current, [snapshot], ['TEST'])
        self.assertNotIn('initial_stop', result['TEST'])
        self.assertNotIn('risk_reference_price', result['TEST'])
