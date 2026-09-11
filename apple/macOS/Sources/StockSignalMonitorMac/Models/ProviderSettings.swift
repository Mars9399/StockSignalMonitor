import Foundation

enum MarketDataProvider: String, CaseIterable, Codable, Identifiable, Sendable {
    case alpaca = "Alpaca IEX"
    case yahoo = "Yahoo Finance"
    case massive = "Massive / Polygon"
    case ibkr = "IBKR TWS + Yahoo 行情"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .alpaca: "bolt.horizontal.circle"
        case .yahoo: "network"
        case .massive: "waveform.path.ecg"
        case .ibkr: "desktopcomputer"
        }
    }

    var needsAPIKey: Bool { self == .alpaca || self == .massive }
}

struct ProviderConfigurationSnapshot: Sendable {
    var provider: MarketDataProvider
    var apiKey: String
    var apiSecret: String
}

struct RiskConfiguration: Codable, Sendable {
    var accountValue: Double = 100_000
    var riskPercent: Double = 1
    var maximumPositionPercent: Double = 10
}
