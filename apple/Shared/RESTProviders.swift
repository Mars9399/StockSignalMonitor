import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public struct YahooFinanceService: MarketDataService {
    public let provider: MarketDataProviderKind = .yahoo
    private let transport: HTTPTransport

    public init(session: URLSession = .shared) { transport = HTTPTransport(session: session) }

    public func history(for symbol: String, lookbackDays: Int = 730) async throws -> [DailyBar] {
        let encoded = try normalized(symbol).addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? symbol
        let url = URL(string: "https://query1.finance.yahoo.com/v8/finance/chart/\(encoded)")!
            .appendingQueryItems([
                URLQueryItem(name: "range", value: lookbackDays > 365 ? "2y" : "1y"),
                URLQueryItem(name: "interval", value: "1d"),
                URLQueryItem(name: "events", value: "history")
            ])
        let data = try await transport.data(for: URLRequest(url: url))
        let response = try JSONDecoder().decode(YahooChartResponse.self, from: data)
        guard let result = response.chart.result?.first,
              let quote = result.indicators.quote.first else { throw MarketDataError.noData(symbol) }
        return zip(result.timestamp, quote).compactMap { timestamp, values in
            guard let open = values.open, let high = values.high, let low = values.low,
                  let close = values.close else { return nil }
            return DailyBar(date: Date(timeIntervalSince1970: TimeInterval(timestamp)), open: open, high: high, low: low, close: close, volume: values.volume ?? 0)
        }
    }

    public func quote(for symbol: String) async throws -> StockQuote {
        let normalized = try normalized(symbol)
        let encoded = normalized.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? normalized
        let url = URL(string: "https://query1.finance.yahoo.com/v8/finance/chart/\(encoded)")!
            .appendingQueryItems([
                URLQueryItem(name: "range", value: "1d"),
                URLQueryItem(name: "interval", value: "1m")
            ])
        let data = try await transport.data(for: URLRequest(url: url))
        let response = try JSONDecoder().decode(YahooChartResponse.self, from: data)
        guard let result = response.chart.result?.first,
              let price = result.meta.regularMarketPrice else { throw MarketDataError.noData(symbol) }
        return StockQuote(
            symbol: result.meta.symbol ?? normalized,
            price: price,
            timestamp: Date(timeIntervalSince1970: TimeInterval(result.meta.regularMarketTime ?? Int(Date.now.timeIntervalSince1970)))
        )
    }

    private func normalized(_ symbol: String) throws -> String {
        let value = symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !value.isEmpty else { throw MarketDataError.invalidSymbol }
        return value
    }
}

public struct AlpacaMarketDataService: MarketDataService {
    public let provider: MarketDataProviderKind = .alpaca
    private let apiKey: String
    private let apiSecret: String
    private let feed: String
    private let baseURL: URL
    private let transport: HTTPTransport

    public init(apiKey: String, apiSecret: String, feed: String = "iex", baseURL: URL = URL(string: "https://data.alpaca.markets")!, session: URLSession = .shared) {
        self.apiKey = apiKey
        self.apiSecret = apiSecret
        self.feed = feed
        self.baseURL = baseURL
        transport = HTTPTransport(session: session)
    }

    public func history(for symbol: String, lookbackDays: Int = 730) async throws -> [DailyBar] {
        let start = Calendar.current.date(byAdding: .day, value: -max(35, lookbackDays), to: .now)!
        let url = baseURL.appending(path: "v2/stocks/\(symbol.uppercased())/bars").appendingQueryItems([
            URLQueryItem(name: "timeframe", value: "1Day"),
            URLQueryItem(name: "start", value: ISO8601DateFormatter().string(from: start)),
            URLQueryItem(name: "limit", value: "1000"),
            URLQueryItem(name: "adjustment", value: "all"),
            URLQueryItem(name: "feed", value: feed)
        ])
        let data = try await transport.data(for: authorized(url))
        let response = try JSONDecoder().decode(AlpacaBarsResponse.self, from: data)
        return try response.bars.map { try $0.dailyBar() }
    }

    public func quote(for symbol: String) async throws -> StockQuote {
        let url = baseURL.appending(path: "v2/stocks/\(symbol.uppercased())/trades/latest")
            .appendingQueryItems([URLQueryItem(name: "feed", value: feed)])
        let data = try await transport.data(for: authorized(url))
        let response = try JSONDecoder().decode(AlpacaLatestTradeResponse.self, from: data)
        return StockQuote(symbol: symbol, price: response.trade.p, timestamp: try parseISO8601(response.trade.t))
    }

