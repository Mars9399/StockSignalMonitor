import Foundation

struct MonitorUpdate: Sendable {
    var signals: [SignalPresentation]
    var message: String?
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
}
