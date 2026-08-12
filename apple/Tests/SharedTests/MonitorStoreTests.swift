import XCTest
@testable import StockSignalCore

@MainActor
final class MonitorStoreTests: XCTestCase {
    func testRefreshPopulatesQuoteSignalAndPlan() async {
        let history = (0..<205).map { index in
            DailyBar(date: Date(timeIntervalSince1970: Double(index * 86_400)), open: 99, high: Double(index + 101), low: 99, close: Double(index + 100))
        }
        let mock = MockMarketDataService(
            histories: ["AAPL": history],
            quotes: ["AAPL": StockQuote(symbol: "AAPL", price: 305)]
        )
        let store = MonitorStore(symbols: ["aapl"], serviceFactory: { _ in mock })

        await store.refresh()

        XCTAssertEqual(store.stocks.first?.symbol, "AAPL")
        XCTAssertEqual(store.stocks.first?.quote?.price, 305)
        XCTAssertNotNil(store.stocks.first?.levels)
        XCTAssertNotNil(store.stocks.first?.plan)
        XCTAssertNil(store.stocks.first?.errorMessage)
    }

    func testWatchlistAndPositionMutations() {
        let store = MonitorStore(symbols: ["AAPL", "AAPL"])
        XCTAssertEqual(store.symbols, ["AAPL"])
        XCTAssertEqual(store.stocks.first?.name, "Apple Inc.")
        store.addSymbol(" msft ")
        XCTAssertEqual(store.stocks.first(where: { $0.symbol == "MSFT" })?.name, "Microsoft Corp.")
        store.updatePosition(Position(symbol: "MSFT", averageCost: 400, quantity: 10))
        XCTAssertEqual(store.stocks.first(where: { $0.symbol == "MSFT" })?.position.quantity, 10)
        store.removeSymbol("AAPL")
        XCTAssertEqual(store.symbols, ["MSFT"])
    }

    func testCallerNameOverridesFallbackAndUnknownNameRemainsEmpty() {
        let store = MonitorStore(symbols: [])
        store.addSymbol("NVDA", name: "自定义名称")
        store.addSymbol("XYZQ")

        XCTAssertEqual(CompanyNameResolver.name(for: " nvda "), "NVIDIA Corp.")
        XCTAssertEqual(store.stocks.first(where: { $0.symbol == "NVDA" })?.name, "自定义名称")
        XCTAssertEqual(store.stocks.first(where: { $0.symbol == "XYZQ" })?.name, "")
        XCTAssertEqual(CompanyNameResolver.displayName(for: "xyzq"), "XYZQ")
    }
}
