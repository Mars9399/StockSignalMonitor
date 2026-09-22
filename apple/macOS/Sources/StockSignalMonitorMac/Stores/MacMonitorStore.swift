import Foundation
import Observation
import StockSignalCore

@MainActor
@Observable
final class MacMonitorStore {
    var signals: [SignalPresentation] = []
    var watchlist: [String]
    var positions: [String: PositionInput]
    var selection: SidebarSelection? = .overview
    var listScope: SignalListScope = .all
    var isMonitoring = false
    var connectionMessage = "未启动"
    var isAddingSymbol = false
    var isSyncingTWSPositions = false
    var twsPositionMessage = "尚未同步"
    var lastError: String?
    var activityLog: [String] = []
    var priceMovements: [String: PriceMovement] = [:]
    var marketEntries: [MarketDirectoryEntry] = []
    var marketPage = 0
    var marketTotal = 0
    var marketSearchText = ""
    var marketDirectoryMessage = "分页浏览 Yahoo 美股市场；右键可加入自选"
    var isLoadingMarketDirectory = false

    let preferences: AppPreferences
    let credentials: ProviderCredentials

    private let backend: any MonitoringBackend
    private let twsPositionClient = TWSPositionClient()
    private let marketDirectoryService = YahooMarketDirectoryService()
    private var monitoringTask: Task<Void, Never>?
    private var monitoringGeneration = UUID()
    private var lastPresentedPrices: [String: Double] = [:]
    private let defaults: UserDefaults

    init(
        backend: (any MonitoringBackend)? = nil,
        preferences: AppPreferences? = nil,
        credentials: ProviderCredentials? = nil,
        defaults: UserDefaults = .standard
    ) {
        self.backend = backend ?? CoreMonitoringBackend()
        self.preferences = preferences ?? AppPreferences()
        self.credentials = credentials ?? ProviderCredentials()
        self.defaults = defaults
        watchlist = Self.loadWatchlist(defaults: defaults)
        positions = Self.loadPositions(defaults: defaults)
        signals = watchlist.map(SignalPresentation.placeholder)
    }

    var selectedSignal: SignalPresentation? {
        guard case let .symbol(symbol) = selection else { return nil }
        return signals.first { $0.symbol == symbol }
    }

    var displayedSignals: [SignalPresentation] {
        switch listScope {
        case .all:
            signals
        case .positions:
            signals.filter { hasPosition($0.symbol) }
        }
    }

    var positionCount: Int {
        watchlist.reduce(into: 0) { count, symbol in
            if hasPosition(symbol) { count += 1 }
        }
    }

    func hasPosition(_ symbol: String) -> Bool {
        positions[symbol]?.isEmpty == false
    }

    func toggleMonitoring() {
        isMonitoring ? stopMonitoring() : startMonitoring()
    }

    func startMonitoring(syncTWSPositions: Bool = true) {
        guard !isMonitoring else { return }
        lastError = nil
        isMonitoring = true
        connectionMessage = "正在连接 \(preferences.provider.rawValue)…"
        log("开始使用 \(preferences.provider.rawValue) 监控 \(watchlist.count) 只股票")

        let provider = preferences.providerConfiguration(credentials: credentials)
        let risk = preferences.riskConfiguration
        let generation = UUID()
        monitoringGeneration = generation
        monitoringTask = Task { [weak self, backend] in
            guard let self else { return }
            do {
                if provider.provider == .ibkr, syncTWSPositions {
                    connectionMessage = "正在从 TWS 同步只读持仓…"
                    try await importTWSPositions()
                }
                try Task.checkCancellation()
                let stream = try await backend.updates(
                    symbols: watchlist,
                    provider: provider,
                    risk: risk,
                    positions: positions
                )
                for await update in stream {
                    guard !Task.isCancelled else { break }
                    applySignals(update.signals)
                    if let message = update.message {
                        connectionMessage = message
                        log(message)
                    }
                }
            } catch is CancellationError {
                // User-requested stop.
            } catch {
                lastError = error.localizedDescription
                connectionMessage = "连接失败"
                log("连接错误：\(error.localizedDescription)")
            }
            if monitoringGeneration == generation { isMonitoring = false }
        }
    }

    func stopMonitoring() {
        guard isMonitoring else { return }
        monitoringTask?.cancel()
        monitoringGeneration = UUID()
        monitoringTask = nil
        isMonitoring = false
        connectionMessage = "已停止"
        for index in signals.indices {
            signals[index].action = "仅观察：监控已停止"
            signals[index].status = .noSignal
        }
        log("监控已停止")
        backend.stop()
    }

