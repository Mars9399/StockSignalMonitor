import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public enum MarketRegion: String, Codable, CaseIterable, Hashable, Sendable {
    case us
    case hk

    public var yahooLocale: String { self == .hk ? "HK" : "US" }
    public var displayName: String { self == .hk ? "港股" : "美股" }
    public var defaultCurrency: String { self == .hk ? "HKD" : "USD" }
}

public struct MarketDirectoryEntry: Codable, Hashable, Identifiable, Sendable {
    public var id: String { symbol }
    public let symbol: String
    public let name: String
    public let exchange: String
    public let price: Double
    public let changePercent: Double
    public let volume: Double
    public let marketCap: Double
    public let currency: String
}

public struct MarketDirectoryPage: Codable, Hashable, Sendable {
    public let entries: [MarketDirectoryEntry]
    public let page: Int
    public let pageSize: Int
    public let total: Int
    public let market: MarketRegion
}

public enum MarketMoverSide: String, Codable, Hashable, Sendable {
    case gainers
    case losers

    public var displayName: String { self == .gainers ? "涨幅 Top 20" : "跌幅 Top 20" }
}

/// Yahoo Finance's canonical U.S. equity sector classification.
///
/// Keep the raw values aligned with EquityQuery.valid_values so the UI and
/// screener request cannot drift into a locally invented classification.
public enum MarketSector: String, Codable, CaseIterable, Hashable, Identifiable, Sendable {
    case all = ""
    case basicMaterials = "Basic Materials"
    case communicationServices = "Communication Services"
    case consumerCyclical = "Consumer Cyclical"
    case consumerDefensive = "Consumer Defensive"
    case energy = "Energy"
    case financialServices = "Financial Services"
    case healthcare = "Healthcare"
    case industrials = "Industrials"
    case realEstate = "Real Estate"
    case technology = "Technology"
    case utilities = "Utilities"

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .all: "全部板块"
        case .basicMaterials: "基础材料"
        case .communicationServices: "通信服务"
        case .consumerCyclical: "周期消费"
        case .consumerDefensive: "防御消费"
        case .energy: "能源"
        case .financialServices: "金融服务"
        case .healthcare: "医疗保健"
        case .industrials: "工业"
        case .realEstate: "房地产"
        case .technology: "科技"
        case .utilities: "公用事业"
        }
    }

    public var providerName: String? { self == .all ? nil : rawValue }
}

public struct MarketMoverEntry: Codable, Hashable, Identifiable, Sendable {
    public var id: String { "\(side.rawValue):\(symbol)" }
    public let side: MarketMoverSide
    public let rank: Int
    public let symbol: String
    public let name: String
    public let price: Double
    public let changePercent: Double
    public let volume: Double
    public let buyPoint: Double
    public let sellPoint: Double
    public let opportunity: String
    public let quoteTime: Date?
}

public struct MarketMoverSnapshot: Codable, Hashable, Sendable {
    public let gainers: [MarketMoverEntry]
    public let losers: [MarketMoverEntry]
    public let updatedAt: Date
}

