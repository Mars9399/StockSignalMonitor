import XCTest
@testable import StockSignalCore

final class MarketDirectoryTests: XCTestCase {
    func testDirectoryBootstrapsCookieBeforeCrumbAndScreener() async throws {
        let lock = NSLock()
        var paths: [String] = []
        MarketURLProtocol.handler = { request in
            lock.lock()
            paths.append(request.url!.path)
            lock.unlock()
            let path = request.url!.path
            if request.url?.host == "fc.yahoo.com" {
                return (200, ["Set-Cookie": "A3=test-cookie; Domain=.yahoo.com; Path=/; Secure"], Data())
            }
            if path == "/v1/test/getcrumb" {
                return (200, [:], Data("test-crumb".utf8))
            }
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertTrue(request.url?.query?.contains("crumb=test-crumb") == true)
            let payload = #"{"finance":{"result":[{"total":1,"quotes":[{"symbol":"TEST","shortName":"Test Inc.","fullExchangeName":"NYSE","quoteType":"EQUITY","regularMarketPrice":12.5,"regularMarketChangePercent":1.25,"regularMarketVolume":1000,"regularMarketTime":1791815729,"marketCap":5000000,"currency":"USD"}]}]}}"#
            return (200, [:], Data(payload.utf8))
        }
        defer { MarketURLProtocol.handler = nil }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MarketURLProtocol.self]
        let result = try await YahooMarketDirectoryService(session: URLSession(configuration: configuration)).page(0, pageSize: 25)

        XCTAssertEqual(result.entries.map(\.symbol), ["TEST"])
        XCTAssertEqual(result.total, 1)
        XCTAssertEqual(paths, ["", "/v1/test/getcrumb", "/v1/finance/screener"])
    }

    func testMoverOpportunityLabelsFollowPriceChannel() {
        XCTAssertTrue(YahooMarketMoverService.opportunity(levels: levels(status: .buyAlert, price: 101, buy: 100)).hasPrefix("买入机会"))
        XCTAssertTrue(YahooMarketMoverService.opportunity(levels: levels(status: .buyAlert, price: 104, buy: 100)).hasPrefix("等待回踩"))
        XCTAssertTrue(YahooMarketMoverService.opportunity(levels: levels(status: .watch, price: 99, buy: 100)).hasPrefix("接近买点"))
        XCTAssertTrue(YahooMarketMoverService.opportunity(levels: levels(status: .watch, price: 90, buy: 100)).hasPrefix("等待突破"))
        XCTAssertTrue(YahooMarketMoverService.opportunity(levels: levels(status: .sellAlert, price: 89, buy: 100)).hasPrefix("回避"))
    }

    func testSectorListMatchesYahooEquityClassification() {
        XCTAssertEqual(
            MarketSector.allCases.compactMap(\.providerName),
            [
                "Basic Materials", "Communication Services", "Consumer Cyclical",
                "Consumer Defensive", "Energy", "Financial Services", "Healthcare",
                "Industrials", "Real Estate", "Technology", "Utilities"
            ]
        )
    }

    func testMarketMoverDefaultLimitIsTwentyPerSide() {
        XCTAssertEqual(YahooMarketMoverService.defaultLimit, 20)
        XCTAssertEqual(MarketMoverSide.gainers.displayName, "涨幅 Top 20")
        XCTAssertEqual(MarketMoverSide.losers.displayName, "跌幅 Top 20")
    }

    func testSectorMoversUseAuthenticatedCustomScreener() async throws {
        let lock = NSLock()
        var customRequestCount = 0
        MarketURLProtocol.handler = { request in
            let path = request.url!.path
            if request.url?.host == "fc.yahoo.com" {
                return (200, ["Set-Cookie": "A3=test-cookie; Domain=.yahoo.com; Path=/; Secure"], Data())
            }
            if path == "/v1/test/getcrumb" {
                return (200, [:], Data("sector-crumb".utf8))
            }
            if path == "/v1/finance/screener" {
                XCTAssertEqual(request.httpMethod, "POST")
                XCTAssertTrue(request.url?.query?.contains("crumb=sector-crumb") == true)
                lock.lock()
                customRequestCount += 1
                lock.unlock()
                let payload = """
                {"finance":{"result":[{"total":1,"quotes":[{"symbol":"TEST","shortName":"Test Inc.","regularMarketPrice":100,"regularMarketChangePercent":5,"regularMarketVolume":100000,"regularMarketTime":1791815729}]}]}}
                """
                return (200, [:], Data(payload.utf8))
            }
            if path.hasPrefix("/v8/finance/chart/") {
                let timestamps = Array(1...35).map { 1_760_000_000 + $0 * 86_400 }
                let values = Array(repeating: 100.0, count: timestamps.count)
                let volume = Array(repeating: 100_000.0, count: timestamps.count)
                let object: [String: Any] = [
                    "chart": [
                        "result": [[
                            "timestamp": timestamps,
                            "meta": ["symbol": request.url!.lastPathComponent, "regularMarketPrice": 100],
                            "indicators": ["quote": [[
                                "open": values, "high": values, "low": values,
                                "close": values, "volume": volume
                            ]]]
                        ]]
                    ]
                ]
                return (200, [:], try JSONSerialization.data(withJSONObject: object))
            }
            throw URLError(.badURL)
        }
        defer { MarketURLProtocol.handler = nil }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MarketURLProtocol.self]
        let snapshot = try await YahooMarketMoverService(session: URLSession(configuration: configuration))
            .snapshot(sector: .technology, limit: 1)

        XCTAssertEqual(snapshot.gainers.map(\.symbol), ["TEST"])
        XCTAssertEqual(snapshot.losers.map(\.symbol), ["TEST"])
        XCTAssertEqual(customRequestCount, 2)
    }

    func testLiveYahooDirectoryWhenEnabled() async throws {
        guard ProcessInfo.processInfo.environment["YAHOO_LIVE_TEST"] == "1" else {
            throw XCTSkip("Set YAHOO_LIVE_TEST=1 to verify Yahoo cookie bootstrap and screener.")
        }
        let page = try await YahooMarketDirectoryService().page(0, pageSize: 25)
        XCTAssertFalse(page.entries.isEmpty)
        XCTAssertGreaterThan(page.total, 0)
        XCTAssertTrue(page.entries.allSatisfy { !$0.symbol.isEmpty })
    }

    func testLiveYahooTechnologyMoversWhenEnabled() async throws {
        guard ProcessInfo.processInfo.environment["YAHOO_LIVE_TEST"] == "1" else {
            throw XCTSkip("Set YAHOO_LIVE_TEST=1 to verify Yahoo sector movers.")
        }
        let snapshot = try await YahooMarketMoverService().snapshot(sector: .technology, limit: 1)
        XCTAssertFalse(snapshot.gainers.isEmpty)
        XCTAssertFalse(snapshot.losers.isEmpty)
    }

    private func levels(status: SignalStatus, price: Double, buy: Double) -> SignalLevels {
        .init(
            status: status,
            price: price,
            buyPoint: buy,
            stopPoint: 90,
            riskPercent: 10,
            atr14: 2,
            trendFast: 95,
            trendSlow: 94,
            historyDays: 30,
            quality: .standard,
            modelName: "test",
            isReady: true
        )
    }
}

private final class MarketURLProtocol: URLProtocol, @unchecked Sendable {
    static var handler: ((URLRequest) throws -> (Int, [String: String], Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, headers, data) = try handler(request)
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: status,
                httpVersion: "HTTP/1.1",
                headerFields: headers
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