    func addSymbol(_ rawSymbol: String) {
        let symbol = rawSymbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard symbol.range(of: #"^[A-Z][A-Z0-9.\-]{0,9}$"#, options: .regularExpression) != nil,
              !watchlist.contains(symbol) else { return }
        watchlist.append(symbol)
        watchlist.sort()
        signals.append(.placeholder(symbol: symbol))
        persistWatchlist()
        selection = .symbol(symbol)
        restartIfNeeded()
    }

    func removeSelectedSymbol() {
        guard case let .symbol(symbol) = selection else { return }
        watchlist.removeAll { $0 == symbol }
        signals.removeAll { $0.symbol == symbol }
        positions.removeValue(forKey: symbol)
        selection = .overview
        persistWatchlist()
        persistPositions()
        restartIfNeeded()
    }

    func updatePosition(for symbol: String, input: PositionInput) {
        if input.isEmpty { positions.removeValue(forKey: symbol) }
        else { positions[symbol] = input }
        persistPositions()
        log(input.isEmpty ? "已清除 \(symbol) 持仓" : "已保存 \(symbol) 持仓：\(input.quantity.shareQuantityText) 股")
        restartIfNeeded()
    }

    func syncPositionsFromTWS() {
        guard !isSyncingTWSPositions else { return }
        let resumeMonitoring = isMonitoring
        if resumeMonitoring { stopMonitoring() }
        lastError = nil
        isSyncingTWSPositions = true
        twsPositionMessage = "正在连接 TWS…"
        Task { [weak self] in
            guard let self else { return }
            defer {
                isSyncingTWSPositions = false
                if resumeMonitoring { startMonitoring(syncTWSPositions: false) }
            }
            do {
                try await importTWSPositions()
            } catch {
                lastError = error.localizedDescription
                twsPositionMessage = "同步失败"
                log("TWS 持仓同步失败：\(error.localizedDescription)")
            }
        }
    }

    func clearAllPositions() {
        let resumeMonitoring = isMonitoring
        if resumeMonitoring { stopMonitoring() }
        positions.removeAll()
        defaults.removeObject(forKey: "twsImportedSymbols")
        persistPositions()
        twsPositionMessage = "本地持仓已清除"
        connectionMessage = twsPositionMessage
        log("已清除全部本地持仓；可使用“重新读取持仓”从 TWS 恢复")
        if resumeMonitoring { startMonitoring(syncTWSPositions: false) }
    }

    func refresh() {
        if isMonitoring { stopMonitoring() }
        startMonitoring()
    }

    private func restartIfNeeded() {
        guard isMonitoring else { return }
        stopMonitoring()
        startMonitoring(syncTWSPositions: false)
    }

    func loadMarketDirectory(page: Int? = nil) {
        guard !isLoadingMarketDirectory else { return }
        let requestedPage = max(0, page ?? marketPage)
        let query = marketSearchText.trimmingCharacters(in: .whitespacesAndNewlines)
        isLoadingMarketDirectory = true
        marketDirectoryMessage = query.isEmpty ? "正在读取全市场股票…" : "正在搜索 \(query)…"
        Task { [weak self] in
            guard let self else { return }
            defer { isLoadingMarketDirectory = false }
            do {
                let result = query.isEmpty
                    ? try await marketDirectoryService.page(requestedPage)
                    : try await marketDirectoryService.search(query)
                for entry in result.entries where entry.price > 0 {
                    registerPriceMovement(symbol: entry.symbol, price: entry.price)
                }
                marketEntries = result.entries
                marketPage = result.page
                marketTotal = result.total
                marketDirectoryMessage = query.isEmpty
                    ? "全市场约 \(result.total) 只 · 第 \(result.page + 1) 页"
                    : "搜索“\(query)” · 返回 \(result.entries.count) 只"
            } catch {
                marketDirectoryMessage = "全市场股票读取失败：\(error.localizedDescription)"
            }
        }
    }

    func clearMarketSearchAndLoad(page: Int) {
        marketSearchText = ""
        loadMarketDirectory(page: page)
    }

    func addMarketSymbol(_ symbol: String) {
        addSymbol(symbol)
    }

    private func applySignals(_ newSignals: [SignalPresentation]) {
        for signal in newSignals {
            guard let price = signal.currentPrice else { continue }
            registerPriceMovement(symbol: signal.symbol, price: price)
        }
        signals = newSignals
    }

    private func registerPriceMovement(symbol: String, price: Double) {
        defer { lastPresentedPrices[symbol] = price }
        guard let previous = lastPresentedPrices[symbol], previous != price else { return }
        priceMovements[symbol] = price > previous ? .up : .down
    }

    private func persistWatchlist() {
        defaults.set(watchlist, forKey: "watchlist")
    }

    private func persistPositions() {
        if let data = try? JSONEncoder().encode(positions) {
            defaults.set(data, forKey: "positions")
        }
    }

    private func importTWSPositions() async throws {
        guard (1...65_535).contains(preferences.twsPort),
              (0...Int(Int32.max)).contains(preferences.twsClientID) else {
            throw TWSImportError.invalidConfiguration
        }

        let snapshots = try await twsPositionClient.fetchPositions(
            host: preferences.twsHost,
            port: UInt16(preferences.twsPort),
            clientID: preferences.twsClientID
        )
        let requestedAccount = preferences.twsAccountID.trimmingCharacters(in: .whitespacesAndNewlines)
        try Task.checkCancellation()
        if !requestedAccount.isEmpty && !snapshots.isEmpty && !snapshots.contains(where: { $0.account.caseInsensitiveCompare(requestedAccount) == .orderedSame }) {
            throw NSError(domain: "TWS", code: 1, userInfo: [NSLocalizedDescriptionKey: "未找到指定账户，已保留原有持仓"])
        }
        let scoped = requestedAccount.isEmpty
            ? snapshots
            : snapshots.filter { $0.account.caseInsensitiveCompare(requestedAccount) == .orderedSame }

        var totals: [String: (quantity: Double, weightedCost: Double)] = [:]
        var skipped = 0
        for snapshot in scoped {
            let symbol = snapshot.symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
            guard snapshot.quantity != 0 else { continue }
            guard snapshot.securityType == "STK",
                  snapshot.currency == "USD",
                  snapshot.quantity > 0,
                  snapshot.averageCost > 0,
                  symbol.range(of: #"^[A-Z][A-Z0-9.\-]{0,9}$"#, options: .regularExpression) != nil else {
                skipped += 1
                continue
            }
            let existing = totals[symbol] ?? (0, 0)
            totals[symbol] = (
                existing.quantity + snapshot.quantity,
                existing.weightedCost + snapshot.averageCost * snapshot.quantity
            )
        }

        let importedKey = "twsImportedSymbols"
        let oldPositions = positions
        let previouslyImported = Set(defaults.stringArray(forKey: importedKey) ?? [])
        for symbol in previouslyImported { positions.removeValue(forKey: symbol) }

        let importedSymbols = Set(totals.keys)
        for (symbol, total) in totals where total.quantity > 0 {
            positions[symbol] = PositionInput(
                averageCost: total.weightedCost / total.quantity,
                quantity: total.quantity,
                initialStop: oldPositions[symbol].flatMap {
                    abs($0.averageCost - total.weightedCost / total.quantity) < 0.000001 && $0.quantity == total.quantity ? $0.initialStop : nil
                }
            )
            if !watchlist.contains(symbol) {
                watchlist.append(symbol)
                signals.append(.placeholder(symbol: symbol))
            }
        }

        watchlist.sort()
        let existingSignals = Dictionary(uniqueKeysWithValues: signals.map { ($0.symbol, $0) })
        signals = watchlist.map { existingSignals[$0] ?? .placeholder(symbol: $0) }
        defaults.set(Array(importedSymbols).sorted(), forKey: importedKey)
        persistWatchlist()
        persistPositions()

        let accountText = requestedAccount.isEmpty ? "全部可用账户" : requestedAccount
        twsPositionMessage = "已同步 \(importedSymbols.count) 只持仓 · \(accountText)"
        if skipped > 0 { twsPositionMessage += " · 跳过 \(skipped) 项不支持的持仓" }
        connectionMessage = twsPositionMessage
        log(twsPositionMessage)
    }

    private func log(_ message: String) {
        let timestamp = Date().formatted(SignalFormatting.timestamp)
        activityLog.append("[\(timestamp)] \(message)")
        if activityLog.count > 200 { activityLog.removeFirst(activityLog.count - 200) }
    }

    private static func loadWatchlist(defaults: UserDefaults) -> [String] {
        defaults.stringArray(forKey: "watchlist") ?? ["AAPL", "MSFT", "NVDA", "QQQ", "SPY"]
    }

    private static func loadPositions(defaults: UserDefaults) -> [String: PositionInput] {
        guard let data = defaults.data(forKey: "positions"),
              let positions = try? JSONDecoder().decode([String: PositionInput].self, from: data) else { return [:] }
        return positions
    }
}

private enum TWSImportError: LocalizedError {
    case invalidConfiguration

    var errorDescription: String? {
        "TWS 端口必须为 1–65535，Client ID 必须是非负整数。"
    }
}