public actor YahooMarketDirectoryService {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func page(
        _ page: Int,
        market: MarketRegion = .us,
        pageSize: Int = 100
    ) async throws -> MarketDirectoryPage {
        let safePage = max(0, page)
        let safeSize = min(250, max(25, pageSize))
        let crumb = try await yahooCrumb()
        var components = URLComponents(string: "https://query2.finance.yahoo.com/v1/finance/screener")!
        components.queryItems = [
            .init(name: "crumb", value: crumb),
            .init(name: "lang", value: "en-US"),
            .init(name: "region", value: market.yahooLocale),
            .init(name: "corsDomain", value: "finance.yahoo.com"),
            .init(name: "formatted", value: "false")
        ]
        var request = URLRequest(url: components.url!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Mozilla/5.0 StockSignalMonitor/2.5.3", forHTTPHeaderField: "User-Agent")
        let query: [String: Any] = [
            "operator": "AND",
            "operands": [
                ["operator": "EQ", "operands": ["region", market.rawValue] as [Any]] as [String: Any],
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
            entries: result.quotes.compactMap { $0.directoryEntry(defaultCurrency: market.defaultCurrency) },
            page: safePage,
            pageSize: safeSize,
            total: result.total,
            market: market
        )
    }

    public func search(
        _ text: String,
        market: MarketRegion = .us,
        limit: Int = 100
    ) async throws -> MarketDirectoryPage {
        var components = URLComponents(string: "https://query1.finance.yahoo.com/v1/finance/search")!
        components.queryItems = [
            .init(name: "q", value: text),
            .init(name: "quotesCount", value: String(min(100, max(10, limit)))),
            .init(name: "newsCount", value: "0"),
            .init(name: "lang", value: "en-US"),
            .init(name: "region", value: market.yahooLocale)
        ]
        var request = URLRequest(url: components.url!)
        request.setValue("Mozilla/5.0 StockSignalMonitor/2.5.3", forHTTPHeaderField: "User-Agent")
        let data = try await responseData(for: request)
        let response = try JSONDecoder().decode(SearchEnvelope.self, from: data)
        let entries = response.quotes
            .filter { ["EQUITY", "ETF"].contains($0.quoteType?.uppercased() ?? "") }
            .filter { $0.matches(market: market) }
            .compactMap { $0.directoryEntry(defaultCurrency: market.defaultCurrency) }
        return .init(
            entries: entries,
            page: 0,
            pageSize: limit,
            total: entries.count,
            market: market
        )
    }

    private func yahooCrumb() async throws -> String {
        // Yahoo now rejects getcrumb unless the session already owns an A3
        // cookie. The bootstrap response itself may be an error page; its
        // Set-Cookie header is the useful part and URLSession stores it.
        var bootstrap = URLRequest(url: URL(string: "https://fc.yahoo.com")!)
        bootstrap.setValue("Mozilla/5.0 StockSignalMonitor/2.5.3", forHTTPHeaderField: "User-Agent")
        _ = try await session.data(for: bootstrap)

        var request = URLRequest(url: URL(string: "https://query1.finance.yahoo.com/v1/test/getcrumb")!)
        request.setValue("Mozilla/5.0 StockSignalMonitor/2.5.3", forHTTPHeaderField: "User-Agent")
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

public actor YahooMarketMoverService {
    public nonisolated static let defaultLimit = 20

    private let session: URLSession
    private let historyService: YahooFinanceService

    public init(session: URLSession = .shared) {
        self.session = session
        historyService = YahooFinanceService(session: session)
    }

    public func snapshot(
        sector: MarketSector = .all,
        limit: Int = YahooMarketMoverService.defaultLimit
    ) async throws -> MarketMoverSnapshot {
        let count = min(25, max(1, limit))
        let rawGainers: [MarketMoverEntry]
        let rawLosers: [MarketMoverEntry]
        if sector == .all {
            async let gainers = predefined("day_gainers", side: .gainers, count: count)
            async let losers = predefined("day_losers", side: .losers, count: count)
            (rawGainers, rawLosers) = try await (gainers, losers)
        } else {
            let crumb = try await yahooCrumb()
            async let gainers = custom(sector: sector, side: .gainers, count: count, crumb: crumb)
            async let losers = custom(sector: sector, side: .losers, count: count, crumb: crumb)
            (rawGainers, rawLosers) = try await (gainers, losers)
        }
        return MarketMoverSnapshot(
            gainers: await analyze(rawGainers),
            losers: await analyze(rawLosers),
            updatedAt: .now
        )
    }

    public static func opportunity(levels: SignalLevels) -> String {
        guard levels.isReady else { return "仅观察：历史不足" }
        switch levels.status {
        case .sellAlert:
            return "回避：已跌破卖出点"
        case .buyAlert:
            let extensionPercent = max(0, (levels.price / max(levels.buyPoint, 0.01) - 1) * 100)
            return extensionPercent <= 3
                ? String(format: "买入机会：突破 +%.1f%%", extensionPercent)
                : String(format: "等待回踩：高于买点 %.1f%%", extensionPercent)
        default:
            let gap = max(0, (levels.buyPoint / max(levels.price, 0.01) - 1) * 100)
            return gap <= 2
                ? String(format: "接近买点：还差 %.1f%%", gap)
                : String(format: "等待突破：还差 %.1f%%", gap)
        }
    }

    private func predefined(_ screen: String, side: MarketMoverSide, count: Int) async throws -> [MarketMoverEntry] {
        var components = URLComponents(string: "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved")!
        components.queryItems = [
            .init(name: "scrIds", value: screen),
            .init(name: "count", value: String(count)),
            .init(name: "start", value: "0"),
            .init(name: "lang", value: "en-US"),
            .init(name: "region", value: "US"),
            .init(name: "formatted", value: "false")
        ]
        var request = URLRequest(url: components.url!)
        request.setValue("Mozilla/5.0 StockSignalMonitor/2.5.3", forHTTPHeaderField: "User-Agent")
        let data = try await responseData(for: request)
        guard let result = try JSONDecoder().decode(ScreenEnvelope.self, from: data).finance.result.first else {
            throw MarketDataError.invalidResponse
        }
        return result.quotes.prefix(count).enumerated().compactMap { index, quote in
            quote.moverEntry(side: side, rank: index + 1)
        }
    }

    private func custom(
        sector: MarketSector,
        side: MarketMoverSide,
        count: Int,
        crumb: String
    ) async throws -> [MarketMoverEntry] {
        guard let providerName = sector.providerName else {
            throw MarketDataError.invalidResponse
        }
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
        request.setValue("Mozilla/5.0 StockSignalMonitor/2.5.3", forHTTPHeaderField: "User-Agent")

        // Match Yahoo/yfinance's standard day_gainers/day_losers liquidity
        // filters, adding only the provider-native sector operand.
        let directionFilter: [String: Any] = side == .gainers
            ? ["operator": "GT", "operands": ["percentchange", 3] as [Any]]
            : ["operator": "LT", "operands": ["percentchange", -2.5] as [Any]]
        let volumeFloor = side == .gainers ? 15_000 : 20_000
        let query: [String: Any] = [
            "operator": "AND",
            "operands": [
                directionFilter,
                ["operator": "EQ", "operands": ["region", "us"] as [Any]],
                ["operator": "EQ", "operands": ["sector", providerName] as [Any]],
                ["operator": "GTE", "operands": ["intradaymarketcap", 2_000_000_000] as [Any]],
                ["operator": "GTE", "operands": ["intradayprice", 5] as [Any]],
                ["operator": "GT", "operands": ["dayvolume", volumeFloor] as [Any]]
            ]
        ]
        let body: [String: Any] = [
            "offset": 0,
            "size": count,
            "sortField": "percentchange",
            "sortType": side == .gainers ? "DESC" : "ASC",
            "quoteType": "EQUITY",
            "query": query,
            "userId": "",
            "userIdType": "guid"
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let data = try await responseData(for: request)
        guard let result = try JSONDecoder().decode(ScreenEnvelope.self, from: data).finance.result.first else {
            throw MarketDataError.invalidResponse
        }
        return result.quotes.prefix(count).enumerated().compactMap { index, quote in
            quote.moverEntry(side: side, rank: index + 1)
        }
    }

    private func yahooCrumb() async throws -> String {
        var bootstrap = URLRequest(url: URL(string: "https://fc.yahoo.com")!)
        bootstrap.setValue("Mozilla/5.0 StockSignalMonitor/2.5.3", forHTTPHeaderField: "User-Agent")
        _ = try await session.data(for: bootstrap)

        var request = URLRequest(url: URL(string: "https://query1.finance.yahoo.com/v1/test/getcrumb")!)
        request.setValue("Mozilla/5.0 StockSignalMonitor/2.5.3", forHTTPHeaderField: "User-Agent")
        let data = try await responseData(for: request)
        guard let crumb = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !crumb.isEmpty else { throw MarketDataError.invalidResponse }
        return crumb
    }

    private func analyze(_ entries: [MarketMoverEntry]) async -> [MarketMoverEntry] {
        await withTaskGroup(of: MarketMoverEntry.self) { group in
            for entry in entries {
                group.addTask { [historyService] in
                    do {
                        let history = try await historyService.history(for: entry.symbol, lookbackDays: 180)
                        let completed = DataReliability.completedBars(history)
                        let levels = try SignalCalculator.calculate(history: completed, livePrice: entry.price)
                        return entry.withAnalysis(
                            buyPoint: levels.buyPoint,
                            sellPoint: levels.stopPoint,
                            opportunity: Self.opportunity(levels: levels)
                        )
                    } catch {
                        return entry.withAnalysis(buyPoint: 0, sellPoint: 0, opportunity: "分析失败：\(error.localizedDescription)")
                    }
                }
            }
            var output: [MarketMoverEntry] = []
            for await entry in group { output.append(entry) }
            return output.sorted { $0.rank < $1.rank }
        }
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
    let regularMarketTime: Int?
    let marketCap: Double?
    let currency: String?

    func matches(market: MarketRegion) -> Bool {
        let normalizedSymbol = symbol?.uppercased() ?? ""
        let normalizedExchange = (exchange ?? exchDisp ?? fullExchangeName ?? "").uppercased()
        let isHongKong = normalizedSymbol.hasSuffix(".HK")
            || ["HKG", "HKSE", "HONG KONG"].contains(normalizedExchange)
        return market == .hk ? isHongKong : !isHongKong
    }

    func directoryEntry(defaultCurrency: String) -> MarketDirectoryEntry? {
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
            marketCap: capitalization,
            currency: currency ?? defaultCurrency
        )
    }

    func moverEntry(side: MarketMoverSide, rank: Int) -> MarketMoverEntry? {
        guard let symbol, !symbol.isEmpty,
              let price = regularMarketPrice, price.isFinite, price > 0,
              let change = regularMarketChangePercent, change.isFinite else { return nil }
        return MarketMoverEntry(
            side: side,
            rank: rank,
            symbol: symbol.uppercased(),
            name: shortName ?? longName ?? shortname ?? longname ?? symbol,
            price: price,
            changePercent: change,
            volume: regularMarketVolume ?? 0,
            buyPoint: 0,
            sellPoint: 0,
            opportunity: "正在分析…",
            quoteTime: regularMarketTime.map { Date(timeIntervalSince1970: TimeInterval($0)) }
        )
    }
}

private extension MarketMoverEntry {
    func withAnalysis(buyPoint: Double, sellPoint: Double, opportunity: String) -> Self {
        .init(
            side: side,
            rank: rank,
            symbol: symbol,
            name: name,
            price: price,
            changePercent: changePercent,
            volume: volume,
            buyPoint: buyPoint,
            sellPoint: sellPoint,
            opportunity: opportunity,
            quoteTime: quoteTime
        )
    }
}