    private func authorized(_ url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.setValue(apiKey, forHTTPHeaderField: "APCA-API-KEY-ID")
        request.setValue(apiSecret, forHTTPHeaderField: "APCA-API-SECRET-KEY")
        return request
    }
}

public struct MassiveMarketDataService: MarketDataService {
    public let provider: MarketDataProviderKind = .massive
    private let apiKey: String
    private let baseURL: URL
    private let transport: HTTPTransport

    public init(apiKey: String, baseURL: URL = URL(string: "https://api.massive.com")!, session: URLSession = .shared) {
        self.apiKey = apiKey
        self.baseURL = baseURL
        transport = HTTPTransport(session: session)
    }

    public func history(for symbol: String, lookbackDays: Int = 730) async throws -> [DailyBar] {
        let calendar = Calendar(identifier: .gregorian)
        let start = calendar.date(byAdding: .day, value: -max(35, lookbackDays), to: .now)!
        let path = "v2/aggs/ticker/\(symbol.uppercased())/range/1/day/\(apiDate(start))/\(apiDate(.now))"
        let url = baseURL.appending(path: path).appendingQueryItems([
            URLQueryItem(name: "adjusted", value: "true"),
            URLQueryItem(name: "sort", value: "asc"),
            URLQueryItem(name: "limit", value: "50000"),
            URLQueryItem(name: "apiKey", value: apiKey)
        ])
        let data = try await transport.data(for: URLRequest(url: url))
        let response = try JSONDecoder().decode(MassiveAggregatesResponse.self, from: data)
        guard let results = response.results else { throw MarketDataError.noData(symbol) }
        return results.map { DailyBar(date: Date(timeIntervalSince1970: $0.t / 1000), open: $0.o, high: $0.h, low: $0.l, close: $0.c, volume: $0.v ?? 0) }
    }

    public func quote(for symbol: String) async throws -> StockQuote {
        let url = baseURL.appending(path: "v2/last/trade/\(symbol.uppercased())")
            .appendingQueryItems([URLQueryItem(name: "apiKey", value: apiKey)])
        let data = try await transport.data(for: URLRequest(url: url))
        let response = try JSONDecoder().decode(MassiveLastTradeResponse.self, from: data)
        guard let result = response.results else { throw MarketDataError.noData(symbol) }
        let divisor = result.t > 10_000_000_000_000 ? 1_000_000_000.0 : 1_000.0
        return StockQuote(symbol: symbol, price: result.p, timestamp: Date(timeIntervalSince1970: result.t / divisor))
    }
}

// IBKR Client Portal Gateway must be running locally and authenticated in a browser.
// This adapter calls only read-only contract/search/history/snapshot endpoints.
public actor IBKRClientPortalService: MarketDataService {
    public nonisolated let provider: MarketDataProviderKind = .ibkrClientPortal
    private let baseURL: URL
    private let accountID: String?
    private let transport: HTTPTransport
    private var conids: [String: Int] = [:]

    public init(baseURL: URL = URL(string: "https://localhost:5000/v1/api")!, accountID: String? = nil, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.accountID = accountID
        transport = HTTPTransport(session: session)
    }

    public func history(for symbol: String, lookbackDays: Int = 730) async throws -> [DailyBar] {
        try await ensureAuthenticated()
        let conid = try await conid(for: symbol)
        var query = [
            URLQueryItem(name: "conid", value: String(conid)),
            URLQueryItem(name: "period", value: lookbackDays > 365 ? "2y" : "1y"),
            URLQueryItem(name: "bar", value: "1d"),
            URLQueryItem(name: "outsideRth", value: "false")
        ]
        if let accountID, !accountID.isEmpty { query.append(URLQueryItem(name: "acctId", value: accountID)) }
        let url = baseURL.appending(path: "iserver/marketdata/history").appendingQueryItems(query)
        let data = try await transport.data(for: URLRequest(url: url))
        let response = try JSONDecoder().decode(IBKRHistoryResponse.self, from: data)
        return response.data.map { DailyBar(date: Date(timeIntervalSince1970: $0.t / 1000), open: $0.o, high: $0.h, low: $0.l, close: $0.c, volume: $0.v ?? 0) }
    }

    public func quote(for symbol: String) async throws -> StockQuote {
        try await ensureAuthenticated()
        let conid = try await conid(for: symbol)
        // A first snapshot may preflight subscriptions; one retry obtains populated fields.
        let url = baseURL.appending(path: "iserver/marketdata/snapshot").appendingQueryItems([
            URLQueryItem(name: "conids", value: String(conid)),
            URLQueryItem(name: "fields", value: "31,55,6509")
        ])
        _ = try? await transport.data(for: URLRequest(url: url))
        try await Task.sleep(for: .milliseconds(500))
        let data = try await transport.data(for: URLRequest(url: url))
        let values = try JSONDecoder().decode([IBKRSnapshot].self, from: data)
        guard let first = values.first, let price = first.marketPrice else { throw MarketDataError.noData(symbol) }
        return StockQuote(symbol: first.symbol ?? symbol, price: price, timestamp: .now)
    }

    private func ensureAuthenticated() async throws {
        let data = try await transport.data(for: URLRequest(url: baseURL.appending(path: "iserver/auth/status")))
        let status = try JSONDecoder().decode(IBKRAuthStatus.self, from: data)
        guard status.authenticated == true && status.connected != false else { throw MarketDataError.ibkrAuthenticationRequired }
    }

    private func conid(for symbol: String) async throws -> Int {
        let normalized = symbol.uppercased()
        if let cached = conids[normalized] { return cached }
        let url = baseURL.appending(path: "iserver/secdef/search").appendingQueryItems([
            URLQueryItem(name: "symbol", value: normalized), URLQueryItem(name: "secType", value: "STK")
        ])
        let data = try await transport.data(for: URLRequest(url: url))
        let matches = try JSONDecoder().decode([IBKRSecurity].self, from: data)
        guard let match = matches.first(where: { $0.symbol.uppercased() == normalized }) ?? matches.first else { throw MarketDataError.noData(symbol) }
        conids[normalized] = match.conid
        return match.conid
    }
}

