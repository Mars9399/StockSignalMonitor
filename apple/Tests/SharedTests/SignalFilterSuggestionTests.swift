import XCTest
@testable import StockSignalCore

final class SignalFilterSuggestionTests: XCTestCase {
    func testVolumeFilterDemotesBuyAlert() throws {
        let levels = SignalLevels(
            status: .buyAlert,
            price: 101,
            buyPoint: 100,
            stopPoint: 90,
            riskPercent: 10,
            atr14: 2,
            trendFast: 98,
            trendSlow: 95,
            historyDays: 30,
            quality: .standard,
            modelName: "10日高低点",
            isReady: true,
            volumeRatio: 0.5
        )
        var settings = MonitorStrategySettings.default
        settings.filterVolumeEnabled = true
        let filtered = SignalFilterEngine.apply(levels: levels, settings: settings)
        XCTAssertTrue(filtered.suppressed)
        XCTAssertEqual(filtered.levels.status, .watch)
        XCTAssertEqual(filtered.rawStatus, .buyAlert)
    }

    func testSuggestionPrimaryBuy() {
        let levels = SignalLevels(
            status: .buyAlert,
            price: 101,
            buyPoint: 100,
            stopPoint: 90,
            riskPercent: 10,
            atr14: 2,
            trendFast: 98,
            trendSlow: 95,
            historyDays: 30,
            quality: .standard,
            modelName: "10日高低点",
            isReady: true,
            volumeRatio: 1.5
        )
        let filtered = FilteredSignal(
            levels: levels,
            rawStatus: .buyAlert,
            suppressed: false,
            notes: [],
            breakoutExtensionPercent: 1,
            relativeStrengthSpread: 0.5
        )
        let score = ActionProbabilityScore(buyProbability: 70, reduceProbability: 0, buyLabel: "中高", reduceLabel: "无持仓")
        let plan = PositionPlan(
            riskReductionPoint: 90,
            profitTarget2R: 0,
            profitTarget3R: 0,
            maximumShares: 10,
            action: .openAfterBreakout(maximumShares: 10)
        )
        let suggestion = SuggestionBuilder.build(
            symbol: "AAPL",
            filtered: filtered,
            score: score,
            plan: plan,
            observation: nil,
            feedProfile: "Yahoo · 5s",
            quoteAgeSeconds: 2
        )
        XCTAssertEqual(suggestion.side, "buy")
        XCTAssertEqual(suggestion.alertTier, "primary")
        XCTAssertTrue(suggestion.disclaimer.contains("不构成投资建议"))
    }

    func testDefaultPollIsFiveSeconds() {
        XCTAssertEqual(MonitorStrategySettings.default.quotePollSeconds, 5)
    }
}
