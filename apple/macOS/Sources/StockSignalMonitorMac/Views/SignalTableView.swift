import SwiftUI

struct SignalTableView: View {
    let store: MacMonitorStore

    var body: some View {
        VStack(spacing: 0) {
            MonitorSummaryHeader(store: store)

            Table(store.displayedSignals, selection: tableSelection) {
                TableColumn("股票") { signal in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(signal.symbol).fontWeight(.semibold)
                        Text(signal.companyName)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(min: 90, ideal: 150)

                TableColumn("实时价") { signal in
                    Text(signal.currentPrice.currencyText).monospacedDigit()
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(85)

                TableColumn("持仓") { signal in
                    Group {
                        if let position = store.positions[signal.symbol], !position.isEmpty {
                            Text("\(position.quantity.shareQuantityText) 股")
                                .fontWeight(.medium)
                                .monospacedDigit()
                        } else {
                            Text("—").foregroundStyle(.tertiary)
                        }
                    }
                    .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(80)

                TableColumn("持仓均价") { signal in
                    Text((store.positions[signal.symbol]?.averageCost).currencyText)
                        .monospacedDigit()
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(90)

                TableColumn("突破买入线") { signal in
                    Text(signal.buyTrigger.currencyText).monospacedDigit()
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(125)

                TableColumn("卖出触发点") { signal in
                    Text(signal.riskReductionPoint.currencyText).monospacedDigit()
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(105)

                TableColumn("即时买入概率*") { signal in
                    ProbabilityText(score: signal.buyProbability, label: signal.buyProbabilityLabel, isReduction: false)
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(105)

                TableColumn("建议减持概率*") { signal in
                    ProbabilityText(score: signal.reduceProbability, label: signal.reduceProbabilityLabel, isReduction: true)
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(105)

                TableColumn("状态") { signal in
                    StatusBadge(status: signal.status)
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(100)

                TableColumn("仓位意见") { signal in
                    Text(signal.action)
                        .lineLimit(2)
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(min: 150, ideal: 220)
            }
            .environment(\.defaultMinListRowHeight, store.preferences.tableRowHeight)

            if store.preferences.showActivityLog {
                ActivityLogView(entries: store.activityLog, height: store.preferences.logHeight)
            }
        }
    }

    private var tableSelection: Binding<String?> {
        Binding(
            get: {
                guard case let .symbol(symbol) = store.selection else { return nil }
                return symbol
            },
            set: { symbol in
                if let symbol { store.selection = .symbol(symbol) }
            }
        )
    }
}

private struct ProbabilityText: View {
    let score: Int?
    let label: String
    let isReduction: Bool

    var body: some View {
        if let score {
            Text("\(score)% \(label)")
                .fontWeight(score >= 55 ? .semibold : .regular)
                .monospacedDigit()
                .foregroundStyle(color(for: score))
        } else {
            Text("—").foregroundStyle(.tertiary)
        }
    }

    private func color(for score: Int) -> Color {
        if score >= 75 { return isReduction ? .red : .green }
        if score >= 55 { return isReduction ? .orange : .mint }
        if score >= 35 { return .yellow }
        return .secondary
    }
}

private struct MonitorSummaryHeader: View {
    let store: MacMonitorStore
    @State private var isConfirmingClear = false

    var body: some View {
        @Bindable var store = store

        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 18) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("美股信号监控 · Design by Mars")
                        .font(.title2.weight(.semibold))
                    Text("\(store.preferences.provider.rawValue) · 自选 \(store.watchlist.count) 只 · 持仓 \(store.positionCount) 只 · \(store.connectionMessage)")
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Label("只读 · 永不下单", systemImage: "lock.shield.fill")
                    .foregroundStyle(.green)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(.green.opacity(0.12), in: Capsule())
            }

            HStack(spacing: 10) {
                Picker("显示范围", selection: $store.listScope) {
                    ForEach(SignalListScope.allCases) { scope in
                        Text(scope.title).tag(scope)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 220)

                Spacer()

                Button {
                    store.syncPositionsFromTWS()
                } label: {
                    Label(
                        store.isSyncingTWSPositions ? "正在读取…" : "重新读取持仓",
                        systemImage: "arrow.triangle.2.circlepath"
                    )
                }
                .disabled(store.preferences.provider != .ibkr || store.isSyncingTWSPositions)
                .help(store.preferences.provider == .ibkr ? "从本机 TWS 重新读取持仓" : "请先在设置中选择 IBKR TWS 数据源")

                Button(role: .destructive) {
                    isConfirmingClear = true
                } label: {
                    Label("清除全部持仓", systemImage: "trash")
                }
                .disabled(store.positions.isEmpty)
            }
        }
        .padding()
        .confirmationDialog(
            "清除全部本地持仓？",
            isPresented: $isConfirmingClear
        ) {
            Button("清除全部持仓", role: .destructive) {
                store.clearAllPositions()
            }
        } message: {
            Text("自选股票不会被删除。之后可通过“重新读取持仓”从 TWS 恢复。")
        }
    }
}

struct StatusBadge: View {
    let status: PresentationSignalStatus

    var body: some View {
        Label(status.title, systemImage: status.systemImage)
            .font(.caption.weight(.medium))
            .lineLimit(1)
            .foregroundStyle(statusColor)
    }

    private var statusColor: Color {
        switch status {
        case .buyAlert: .green
        case .riskReduction: .red
        case .profitTaking: .orange
        case .watch: .yellow
        case .dataShort: .orange
        case .unavailable: .red
        default: .secondary
        }
    }
}

struct WatchlistView: View {
    let store: MacMonitorStore

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("自选列表")
                        .font(.title2.weight(.semibold))
                    Text("共 \(store.watchlist.count) 只股票，其中 \(store.positionCount) 只有持仓")
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Button {
                    store.isAddingSymbol = true
                } label: {
                    Label("添加股票", systemImage: "plus")
                }
            }
            .padding()

            Table(store.signals, selection: tableSelection) {
                TableColumn("股票") { signal in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(signal.symbol).fontWeight(.semibold)
                        Text(signal.companyName)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(min: 130, ideal: 190)

                TableColumn("最新价") { signal in
                    Text(signal.currentPrice.currencyText).monospacedDigit()
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(90)

                TableColumn("持仓状态") { signal in
                    Group {
                        if store.hasPosition(signal.symbol) {
                            Label("持仓", systemImage: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                        } else {
                            Text("未持仓").foregroundStyle(.secondary)
                        }
                    }
                    .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(95)

                TableColumn("数量") { signal in
                    Group {
                        if let position = store.positions[signal.symbol], !position.isEmpty {
                            Text("\(position.quantity.shareQuantityText) 股").monospacedDigit()
                        } else {
                            Text("—").foregroundStyle(.tertiary)
                        }
                    }
                    .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(85)

                TableColumn("平均成本") { signal in
                    Text((store.positions[signal.symbol]?.averageCost).currencyText).monospacedDigit()
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(100)

                TableColumn("持仓市值") { signal in
                    Text(marketValue(for: signal).currencyText).monospacedDigit()
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(105)

                TableColumn("信号状态") { signal in
                    StatusBadge(status: signal.status)
                        .priceMovementBackground(store.priceMovements[signal.symbol])
                }
                .width(110)
            }
            .environment(\.defaultMinListRowHeight, store.preferences.tableRowHeight)
        }
    }

    private var tableSelection: Binding<String?> {
        Binding(
            get: {
                guard case let .symbol(symbol) = store.selection else { return nil }
                return symbol
            },
            set: { symbol in
                if let symbol { store.selection = .symbol(symbol) }
            }
        )
    }

    private func marketValue(for signal: SignalPresentation) -> Double? {
        guard let price = signal.currentPrice,
              let position = store.positions[signal.symbol],
              !position.isEmpty else { return nil }
        return price * position.quantity
    }
}

private struct PriceMovementBackground: ViewModifier {
    let movement: PriceMovement?

    func body(content: Content) -> some View {
        content
            .frame(maxWidth: .infinity, minHeight: 24, alignment: .center)
            .padding(.horizontal, 3)
            .background(backgroundColor, in: RoundedRectangle(cornerRadius: 4))
            .animation(.easeOut(duration: 0.16), value: movement != nil)
    }

    private var backgroundColor: Color {
        switch movement {
        case .up: return .green.opacity(0.28)
        case .down: return .red.opacity(0.28)
        case .none: return .clear
        }
    }
}

private extension View {
    func priceMovementBackground(_ movement: PriceMovement?) -> some View {
        modifier(PriceMovementBackground(movement: movement))
    }
}
