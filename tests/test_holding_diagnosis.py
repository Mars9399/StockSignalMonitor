"""Holding diagnosis engine: scenarios, cross-platform fixture and offline guarantees."""

from __future__ import annotations

import ast
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from explain import explain_diagnosis
from holding_diagnosis import (
    DISCLAIMER,
    DiagnosisContext,
    DiagnosisSettings,
    HoldingMetrics,
    context_symbols,
    diagnose_holding,
    diagnose_portfolio,
)
from monitor_settings import read_monitor_settings, write_monitor_settings
from sector_map import SECTOR_ETF_NAMES, SECTOR_MAP
from signal_monitor import calculate_levels

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "apple/Tests/SharedTests/Fixtures/holding_diagnosis.json").read_text(encoding="utf-8"))
TOLERANCE = 0.011


def settings() -> DiagnosisSettings:
    return DiagnosisSettings.from_configs(FIXTURE["settings"], FIXTURE["settings"])


def run_case(case: dict, **holding_overrides):
    context = DiagnosisContext(
        market=HoldingMetrics.from_dict(case["market"]) if case.get("market") else None,
        sector=HoldingMetrics.from_dict(case["sector"]) if case.get("sector") else None,
        peers={key: HoldingMetrics.from_dict(value) for key, value in case.get("peers", {}).items()},
        earnings_days=case.get("earnings_days"),
        leverage_pct=case.get("leverage_pct"),
    )
    holding = dict(case["holding"], **holding_overrides)
    return diagnose_holding(case["symbol"], holding, HoldingMetrics.from_dict(case["metrics"]), context, settings())


def case(name: str) -> dict:
    return next(item for item in FIXTURE["cases"] if item["name"] == name)


def run_portfolio(data: dict, portfolio_settings: DiagnosisSettings | None = None, **kwargs):
    return diagnose_portfolio(
        data["positions"],
        {key: HoldingMetrics.from_dict(value) for key, value in data["metrics"].items()},
        portfolio_settings or settings(),
        benchmark_symbol=data["benchmark_symbol"],
        earnings_days=data["earnings_days"],
        **kwargs,
    )


def leveraged_settings() -> DiagnosisSettings:
    data = FIXTURE["leveraged_portfolio"]["settings"]
    return DiagnosisSettings.from_configs(data, data)