private struct YahooChartResponse: Decodable { let chart: Chart; struct Chart: Decodable { let result: [Result]? }; struct Result: Decodable { let timestamp: [Int]; let indicators: Indicators; let meta: Meta }; struct Meta: Decodable { let symbol: String?; let regularMarketPrice: Double?; let regularMarketTime: Int? }; struct Indicators: Decodable { let quote: [QuoteSeries] }; struct QuoteSeries: Decodable { let open, high, low, close, volume: [Double?] } }
private struct AlpacaBarsResponse: Decodable { let bars: [Bar] }
private struct Bar: Decodable { let t: String; let o, h, l, c: Double; let v: Double?; func dailyBar() throws -> DailyBar { DailyBar(date: try parseISO8601(t), open: o, high: h, low: l, close: c, volume: v ?? 0) } }
private struct AlpacaLatestTradeResponse: Decodable { let trade: Trade; struct Trade: Decodable { let p: Double; let t: String } }
private struct MassiveAggregatesResponse: Decodable { let results: [Aggregate]?; struct Aggregate: Decodable { let o, h, l, c, t: Double; let v: Double? } }
private struct MassiveLastTradeResponse: Decodable { let results: Result?; struct Result: Decodable { let p, t: Double } }
private struct IBKRAuthStatus: Decodable { let authenticated: Bool?; let connected: Bool? }
private struct IBKRSecurity: Decodable { let conid: Int; let symbol: String }
private struct IBKRHistoryResponse: Decodable { let data: [Bar]; struct Bar: Decodable { let o, h, l, c, t: Double; let v: Double? } }
private struct IBKRSnapshot: Decodable {
    let symbol: String?
    let marketPrice: Double?
    enum CodingKeys: String, CodingKey { case symbol = "55"; case marketPrice = "31" }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        symbol = try values.decodeIfPresent(String.self, forKey: .symbol)
        if let number = try? values.decode(Double.self, forKey: .marketPrice) { marketPrice = number }
        else if let text = try? values.decode(String.self, forKey: .marketPrice) {
            let scanner = Scanner(string: text.replacingOccurrences(of: ",", with: ""))
            marketPrice = scanner.scanDouble()
        }
        else { marketPrice = nil }
    }
}

private func parseISO8601(_ value: String) throws -> Date {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: value) { return date }
    formatter.formatOptions = [.withInternetDateTime]
    if let date = formatter.date(from: value) { return date }
    throw MarketDataError.invalidResponse
}

private func apiDate(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: date)
}

private func zip(_ timestamps: [Int], _ series: YahooChartResponse.QuoteSeries) -> [(Int, (open: Double?, high: Double?, low: Double?, close: Double?, volume: Double?))] {
    timestamps.indices.map { index in
        (timestamps[index], (
            index < series.open.count ? series.open[index] : nil,
            index < series.high.count ? series.high[index] : nil,
            index < series.low.count ? series.low[index] : nil,
            index < series.close.count ? series.close[index] : nil,
            index < series.volume.count ? series.volume[index] : nil
        ))
    }
}
