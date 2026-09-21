import XCTest
@testable import StockSignalCore

final class SignalCalculatorTests: XCTestCase {
    func testStandardModelMatchesPythonFormula() throws {
        let bars = makeBars(count: 205, start: 100, dailyIncrease: 1)
        let levels = try SignalCalculator.calculate(history: bars, livePrice: 305)

        XCTAssertTrue(levels.isReady)
        XCTAssertEqual(levels.quality, .standard)
        XCTAssertEqual(levels.modelName, "10日高低点")
        XCTAssertEqual(levels.buyPoint, 305, accuracy: 0.0001)
        XCTAssertEqual(levels.atr14, 2, accuracy: 0.0001)
        XCTAssertEqual(levels.stopPoint, 294, accuracy: 0.0001)
        XCTAssertEqual(levels.status, .buyAlert)
    }

    func testShortHistorySuppressesTradingLevels() throws {
        let levels = try SignalCalculator.calculate(history: makeBars(count: 19), livePrice: 120)
        XCTAssertFalse(levels.isReady)
        XCTAssertEqual(levels.status, .dataShort)
        XCTAssertEqual(levels.buyPoint, 0)
        XCTAssertEqual(levels.stopPoint, 0)
    }

    func testTwentyDaysProducesDirectSellSignal() throws {
        let levels = try SignalCalculator.calculate(history: makeBars(count: 20), livePrice: 90)
        XCTAssertTrue(levels.isReady)
        XCTAssertEqual(levels.modelName, "10日高低点")
        XCTAssertEqual(levels.status, .sellAlert)
    }

    func testPositionPlannerAppliesRiskAndExposureCaps() throws {
        let levels = try SignalCalculator.calculate(history: makeBars(count: 205), livePrice: 305)
        let plan = PositionPlanner.makePlan(
            levels: levels,
            position: Position(symbol: "AAPL"),
            settings: RiskSettings(accountValue: 100_000, riskPercent: 1, maxPositionPercent: 10)
        )
        XCTAssertEqual(plan.maximumShares, 32) // $10,000 / $305 is tighter than risk cap.
        XCTAssertEqual(plan.profitTarget2R, 0, accuracy: 0.0001)
        XCTAssertEqual(plan.profitTarget3R, 0, accuracy: 0.0001)
        XCTAssertEqual(plan.action, .openAfterBreakout(maximumShares: 32))
    }

    func testActionProbabilityUsesMarketAndAccountContext() throws {
        let levels = try SignalCalculator.calculate(history: makeBars(count: 205), livePrice: 305)
        let settings = RiskSettings(accountValue: 100_000, riskPercent: 1, maxPositionPercent: 10)
        let empty = ActionProbabilityEstimator.estimate(
            levels: levels,
            position: Position(symbol: "AAPL"),
            settings: settings
        )
        XCTAssertTrue((5...95).contains(empty.buyProbability))
        XCTAssertEqual(empty.reduceProbability, 0)
        XCTAssertEqual(empty.reduceLabel, "无持仓")

        let overloaded = ActionProbabilityEstimator.estimate(
            levels: levels,
            position: Position(symbol: "AAPL", averageCost: 250, quantity: 50),
            settings: settings,
            portfolioValue: 95_000,
            availableFunds: 2_000
        )
        XCTAssertLessThan(overloaded.buyProbability, empty.buyProbability)
        XCTAssertGreaterThan(overloaded.reduceProbability, 0)
    }

    func testActionProbabilityPrioritizesBrokenRiskLine() {
        let levels = SignalLevels(
            status: .sellAlert,
            price: 89,
            buyPoint: 110,
            stopPoint: 90,
            riskPercent: 18.18,
            atr14: 2,
            trendFast: 95,
            trendSlow: 100,
            historyDays: 30,
            quality: .standard,
            modelName: "10日高低点",
            isReady: true,
            momentum5DayPercent: -5,
            momentum10DayPercent: -8,
            rsi14: 30,
            volumeRatio: 1.6
        )
        let score = ActionProbabilityEstimator.estimate(
            levels: levels,
            position: Position(symbol: "AAPL", averageCost: 105, quantity: 20, initialStop: 94),
            settings: RiskSettings()
        )
        XCTAssertGreaterThanOrEqual(score.reduceProbability, 90)
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
