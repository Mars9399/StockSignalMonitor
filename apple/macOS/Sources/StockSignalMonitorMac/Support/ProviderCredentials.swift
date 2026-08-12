import Foundation
import Observation
import Security

@MainActor
@Observable
final class ProviderCredentials {
    var alpacaAPIKey: String = ""
    var alpacaAPISecret: String = ""
    var massiveAPIKey: String = ""

    private let service = "com.stocksignalmonitor.credentials"

    private enum Account {
        static let alpacaAPIKey = "alpaca.apiKey"
        static let alpacaAPISecret = "alpaca.apiSecret"
        static let massiveAPIKey = "massive.apiKey"
    }

    init() {
        alpacaAPIKey = read(account: Account.alpacaAPIKey)
        alpacaAPISecret = read(account: Account.alpacaAPISecret)
        massiveAPIKey = read(account: Account.massiveAPIKey)
    }

    func save(for provider: MarketDataProvider) {
        switch provider {
        case .alpaca:
            write(alpacaAPIKey, account: Account.alpacaAPIKey)
            write(alpacaAPISecret, account: Account.alpacaAPISecret)
        case .massive:
            write(massiveAPIKey, account: Account.massiveAPIKey)
        case .yahoo, .ibkr:
            break
        }
    }

    private func read(account: String) -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data,
              let value = String(data: data, encoding: .utf8) else { return "" }
        return value
    }

    private func write(_ value: String, account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
        guard !value.isEmpty, let data = value.data(using: .utf8) else { return }
        var item = query
        item[kSecValueData as String] = data
        SecItemAdd(item as CFDictionary, nil)
    }
}
