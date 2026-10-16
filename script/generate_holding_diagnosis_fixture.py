"""Regenerate apple/Tests/SharedTests/Fixtures/holding_diagnosis.json from the Python engine.

The fixture is the cross-platform contract: Python and Swift tests both assert
against it. Run from the repository root: python script/generate_holding_diagnosis_fixture.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from holding_diagnosis import (  # noqa: E402
    DiagnosisContext,
    DiagnosisSettings,
    HoldingMetrics,
    diagnose_holding,
    diagnose_portfolio,
    holding_metric_fields,
)

FIXTURE = ROOT / "apple/Tests/SharedTests/Fixtures/holding_diagnosis.json"

SETTINGS = {
    "account_value": 100000.0, "risk_pct": 1.0, "max_position_pct": 10.0,
    "atr_stop_multiplier": 2.0, "take_profit_atr_multiple": 3.0,
}


def m(price, atr14, ma20, ma50, ma200, channel_low_10, swing_low, ref_close_5, ref_close_20, rsi14=50.0,
      history_days=250, ref_close_60=None):
    return {
        "price": price, "atr14": atr14, "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "channel_low_10": channel_low_10, "swing_low": swing_low,
        "ref_close_5": ref_close_5, "ref_close_20": ref_close_20,
        "rsi14": rsi14, "history_days": history_days, "ref_close_60": ref_close_60,
    }


def r(price, ret5, ret20, ret60, atr14, ma20, ma50, ma200, channel_low_10, swing_low, rsi14, history_days=250):
    """Metrics from 5/20/60-day returns (%), rounded like stored quotes."""
    def ref(change):
        return round(price / (1.0 + change / 100.0), 2)
    return m(price, atr14, ma20, ma50, ma200, channel_low_10, swing_low, ref(ret5), ref(ret20), rsi14,
             history_days, ref(ret60))


SPY_FLAT = m(500.0, 6.0, 495.0, 490.0, 470.0, 488.0, 480.0, 498.0, 495.0, 55.0)
SPY_DOWN = m(500.0, 8.0, 510.0, 505.0, 480.0, 497.0, 490.0, 506.0, 515.0, 40.0)

CASES = [
    {
        "name": "idio_breakdown_loss",
        "symbol": "AMD",
        "holding": {"quantity": 80, "avg_cost": 100.0},
        "metrics": m(84.0, 3.0, 92.0, 95.0, 98.0, 85.0, 88.0, 90.0, 98.0, 30.0),
        "market": SPY_FLAT,
        "sector": m(200.0, 3.0, 198.0, 195.0, 185.0, 196.0, 192.0, 199.0, 198.0),
        "peers": {"MSFT": m(420.0, 6.0, 410.0, 400.0, 380.0, 405.0, 395.0, 415.0, 400.0, 60.0)},
    },
    {
        "name": "market_pullback_small_loss",
        "symbol": "MSFT",
        "holding": {"quantity": 20, "avg_cost": 400.0},
        "metrics": m(390.0, 6.0, 385.0, 380.0, 360.0, 375.0, 370.0, 392.0, 400.0, 45.0),
        "market": SPY_DOWN,
        "sector": m(200.0, 3.0, 204.0, 202.0, 190.0, 198.0, 195.0, 201.0, 206.0),
    },
    {
        "name": "intact_small_loss_cost_basis",
        "symbol": "JPM",
        "holding": {"quantity": 40, "avg_cost": 200.0},
        "metrics": m(196.0, 3.5, 192.0, 188.0, 175.0, 190.0, 185.0, 195.0, 194.0, 52.0),
        "market": SPY_FLAT,
        "sector": m(45.0, 0.6, 44.5, 44.0, 42.0, 44.0, 43.5, 44.8, 44.6),
    },
    {
        "name": "large_profit_overbought",
        "symbol": "LLY",
        "holding": {"quantity": 15, "avg_cost": 500.0},
        "metrics": m(700.0, 15.0, 650.0, 600.0, 550.0, 660.0, 620.0, 680.0, 630.0, 76.0),
        "market": SPY_FLAT,
        "sector": m(150.0, 1.5, 148.0, 146.0, 140.0, 147.0, 145.0, 149.0, 147.0),
    },
    {
        "name": "overweight_over_budget_loss",
        "symbol": "TSLA",
        "holding": {"quantity": 60, "avg_cost": 300.0},
        "metrics": m(270.0, 9.0, 280.0, 265.0, 240.0, 250.0, 245.0, 272.0, 293.5, 42.0),
        "market": m(500.0, 6.0, 498.0, 490.0, 470.0, 488.0, 480.0, 501.0, 505.0, 50.0),
        "sector": m(190.0, 2.5, 192.0, 188.0, 180.0, 186.0, 184.0, 191.0, 193.88, 48.0),
    },
    {
        "name": "earnings_blocks_average_down",
        "symbol": "MSFT",
        "holding": {"quantity": 20, "avg_cost": 400.0},
        "metrics": m(390.0, 6.0, 385.0, 380.0, 360.0, 375.0, 370.0, 392.0, 400.0, 45.0),
        "market": SPY_DOWN,
        "sector": m(200.0, 3.0, 204.0, 202.0, 190.0, 198.0, 195.0, 201.0, 206.0),
        "earnings_days": 3,
    },
    {
        "name": "max_average_down_reached",
        "symbol": "MSFT",
        "holding": {"quantity": 20, "avg_cost": 400.0, "average_down_count": 2},
        "metrics": m(390.0, 6.0, 385.0, 380.0, 360.0, 375.0, 370.0, 392.0, 400.0, 45.0),
        "market": SPY_DOWN,
        "sector": m(200.0, 3.0, 204.0, 202.0, 190.0, 198.0, 195.0, 201.0, 206.0),
    },
    {
        "name": "short_history_observe",
        "symbol": "PLTR",
        "holding": {"quantity": 100, "avg_cost": 30.0},
        "metrics": m(27.0, 1.2, None, None, None, 26.0, None, 28.0, None, 45.0, 15),
        "market": SPY_FLAT,
    },
    {
        "name": "profit_trend_intact",
        "symbol": "AAPL",
        "holding": {"quantity": 30, "avg_cost": 180.0, "initial_stop": 170.0},
        "metrics": m(200.0, 4.0, 195.0, 190.0, 180.0, 192.0, 185.0, 198.0, 190.0, 60.0),
        "market": SPY_FLAT,
        "sector": m(200.0, 3.0, 198.0, 195.0, 185.0, 196.0, 192.0, 199.0, 198.0),
    },
    {
        "name": "sector_drag_weakening_loss",
        "symbol": "XOM",
        "holding": {"quantity": 50, "avg_cost": 120.0},
        "metrics": m(112.0, 2.5, 115.0, 110.0, 105.0, 108.0, 106.0, 113.0, 119.15, 40.0),
        "market": m(500.0, 6.0, 495.0, 490.0, 470.0, 488.0, 480.0, 498.0, 495.0, 55.0),
        "sector": m(90.0, 1.2, 92.0, 91.0, 88.0, 89.0, 87.0, 90.5, 95.24, 41.0),
    },
    {
        "name": "protective_stop_hit",
        "symbol": "NVDA",
        "holding": {"quantity": 40, "avg_cost": 130.0, "initial_stop": 120.0},
        "metrics": m(119.0, 4.0, 124.0, 121.0, 110.0, 117.0, 112.0, 123.0, 126.0, 38.0),
        "market": SPY_FLAT,
        "sector": m(200.0, 3.0, 198.0, 195.0, 185.0, 196.0, 192.0, 199.0, 198.0),
    },
    {
        "name": "over_leveraged_blocks_average_down",
        "symbol": "MSFT",
        "holding": {"quantity": 20, "avg_cost": 400.0},
        "metrics": m(390.0, 6.0, 385.0, 380.0, 360.0, 375.0, 370.0, 392.0, 400.0, 45.0),
        "market": SPY_DOWN,
        "sector": m(200.0, 3.0, 204.0, 202.0, 190.0, 198.0, 195.0, 201.0, 206.0),
        "leverage_pct": 130.0,
    },
]

# Desensitized margin account: stand-in tickers, rounded prices and a synthetic
# account size. Shape only (≈155% gross leverage, one oversized tech name).
LEVERAGED_SETTINGS = {
    "account_value": 26800.0, "risk_pct": 2.0, "max_position_pct": 80.0,
    "atr_stop_multiplier": 2.0, "take_profit_atr_multiple": 3.0,
}
LEVERAGED_PORTFOLIO = {
    "benchmark_symbol": "SPY",
    "positions": {
        "MU": {"quantity": 160, "avg_cost": 153.0, "initial_stop": 123.2},
        "TXN": {"quantity": 127, "avg_cost": 50.3, "initial_stop": 42.2},
        "V": {"quantity": 139, "avg_cost": 90.3, "initial_stop": 76.4},
        "TMO": {"quantity": 20, "avg_cost": 75.9, "initial_stop": 57.3},
    },
    "metrics": {
        "MU": r(138.6, -3.0, -24.2, -8.3, 8.3, 177.0, 170.7, None, 137.8, 124.8, 20.0, 70),
        "TXN": r(46.3, -2.0, -4.8, -25.1, 2.2, 52.4, 51.7, 49.2, 44.3, 47.5, 36.0),
        "V": r(86.6, -1.0, 1.8, 32.4, 5.2, 85.7, 85.5, 86.1, 75.3, 57.8, 47.0),
        "TMO": r(68.0, -2.0, -15.4, 40.5, 6.0, 75.6, 67.9, 56.8, 63.6, 40.8, 32.0),
        "SPY": r(770.0, 0.0, 1.1, 3.9, 8.0, 760.0, 750.0, 700.0, 750.0, 700.0, 55.0),
        "XLK": r(250.0, 0.0, -1.8, -1.6, 4.0, 250.0, 250.0, 240.0, 240.0, 230.0, 50.0),
        "XLF": r(50.0, 0.0, 0.0, -0.2, 0.8, 50.0, 50.0, 48.0, 49.0, 47.0, 50.0),
        "XLV": r(150.0, 0.0, 5.1, 11.5, 2.0, 148.0, 145.0, 140.0, 145.0, 140.0, 55.0),
    },
    "earnings_days": {"MU": 12, "TXN": 13, "V": 19, "TMO": 17},
}

PORTFOLIO = {
    "benchmark_symbol": "SPY",
    "positions": {
        "AMD": {"quantity": 80, "avg_cost": 100.0},
        "MSFT": {"quantity": 20, "avg_cost": 400.0},
        "NVDA": {"quantity": 150, "avg_cost": 110.0},
        "JPM": {"quantity": 40, "avg_cost": 200.0},
    },
    "metrics": {
        "AMD": CASES[0]["metrics"],
        "MSFT": m(420.0, 6.0, 410.0, 400.0, 380.0, 405.0, 395.0, 415.0, 400.0, 60.0),
        "NVDA": m(125.0, 4.0, 122.0, 118.0, 105.0, 119.0, 114.0, 123.0, 118.0, 62.0),
        "JPM": CASES[2]["metrics"],
        "SPY": SPY_FLAT,
        "XLK": CASES[0]["sector"],
        "XLF": CASES[2]["sector"],
    },
    "earnings_days": {"NVDA": 5},
}


def synthetic_bars(count: int = 230) -> list[list[float]]:
    bars = []
    for i in range(count):
        close = round(100 + 10 * math.sin(i / 9.0) + i * 0.05, 4)
        high = round(close + 1 + (i % 3) * 0.2, 4)
        low = round(close - 1 - (i % 4) * 0.15, 4)
        bars.append([high, low, close])
    return bars


def atr14(bars: list[list[float]]) -> float:
    ranges = []
    for index, (high, low, _close) in enumerate(bars):
        candidates = [high - low]
        if index > 0:
            previous = bars[index - 1][2]
            candidates += [abs(high - previous), abs(low - previous)]
        ranges.append(max(candidates))
    window = ranges[-14:]
    return sum(window) / len(window)


def plan_summary(plan) -> dict:
    return {
        "allowed": plan.allowed,
        "score": plan.score,
        "price": plan.price,
        "quantity_change": plan.quantity_change,
        "quantity_after": plan.quantity_after,
        "avg_cost_after": plan.avg_cost_after,
        "worst_loss": plan.worst_loss,
        "target_symbol": plan.target_symbol,
    }


def expected_for(diagnosis) -> dict:
    return {
        "mode": diagnosis.mode,
        "trend_state": diagnosis.trend_state,
        "loss_source": diagnosis.loss_source,
        "recommended": diagnosis.recommended,
        "confidence": diagnosis.confidence,
        "stop": diagnosis.stop,
        "hold_risk": diagnosis.hold_risk,
        "rs_stable": diagnosis.rs_stable,
        "event_near": diagnosis.event_near,
        "overweight": diagnosis.overweight,
        "plan_order": [plan.id for plan in diagnosis.plans],
        "plans": {plan.id: plan_summary(plan) for plan in diagnosis.plans},
        "switch_targets": [item["target"] for item in diagnosis.switch_conditions],
        "rs60": diagnosis.rs60,
        "over_leveraged": diagnosis.over_leveraged,
    }


def portfolio_expected(portfolio) -> dict:
    return {
        "recommended": {item.symbol: item.recommended for item in portfolio.holdings},
        "sector_exposure": [[row["sector_symbol"], row["weight_pct"]] for row in portfolio.sector_exposure],
        "top_weight_pct": portfolio.top_weight_pct,
        "top3_weight_pct": portfolio.top3_weight_pct,
        "total_hold_risk": portfolio.total_hold_risk,
        "note_count": len(portfolio.notes),
        "leverage_pct": portfolio.leverage_pct,
        "over_leveraged": portfolio.over_leveraged,
        "deleverage_amount": portfolio.deleverage_amount,
        "holdings": {item.symbol: expected_for(item) for item in portfolio.holdings},
    }


def run_portfolio(spec: dict, settings):
    return diagnose_portfolio(
        spec["positions"],
        {key: HoldingMetrics.from_dict(value) for key, value in spec["metrics"].items()},
        settings,
        benchmark_symbol=spec["benchmark_symbol"],
        earnings_days=spec["earnings_days"],
    )


def main() -> None:
    settings = DiagnosisSettings.from_configs(SETTINGS, SETTINGS)
    cases = []
    for case in CASES:
        context = DiagnosisContext(
            market=HoldingMetrics.from_dict(case["market"]) if case.get("market") else None,
            sector=HoldingMetrics.from_dict(case["sector"]) if case.get("sector") else None,
            peers={key: HoldingMetrics.from_dict(value) for key, value in case.get("peers", {}).items()},
            earnings_days=case.get("earnings_days"),
            leverage_pct=case.get("leverage_pct"),
        )
        diagnosis = diagnose_holding(case["symbol"], case["holding"], HoldingMetrics.from_dict(case["metrics"]), context, settings)
        cases.append(dict(case, expected=expected_for(diagnosis)))

    portfolio_case = dict(PORTFOLIO, expected=portfolio_expected(run_portfolio(PORTFOLIO, settings)))
    leveraged_settings = DiagnosisSettings.from_configs(LEVERAGED_SETTINGS, LEVERAGED_SETTINGS)
    leveraged_case = dict(
        LEVERAGED_PORTFOLIO,
        settings=LEVERAGED_SETTINGS,
        expected=portfolio_expected(run_portfolio(LEVERAGED_PORTFOLIO, leveraged_settings)),
    )

    bars = synthetic_bars()
    fields = holding_metric_fields([b[0] for b in bars], [b[1] for b in bars], [b[2] for b in bars])
    metrics_case = {"bars": bars, "price": 111.0, "expected": dict(fields, atr14=atr14(bars), history_days=len(bars))}

    FIXTURE.write_text(json.dumps({
        "note": "Generated by script/generate_holding_diagnosis_fixture.py; shared by Python and Swift tests.",
        "settings": SETTINGS,
        "cases": cases,
        "portfolio": portfolio_case,
        "leveraged_portfolio": leveraged_case,
        "metrics": metrics_case,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)} with {len(cases)} cases")


if __name__ == "__main__":
    main()
