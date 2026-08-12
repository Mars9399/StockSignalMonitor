import Foundation
import Security

/// App-private storage for market-data credentials. Values are never written to UserDefaults.
struct KeychainCredentialStore: Sendable {
    static let shared = KeychainCredentialStore()

    private let service = "com.mars9399.StockSignalMonitor.market-data"

    enum Account: String, Sendable {
        case alpacaAPIKey = "alpaca.api-key"
        case alpacaAPISecret = "alpaca.api-secret"
        case massiveAPIKey = "massive.api-key"
    }

    func value(for account: Account) throws -> String? {
        var query = baseQuery(for: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw KeychainError.unexpectedStatus(status) }
        guard let data = result as? Data,
              let value = String(data: data, encoding: .utf8)
        else { throw KeychainError.invalidData }
        return value
    }

    func save(_ value: String, for account: Account) throws {
        guard let data = value.data(using: .utf8) else { throw KeychainError.invalidData }
        let query = baseQuery(for: account)
        let update: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]

        let status = SecItemUpdate(query as CFDictionary, update as CFDictionary)
        if status == errSecSuccess { return }
        guard status == errSecItemNotFound else { throw KeychainError.unexpectedStatus(status) }

        var newItem = query
        newItem.merge(update) { _, latest in latest }
        let addStatus = SecItemAdd(newItem as CFDictionary, nil)
        guard addStatus == errSecSuccess else { throw KeychainError.unexpectedStatus(addStatus) }
    }

    func remove(_ account: Account) throws {
        let status = SecItemDelete(baseQuery(for: account) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unexpectedStatus(status)
        }
    }

    private func baseQuery(for account: Account) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account.rawValue,
            kSecAttrSynchronizable as String: false
        ]
    }
}

private enum KeychainError: LocalizedError {
    case invalidData
    case unexpectedStatus(OSStatus)

    var errorDescription: String? {
        switch self {
        case .invalidData:
            "凭据无法安全编码"
        case let .unexpectedStatus(status):
            if let message = SecCopyErrorMessageString(status, nil) {
                "钥匙串错误：\(message)"
            } else {
                "钥匙串错误（\(status)）"
            }
        }
    }
}