class ScenarioTests(unittest.TestCase):
    def test_idiosyncratic_breakdown_loss_recommends_exit(self):
        result = run_case(case("idio_breakdown_loss"))
        self.assertEqual(result.mode, "loss")
        self.assertEqual(result.trend_state, "broken")
        self.assertEqual(result.loss_source, "idio")
        self.assertEqual(result.recommended, "stop_exit")
        self.assertFalse(result.plan("average_down").allowed)
        self.assertIn("破位", result.plan("average_down").blocked_reason)
        switch = result.plan("switch")
        self.assertTrue(switch.allowed)
        self.assertEqual(switch.target_symbol, "MSFT")
        self.assertIn("跌破前低", "；".join(result.trend_flags))

    def test_market_pullback_small_loss_holds_and_allows_average_down(self):
        result = run_case(case("market_pullback_small_loss"))
        self.assertEqual(result.trend_state, "intact")
        self.assertEqual(result.loss_source, "market")
        self.assertEqual(result.recommended, "hold_watch")
        self.assertEqual(result.non_sell_plan, "hold_watch")
        self.assertEqual(result.watch_line, 380.0)  # MA50 soft watch above hard stop
        self.assertEqual(result.hard_stop, 375.0)
        self.assertEqual(result.watch_days, 10)
        hold = result.plan("hold_watch")
        self.assertIn("观察线", hold.trigger)
        self.assertIn("硬止损", hold.trigger)
        self.assertEqual(len(hold.steps), 2)
        add = result.plan("average_down")
        self.assertTrue(add.allowed)
        # First tranche at MA50; sized by single-stock headroom → 5 shares.
        self.assertEqual(add.price, 380.0)
        self.assertEqual(add.quantity_change, 5)
        self.assertEqual(add.steps[0]["price"], 380.0)
        self.assertAlmostEqual(add.avg_cost_after, (400 * 20 + 380 * 5) / 25)
        self.assertAlmostEqual(add.worst_loss, (390 - 375) * 20 + (380 - 375) * 5)
        self.assertAlmostEqual(add.budget_pct, add.worst_loss / 1000 * 100)

    def test_intact_small_loss_without_recent_weakness(self):
        result = run_case(case("intact_small_loss_cost_basis"))
        self.assertEqual(result.loss_source, "cost")
        self.assertEqual(result.recommended, "hold_watch")
        self.assertTrue(result.plan("average_down").allowed)

    def test_large_profit_overbought_scales_out_with_trailing_stop(self):
        result = run_case(case("large_profit_overbought"))
        self.assertEqual(result.mode, "profit")
        self.assertEqual(result.recommended, "scale_out")
        self.assertEqual(result.stop, 670.0)  # price - 2*ATR beats channel low and breakeven.
        self.assertTrue(result.overweight)
        self.assertFalse(result.plan("add_on_strength").allowed)
        scale = result.plan("scale_out")
        self.assertEqual(scale.quantity_change, -5)
        self.assertAlmostEqual(scale.realized_pnl, (700 - 500) * 5)

    def test_overweight_over_budget_reduces(self):
        result = run_case(case("overweight_over_budget_loss"))
        self.assertGreater(result.budget_ratio, 1.0)
        self.assertEqual(result.recommended, "reduce_risk")
        reduce = result.plan("reduce_risk")
        self.assertEqual(reduce.quantity_after, 30)
        self.assertLessEqual(reduce.worst_loss, result.position_budget)

    def test_earnings_and_max_adds_block_average_down(self):
        earnings = run_case(case("earnings_blocks_average_down"))
        self.assertTrue(earnings.event_near)
        self.assertIn("财报", earnings.plan("average_down").blocked_reason)
        self.assertIn("hold_watch", [item["target"] for item in earnings.switch_conditions])
        maxed = run_case(case("max_average_down_reached"))
        self.assertIn("上限", maxed.plan("average_down").blocked_reason)

    def test_short_history_only_hold_or_exit(self):
        result = run_case(case("short_history_observe"))
        self.assertFalse(result.data_ready)
        allowed = {plan.id for plan in result.plans if plan.allowed}
        self.assertEqual(allowed, {"stop_exit", "hold_watch"})

    def test_protective_stop_hit_prefers_exit(self):
        result = run_case(case("protective_stop_hit"))
        self.assertTrue(result.stop_hit)
        self.assertEqual(result.recommended, "stop_exit")

    def test_sector_drag_and_rally_reduce_level(self):
        result = run_case(case("sector_drag_weakening_loss"))
        self.assertEqual(result.loss_source, "sector")
        self.assertEqual(result.recommended, "rally_reduce")
        self.assertEqual(result.plan("rally_reduce").price, 115.0)

    def test_saved_stop_beats_channel_low_hugging_price(self):
        result = run_portfolio(FIXTURE["leveraged_portfolio"], leveraged_settings())
        mu = next(item for item in result.holdings if item.symbol == "MU")
        self.assertEqual(mu.stop_basis, "已保存保护线")
        self.assertEqual(mu.stop, 123.2)
        self.assertIn("观察线", mu.plan("hold_watch").trigger)
        # No MA200 yet: below MA50 alone is weakening, not broken.
        self.assertEqual(mu.trend_state, "weakening")


