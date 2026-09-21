import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public struct MarketDirectoryEntry: Codable, Hashable, Identifiable, Sendable {
    public var id: String { symbol }
    public let symbol: String
    public let name: String
    public let exchange: String
    public let price: Double
    public let changePercent: Double
    public let volume: Double
    public let marketCap: Double
}

public struct MarketDirectoryPage: Codable, Hashable, Sendable {
    public let entries: [MarketDirectoryEntry]
    public let page: Int
    public let pageSize: Int
    public let total: Int
}

public actor YahooMarketDirectoryService {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func page(_ page: Int, pageSize: Int = 100) async throws -> MarketDirectoryPage {
        let safePage = max(0, page)
        let safeSize = min(250, max(25, pageSize))
        let crumb = try await yahooCrumb()
        var components = URLComponents(string: "https://query2.finance.yahoo.com/v1/finance/screener")!
        components.queryItems = [
            .init(name: "crumb", value: crumb),
            .init(name: "lang", value: "en-US"),
            .init(name: "region", value: "US"),
            .init(name: "corsDomain", value: "finance.yahoo.com"),
            .init(name: "formatted", value: "false")
        ]
        var request = URLRequest(url: components.url!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Mozilla/5.0 StockSignalMonitor/2.5.0", forHTTPHeaderField: "User-Agent")
        let query: [String: Any] = [
            "operator": "AND",
            "operands": [
                ["operator": "EQ", "operands": ["region", "us"] as [Any]] as [String: Any],
                ["operator": "GT", "operands": ["intradayprice", 0] as [Any]] as [String: Any]
            ]
        ]
        let body: [String: Any] = [
            "offset": safePage * safeSize,
            "size": safeSize,
            "sortField": "ticker",
            "sortType": "ASC",
            "quoteType": "EQUITY",
            "query": query,
            "userId": "",
            "userIdType": "guid"
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data = try await responseData(for: request)
        let result = try JSONDecoder().decode(ScreenEnvelope.self, from: data).finance.result.first
        guard let result else { throw MarketDataError.invalidResponse }
        return .init(
            entries: result.quotes.compactMap(\.directoryEntry),
            page: safePage,
            pageSize: safeSize,
            total: result.total
        )
    }

    public func search(_ text: String, limit: Int = 100) async throws -> MarketDirectoryPage {
        var components = URLComponents(string: "https://query1.finance.yahoo.com/v1/finance/search")!
        components.queryItems = [
            .init(name: "q", value: text),
            .init(name: "quotesCount", value: String(min(100, max(10, limit)))),
            .init(name: "newsCount", value: "0"),
            .init(name: "lang", value: "en-US"),
            .init(name: "region", value: "US")
        ]
        var request = URLRequest(url: components.url!)
        request.setValue("Mozilla/5.0 StockSignalMonitor/2.5.0", forHTTPHeaderField: "User-Agent")
        let data = try await responseData(for: request)
        let response = try JSONDecoder().decode(SearchEnvelope.self, from: data)
        let entries = response.quotes
            .filter { ["EQUITY", "ETF"].contains($0.quoteType?.uppercased() ?? "") }
            .compactMap(\.directoryEntry)
        return .init(entries: entries, page: 0, pageSize: limit, total: entries.count)
    }

    private func yahooCrumb() async throws -> String {
        var request = URLRequest(url: URL(string: "https://query1.finance.yahoo.com/v1/test/getcrumb")!)
        request.setValue("Mozilla/5.0 StockSignalMonitor/2.5.0", forHTTPHeaderField: "User-Agent")
        let data = try await responseData(for: request)
        guard let crumb = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !crumb.isEmpty else { throw MarketDataError.invalidResponse }
        return crumb
    }

    private func responseData(for request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw MarketDataError.invalidResponse }
        guard (200...299).contains(http.statusCode) else {
            throw MarketDataError.httpStatus(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
        return data
    }
}

private struct ScreenEnvelope: Decodable {
    let finance: Finance
    struct Finance: Decodable { let result: [Result] }
    struct Result: Decodable { let total: Int; let quotes: [DirectoryQuote] }
}

private struct SearchEnvelope: Decodable { let quotes: [DirectoryQuote] }

private struct DirectoryQuote: Decodable {
    let symbol: String?
    let shortName: String?
    let longName: String?
    let shortname: String?
    let longname: String?
    let fullExchangeName: String?
    let exchDisp: String?
    let exchange: String?
    let quoteType: String?
    let regularMarketPrice: Double?
    let regularMarketChangePercent: Double?
    let regularMarketVolume: Double?
    let marketCap: Double?

    var directoryEntry: MarketDirectoryEntry? {
        guard let symbol, !symbol.isEmpty else { return nil }
        let normalizedSymbol = symbol.uppercased()
        let displayName = shortName ?? longName ?? shortname ?? longname ?? symbol
        let displayExchange = fullExchangeName ?? exchDisp ?? exchange ?? "—"
        let price = regularMarketPrice ?? 0
        let changePercent = regularMarketChangePercent ?? 0
        let volume = regularMarketVolume ?? 0
        let capitalization = marketCap ?? 0
        return MarketDirectoryEntry(
            symbol: normalizedSymbol,
            name: displayName,
            exchange: displayExchange,
            price: price,
            changePercent: changePercent,
            volume: volume,
            marketCap: capitalization
        )
    }
}
