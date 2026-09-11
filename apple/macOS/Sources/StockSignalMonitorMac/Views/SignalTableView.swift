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
                }
                .width(min: 90, ideal: 150)

                TableColumn("实时价") { signal in
                    Text(signal.currentPrice.currencyText).monospacedDigit()
                }
                .width(85)

                TableColumn("持仓") { signal in
                    if let position = store.positions[signal.symbol], !position.isEmpty {
                        Text("\(position.quantity.shareQuantityText) 股")
                            .fontWeight(.medium)
                            .monospacedDigit()
                    } else {
                        Text("—").foregroundStyle(.tertiary)
                    }
                }
                .width(80)

                TableColumn("持仓均价") { signal in
                    Text((store.positions[signal.symbol]?.averageCost).currencyText)
                        .monospacedDigit()
                }
                .width(90)

                TableColumn("买入/突破加仓点") { signal in
                    Text(signal.buyTrigger.currencyText).monospacedDigit()
                }
                .width(125)

                TableColumn("风险减仓点") { signal in
                    Text(signal.riskReductionPoint.currencyText).monospacedDigit()
                }
                .width(105)

                TableColumn("盈利减仓 2R / 3R") { signal in
                    Text("\(signal.profitTarget2R.currencyText) / \(signal.profitTarget3R.currencyText)")
                        .monospacedDigit()
                }
                .width(min: 150, ideal: 175)

                TableColumn("状态") { signal in
                    StatusBadge(status: signal.status)
                }
                .width(100)

                TableColumn("仓位意见") { signal in
                    Text(signal.action)
                        .lineLimit(2)
                }
                .width(min: 150, ideal: 220)
            }

            ActivityLogView(entries: store.activityLog)
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

private struct MonitorSummaryHeader: View {
    let store: MacMonitorStore
    @State private var isConfirmingClear = false

    var body: some View {
        @Bindable var store = store

        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 18) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("美股信号监控")
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
                }
                .width(min: 130, ideal: 190)

                TableColumn("最新价") { signal in
                    Text(signal.currentPrice.currencyText).monospacedDigit()
                }
                .width(90)

                TableColumn("持仓状态") { signal in
                    if store.hasPosition(signal.symbol) {
                        Label("持仓", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    } else {
                        Text("未持仓").foregroundStyle(.secondary)
                    }
                }
                .width(95)

                TableColumn("数量") { signal in
                    if let position = store.positions[signal.symbol], !position.isEmpty {
                        Text("\(position.quantity.shareQuantityText) 股").monospacedDigit()
                    } else {
                        Text("—").foregroundStyle(.tertiary)
                    }
                }
                .width(85)

                TableColumn("平均成本") { signal in
                    Text((store.positions[signal.symbol]?.averageCost).currencyText).monospacedDigit()
                }
                .width(100)

                TableColumn("持仓市值") { signal in
                    Text(marketValue(for: signal).currencyText).monospacedDigit()
                }
                .width(105)

                TableColumn("信号状态") { signal in
                    StatusBadge(status: signal.status)
                }
                .width(110)
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

    private func marketValue(for signal: SignalPresentation) -> Double? {
        guard let price = signal.currentPrice,
              let position = store.positions[signal.symbol],
              !position.isEmpty else { return nil }
        return price * position.quantity
    }
}
