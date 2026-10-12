import SwiftUI
import StockSignalCore

struct MarketMoversView: View {
    let store: MacMonitorStore

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("市场涨跌 Top 20")
                        .font(.title2.weight(.semibold))
                    Text(store.marketMoversMessage)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Picker(
                    "板块",
                    selection: Binding(
                        get: { store.marketMoverSector },
                        set: { store.selectMarketMoverSector($0) }
                    )
                ) {
                    ForEach(MarketSector.allCases) { sector in
                        Text(sector.displayName).tag(sector)
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 170)
                .disabled(store.isLoadingMarketMovers)
                .help("Yahoo Finance 官方板块分类")

                if let updatedAt = store.marketMoversUpdatedAt {
                    Text("更新于 \(updatedAt.formatted(date: .omitted, time: .standard))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Button {
                    store.loadMarketMovers()
                } label: {
                    Label("刷新", systemImage: "arrow.clockwise")
                }
                .disabled(store.isLoadingMarketMovers)

                if store.isLoadingMarketMovers {
                    ProgressView().controlSize(.small)
                }
            }
            .padding()

            HSplitView {
                MoverTable(
                    title: MarketMoverSide.gainers.displayName,
                    systemImage: "arrow.up.right",
                    entries: store.marketGainers,
                    store: store,
                    accent: .green
                )
                MoverTable(
                    title: MarketMoverSide.losers.displayName,
                    systemImage: "arrow.down.right",
                    entries: store.marketLosers,
                    store: store,
                    accent: .red
                )
            }
        }
        .task {
            if store.marketGainers.isEmpty && store.marketLosers.isEmpty {
                store.loadMarketMovers()
            }
        }
    }
}

private struct MoverTable: View {
    let title: String
    let systemImage: String
    let entries: [MarketMoverEntry]
    let store: MacMonitorStore
    let accent: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: systemImage)
                .font(.headline)
                .foregroundStyle(accent)
                .padding(.horizontal)
                .padding(.top, 10)

            Table(entries) {
                TableColumn("#") { entry in
                    Text(entry.rank.formatted()).monospacedDigit()
                }
                .width(28)

                TableColumn("股票") { entry in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.symbol).fontWeight(.semibold)
                        Text(entry.name).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                    .contextMenu {
                        Button(store.watchlist.contains(entry.symbol) ? "已在自选中" : "加入自选") {
                            store.addMarketSymbol(entry.symbol)
                        }
                        .disabled(store.watchlist.contains(entry.symbol))
                    }
                    .onTapGesture(count: 2) { store.addMarketSymbol(entry.symbol) }
                }
                .width(min: 105, ideal: 145)

                TableColumn("现价") { entry in
                    Text(entry.price.formatted(.currency(code: "USD")))
                        .monospacedDigit()
                }
                .width(82)

                TableColumn("涨跌") { entry in
                    Text(String(format: "%+.2f%%", entry.changePercent))
                        .monospacedDigit()
                        .foregroundStyle(entry.changePercent >= 0 ? Color.green : Color.red)
                }
                .width(72)

                TableColumn("买点 / 卖点") { entry in
                    Text(levels(entry)).monospacedDigit()
                }
                .width(115)

                TableColumn("辅助判断") { entry in
                    Text(entry.opportunity)
                        .foregroundStyle(opportunityColor(entry.opportunity))
                        .lineLimit(1)
                }
                .width(min: 150, ideal: 210)
            }
            .environment(\.defaultMinListRowHeight, store.preferences.tableRowHeight)
        }
        .frame(minWidth: 520)
    }

    private func levels(_ entry: MarketMoverEntry) -> String {
        guard entry.buyPoint > 0, entry.sellPoint > 0 else { return "—" }
        return String(format: "$%.2f / $%.2f", entry.buyPoint, entry.sellPoint)
    }

    private func opportunityColor(_ text: String) -> Color {
        if text.hasPrefix("买入机会") || text.hasPrefix("接近买点") { return .green }
        if text.hasPrefix("回避") || text.hasPrefix("分析失败") { return .red }
        if text.hasPrefix("等待回踩") { return .orange }
        return .secondary
    }
}
