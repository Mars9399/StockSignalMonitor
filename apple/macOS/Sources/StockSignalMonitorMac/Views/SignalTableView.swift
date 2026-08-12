import SwiftUI

struct SignalTableView: View {
    let store: MacMonitorStore

    var body: some View {
        VStack(spacing: 0) {
            MonitorSummaryHeader(store: store)

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
                .width(min: 90, ideal: 150)

                TableColumn("实时价") { signal in
                    Text(signal.currentPrice.currencyText).monospacedDigit()
                }
                .width(85)

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

    var body: some View {
        HStack(spacing: 18) {
            VStack(alignment: .leading, spacing: 4) {
                Text("美股信号监控")
                    .font(.title2.weight(.semibold))
                Text("\(store.preferences.provider.rawValue) · \(store.watchlist.count) 只股票 · \(store.connectionMessage)")
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Label("只读 · 永不下单", systemImage: "lock.shield.fill")
                .foregroundStyle(.green)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(.green.opacity(0.12), in: Capsule())
        }
        .padding()
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
