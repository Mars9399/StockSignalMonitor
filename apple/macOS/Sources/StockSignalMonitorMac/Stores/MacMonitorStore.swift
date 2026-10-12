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
    var twsAccountSummary: TWSAccountSummary?
    var twsAccountSummaryMessage = "尚未读取账户情况"
    var isLoadingTWSAccountSummary = false
    var isTWSAccountSummaryHidden = false
    var lastError: String?
    var activityLog: [String] = []
    var priceMovements: [String: PriceMovement] = [:]
    var marketEntries: [MarketDirectoryEntry] = []
    var marketRegion: MarketRegion = .us
    var marketPage = 0
    var marketTotal = 0
    var marketSearchText = ""
    var marketDirectoryMessage = "分页浏览 Yahoo 美股市场；右键可加入自选"
    var isLoadingMarketDirectory = false
    var marketGainers: [MarketMoverEntry] = []
    var marketLosers: [MarketMoverEntry] = []
    var marketMoverSector: MarketSector = .all
    var marketMoversMessage = "Yahoo 美股当日涨跌榜；结合 10 日价格通道辅助判断"
    var isLoadingMarketMovers = false
    var marketMoversUpdatedAt: Date?

    let preferences: AppPreferences
    let credentials: ProviderCredentials

    private let backend: any MonitoringBackend
    private let twsPositionClient = TWSPositionClient()
    private let marketDirectoryService = YahooMarketDirectoryService()
    private let marketMoverService = YahooMarketMoverService()
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
                    var baselineChanged = false
                    for (symbol, candidate) in update.positions {
                        if let current = positions[symbol], current.initialStop == nil,
                           candidate.initialStop != nil, current.quantity == candidate.quantity,
                           current.averageCost == candidate.averageCost {
                            positions[symbol] = candidate
                            baselineChanged = true
                        }
                    }
                    if baselineChanged { persistPositions() }
                    if let message = update.message {
                        connectionMessage = message
                        log(message)
                    }
                }
            } catch is CancellationError {
                // User-requested stop.
            } catch {
                lastError = error.localizedDescription
                connectionMessage = "连接失败：\(error.localizedDescription)"
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
        guard symbol.range(of: #"^[A-Z0-9][A-Z0-9.\-]{0,11}$"#, options: .regularExpression) != nil,
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
        guard !isSyncingTWSPositions, !isLoadingTWSAccountSummary else { return }
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
                twsPositionMessage = "同步失败 · \(preferences.twsHost):\(preferences.twsPort)"
                connectionMessage = "TWS 连接失败：\(error.localizedDescription)"
                log("TWS 持仓同步失败（\(preferences.twsHost):\(preferences.twsPort)）：\(error.localizedDescription)")
            }
        }
    }

    func refreshTWSAccountSummary() {
        guard preferences.provider == .ibkr,
              !isLoadingTWSAccountSummary,
              !isSyncingTWSPositions else { return }
        lastError = nil
        isLoadingTWSAccountSummary = true
        twsAccountSummaryMessage = "正在读取账户情况…"
        Task { [weak self] in
            guard let self else { return }
            defer { isLoadingTWSAccountSummary = false }
            do {
                let result = try await readTWSAccountSummary()
                applyTWSAccountSummary(result.summary, includesLivePnL: result.includesLivePnL)
            } catch {
                twsAccountSummaryMessage = "账户情况读取失败：\(error.localizedDescription)"
                log("TWS 账户情况读取失败：\(error.localizedDescription)")
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
        let requestedMarket = marketRegion
        isLoadingMarketDirectory = true
        marketDirectoryMessage = query.isEmpty
            ? "正在读取\(requestedMarket.displayName)全市场股票…"
            : "正在搜索\(requestedMarket.displayName) \(query)…"
        Task { [weak self] in
            guard let self else { return }
            defer { isLoadingMarketDirectory = false }
            do {
                let result = query.isEmpty
                    ? try await marketDirectoryService.page(requestedPage, market: requestedMarket)
                    : try await marketDirectoryService.search(query, market: requestedMarket)
                guard result.market == marketRegion else { return }
                for entry in result.entries where entry.price > 0 {
                    registerPriceMovement(symbol: entry.symbol, price: entry.price)
                }
                marketEntries = result.entries
                marketPage = result.page
                marketTotal = result.total
                marketDirectoryMessage = query.isEmpty
                    ? "\(result.market.displayName)全市场约 \(result.total) 只 · 第 \(result.page + 1) 页"
                    : "\(result.market.displayName)搜索“\(query)” · 返回 \(result.entries.count) 只"
            } catch {
                marketDirectoryMessage = "全市场股票读取失败：\(error.localizedDescription)"
            }
        }
    }

    func selectMarketRegion(_ region: MarketRegion) {
        guard marketRegion != region, !isLoadingMarketDirectory else { return }
        marketRegion = region
        marketSearchText = ""
        marketEntries = []
        marketPage = 0
        marketTotal = 0
        loadMarketDirectory(page: 0)
    }

    func clearMarketSearchAndLoad(page: Int) {
        marketSearchText = ""
        loadMarketDirectory(page: page)
    }

    func addMarketSymbol(_ symbol: String) {
        addSymbol(symbol)
    }

    func loadMarketMovers() {
        guard !isLoadingMarketMovers else { return }
        let requestedSector = marketMoverSector
        isLoadingMarketMovers = true
        marketMoversMessage = "正在读取\(requestedSector.displayName)涨跌 Top 20 并分析价格通道…"
        Task { [weak self] in
            guard let self else { return }
            defer { isLoadingMarketMovers = false }
            do {
                let snapshot = try await marketMoverService.snapshot(
                    sector: requestedSector,
                    limit: YahooMarketMoverService.defaultLimit
                )
                guard requestedSector == marketMoverSector else { return }
                for entry in snapshot.gainers + snapshot.losers where entry.price > 0 {
                    registerPriceMovement(symbol: entry.symbol, price: entry.price)
                }
                marketGainers = snapshot.gainers
                marketLosers = snapshot.losers
                marketMoversUpdatedAt = snapshot.updatedAt
                marketMoversMessage = "\(requestedSector.displayName) · 已更新 \(snapshot.gainers.count) 只涨幅榜、\(snapshot.losers.count) 只跌幅榜"
            } catch {
                marketMoversMessage = "\(requestedSector.displayName) Top 20 读取失败：\(error.localizedDescription)"
            }
        }
    }

    func selectMarketMoverSector(_ sector: MarketSector) {
        guard sector != marketMoverSector, !isLoadingMarketMovers else { return }
        marketMoverSector = sector
        marketGainers = []
        marketLosers = []
        marketMoversUpdatedAt = nil
        loadMarketMovers()
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
                },
                riskReferencePrice: oldPositions[symbol].flatMap {
                    abs($0.averageCost - total.weightedCost / total.quantity) < 0.000001 && $0.quantity == total.quantity ? $0.riskReferencePrice : nil
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

        do {
            let result = try await readTWSAccountSummary()
            applyTWSAccountSummary(result.summary, includesLivePnL: result.includesLivePnL)
        } catch {
            twsAccountSummaryMessage = "账户情况读取失败：\(error.localizedDescription)"
            log("持仓已同步，但 TWS 账户情况读取失败：\(error.localizedDescription)")
        }

        let accountText = requestedAccount.isEmpty ? "全部可用账户" : requestedAccount
        twsPositionMessage = "已同步 \(importedSymbols.count) 只持仓 · \(accountText)"
        if skipped > 0 { twsPositionMessage += " · 跳过 \(skipped) 项不支持的持仓" }
        connectionMessage = twsPositionMessage
        log(twsPositionMessage)
    }

    private func readTWSAccountSummary() async throws -> (summary: TWSAccountSummary, includesLivePnL: Bool) {
        guard (1...65_535).contains(preferences.twsPort),
              (0...Int(Int32.max)).contains(preferences.twsClientID) else {
            throw TWSImportError.invalidConfiguration
        }
        let summary = try await twsPositionClient.fetchAccountSummary(
            host: preferences.twsHost,
            port: UInt16(preferences.twsPort),
            clientID: TWSPositionClient.auxiliaryClientID(base: preferences.twsClientID),
            accountID: preferences.twsAccountID
        )
        do {
            let pnl = try await twsPositionClient.fetchPnL(
                host: preferences.twsHost,
                port: UInt16(preferences.twsPort),
                clientID: TWSPositionClient.auxiliaryClientID(base: preferences.twsClientID, offset: 102),
                accountID: summary.account
            )
            return (summary.merging(pnl: pnl), true)
        } catch {
            log("TWS 资金数据已读取，但实时盈亏暂不可用：\(error.localizedDescription)")
            return (summary, false)
        }
    }

    private func applyTWSAccountSummary(_ summary: TWSAccountSummary, includesLivePnL: Bool) {
        twsAccountSummary = summary
        let pnlStatus = includesLivePnL ? "实时盈亏已同步" : "盈亏暂不可用"
        twsAccountSummaryMessage = "账户 \(summary.account) · \(pnlStatus) · 已更新 \(Date.now.formatted(date: .omitted, time: .standard))"
        log("已读取 TWS 账户 \(summary.account) 情况 · \(pnlStatus)")
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
