import Foundation
import Observation

@MainActor
@Observable
final class AppPreferences {
    private enum Key {
        static let provider = "marketDataProvider"
        static let accountValue = "risk.accountValue"
        static let riskPercent = "risk.percent"
        static let maxPositionPercent = "risk.maxPositionPercent"
        static let twsHost = "tws.host"
        static let twsPort = "tws.port"
        static let twsClientID = "tws.clientID"
        static let twsAccountID = "tws.accountID"
        static let windowWidth = "ui.windowWidth"
        static let windowHeight = "ui.windowHeight"
        static let interfaceScale = "ui.interfaceScale"
        static let tableRowHeight = "ui.tableRowHeight"
        static let logHeight = "ui.logHeight"
        static let showActivityLog = "ui.showActivityLog"
        static let autoStartMonitoring = "monitor.autoStart"
    }

    var provider: MarketDataProvider { didSet { defaults.set(provider.rawValue, forKey: Key.provider) } }
    var accountValue: Double { didSet { defaults.set(accountValue, forKey: Key.accountValue) } }
    var riskPercent: Double { didSet { defaults.set(riskPercent, forKey: Key.riskPercent) } }
    var maximumPositionPercent: Double { didSet { defaults.set(maximumPositionPercent, forKey: Key.maxPositionPercent) } }
    var twsHost: String { didSet { defaults.set(twsHost, forKey: Key.twsHost) } }
    var twsPort: Int { didSet { defaults.set(twsPort, forKey: Key.twsPort) } }
    var twsClientID: Int { didSet { defaults.set(twsClientID, forKey: Key.twsClientID) } }
    var twsAccountID: String { didSet { defaults.set(twsAccountID, forKey: Key.twsAccountID) } }
    var windowWidth: Double { didSet { defaults.set(windowWidth, forKey: Key.windowWidth) } }
    var windowHeight: Double { didSet { defaults.set(windowHeight, forKey: Key.windowHeight) } }
    var interfaceScale: Double { didSet { defaults.set(interfaceScale, forKey: Key.interfaceScale) } }
    var tableRowHeight: Double { didSet { defaults.set(tableRowHeight, forKey: Key.tableRowHeight) } }
    var logHeight: Double { didSet { defaults.set(logHeight, forKey: Key.logHeight) } }
    var showActivityLog: Bool { didSet { defaults.set(showActivityLog, forKey: Key.showActivityLog) } }
    var autoStartMonitoring: Bool { didSet { defaults.set(autoStartMonitoring, forKey: Key.autoStartMonitoring) } }

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        provider = MarketDataProvider(rawValue: defaults.string(forKey: Key.provider) ?? "") ?? .yahoo
        accountValue = defaults.object(forKey: Key.accountValue) as? Double ?? 100_000
        riskPercent = defaults.object(forKey: Key.riskPercent) as? Double ?? 1
        maximumPositionPercent = defaults.object(forKey: Key.maxPositionPercent) as? Double ?? 10
        twsHost = defaults.string(forKey: Key.twsHost) ?? "127.0.0.1"
        twsPort = defaults.object(forKey: Key.twsPort) as? Int ?? 7497
        twsClientID = defaults.object(forKey: Key.twsClientID) as? Int ?? 17
        twsAccountID = defaults.string(forKey: Key.twsAccountID) ?? ""
        windowWidth = defaults.object(forKey: Key.windowWidth) as? Double ?? 1180
        windowHeight = defaults.object(forKey: Key.windowHeight) as? Double ?? 760
        interfaceScale = defaults.object(forKey: Key.interfaceScale) as? Double ?? 1
        tableRowHeight = defaults.object(forKey: Key.tableRowHeight) as? Double ?? 32
        logHeight = defaults.object(forKey: Key.logHeight) as? Double ?? 105
        showActivityLog = defaults.object(forKey: Key.showActivityLog) as? Bool ?? true
        autoStartMonitoring = defaults.object(forKey: Key.autoStartMonitoring) as? Bool ?? false
    }

    var riskConfiguration: RiskConfiguration {
        return .init(
            accountValue: accountValue,
            riskPercent: riskPercent,
            maximumPositionPercent: maximumPositionPercent
        )
    }

    func providerConfiguration(credentials: ProviderCredentials) -> ProviderConfigurationSnapshot {
        let apiKey: String
        let apiSecret: String
        switch provider {
        case .alpaca:
            apiKey = credentials.alpacaAPIKey
            apiSecret = credentials.alpacaAPISecret
        case .massive:
            apiKey = credentials.massiveAPIKey
            apiSecret = ""
        case .yahoo, .ibkr:
            apiKey = ""
            apiSecret = ""
        }

        return .init(
            provider: provider,
            apiKey: apiKey,
            apiSecret: apiSecret
        )
    }

    func restoreInterfaceDefaults() {
        windowWidth = 1180
        windowHeight = 760
        interfaceScale = 1
        tableRowHeight = 32
        logHeight = 105
        showActivityLog = true
        autoStartMonitoring = false
    }
}
