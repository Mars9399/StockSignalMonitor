import SwiftUI

struct SignalDetailView: View {
    let store: MacMonitorStore
    let signal: SignalPresentation

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], spacing: 12) {
                    MetricCard(
                        title: "实时价格",
                        value: signal.currentPrice.currencyText,
                        detail: signal.updatedAt?.formatted(SignalFormatting.timestamp) ?? "等待行情",
                        systemImage: "waveform.path.ecg"
                    )
                    MetricCard(
                        title: "买入/突破加仓点",
                        value: signal.buyTrigger.currencyText,
                        detail: "到价并满足趋势条件后提示",
                        systemImage: "arrow.up.right"
                    )
                    MetricCard(
                        title: "风险减仓点",
                        value: signal.riskReductionPoint.currencyText,
                        detail: "跌破后按仓位规则减仓",
                        systemImage: "shield.lefthalf.filled"
                    )
                    MetricCard(
                        title: "盈利减仓点 2R / 3R",
                        value: "\(signal.profitTarget2R.currencyText) / \(signal.profitTarget3R.currencyText)",
                        detail: "分批锁定收益的参考区间",
                        systemImage: "dollarsign.arrow.circlepath"
                    )
                }

                PositionEditorCard(
                    symbol: signal.symbol,
                    position: store.positions[signal.symbol] ?? .init(),
                    onSave: { store.updatePosition(for: signal.symbol, input: $0) }
                )
                .id(store.positions[signal.symbol])

                GroupBox("信号说明") {
                    Grid(alignment: .leading, horizontalSpacing: 24, verticalSpacing: 10) {
                        DetailRow(label: "当前状态", value: signal.status.title)
                        DetailRow(label: "数据/模型", value: signal.signalQuality)
                        DetailRow(label: "历史日线", value: signal.historyDays > 0 ? "\(signal.historyDays) 天" : "—")
                        DetailRow(label: "仓位意见", value: signal.action)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 4)
                }

                Label(
                    "本应用仅显示行情、信号和仓位参考，不包含任何下单接口。",
                    systemImage: "lock.shield"
                )
                .font(.callout)
                .foregroundStyle(.secondary)
            }
            .padding()
        }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(signal.symbol)
                        .font(.largeTitle.weight(.bold))
                    StatusBadge(status: signal.status)
                }
                Text(signal.companyName)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Menu {
                Button("移除 \(signal.symbol)", role: .destructive) {
                    store.removeSelectedSymbol()
                }
            } label: {
                Label("更多", systemImage: "ellipsis.circle")
            }
            .menuStyle(.borderlessButton)
        }
    }
}

private struct MetricCard: View {
    let title: String
    let value: String
    let detail: String
    let systemImage: String

    var body: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 7) {
                Label(title, systemImage: systemImage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.title3.weight(.semibold).monospacedDigit())
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity, minHeight: 88, alignment: .leading)
        }
    }
}

private struct DetailRow: View {
    let label: String
    let value: String

    var body: some View {
        GridRow {
            Text(label)
                .foregroundStyle(.secondary)
                .gridColumnAlignment(.trailing)
            Text(value)
                .textSelection(.enabled)
                .gridColumnAlignment(.leading)
        }
    }
}

private struct PositionEditorCard: View {
    let symbol: String
    let onSave: (PositionInput) -> Void

    @State private var averageCost: Double?
    @State private var quantity: Double?
    @State private var initialStop: Double?

    init(symbol: String, position: PositionInput, onSave: @escaping (PositionInput) -> Void) {
        self.symbol = symbol
        self.onSave = onSave
        _averageCost = State(initialValue: position.averageCost > 0 ? position.averageCost : nil)
        _quantity = State(initialValue: position.quantity > 0 ? position.quantity : nil)
        _initialStop = State(initialValue: position.initialStop)
    }

    var body: some View {
        GroupBox("我的持仓") {
            HStack(spacing: 14) {
                LabeledContent("持仓均价") {
                    TextField("0.00", value: $averageCost, format: .number.precision(.fractionLength(2...4)))
                        .frame(width: 110)
                        .multilineTextAlignment(.trailing)
                }

                LabeledContent("持股数量") {
                    TextField("0", value: $quantity, format: .number.precision(.fractionLength(0...6)))
                        .frame(width: 90)
                        .multilineTextAlignment(.trailing)
                }

                Spacer()

                LabeledContent("初始风险线") {
                    TextField("留空仅观察", value: $initialStop, format: .number)
                        .frame(width: 100)
                        .help("低于持仓成本。保存后固定风险线与 2R/3R；提示不代表已执行。")
                }

                Button("清除") {
                    averageCost = nil
                    quantity = nil
                    onSave(.init())
                }

                Button("保存持仓") {
                    onSave(.init(averageCost: averageCost ?? 0, quantity: quantity ?? 0, initialStop: initialStop))
                }
                .buttonStyle(.borderedProminent)
                .disabled(!isValid)
            }
            .padding(.vertical, 4)
        }
        .id(symbol)
    }

    private var isValid: Bool {
        guard let averageCost, let quantity else { return false }
        return averageCost.isFinite && quantity.isFinite && averageCost > 0 && quantity > 0 && (initialStop == nil || (initialStop!.isFinite && initialStop! > 0 && initialStop! < averageCost))
    }
}
