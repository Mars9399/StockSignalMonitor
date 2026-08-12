import Foundation
import Observation

@MainActor
@Observable
public final class MonitorStore {
    public private(set) var stocks: [MonitoredStock]
    public private(set) var isMonitoring = false
    public private(set) var connectionMessage = "未启动"
    public private(set) var lastUpdated: Date?
    public private(set) var errorMessage: String?
    public var riskSettings: RiskSettings
    public var configuration: DataProviderConfiguration

    @ObservationIgnored private let serviceFactory: MarketDataServiceFactory
    @ObservationIgnored private var service: (any MarketDataService)?
    @ObservationIgnored private var histories: [String: [DailyBar]] = [:]
    @ObservationIgnored private var monitoringTask: Task<Void, Never>?

    public var symbols: [String] { stocks.map(\.symbol) }
    public var providerKind: MarketDataProviderKind { configuration.kind }

    public init(
        symbols: [String] = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"],
        riskSettings: RiskSettings = RiskSettings(),
        configuration: DataProviderConfiguration = .yahoo,
        serviceFactory: @escaping MarketDataServiceFactory = { configuration in
            try defaultMarketDataService(configuration: configuration)
        }
    ) {
        let normalized = Self.normalizedSymbols(symbols)
        self.stocks = normalized.map {
            MonitoredStock(symbol: $0, name: CompanyNameResolver.name(for: $0) ?? "")
        }
        self.riskSettings = riskSettings
        self.configuration = configuration
        self.serviceFactory = serviceFactory
    }

    deinit { monitoringTask?.cancel() }

    public func addSymbol(_ symbol: String, name: String = "") {
        guard let normalized = Self.normalize(symbol), !symbols.contains(normalized) else { return }
        let suppliedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedName = suppliedName.isEmpty ? CompanyNameResolver.name(for: normalized) ?? "" : suppliedName
        stocks.append(MonitoredStock(symbol: normalized, name: resolvedName))
    }

    public func removeSymbol(_ symbol: String) {
        let normalized = symbol.uppercased()
        stocks.removeAll { $0.symbol == normalized }
        histories.removeValue(forKey: normalized)
    }

    public func updatePosition(_ position: Position) {
        guard let index = stocks.firstIndex(where: { $0.symbol == position.symbol.uppercased() }) else { return }
        stocks[index].position = position
        recalculatePlan(at: index)
    }

    public func setRiskSettings(_ settings: RiskSettings) {
        riskSettings = settings
        for index in stocks.indices { recalculatePlan(at: index) }
    }

    public func setConfiguration(_ configuration: DataProviderConfiguration) {
        stopMonitoring()
        self.configuration = configuration
        service = nil
        histories = [:]
        errorMessage = nil
        connectionMessage = "数据源已切换至 \(configuration.kind.displayName)"
    }

    public func refresh() async {
        errorMessage = nil
        connectionMessage = "正在更新 \(configuration.kind.displayName) 行情…"
        do {
            let service = try resolvedService()
            let requestedSymbols = symbols
            for symbol in requestedSymbols {
                do {
                    async let history = service.history(for: symbol, lookbackDays: 730)
                    async let quote = service.quote(for: symbol)
                    let (loadedHistory, latestQuote) = try await (history, quote)
                    histories[symbol] = loadedHistory
                    if let index = stocks.firstIndex(where: { $0.symbol == symbol }) {
                        apply(quote: latestQuote, history: loadedHistory, at: index)
                    }
                } catch {
                    if let index = stocks.firstIndex(where: { $0.symbol == symbol }) {
                        stocks[index].errorMessage = error.localizedDescription
                    }
                }
            }
            lastUpdated = .now
            connectionMessage = "\(configuration.kind.displayName) 行情已更新"
        } catch {
            errorMessage = error.localizedDescription
            connectionMessage = "连接失败"
        }
    }

    public func startMonitoring(interval: Duration = .seconds(15)) {
        guard !isMonitoring else { return }
        isMonitoring = true
        errorMessage = nil
        monitoringTask = Task { [weak self] in
            guard let self else { return }
            await self.refresh()
            guard !Task.isCancelled else { return }
            do {
                let service = try self.resolvedService()
                self.connectionMessage = "正在监控 \(self.configuration.kind.displayName) 行情"
                for try await quotes in service.quoteStream(for: self.symbols, pollInterval: interval) {
                    guard !Task.isCancelled else { break }
                    for quote in quotes { self.applyLiveQuote(quote) }
                    self.lastUpdated = .now
                }
            } catch is CancellationError {
                // Normal stop.
            } catch {
                self.errorMessage = error.localizedDescription
                self.connectionMessage = "监控中断"
            }
            self.isMonitoring = false
        }
    }

    public func stopMonitoring() {
        monitoringTask?.cancel()
        monitoringTask = nil
        isMonitoring = false
        connectionMessage = "已停止"
    }

    private func resolvedService() throws -> any MarketDataService {
        if let service { return service }
        let created = try serviceFactory(configuration)
        service = created
        return created
    }

    private func applyLiveQuote(_ quote: StockQuote) {
        guard let index = stocks.firstIndex(where: { $0.symbol == quote.symbol }),
              let history = histories[quote.symbol] else { return }
        apply(quote: quote, history: history, at: index)
    }

    private func apply(quote: StockQuote, history: [DailyBar], at index: Int) {
        stocks[index].quote = quote
        do {
            let levels = try SignalCalculator.calculate(history: history, livePrice: quote.price)
            stocks[index].levels = levels
            stocks[index].plan = PositionPlanner.makePlan(levels: levels, position: stocks[index].position, settings: riskSettings)
            stocks[index].errorMessage = nil
        } catch {
            stocks[index].errorMessage = error.localizedDescription
        }
    }

    private func recalculatePlan(at index: Int) {
        guard let levels = stocks[index].levels else { return }
        stocks[index].plan = PositionPlanner.makePlan(levels: levels, position: stocks[index].position, settings: riskSettings)
    }

    private static func normalizedSymbols(_ symbols: [String]) -> [String] {
        var seen: Set<String> = []
        return symbols.compactMap(normalize).filter { seen.insert($0).inserted }
    }

    private static func normalize(_ symbol: String) -> String? {
        let normalized = symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        return normalized.isEmpty ? nil : normalized
    }
}
