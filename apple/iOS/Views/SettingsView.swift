import StockSignalCore
import SwiftUI

struct SettingsView: View {
    @Environment(MonitorStore.self) private var store
    @State private var providerEditor: ProviderEditorContext?
    @State private var riskEditor: RiskEditorContext?

    var body: some View {
        List {
            Section {
                ReadOnlyBanner()
                    .listRowInsets(.init(top: 8, leading: 0, bottom: 8, trailing: 0))
                    .listRowBackground(Color.clear)
            }

            Section("行情数据") {
                Button {
                    providerEditor = ProviderEditorContext(configuration: store.configuration)
                } label: {
                    LabeledContent("数据源", value: store.configuration.kind.displayName)
                }
                .buttonStyle(.plain)
                .accessibilityHint("打开数据源配置")
            }

            Section("风险控制") {
                Button {
                    riskEditor = RiskEditorContext(settings: store.riskSettings)
                } label: {
                    VStack(spacing: 10) {
                        LabeledContent("账户参考市值", value: DisplayFormatting.price(store.riskSettings.accountValue))
                        LabeledContent("单次风险", value: DisplayFormatting.percent(store.riskSettings.riskPercent))
                        LabeledContent("单股仓位上限", value: DisplayFormatting.percent(store.riskSettings.maxPositionPercent))
                    }
                }
                .buttonStyle(.plain)
                .accessibilityHint("打开风险参数编辑")
            }

            Section("监控") {
                Button {
                    if store.isMonitoring {
                        store.stopMonitoring()
                    } else {
                        store.startMonitoring()
                    }
                } label: {
                    Label(
                        store.isMonitoring ? "停止流式监控" : "开始流式监控",
                        systemImage: store.isMonitoring ? "stop.circle" : "play.circle"
                    )
                }

                Button {
                    Task { await store.refresh() }
                } label: {
                    Label("立即刷新全部", systemImage: "arrow.clockwise")
                }
            }

            Section("安全说明") {
                Text("本客户端只请求行情和历史日线。界面与共享核心均不包含创建、修改或提交订单的入口。所有价格与仓位意见仅供辅助观察，不构成投资建议。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("设置")
        .sheet(item: $providerEditor) { context in
            ProviderSettingsView(initialConfiguration: context.configuration)
        }
        .sheet(item: $riskEditor) { context in
            RiskSettingsView(initialSettings: context.settings)
        }
    }
}

private struct ProviderEditorContext: Identifiable {
    let configuration: DataProviderConfiguration
    var id: MarketDataProviderKind { configuration.kind }
}

private struct RiskEditorContext: Identifiable {
    let settings: RiskSettings
    let id = UUID()
}
