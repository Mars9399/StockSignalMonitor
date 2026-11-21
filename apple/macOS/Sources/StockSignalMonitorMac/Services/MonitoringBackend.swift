import Foundation

struct MonitorUpdate: Sendable {
    var signals: [SignalPresentation]
    var message: String?
    var positions: [String: PositionInput] = [:]
}

@MainActor
protocol MonitoringBackend: AnyObject {
    func updates(
        symbols: [String],
        provider: ProviderConfigurationSnapshot,
        risk: RiskConfiguration,
        positions: [String: PositionInput]
    ) async throws -> AsyncStream<MonitorUpdate>

    func stop()

    /// Optional live account values for leverage-aware holding diagnosis.
    func setAccountContext(netLiquidation: Double?, grossPositionValue: Double?)
}
