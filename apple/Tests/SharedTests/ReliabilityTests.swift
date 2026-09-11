import XCTest
@testable import StockSignalCore

final class ReliabilityTests: XCTestCase {
    struct Scenario: Decodable {
        let price: Double
        let quantity: Double
        let stop: Double?
        let riskLine: Double
        let target2: Double
        let target3: Double
        let action: String
    }

    func testSharedWindowsScenarios() throws {
        let url = Bundle.module.url(forResource: "reliability", withExtension: "json", subdirectory: "Fixtures")!
        let scenarios = try JSONDecoder().decode([Scenario].self, from: Data(contentsOf: url))
        for s in scenarios {
            let levels = SignalLevels(status: .noSignal, price: s.price, buyPoint: 110, stopPoint: 100,
                riskPercent: 9, atr14: 5, trendFast: 70, trendSlow: 60, historyDays: 205,
                quality: .standard, modelName: "SMA50 / SMA200", isReady: true)
            let plan = PositionPlanner.makePlan(levels: levels,
                position: Position(symbol: "TEST", averageCost: 100, quantity: s.quantity, initialStop: s.stop),
                settings: RiskSettings())
            XCTAssertEqual(plan.riskReductionPoint, s.riskLine)
            XCTAssertEqual(plan.profitTarget2R, s.target2)
            XCTAssertEqual(plan.profitTarget3R, s.target3)
            switch s.action {
            case "risk": XCTAssertEqual(plan.action, .reduceForRisk(shares: s.quantity))
            case "profit": XCTAssertEqual(plan.action, .reduceAt2R(shares: 0.5))
            case "baseline": XCTAssertEqual(plan.action, .needsRiskBaseline)
            default: XCTAssertEqual(plan.action, .hold)
            }
        }
    }

    func testFreshnessAndCompletedDays() throws {
        let format = ISO8601DateFormatter()
        let now = format.date(from: "2026-09-11T15:00:00Z")!
        let prior = DailyBar(date: format.date(from: "2026-09-10T00:00:00Z")!, open: 100, high: 101, low: 99, close: 100)
        let today = DailyBar(date: now, open: 100, high: 999, low: 99, close: 100)
        let bars = DataReliability.completedBars([prior, prior, today], now: now)
        XCTAssertEqual(bars.count, 1)
        XCTAssertNil(DataReliability.reason(quote: StockQuote(symbol: "TEST", price: 100, timestamp: now), history: bars, now: now))
        XCTAssertNotNil(DataReliability.reason(quote: StockQuote(symbol: "TEST", price: 100, timestamp: now.addingTimeInterval(-121)), history: bars, now: now))
        XCTAssertNotNil(DataReliability.reason(quote: StockQuote(symbol: "TEST", price: 100, timestamp: now), history: [], now: now))
        let weekend = format.date(from: "2026-09-12T15:00:00Z")!
        XCTAssertNotNil(DataReliability.reason(quote: StockQuote(symbol: "TEST", price: 100, timestamp: weekend), history: bars, now: weekend))
    }

    func testLegacyPositionDecodesWithoutBaseline() throws {
        let p = try JSONDecoder().decode(Position.self, from: Data(#"{"symbol":"TEST","averageCost":100,"quantity":2}"#.utf8))
        XCTAssertNil(p.initialStop)
        XCTAssertEqual(p.quantity, 2)
    }
}
