import Foundation
import StockSignalCore

@MainActor
final class CoreMonitoringBackend: MonitoringBackend {
    private var coreStore: StockSignalCore.MonitorStore?
    private var relayTask: Task<Void, Never>?
    private var generation = UUID()

    func updates(
        symbols: [String],
        provider: ProviderConfigurationSnapshot,
        risk: RiskConfiguration,
        positions: [String: PositionInput]
    ) async throws -> AsyncStream<MonitorUpdate> {
        stop()
        let generation = UUID()
        self.generation = generation

        let configuration = try makeConfiguration(provider)
        let riskSettings = StockSignalCore.RiskSettings(
            accountValue: risk.accountValue,
            riskPercent: risk.riskPercent,
            maxPositionPercent: risk.maximumPositionPercent
        )
        let store = StockSignalCore.MonitorStore(
            symbols: symbols,
            riskSettings: riskSettings,
            configuration: configuration
        )
        for (symbol, position) in positions {
            store.updatePosition(
                StockSignalCore.Position(
                    symbol: symbol,
                    averageCost: position.averageCost,
                    quantity: position.quantity,
                    initialStop: position.initialStop
                )
            )
        }
        coreStore = store

        let pair = AsyncStream<MonitorUpdate>.makeStream()
        relayTask = Task { @MainActor [weak self, weak store] in
            guard let self, let store else {
                pair.continuation.finish()
                return
            }

            store.startMonitoring(interval: .seconds(15))
            var lastMessage = ""
            while !Task.isCancelled {
                let message = store.connectionMessage
                pair.continuation.yield(
                    .init(
                        signals: store.stocks.map(Self.present),
                        message: message == lastMessage ? nil : message
                    )
                )
                lastMessage = message

                if !store.isMonitoring, store.lastUpdated != nil || store.errorMessage != nil {
                    if let error = store.errorMessage {
                        pair.continuation.yield(.init(signals: store.stocks.map(Self.present), message: "行情错误：\(error)"))
                    }
                    break
                }

                do {
                    try await Task.sleep(for: .milliseconds(500))
                } catch {
                    break
                }
            }

            store.stopMonitoring()
            if self.coreStore === store { self.coreStore = nil }
            pair.continuation.finish()
        }

        pair.continuation.onTermination = { @Sendable [weak self] _ in
            Task { @MainActor in
                guard self?.generation == generation else { return }
                self?.stop()
            }
        }
        return pair.stream
    }

    func stop() {
        relayTask?.cancel()
        relayTask = nil
        coreStore?.stopMonitoring()
        coreStore = nil
    }

    private func makeConfiguration(_ snapshot: ProviderConfigurationSnapshot) throws -> DataProviderConfiguration {
        switch snapshot.provider {
        case .yahoo:
            return .yahoo
        case .alpaca:
            return .alpaca(apiKey: snapshot.apiKey, apiSecret: snapshot.apiSecret, feed: "iex")
        case .massive:
            return .massive(apiKey: snapshot.apiKey)
        case .ibkr:
            // TWS supplies read-only positions. Yahoo remains the quote/history
            // source so the macOS client no longer needs Client Portal Gateway.
            return .yahoo
        }
    }

    private static func present(_ stock: MonitoredStock) -> SignalPresentation {
        let levels = stock.levels
        let plan = stock.plan
        return .init(
            symbol: stock.symbol,
            companyName: CompanyNameResolver.resolve(symbol: stock.symbol, suppliedName: stock.name),
            currentPrice: stock.quote?.price,
            buyTrigger: positive(levels?.buyPoint),
            riskReductionPoint: positive(plan?.riskReductionPoint ?? levels?.stopPoint ?? 0),
            profitTarget2R: positive(plan?.profitTarget2R),
            profitTarget3R: positive(plan?.profitTarget3R),
            status: presentationStatus(levels: levels, plan: plan, error: stock.errorMessage),
            signalQuality: levels.map { "\($0.quality.rawValue) · \($0.modelName)" } ?? "—",
            action: actionText(plan?.action),
            updatedAt: stock.quote?.timestamp,
            historyDays: levels?.historyDays ?? 0
        )
    }

    private static func presentationStatus(
        levels: SignalLevels?,
        plan: PositionPlan?,
        error: String?
    ) -> PresentationSignalStatus {
        if error != nil { return .unavailable }
        guard let levels else { return .loading }
        if let plan {
            switch plan.action {
            case .reduceForRisk, .reduceForExposure: return .riskReduction
            case .reduceAt2R, .reduceAt3R: return .profitTaking
            default: break
            }
        }
        switch levels.status {
        case .dataShort: return .dataShort
        case .buyAlert: return .buyAlert
        case .watch: return .watch
        case .noSignal: return .noSignal
        }
    }

    private static func actionText(_ action: PositionAction?) -> String {
        guard let action else { return "等待行情与历史数据" }
        switch action {
        case .needsRiskBaseline:
            return "请设置初始风险线；暂停仓位建议"
        case let .observationOnly(reason):
            return "仅观察：\(reason)"
        case .insufficientHistory:
            return "历史不足，仅观察，不给出仓位意见"
        case let .reduceForRisk(shares):
            return "跌破风险线，参考减仓 \(shares) 股"
        case let .reduceForExposure(shares):
            return "超过单股上限，参考减仓 \(shares) 股"
        case let .reduceAt2R(shares):
            return "达到 2R，参考盈利减仓 \(shares) 股"
        case let .reduceAt3R(shares):
            return "达到 3R，参考盈利减仓 \(shares) 股"
        case let .addAfterBreakout(maximumShares):
            return "突破确认后，最多参考加仓 \(maximumShares) 股"
        case let .openAfterBreakout(maximumShares):
            return "突破确认后，最多参考买入 \(maximumShares) 股"
        case let .wait(candidateMaximumShares):
            return "继续观察；触发后候选上限 \(candidateMaximumShares) 股"
        case .hold:
            return "持有观察，暂不加减仓"
        }
    }

    private static func positive(_ value: Double?) -> Double? {
        guard let value, value > 0 else { return nil }
        return value
    }
}
