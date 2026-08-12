import Foundation
import StockSignalCore

/// Persists only non-sensitive UI settings. Market-data secrets stay exclusively in Keychain.
@MainActor
enum AppPreferences {
    private enum Key {
        static let providerKind = "marketData.providerKind"
        static let alpacaFeed = "marketData.alpaca.feed"
        static let massiveBaseURL = "marketData.massive.baseURL"
        static let ibkrBaseURL = "marketData.ibkr.baseURL"
        static let ibkrAccountID = "marketData.ibkr.accountID"
        static let accountValue = "risk.accountValue"
        static let riskPercent = "risk.riskPercent"
        static let maxPositionPercent = "risk.maxPositionPercent"
    }

    static func restoredConfiguration(
        defaults: UserDefaults = .standard,
        credentials: KeychainCredentialStore = .shared
    ) -> DataProviderConfiguration {
        let kind = defaults.string(forKey: Key.providerKind)
            .flatMap { MarketDataProviderKind(rawValue: $0) } ?? .yahoo

        switch kind {
        case .yahoo:
            return .yahoo
        case .alpaca:
            let apiKey = (try? credentials.value(for: .alpacaAPIKey)) ?? ""
            let apiSecret = (try? credentials.value(for: .alpacaAPISecret)) ?? ""
            let feed = defaults.string(forKey: Key.alpacaFeed) ?? "iex"
            return .alpaca(apiKey: apiKey, apiSecret: apiSecret, feed: feed)
        case .massive:
            let apiKey = (try? credentials.value(for: .massiveAPIKey)) ?? ""
            let url = defaults.string(forKey: Key.massiveBaseURL)
                .flatMap { URL(string: $0) } ?? URL(string: "https://api.massive.com")!
            return .massive(apiKey: apiKey, baseURL: url)
        case .ibkrClientPortal:
            let url = defaults.string(forKey: Key.ibkrBaseURL)
                .flatMap { URL(string: $0) } ?? URL(string: "https://localhost:5000/v1/api")!
            let accountID = defaults.string(forKey: Key.ibkrAccountID)
                .flatMap { $0.isEmpty ? nil : $0 }
            return .ibkrClientPortal(baseURL: url, accountID: accountID)
        }
    }

    static func restoredRiskSettings(defaults: UserDefaults = .standard) -> RiskSettings {
        RiskSettings(
            accountValue: storedDouble(forKey: Key.accountValue, fallback: 100_000, defaults: defaults),
            riskPercent: storedDouble(forKey: Key.riskPercent, fallback: 1, defaults: defaults),
            maxPositionPercent: storedDouble(forKey: Key.maxPositionPercent, fallback: 10, defaults: defaults)
        )
    }

    static func save(_ configuration: DataProviderConfiguration, defaults: UserDefaults = .standard) {
        defaults.set(configuration.kind.rawValue, forKey: Key.providerKind)
        switch configuration {
        case .yahoo:
            break
        case let .alpaca(_, _, feed):
            defaults.set(feed, forKey: Key.alpacaFeed)
        case let .massive(_, baseURL):
            defaults.set(baseURL.absoluteString, forKey: Key.massiveBaseURL)
        case let .ibkrClientPortal(baseURL, accountID):
            defaults.set(baseURL.absoluteString, forKey: Key.ibkrBaseURL)
            if let accountID, !accountID.isEmpty {
                defaults.set(accountID, forKey: Key.ibkrAccountID)
            } else {
                defaults.removeObject(forKey: Key.ibkrAccountID)
            }
        }
    }

    static func save(_ settings: RiskSettings, defaults: UserDefaults = .standard) {
        defaults.set(settings.accountValue, forKey: Key.accountValue)
        defaults.set(settings.riskPercent, forKey: Key.riskPercent)
        defaults.set(settings.maxPositionPercent, forKey: Key.maxPositionPercent)
    }

    private static func storedDouble(
        forKey key: String,
        fallback: Double,
        defaults: UserDefaults
    ) -> Double {
        guard defaults.object(forKey: key) != nil else { return fallback }
        return defaults.double(forKey: key)
    }
}