class LeverageTests(unittest.TestCase):
    def test_over_leverage_blocks_buying_plans(self):
        result = run_case(case("over_leveraged_blocks_average_down"))
        self.assertTrue(result.over_leveraged)
        self.assertFalse(result.plan("average_down").allowed)
        self.assertIn("先降杠杆", result.plan("average_down").blocked_reason)
        self.assertIn("先降杠杆", result.plan("switch").blocked_reason)
        self.assertTrue(run_case(case("market_pullback_small_loss")).plan("average_down").allowed)

    def test_over_leverage_blocks_add_on_strength_and_switch(self):
        source = case("idio_breakdown_loss")
        result = run_case(dict(source, leverage_pct=120.0))
        self.assertFalse(result.plan("switch").allowed)
        self.assertNotEqual(result.recommended, "switch")
        profit = run_case(dict(case("profit_trend_intact"), leverage_pct=150.0))
        self.assertFalse(profit.plan("add_on_strength").allowed)
        self.assertIn("先降杠杆", profit.plan("add_on_strength").blocked_reason)

    def test_leverage_at_limit_is_allowed(self):
        result = run_case(dict(case("market_pullback_small_loss"), leverage_pct=100.0))
        self.assertFalse(result.over_leveraged)
        self.assertTrue(result.plan("average_down").allowed)

    def test_desensitized_margin_account_matches_reference_review(self):
        result = run_portfolio(FIXTURE["leveraged_portfolio"], leveraged_settings())
        self.assertTrue(result.over_leveraged)
        self.assertGreater(result.leverage_pct, 150.0)
        self.assertEqual(
            {item.symbol: item.recommended for item in result.holdings},
            {"MU": "reduce_risk", "TXN": "stop_exit", "V": "reduce_risk", "TMO": "hold_watch"},
        )
        for item in result.holdings:
            for plan_id in ("average_down", "add_on_strength", "switch"):
                plan = item.plan(plan_id)
                if plan is not None:
                    self.assertFalse(plan.allowed, f"{item.symbol}.{plan_id}")
        self.assertTrue(result.notes[0].startswith("杠杆优先"))
        self.assertIn("不执行任何补仓/加仓/建仓", result.notes[0])
        self.assertAlmostEqual(result.deleverage_amount, 160 * 138.6 + 127 * 46.3 + 139 * 86.6 + 20 * 68.0 - 26800.0, places=1)

    def test_explicit_account_values_override_estimate(self):
        result = run_portfolio(FIXTURE["leveraged_portfolio"], leveraged_settings(),
                               net_liquidation=50000.0, gross_position_value=45000.0)
        self.assertFalse(result.over_leveraged)
        self.assertAlmostEqual(result.leverage_pct, 90.0)
        self.assertFalse(any(note.startswith("杠杆优先") for note in result.notes))

    def test_fixture_contains_no_account_identifiers(self):
        text = (ROOT / "apple/Tests/SharedTests/Fixtures/holding_diagnosis.json").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b[DU]\d{6,}\b", text))


