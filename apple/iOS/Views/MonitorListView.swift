import StockSignalCore
import SwiftUI

struct MonitorListView: View {
    @Environment(MonitorStore.self) private var store

    var body: some View {
        List {
            Section {
                ReadOnlyBanner()
                    .listRowInsets(.init(top: 8, leading: 16, bottom: 8, trailing: 16))
                    .listRowBackground(Color.clear)
            }

            if store.stocks.isEmpty {
                ContentUnavailableView(
                    "尚未添加股票",
                    systemImage: "chart.line.uptrend.xyaxis",
                    description: Text("请在“股票”分页添加美股代码。")
                )
                .listRowBackground(Color.clear)
            } else {
                Section("实时信号") {
                    ForEach(store.stocks) { stock in
                        NavigationLink(value: stock.symbol) {
                            StockSignalRow(stock: stock)
                        }
                        .accessibilityHint("查看 \(stock.symbol) 的信号和持仓建议")
                    }
                }
            }

            Section("连接") {
                LabeledContent("数据源", value: store.configuration.kind.displayName)
                LabeledContent("状态", value: store.connectionMessage)
                LabeledContent("最后更新", value: DisplayFormatting.date(store.lastUpdated))
            }

            if let errorMessage = store.errorMessage {
                Section("需要注意") {
                    Label(errorMessage, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("美股信号监控")
        .navigationDestination(for: String.self) { symbol in
            StockDetailView(symbol: symbol)
        }
        .refreshable {
            await store.refresh()
        }
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button {
                    Task { await store.refresh() }
                } label: {
                    Label("立即刷新", systemImage: "arrow.clockwise")
                }
                .accessibilityIdentifier("refreshSignals")

                Button {
                    if store.isMonitoring {
                        store.stopMonitoring()
                    } else {
                        store.startMonitoring()
                    }
                } label: {
                    Label(
                        store.isMonitoring ? "停止监控" : "开始监控",
                        systemImage: store.isMonitoring ? "stop.fill" : "play.fill"
                    )
                }
                .accessibilityIdentifier("toggleMonitoring")
            }
        }
    }
}

private struct StockSignalRow: View {
    let stock: MonitoredStock

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(stock.symbol)
                        .font(.headline)
                    if !stock.name.isEmpty {
                        Text(stock.name)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Spacer()
                Text(DisplayFormatting.price(stock.quote?.price))
                    .font(.headline.monospacedDigit())
            }

            HStack {
                SignalStatusBadge(status: stock.levels?.status)
                Spacer()
                Text("突破加仓点 \(DisplayFormatting.price(stock.levels?.buyPoint))")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            if let errorMessage = stock.errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}
