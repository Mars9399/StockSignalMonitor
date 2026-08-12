import StockSignalCore
import SwiftUI

struct RiskSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(MonitorStore.self) private var store
    @State private var accountValue: Double
    @State private var riskPercent: Double
    @State private var maxPositionPercent: Double

    init(initialSettings: RiskSettings) {
        _accountValue = State(initialValue: initialSettings.accountValue)
        _riskPercent = State(initialValue: initialSettings.riskPercent)
        _maxPositionPercent = State(initialValue: initialSettings.maxPositionPercent)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("账户") {
                    TextField("参考市值（美元）", value: $accountValue, format: .number.precision(.fractionLength(0...2)))
                        .keyboardType(.decimalPad)
                }

                Section("仓位规则") {
                    VStack(alignment: .leading) {
                        LabeledContent("单次风险", value: DisplayFormatting.percent(riskPercent))
                        Slider(value: $riskPercent, in: 0.1...10, step: 0.1)
                            .accessibilityLabel("单次风险百分比")
                    }
                    VStack(alignment: .leading) {
                        LabeledContent("单股仓位上限", value: DisplayFormatting.percent(maxPositionPercent))
                        Slider(value: $maxPositionPercent, in: 1...100, step: 1)
                            .accessibilityLabel("单股仓位上限百分比")
                    }
                }

                Section {
                    Text("参数仅用于计算建议股数，不会改变任何券商账户设置。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("风险设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        let settings = RiskSettings(
                            accountValue: accountValue,
                            riskPercent: riskPercent,
                            maxPositionPercent: maxPositionPercent
                        )
                        AppPreferences.save(settings)
                        store.setRiskSettings(settings)
                        dismiss()
                    }
                    .disabled(accountValue <= 0)
                }
            }
        }
    }
}