class EdgeTests(unittest.TestCase):
    def test_empty_position_is_skipped(self):
        self.assertIsNone(run_case(case("idio_breakdown_loss"), quantity=0))

    def test_settings_are_configurable(self):
        loose = DiagnosisSettings.from_configs(
            {"account_value": 100000, "risk_pct": 1, "max_position_pct": 20},
            {"diagnosis_average_down_fraction": 0.25, "diagnosis_average_down_tranches": 1},
        )
        source = case("market_pullback_small_loss")
        context = DiagnosisContext(
            market=HoldingMetrics.from_dict(source["market"]),
            sector=HoldingMetrics.from_dict(source["sector"]),
        )
        result = diagnose_holding("MSFT", source["holding"], HoldingMetrics.from_dict(source["metrics"]), context, loose)
        self.assertEqual(result.plan("average_down").quantity_change, 5)  # 20 * 0.25
        clamped = DiagnosisSettings.from_configs({"risk_pct": 99}, {"diagnosis_max_average_down_count": -3})
        self.assertEqual(clamped.risk_pct, 10.0)
        self.assertEqual(clamped.max_average_down_count, 0)

    def test_loss_non_sell_path_quantifies_hold_and_paper_average_down(self):
        """When the user chooses not to sell: hold playbook + average-down math even if blocked."""
        data = FIXTURE["leveraged_portfolio"]
        result = run_portfolio(data, leveraged_settings())
        tmo = next(item for item in result.holdings if item.symbol == "TMO")
        self.assertEqual(tmo.mode, "loss")
        self.assertEqual(tmo.recommended, "hold_watch")
        self.assertEqual(tmo.non_sell_plan, "hold_watch")
        self.assertAlmostEqual(tmo.watch_line, 63.6, places=1)
        self.assertAlmostEqual(tmo.hard_stop, 57.3, places=1)
        self.assertEqual(tmo.watch_days, 10)
        hold = tmo.plan("hold_watch")
        self.assertIn("观察线", hold.trigger)
        self.assertIn("硬止损", hold.trigger)
        self.assertIn("观察 10 个交易日", hold.trigger)
        self.assertEqual([step["side"] for step in hold.steps], ["SELL", "SELL"])
        add = tmo.plan("average_down")
        self.assertFalse(add.allowed)
        self.assertIn("先降杠杆", add.blocked_reason)
        self.assertGreaterEqual(len(add.steps), 1)
        self.assertAlmostEqual(add.steps[0]["price"], 67.9, places=0)  # MA50 pullback
        self.assertIsNotNone(add.avg_cost_after)
        self.assertLess(add.avg_cost_after, tmo.avg_cost)
        self.assertGreater(add.worst_loss, tmo.hold_risk)
        # Sell-recommended name still exposes a non-sell hold playbook.
        txn = next(item for item in result.holdings if item.symbol == "TXN")
        self.assertEqual(txn.recommended, "stop_exit")
        self.assertEqual(txn.non_sell_plan, "hold_watch")
        self.assertIn("硬止损", txn.non_sell_summary)

    def test_settings_persist_in_monitor_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "monitor_settings.json"
            write_monitor_settings(path, {"diagnosis_portfolio_risk_pct": 4.0})
            loaded = read_monitor_settings(path)
            self.assertEqual(loaded["diagnosis_portfolio_risk_pct"], 4.0)
            self.assertEqual(loaded["diagnosis_max_average_down_count"], 2.0)

    def test_context_symbols_include_benchmark_and_sectors(self):
        symbols = context_symbols({"AAPL": {"quantity": 1}, "JPM": {"quantity": 2}, "XOM": {"quantity": 0}})
        self.assertEqual(symbols, ["SPY", "XLK", "XLF"])


