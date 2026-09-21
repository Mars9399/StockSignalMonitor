import Foundation

public protocol MarketDataService: Sendable {
    var provider: MarketDataProviderKind { get }
    func history(for symbol: String, lookbackDays: Int) async throws -> [DailyBar]
    func quote(for symbol: String) async throws -> StockQuote
    func quoteStream(for symbols: [String], pollInterval: Duration) -> AsyncThrowingStream<[StockQuote], Error>
}

public extension MarketDataService {
    func quoteStream(
        for symbols: [String],
        pollInterval: Duration = .seconds(15)
    ) -> AsyncThrowingStream<[StockQuote], Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var consecutiveEmptyPolls = 0
                    while !Task.isCancelled {
                        let quotes = await withTaskGroup(of: StockQuote?.self) { group in
                            for symbol in symbols {
                                group.addTask { try? await quote(for: symbol) }
                            }
                            var output: [StockQuote] = []
                            for await quote in group {
                                if let quote { output.append(quote) }
                            }
                            return output.sorted { $0.symbol < $1.symbol }
                        }
                        if quotes.isEmpty {
                            consecutiveEmptyPolls += 1
                            if consecutiveEmptyPolls >= 3 { throw MarketDataError.noData("所有监控股票") }
                        } else {
                            consecutiveEmptyPolls = 0
                            continuation.yield(quotes)
                        }
                        try await Task.sleep(for: pollInterval)
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}

public typealias MarketDataServiceFactory = @Sendable (DataProviderConfiguration) throws -> any MarketDataService

public func defaultMarketDataService(configuration: DataProviderConfiguration) throws -> any MarketDataService {
    switch configuration {
    case .yahoo:
        return YahooFinanceService()
    case let .alpaca(apiKey, apiSecret, feed):
        guard !apiKey.isEmpty, !apiSecret.isEmpty else { throw MarketDataError.missingCredentials("Alpaca") }
        return AlpacaMarketDataService(apiKey: apiKey, apiSecret: apiSecret, feed: feed)
    case let .massive(apiKey, baseURL):
        guard !apiKey.isEmpty else { throw MarketDataError.missingCredentials("Massive") }
        return MassiveMarketDataService(apiKey: apiKey, baseURL: baseURL)
    case let .ibkrClientPortal(baseURL, accountID):
        return IBKRClientPortalService(baseURL: baseURL, accountID: accountID)
    }
}

public actor MockMarketDataService: MarketDataService {
    public nonisolated let provider: MarketDataProviderKind
    private var histories: [String: [DailyBar]]
    private var quotes: [String: StockQuote]

    public init(
        provider: MarketDataProviderKind = .yahoo,
        histories: [String: [DailyBar]] = [:],
        quotes: [String: StockQuote] = [:]
    ) {
        self.provider = provider
        self.histories = histories
        self.quotes = quotes
    }

    public func history(for symbol: String, lookbackDays: Int) async throws -> [DailyBar] {
        guard let bars = histories[symbol.uppercased()] else { throw MarketDataError.noData(symbol) }
        return Array(bars.suffix(max(1, lookbackDays)))
    }

    public func quote(for symbol: String) async throws -> StockQuote {
        guard let quote = quotes[symbol.uppercased()] else { throw MarketDataError.noData(symbol) }
        return quote
    }

    public func set(history: [DailyBar], quote: StockQuote, for symbol: String) {
        histories[symbol.uppercased()] = history
        quotes[symbol.uppercased()] = quote
    }
}

struct HTTPTransport: Sendable {
    let session: URLSession

    init(session: URLSession = .shared) { self.session = session }

    func data(for request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw MarketDataError.invalidResponse }
        guard (200...299).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw MarketDataError.httpStatus(http.statusCode, String(body.prefix(200)))
        }
        return data
    }
}

extension URL {
    func appendingQueryItems(_ items: [URLQueryItem]) -> URL {
        var components = URLComponents(url: self, resolvingAgainstBaseURL: false)!
        components.queryItems = (components.queryItems ?? []) + items
        return components.url!
    }
}

extension JSONDecoder {
    static let marketData: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .secondsSince1970
        return decoder
    }()
}
