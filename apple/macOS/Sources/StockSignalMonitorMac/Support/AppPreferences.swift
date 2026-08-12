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
        static let ibkrBaseURL = "ibkr.baseURL"
        static let ibkrAccountID = "ibkr.accountID"
    }

    var provider: MarketDataProvider { didSet { defaults.set(provider.rawValue, forKey: Key.provider) } }
    var accountValue: Double { didSet { defaults.set(accountValue, forKey: Key.accountValue) } }
    var riskPercent: Double { didSet { defaults.set(riskPercent, forKey: Key.riskPercent) } }
    var maximumPositionPercent: Double { didSet { defaults.set(maximumPositionPercent, forKey: Key.maxPositionPercent) } }
    var ibkrBaseURL: String { didSet { defaults.set(ibkrBaseURL, forKey: Key.ibkrBaseURL) } }
    var ibkrAccountID: String { didSet { defaults.set(ibkrAccountID, forKey: Key.ibkrAccountID) } }

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        provider = MarketDataProvider(rawValue: defaults.string(forKey: Key.provider) ?? "") ?? .yahoo
        accountValue = defaults.object(forKey: Key.accountValue) as? Double ?? 100_000
        riskPercent = defaults.object(forKey: Key.riskPercent) as? Double ?? 1
        maximumPositionPercent = defaults.object(forKey: Key.maxPositionPercent) as? Double ?? 10
        ibkrBaseURL = defaults.string(forKey: Key.ibkrBaseURL) ?? "https://localhost:5000/v1/api"
        ibkrAccountID = defaults.string(forKey: Key.ibkrAccountID) ?? ""
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
            apiSecret: apiSecret,
            ibkrBaseURL: ibkrBaseURL,
            ibkrAccountID: ibkrAccountID
        )
    }
}