class FixtureConsistencyTests(unittest.TestCase):
    """The same fixture is asserted by apple/Tests/SharedTests/HoldingDiagnosisTests.swift."""

    def assertClose(self, actual, expected, label):
        if expected is None:
            self.assertIsNone(actual, label)
        else:
            self.assertIsNotNone(actual, label)
            self.assertLessEqual(abs(float(actual) - float(expected)), TOLERANCE, label)

    def test_cases_match_fixture(self):
        for item in FIXTURE["cases"]:
            with self.subTest(item["name"]):
                result = run_case(item)
                expected = item["expected"]
                for key in ("mode", "trend_state", "loss_source", "recommended", "confidence",
                            "rs_stable", "event_near", "overweight"):
                    self.assertEqual(getattr(result, key), expected[key], key)
                self.assertClose(result.stop, expected["stop"], "stop")
                self.assertClose(result.hold_risk, expected["hold_risk"], "hold_risk")
                self.assertEqual([plan.id for plan in result.plans], expected["plan_order"])
                self.assertEqual([c["target"] for c in result.switch_conditions], expected["switch_targets"])
                for plan in result.plans:
                    want = expected["plans"][plan.id]
                    self.assertEqual(plan.allowed, want["allowed"], plan.id)
                    self.assertEqual(plan.score, want["score"], plan.id)
                    self.assertEqual(plan.target_symbol, want["target_symbol"], plan.id)
                    for key in ("price", "quantity_change", "quantity_after", "avg_cost_after", "worst_loss"):
                        self.assertClose(getattr(plan, key), want[key], f"{plan.id}.{key}")

    def assertPortfolio(self, result, expected):
        self.assertEqual({item.symbol: item.recommended for item in result.holdings}, expected["recommended"])
        self.assertClose(result.leverage_pct, expected["leverage_pct"], "leverage")
        self.assertEqual(result.over_leveraged, expected["over_leveraged"])
        self.assertClose(result.deleverage_amount, expected["deleverage_amount"], "deleverage")
        for item in result.holdings:
            want = expected["holdings"][item.symbol]
            with self.subTest(item.symbol):
                self.assertEqual(item.trend_state, want["trend_state"])
                self.assertEqual(item.over_leveraged, want["over_leveraged"])
                self.assertClose(item.stop, want["stop"], "stop")
                self.assertClose(item.rs60, want["rs60"], "rs60")
                for plan in item.plans:
                    self.assertEqual(plan.allowed, want["plans"][plan.id]["allowed"], plan.id)
                    self.assertEqual(plan.score, want["plans"][plan.id]["score"], plan.id)

    def test_leveraged_portfolio_matches_fixture(self):
        data = FIXTURE["leveraged_portfolio"]
        result = run_portfolio(data, leveraged_settings())
        self.assertPortfolio(result, data["expected"])
        self.assertEqual(len(result.notes), data["expected"]["note_count"])

    def test_portfolio_matches_fixture(self):
        data = FIXTURE["portfolio"]
        result = run_portfolio(data)
        expected = data["expected"]
        self.assertPortfolio(result, expected)
        self.assertEqual({item.symbol: item.recommended for item in result.holdings}, expected["recommended"])
        self.assertEqual([row["sector_symbol"] for row in result.sector_exposure],
                         [row[0] for row in expected["sector_exposure"]])
        for row, want in zip(result.sector_exposure, expected["sector_exposure"]):
            self.assertClose(row["weight_pct"], want[1], "sector weight")
        self.assertClose(result.total_hold_risk, expected["total_hold_risk"], "total risk")
        self.assertClose(result.top3_weight_pct, expected["top3_weight_pct"], "top3")
        self.assertEqual(len(result.notes), expected["note_count"])
        self.assertTrue(any("单票集中" in note and "NVDA" in note for note in result.notes))

    def test_calculate_levels_emits_fixture_metrics(self):
        data = FIXTURE["metrics"]
        bars = data["bars"]
        index = pd.bdate_range("2024-01-02", periods=len(bars))
        frame = pd.DataFrame(
            {"high": [b[0] for b in bars], "low": [b[1] for b in bars], "close": [b[2] for b in bars]},
            index=index,
        )
        values = calculate_levels(frame, data["price"])
        metrics = HoldingMetrics.from_values(values)
        for key, want in data["expected"].items():
            self.assertClose(getattr(metrics, key), want, key)

    def test_sector_map_matches_swift(self):
        source = (ROOT / "apple/Shared/SectorMap.swift").read_text(encoding="utf-8")
        def block(name: str) -> str:
            match = re.search(rf"static let {name}: \[String: String\] = \[(.*?)\n    \]", source, re.DOTALL)
            self.assertIsNotNone(match, name)
            return match.group(1)

        map_block = block("symbols")
        swift_map = dict(re.findall(r'"([A-Z.]+)":\s*"([A-Z]+)"', map_block))
        self.assertEqual(swift_map, SECTOR_MAP)
        names_block = block("etfNames")
        self.assertEqual(dict(re.findall(r'"([A-Z]+)":\s*"([^"]+)"', names_block)), SECTOR_ETF_NAMES)


class OfflineGuaranteeTests(unittest.TestCase):
    def test_engine_imports_no_network_or_llm_modules(self):
        tree = ast.parse((ROOT / "holding_diagnosis.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"__future__", "math", "dataclasses", "sector_map"})

    def test_explain_without_key_is_rule_text(self):
        result = run_case(case("idio_breakdown_loss"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            plain = explain_diagnosis(result)
            fallback = explain_diagnosis(result, use_llm=True)
        self.assertIn("止损离场", plain)
        self.assertIn(DISCLAIMER, plain)
        self.assertTrue(fallback.startswith(plain))
        self.assertIn("未配置 OPENAI_API_KEY", fallback)

    def test_llm_cannot_change_recommendation(self):
        result = run_case(case("market_pullback_small_loss"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), \
             patch("explain._llm_rewrite", return_value="建议立即全部卖出"):
            text = explain_diagnosis(result, use_llm=True)
        self.assertTrue(text.startswith("【规则引擎结论】推荐方案：持有观察"))
        self.assertIn(result.explain_text(), text)
        self.assertEqual(result.recommended, "hold_watch")


if __name__ == "__main__":
    unittest.main()
