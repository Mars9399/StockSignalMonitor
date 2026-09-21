import SwiftUI

struct SettingsView: View {
    let store: MacMonitorStore

    var body: some View {
        TabView {
            DataSourceSettingsPane(
                store: store,
                preferences: store.preferences,
                credentials: store.credentials,
                restart: restart
            )
            .tabItem { Label("数据源", systemImage: "antenna.radiowaves.left.and.right") }

            RiskSettingsPane(preferences: store.preferences, restart: restart)
                .tabItem { Label("风控", systemImage: "shield") }

            InterfaceSettingsPane(preferences: store.preferences)
                .tabItem { Label("界面", systemImage: "slider.horizontal.3") }

            ReadOnlySettingsPane()
                .tabItem { Label("安全", systemImage: "lock.shield") }
        }
        .frame(width: 620, height: 540)
        .scenePadding()
    }

    private func restart() {
        guard store.isMonitoring else { return }
        store.refresh()
    }
}

private struct InterfaceSettingsPane: View {
    @Bindable var preferences: AppPreferences

    var body: some View {
        Form {
            Section("初始窗口") {
                HStack {
                    Text("宽度")
                    Slider(value: $preferences.windowWidth, in: 920...2000, step: 20)
                    Text("\(Int(preferences.windowWidth))")
                        .monospacedDigit()
                        .frame(width: 48, alignment: .trailing)
                }
                HStack {
                    Text("高度")
                    Slider(value: $preferences.windowHeight, in: 600...1400, step: 20)
                    Text("\(Int(preferences.windowHeight))")
                        .monospacedDigit()
                        .frame(width: 48, alignment: .trailing)
                }
                Text("初始窗口大小在下次新建主窗口时生效。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("文字与列表") {
                HStack {
                    Text("文字缩放")
                    Slider(value: $preferences.interfaceScale, in: 0.8...1.4, step: 0.05)
                    Text("\(Int((preferences.interfaceScale * 100).rounded()))%")
                        .monospacedDigit()
                        .frame(width: 48, alignment: .trailing)
                }
                HStack {
                    Text("列表行高")
                    Slider(value: $preferences.tableRowHeight, in: 24...56, step: 2)
                    Text("\(Int(preferences.tableRowHeight))")
                        .monospacedDigit()
                        .frame(width: 48, alignment: .trailing)
                }
                HStack {
                    Text("日志高度")
                    Slider(value: $preferences.logHeight, in: 60...240, step: 5)
                    Text("\(Int(preferences.logHeight))")
                        .monospacedDigit()
                        .frame(width: 48, alignment: .trailing)
                }
            }

            Section("启动与显示") {
                Toggle("显示运行日志", isOn: $preferences.showActivityLog)
                Toggle("启动应用后自动开始监控", isOn: $preferences.autoStartMonitoring)
            }

            Section {
                HStack {
                    Spacer()
                    Button("恢复界面默认值") { preferences.restoreInterfaceDefaults() }
                }
            }
        }
        .formStyle(.grouped)
        .padding()
    }
}

private struct DataSourceSettingsPane: View {
    let store: MacMonitorStore
    @Bindable var preferences: AppPreferences
    @Bindable var credentials: ProviderCredentials
    let restart: () -> Void

    var body: some View {
        Form {
            Section("行情接口") {
                Picker("数据源", selection: $preferences.provider) {
                    ForEach(MarketDataProvider.allCases) { provider in
                        Label(provider.rawValue, systemImage: provider.systemImage)
                            .tag(provider)
                    }
                }

                providerFields
            }

            Section {
                HStack {
                    Spacer()
                    Button("保存并应用") {
                        credentials.save(for: preferences.provider)
                        restart()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
        .formStyle(.grouped)
        .padding()
    }

    @ViewBuilder
    private var providerFields: some View {
        switch preferences.provider {
        case .yahoo:
            LabeledContent("凭据") {
                Text("无需密钥").foregroundStyle(.secondary)
            }

        case .alpaca:
            SecureField("Alpaca API Key", text: $credentials.alpacaAPIKey)
            SecureField("Alpaca API Secret", text: $credentials.alpacaAPISecret)
            Text("凭据仅保存在本机钥匙串中。")
                .font(.caption)
                .foregroundStyle(.secondary)

        case .massive:
            SecureField("Massive API Key", text: $credentials.massiveAPIKey)
            Text("凭据仅保存在本机钥匙串中。")
                .font(.caption)
                .foregroundStyle(.secondary)

        case .ibkr:
            TextField("TWS 主机", text: $preferences.twsHost)
            TextField("Socket 端口", value: $preferences.twsPort, format: .number.grouping(.never))
            TextField("Client ID", value: $preferences.twsClientID, format: .number.grouping(.never))
            TextField("账户 ID（可选）", text: $preferences.twsAccountID)
            Text("Paper 常用 7497，Live 常用 7496。应用仅发送持仓读取请求；行情由 Yahoo 提供。")
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack {
                Text(store.twsPositionMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button(store.isSyncingTWSPositions ? "正在同步…" : "测试并同步持仓") {
                    store.syncPositionsFromTWS()
                }
                .disabled(store.isSyncingTWSPositions)
            }
        }
    }
}

private struct RiskSettingsPane: View {
    @Bindable var preferences: AppPreferences
    let restart: () -> Void

    var body: some View {
        Form {
            Section("账户与风险") {
                TextField(
                    "账户规模（USD）",
                    value: $preferences.accountValue,
                    format: .number.precision(.fractionLength(0...2))
                )
                TextField(
                    "单笔风险（%）",
                    value: $preferences.riskPercent,
                    format: .number.precision(.fractionLength(0...2))
                )
                TextField(
                    "单股资金上限（%）",
                    value: $preferences.maximumPositionPercent,
                    format: .number.precision(.fractionLength(0...2))
                )
            }

            Section {
                Text("系统会根据风险额度、价格通道卖出点与单股上限估算参考股数；这些参数不改变买卖方向。")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    Spacer()
                    Button("应用风控设置", action: restart)
                        .buttonStyle(.borderedProminent)
                        .disabled(!isValid)
                }
            }
        }
        .formStyle(.grouped)
        .padding()
    }

    private var isValid: Bool {
        preferences.accountValue > 0 &&
        (0.1...10).contains(preferences.riskPercent) &&
        (1...100).contains(preferences.maximumPositionPercent)
    }
}

private struct ReadOnlySettingsPane: View {
    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "lock.shield.fill")
                .font(.system(size: 54))
                .foregroundStyle(.green)

            Text("只读模式")
                .font(.title2.weight(.semibold))

            Text("应用只读取历史行情、价格和 TWS 持仓，用于生成信号及仓位参考。客户端不包含创建、修改或提交订单的方法。")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .frame(maxWidth: 390)

            GroupBox {
                LabeledContent("交易下单", value: "未实现")
                LabeledContent("行情读取", value: "启用")
                LabeledContent("TWS 持仓", value: "只读")
                LabeledContent("凭据存储", value: "macOS 钥匙串")
            }
            .frame(maxWidth: 400)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}
