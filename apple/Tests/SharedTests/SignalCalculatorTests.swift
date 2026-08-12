import XCTest
@testable import StockSignalCore

final class SignalCalculatorTests: XCTestCase {
    func testStandardModelMatchesPythonFormula() throws {
        let bars = makeBars(count: 205, start: 100, dailyIncrease: 1)
        let levels = try SignalCalculator.calculate(history: bars, livePrice: 305)

        XCTAssertTrue(levels.isReady)
        XCTAssertEqual(levels.quality, .standard)
        XCTAssertEqual(levels.modelName, "SMA50 / SMA200")
        XCTAssertEqual(levels.buyPoint, 305, accuracy: 0.0001)
        XCTAssertEqual(levels.atr14, 2, accuracy: 0.0001)
        XCTAssertEqual(levels.stopPoint, 301, accuracy: 0.0001)
        XCTAssertEqual(levels.status, .buyAlert)
    }

    func testShortHistorySuppressesTradingLevels() throws {
        let levels = try SignalCalculator.calculate(history: makeBars(count: 20), livePrice: 120)
        XCTAssertFalse(levels.isReady)
        XCTAssertEqual(levels.status, .dataShort)
        XCTAssertEqual(levels.buyPoint, 0)
        XCTAssertEqual(levels.stopPoint, 0)
    }

    func testMediumAndLowFallbackModels() throws {
        let medium = try SignalCalculator.calculate(history: makeBars(count: 65), livePrice: 200)
        let low = try SignalCalculator.calculate(history: makeBars(count: 35), livePrice: 200)
        XCTAssertEqual(medium.modelName, "SMA20 / SMA50")
        XCTAssertEqual(medium.quality, .medium)
        XCTAssertEqual(low.modelName, "SMA10 / SMA30")
        XCTAssertEqual(low.quality, .low)
    }

    func testPositionPlannerAppliesRiskAndExposureCaps() throws {
        let levels = try SignalCalculator.calculate(history: makeBars(count: 205), livePrice: 305)
        let plan = PositionPlanner.makePlan(
            levels: levels,
            position: Position(symbol: "AAPL"),
            settings: RiskSettings(accountValue: 100_000, riskPercent: 1, maxPositionPercent: 10)
        )
        XCTAssertEqual(plan.maximumShares, 32) // $10,000 / $305 is tighter than risk cap.
        XCTAssertEqual(plan.profitTarget2R, 313, accuracy: 0.0001)
        XCTAssertEqual(plan.profitTarget3R, 317, accuracy: 0.0001)
        XCTAssertEqual(plan.action, .openAfterBreakout(maximumShares: 32))
    }

    private func makeBars(count: Int, start: Double = 100, dailyIncrease: Double = 1) -> [DailyBar] {
        (0..<count).map { index in
            let close = start + Double(index) * dailyIncrease
            return DailyBar(
                date: Date(timeIntervalSince1970: Double(index * 86_400)),
                open: close - 0.5,
                high: close + 1,
                low: close - 1,
                close: close,
                volume: 1000
            )
        }
    }
}
