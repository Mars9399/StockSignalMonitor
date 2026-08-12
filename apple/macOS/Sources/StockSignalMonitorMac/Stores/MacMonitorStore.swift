import Foundation
import Observation

@MainActor
@Observable
final class MacMonitorStore {
    var signals: [SignalPresentation] = []
    var watchlist: [String]
    var positions: [String: PositionInput]
    var selection: SidebarSelection? = .overview
    var isMonitoring = false
    var connectionMessage = "未启动"
    var isAddingSymbol = false
    var lastError: String?
    var activityLog: [String] = []

    let preferences: AppPreferences
    let credentials: ProviderCredentials

    private let backend: any MonitoringBackend
    private var monitoringTask: Task<Void, Never>?
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

    func toggleMonitoring() {
        isMonitoring ? stopMonitoring() : startMonitoring()
    }

    func startMonitoring() {
        guard !isMonitoring else { return }
        lastError = nil
        isMonitoring = true
        connectionMessage = "正在连接 \(preferences.provider.rawValue)…"
        log("开始使用 \(preferences.provider.rawValue) 监控 \(watchlist.count) 只股票")

        let symbols = watchlist
        let provider = preferences.providerConfiguration(credentials: credentials)
        let risk = preferences.riskConfiguration
        let positionSnapshot = positions
        monitoringTask = Task { [weak self, backend] in
            do {
                let stream = try await backend.updates(
                    symbols: symbols,
                    provider: provider,
                    risk: risk,
                    positions: positionSnapshot
                )
                for await update in stream {
                    guard !Task.isCancelled else { break }
                    self?.signals = update.signals
                    if let message = update.message {
                        self?.connectionMessage = message
                        self?.log(message)
                    }
                }
            } catch is CancellationError {
                // User-requested stop.
            } catch {
                self?.lastError = error.localizedDescription
                self?.connectionMessage = "连接失败"
                self?.log("行情错误：\(error.localizedDescription)")
            }
            self?.isMonitoring = false
        }
    }

    func stopMonitoring() {
        guard isMonitoring else { return }
        monitoringTask?.cancel()
        monitoringTask = nil
        isMonitoring = false
        connectionMessage = "已停止"
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
        log(input.isEmpty ? "已清除 \(symbol) 持仓" : "已保存 \(symbol) 持仓：\(input.quantity) 股")
        restartIfNeeded()
    }

    func refresh() {
        if isMonitoring { stopMonitoring() }
        startMonitoring()
    }

    private func restartIfNeeded() {
        guard isMonitoring else { return }
        stopMonitoring()
        startMonitoring()
    }

    private func persistWatchlist() {
        defaults.set(watchlist, forKey: "watchlist")
    }

    private func persistPositions() {
        if let data = try? JSONEncoder().encode(positions) {
            defaults.set(data, forKey: "positions")
        }
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
