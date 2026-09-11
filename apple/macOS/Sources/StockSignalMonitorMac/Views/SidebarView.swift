import SwiftUI

struct SidebarView: View {
    let store: MacMonitorStore
    @Binding var selection: SidebarSelection?

    var body: some View {
        List(selection: $selection) {
            Label("监控概览", systemImage: "rectangle.grid.1x2")
                .tag(SidebarSelection.overview)

            Label("自选列表", systemImage: "star.square.on.square")
                .tag(SidebarSelection.watchlist)

            Section("自选股票") {
                ForEach(store.signals) { signal in
                    SidebarSignalRow(signal: signal, hasPosition: store.hasPosition(signal.symbol))
                        .tag(SidebarSelection.symbol(signal.symbol))
                        .contextMenu {
                            Button("移除 \(signal.symbol)", role: .destructive) {
                                selection = .symbol(signal.symbol)
                                store.removeSelectedSymbol()
                            }
                        }
                }
            }
        }
        .listStyle(.sidebar)
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 8) {
                Divider()
                HStack {
                    Button {
                        store.isAddingSymbol = true
                    } label: {
                        Label("添加股票", systemImage: "plus")
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    if store.isMonitoring {
                        ProgressView().controlSize(.small)
                    }
                }

                Label("只读模式 · 永不下单", systemImage: "lock.shield")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal)
            .padding(.bottom, 8)
        }
    }
}

private struct SidebarSignalRow: View {
    let signal: SignalPresentation
    let hasPosition: Bool

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: signal.status.systemImage)
                .foregroundStyle(statusStyle)
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Text(signal.symbol)
                        .fontWeight(.medium)
                        .lineLimit(1)
                    if hasPosition {
                        Text("持仓")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.green)
                    }
                }

                Text(signal.currentPrice.currencyText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
    }

    private var statusStyle: Color {
        switch signal.status {
        case .buyAlert: .green
        case .riskReduction: .red
        case .profitTaking: .orange
        case .watch: .yellow
        default: .secondary
        }
    }
}
