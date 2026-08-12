import StockSignalCore
import SwiftUI

struct ProviderSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(MonitorStore.self) private var store

    @State private var kind: MarketDataProviderKind
    @State private var apiKey = ""
    @State private var apiSecret = ""
    @State private var feed = "iex"
    @State private var baseURL = ""
    @State private var accountID = ""
    @State private var credentialError: String?
    @State private var loadedProvider: MarketDataProviderKind?

    private let credentialStore = KeychainCredentialStore.shared

    init(initialConfiguration: DataProviderConfiguration) {
        _kind = State(initialValue: initialConfiguration.kind)
        switch initialConfiguration {
        case .yahoo:
            break
        case let .alpaca(apiKey, apiSecret, feed):
            _apiKey = State(initialValue: apiKey)
            _apiSecret = State(initialValue: apiSecret)
            _feed = State(initialValue: feed)
        case let .massive(apiKey, baseURL):
            _apiKey = State(initialValue: apiKey)
            _baseURL = State(initialValue: baseURL.absoluteString)
        case let .ibkrClientPortal(baseURL, accountID):
            _baseURL = State(initialValue: baseURL.absoluteString)
            _accountID = State(initialValue: accountID ?? "")
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("数据源") {
                    Picker("服务", selection: $kind) {
                        ForEach(MarketDataProviderKind.allCases) { provider in
                            Text(provider.displayName).tag(provider)
                        }
                    }
                }

                configurationFields

                if let credentialError {
                    Section("无法访问安全凭据") {
                        Label(credentialError, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.orange)
                    }
                }

                Section("只读连接") {
                    Text("Alpaca 与 Massive 密钥保存在系统钥匙串中，仅用于获取行情。应用没有订单接口；IBKR 需要先在本机或受信任网络中登录 Client Portal Gateway。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("数据源设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        guard let configuration = makeConfiguration() else { return }
                        save(configuration)
                    }
                    .disabled(makeConfiguration() == nil)
                }
            }
            .task(id: kind) {
                loadCredentials(for: kind)
            }
        }
    }

    @ViewBuilder
    private var configurationFields: some View {
        switch kind {
        case .yahoo:
            Section {
                Text("无需密钥，适合快速查看。请遵守 Yahoo Finance 的数据使用条款。")
                    .foregroundStyle(.secondary)
            }
        case .alpaca:
            Section("Alpaca 只读行情凭据") {
                TextField("API Key", text: $apiKey)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField("API Secret", text: $apiSecret)
                TextField("Feed", text: $feed)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            }
        case .massive:
            Section("Massive / Polygon") {
                SecureField("API Key", text: $apiKey)
                TextField("服务地址", text: $baseURL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            }
        case .ibkrClientPortal:
            Section("IBKR Client Portal Gateway") {
                TextField("Gateway 地址", text: $baseURL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                TextField("账户 ID（可选）", text: $accountID)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
            }
        }
    }

    private func makeConfiguration() -> DataProviderConfiguration? {
        switch kind {
        case .yahoo:
            return .yahoo
        case .alpaca:
            guard !apiKey.isEmpty, !apiSecret.isEmpty else { return nil }
            return .alpaca(apiKey: apiKey, apiSecret: apiSecret, feed: feed.isEmpty ? "iex" : feed)
        case .massive:
            guard !apiKey.isEmpty,
                  let url = URL(string: baseURL.isEmpty ? "https://api.massive.com" : baseURL)
            else { return nil }
            return .massive(apiKey: apiKey, baseURL: url)
        case .ibkrClientPortal:
            guard let url = URL(string: baseURL.isEmpty ? "https://localhost:5000/v1/api" : baseURL) else { return nil }
            return .ibkrClientPortal(baseURL: url, accountID: accountID.isEmpty ? nil : accountID)
        }
    }

    private func loadCredentials(for provider: MarketDataProviderKind) {
        credentialError = nil
        let isInitialLoad = loadedProvider == nil
        defer { loadedProvider = provider }
        do {
            switch provider {
            case .alpaca:
                apiKey = try credentialStore.value(for: .alpacaAPIKey) ?? (isInitialLoad ? apiKey : "")
                apiSecret = try credentialStore.value(for: .alpacaAPISecret) ?? (isInitialLoad ? apiSecret : "")
            case .massive:
                apiKey = try credentialStore.value(for: .massiveAPIKey) ?? (isInitialLoad ? apiKey : "")
            case .yahoo, .ibkrClientPortal:
                break
            }
        } catch {
            credentialError = error.localizedDescription
        }
    }

    private func save(_ configuration: DataProviderConfiguration) {
        credentialError = nil
        do {
            switch configuration {
            case let .alpaca(apiKey, apiSecret, _):
                try credentialStore.save(apiKey, for: .alpacaAPIKey)
                try credentialStore.save(apiSecret, for: .alpacaAPISecret)
            case let .massive(apiKey, _):
                try credentialStore.save(apiKey, for: .massiveAPIKey)
            case .yahoo, .ibkrClientPortal:
                break
            }
            AppPreferences.save(configuration)
            store.setConfiguration(configuration)
            dismiss()
        } catch {
            credentialError = error.localizedDescription
        }
    }
}
