import XCTest
@testable import StockSignalCore

/// Asserts the same fixture as tests/test_holding_diagnosis.py so both engines stay identical.
final class HoldingDiagnosisTests: XCTestCase {
    private let tolerance = 0.011

    private func fixture() throws -> [String: Any] {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "holding_diagnosis", withExtension: "json", subdirectory: "Fixtures"))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }

    private func number(_ value: Any?) -> Double? {
        guard let value, !(value is NSNull) else { return nil }
        return (value as? NSNumber)?.doubleValue
    }

    private func dict(_ value: Any?) -> [String: Any] { value as? [String: Any] ?? [:] }

    private func metrics(_ value: Any?) -> HoldingMetrics? {
        let data = dict(value)
        guard let price = number(data["price"]) else { return nil }
        return HoldingMetrics(
            price: price,
            atr14: number(data["atr14"]) ?? 0,
            ma20: number(data["ma20"]),
            ma50: number(data["ma50"]),
            ma200: number(data["ma200"]),
            channelLow10: number(data["channel_low_10"]),
            swingLow: number(data["swing_low"]),
            refClose5: number(data["ref_close_5"]),
            refClose20: number(data["ref_close_20"]),
            rsi14: number(data["rsi14"]) ?? 50,
            historyDays: Int(number(data["history_days"]) ?? 0),
            refClose60: number(data["ref_close_60"])
        )
    }

    private func settings(_ value: Any?) -> HoldingDiagnosisSettings {
        let data = dict(value)
        return HoldingDiagnosisSettings(
            accountValue: number(data["account_value"]) ?? 100_000,
            riskPercent: number(data["risk_pct"]) ?? 1,
            maxPositionPercent: number(data["max_position_pct"]) ?? 10,
            atrStopMultiplier: number(data["atr_stop_multiplier"]) ?? 2,
            takeProfitATRMultiple: number(data["take_profit_atr_multiple"]) ?? 3
        )
    }

    private func positions(_ value: Any?) -> [Position] {
        dict(value).map { symbol, raw in
            let data = dict(raw)
            return Position(
                symbol: symbol,
                averageCost: number(data["avg_cost"]) ?? 0,
                quantity: number(data["quantity"]) ?? 0,
                initialStop: number(data["initial_stop"])
            )
        }
    }

    private func assertClose(_ actual: Double?, _ expected: Any?, _ label: String, file: StaticString = #filePath, line: UInt = #line) {
        guard let want = number(expected) else {
            XCTAssertNil(actual, label, file: file, line: line)
            return
        }
        guard let actual else { return XCTFail("\(label) is nil", file: file, line: line) }
        XCTAssertLessThanOrEqual(abs(actual - want), tolerance, label, file: file, line: line)
    }

    private func assertPlans(_ diagnosis: HoldingDiagnosis, _ expected: [String: Any], label: String) {
        let plans = dict(expected["plans"])
        for plan in diagnosis.plans {
            let want = dict(plans[plan.kind.rawValue])
            let name = "\(label).\(plan.kind.rawValue)"
            XCTAssertEqual(plan.allowed, want["allowed"] as? Bool, name)
            XCTAssertEqual(plan.score, Int(number(want["score"]) ?? -1), name)
            if let target = want["target_symbol"] as? String { XCTAssertEqual(plan.targetSymbol, target, name) }
            if want["price"] != nil {
                assertClose(plan.price, want["price"], "\(name).price")
                assertClose(plan.quantityChange, want["quantity_change"], "\(name).quantity_change")
                assertClose(plan.quantityAfter, want["quantity_after"], "\(name).quantity_after")
                assertClose(plan.averageCostAfter, want["avg_cost_after"], "\(name).avg_cost_after")
                assertClose(plan.worstLoss, want["worst_loss"], "\(name).worst_loss")
            }
        }
    }

    private func assertDiagnosis(_ diagnosis: HoldingDiagnosis, _ expected: [String: Any], label: String) {
        XCTAssertEqual(diagnosis.mode.rawValue, expected["mode"] as? String, label)
        XCTAssertEqual(diagnosis.trendState.rawValue, expected["trend_state"] as? String, label)
        XCTAssertEqual(diagnosis.lossSource.rawValue, expected["loss_source"] as? String, label)
        XCTAssertEqual(diagnosis.recommended.rawValue, expected["recommended"] as? String, label)
        XCTAssertEqual(diagnosis.confidence, expected["confidence"] as? String, label)
        XCTAssertEqual(diagnosis.rsStable, expected["rs_stable"] as? Bool, label)
        XCTAssertEqual(diagnosis.eventNear, expected["event_near"] as? Bool, label)
        XCTAssertEqual(diagnosis.overweight, expected["overweight"] as? Bool, label)
        XCTAssertEqual(diagnosis.overLeveraged, expected["over_leveraged"] as? Bool, label)
        assertClose(diagnosis.stop, expected["stop"], "\(label).stop")
        assertClose(diagnosis.holdRisk, expected["hold_risk"], "\(label).hold_risk")
        assertClose(diagnosis.rs60, expected["rs60"], "\(label).rs60")
        assertClose(diagnosis.watchLine, expected["watch_line"], "\(label).watch_line")
        assertClose(diagnosis.hardStop, expected["hard_stop"], "\(label).hard_stop")
        XCTAssertEqual(diagnosis.watchDays, Int(number(expected["watch_days"]) ?? 0), "\(label).watch_days")
        let wantNonSell = expected["non_sell_plan"] as? String ?? ""
        XCTAssertEqual(diagnosis.nonSellPlan?.rawValue ?? "", wantNonSell, "\(label).non_sell_plan")
        XCTAssertEqual(diagnosis.plans.map(\.kind.rawValue), expected["plan_order"] as? [String], label)
        XCTAssertEqual(diagnosis.switchConditions.map(\.target.rawValue), expected["switch_targets"] as? [String], label)
        assertPlans(diagnosis, expected, label: label)
        for plan in diagnosis.plans {
            let want = dict(dict(expected["plans"])[plan.kind.rawValue])
            let wantSteps = want["steps"] as? [[String: Any]] ?? []
            XCTAssertEqual(plan.steps.count, wantSteps.count, "\(label).\(plan.kind.rawValue).steps")
            for (step, raw) in zip(plan.steps, wantSteps) {
                XCTAssertEqual(step.side, raw["side"] as? String)
                assertClose(step.quantity, raw["quantity"], "\(label).step.qty")
                assertClose(step.price, raw["price"], "\(label).step.price")
            }
        }
    }

    func testCasesMatchPythonFixture() throws {
        let data = try fixture()
        let engineSettings = settings(data["settings"])
        let cases = try XCTUnwrap(data["cases"] as? [[String: Any]])
        XCTAssertGreaterThanOrEqual(cases.count, 12)
        for item in cases {
            let name = item["name"] as? String ?? "?"
            let holding = dict(item["holding"])
            let peers = dict(item["peers"]).reduce(into: [String: HoldingMetrics]()) { result, pair in
                result[pair.key] = metrics(pair.value)
            }
            let context = HoldingDiagnosisContext(
                market: metrics(item["market"]),
                sector: metrics(item["sector"]),
                peers: peers,
                earningsDays: number(item["earnings_days"]).map { Int($0) },
                leveragePercent: number(item["leverage_pct"])
            )
            let diagnosis = try XCTUnwrap(HoldingDiagnosisEngine.diagnose(
                symbol: item["symbol"] as? String ?? "",
                quantity: number(holding["quantity"]) ?? 0,
                averageCost: number(holding["avg_cost"]) ?? 0,
                initialStop: number(holding["initial_stop"]),
                averageDownCount: Int(number(holding["average_down_count"]) ?? 0),
                metrics: try XCTUnwrap(metrics(item["metrics"])),
                context: context,
                settings: engineSettings
            ), name)
            assertDiagnosis(diagnosis, dict(item["expected"]), label: name)
            XCTAssertEqual(diagnosis.disclaimer, HoldingDiagnosisText.disclaimer)
        }
    }

    private func runPortfolio(_ spec: [String: Any], settings engineSettings: HoldingDiagnosisSettings) -> PortfolioDiagnosis {
        let allMetrics = dict(spec["metrics"]).reduce(into: [String: HoldingMetrics]()) { result, pair in
            result[pair.key] = metrics(pair.value)
        }
        let earnings = dict(spec["earnings_days"]).reduce(into: [String: Int]()) { result, pair in
            result[pair.key] = number(pair.value).map { Int($0) }
        }
        return HoldingDiagnosisEngine.diagnosePortfolio(
            positions: positions(spec["positions"]),
            metrics: allMetrics,
            settings: engineSettings,
            benchmarkSymbol: spec["benchmark_symbol"] as? String ?? "SPY",
            earningsDays: earnings
        )
    }

    private func assertPortfolio(_ result: PortfolioDiagnosis, _ expected: [String: Any]) {
        let recommended = Dictionary(uniqueKeysWithValues: result.holdings.map { ($0.symbol, $0.recommended.rawValue) })
        XCTAssertEqual(recommended, expected["recommended"] as? [String: String])
        let exposure = expected["sector_exposure"] as? [[Any]] ?? []
        XCTAssertEqual(result.sectorExposure.map(\.sectorSymbol), exposure.map { $0.first as? String })
        for (row, want) in zip(result.sectorExposure, exposure) { assertClose(row.weightPercent, want.last, "sector weight") }
        assertClose(result.totalHoldRisk, expected["total_hold_risk"], "total risk")
        assertClose(result.top3WeightPercent, expected["top3_weight_pct"], "top3")
        assertClose(result.leveragePercent, expected["leverage_pct"], "leverage")
        assertClose(result.deleverageAmount, expected["deleverage_amount"], "deleverage")
        XCTAssertEqual(result.overLeveraged, expected["over_leveraged"] as? Bool)
        XCTAssertEqual(result.notes.count, Int(number(expected["note_count"]) ?? -1))
        let holdings = dict(expected["holdings"])
        for item in result.holdings {
            assertDiagnosis(item, dict(holdings[item.symbol]), label: "portfolio.\(item.symbol)")
        }
    }

    func testPortfolioMatchesPythonFixture() throws {
        let data = try fixture()
        let portfolio = dict(data["portfolio"])
        let result = runPortfolio(portfolio, settings: settings(data["settings"]))
        assertPortfolio(result, dict(portfolio["expected"]))
        XCTAssertTrue(result.notes.contains { $0.contains("单票集中") && $0.contains("NVDA") })
    }

    func testLeveragedPortfolioPrioritisesDeleveraging() throws {
        let data = try fixture()
        let portfolio = dict(data["leveraged_portfolio"])
        let result = runPortfolio(portfolio, settings: settings(portfolio["settings"]))
        assertPortfolio(result, dict(portfolio["expected"]))
        XCTAssertTrue(result.overLeveraged)
        XCTAssertTrue(result.notes.first?.hasPrefix("杠杆优先") == true)
        for item in result.holdings {
            for kind in [HoldingPlanKind.averageDown, .addOnStrength, .switchPosition] {
                if let plan = item.plan(kind) { XCTAssertFalse(plan.allowed, "\(item.symbol).\(kind.rawValue)") }
            }
        }
    }

    func testMetricsFromBarsMatchPythonCalculateLevels() throws {
        let data = dict(try fixture()["metrics"])
        let bars = try XCTUnwrap(data["bars"] as? [[Any]])
        let start = Date(timeIntervalSince1970: 1_704_153_600)
        let history = bars.enumerated().map { index, bar in
            let high = number(bar[0]) ?? 0
            let low = number(bar[1]) ?? 0
            let close = number(bar[2]) ?? 0
            return DailyBar(date: start.addingTimeInterval(Double(index) * 86_400), open: close, high: high, low: low, close: close)
        }
        let computed = try XCTUnwrap(HoldingMetrics.compute(history: history, livePrice: number(data["price"]) ?? 0))
        let expected = dict(data["expected"])
        assertClose(computed.atr14, expected["atr14"], "atr14")
        assertClose(computed.ma20, expected["ma20"], "ma20")
        assertClose(computed.ma50, expected["ma50"], "ma50")
        assertClose(computed.ma200, expected["ma200"], "ma200")
        assertClose(computed.channelLow10, expected["channel_low_10"], "channel_low_10")
        assertClose(computed.swingLow, expected["swing_low"], "swing_low")
        assertClose(computed.refClose5, expected["ref_close_5"], "ref_close_5")
        assertClose(computed.refClose20, expected["ref_close_20"], "ref_close_20")
        assertClose(computed.refClose60, expected["ref_close_60"], "ref_close_60")
        XCTAssertEqual(computed.historyDays, Int(number(expected["history_days"]) ?? 0))
    }

    func testContextSymbolsIncludeBenchmarkAndSectors() {
        let symbols = HoldingDiagnosisEngine.contextSymbols(positions: [
            Position(symbol: "AAPL", quantity: 1), Position(symbol: "JPM", quantity: 2), Position(symbol: "XOM", quantity: 0),
        ])
        XCTAssertEqual(symbols, ["SPY", "XLK", "XLF"])
    }
}
