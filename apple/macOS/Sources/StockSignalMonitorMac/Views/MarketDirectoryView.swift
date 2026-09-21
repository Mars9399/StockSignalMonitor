import SwiftUI

struct MarketDirectoryView: View {
    let store: MacMonitorStore
    @State private var selectedSymbol: String?

    var body: some View {
        @Bindable var store = store

        VStack(spacing: 0) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("全市场股票")
                        .font(.title2.weight(.semibold))
                    Text(store.marketDirectoryMessage)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                TextField("股票代码或名称", text: $store.marketSearchText)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 210)
                    .onSubmit { store.loadMarketDirectory(page: 0) }

                Button("搜索") { store.loadMarketDirectory(page: 0) }
                Button("上一页") { store.clearMarketSearchAndLoad(page: max(0, store.marketPage - 1)) }
                    .disabled(store.marketPage == 0 || store.isLoadingMarketDirectory || !store.marketSearchText.isEmpty)
                Button("下一页") { store.clearMarketSearchAndLoad(page: store.marketPage + 1) }
                    .disabled((store.marketPage + 1) * 100 >= store.marketTotal || store.isLoadingMarketDirectory || !store.marketSearchText.isEmpty)
                Button("刷新") { store.loadMarketDirectory() }
                    .disabled(store.isLoadingMarketDirectory)
                Button("加入自选") { addSelected() }
                    .buttonStyle(.borderedProminent)
                    .disabled(selectedSymbol == nil)

                if store.isLoadingMarketDirectory { ProgressView().controlSize(.small) }
            }
            .padding()

            Table(store.marketEntries, selection: $selectedSymbol) {
                TableColumn("股票") { entry in
                    Text(entry.symbol)
                        .fontWeight(.semibold)
                        .foregroundStyle(color(for: entry))
                        .contextMenu {
                            Button(store.watchlist.contains(entry.symbol) ? "已在自选中" : "加入自选") {
                                store.addMarketSymbol(entry.symbol)
                            }
                            .disabled(store.watchlist.contains(entry.symbol))
                        }
                        .onTapGesture(count: 2) { store.addMarketSymbol(entry.symbol) }
                }
                .width(90)

                TableColumn("名称") { entry in Text(entry.name).lineLimit(1) }
                    .width(min: 180, ideal: 270)
                TableColumn("交易所") { entry in Text(entry.exchange) }
                    .width(130)
                TableColumn("现价") { entry in
                    Text(entry.price > 0 ? entry.price.formatted(SignalFormatting.currency) : "—")
                        .monospacedDigit()
                        .foregroundStyle(color(for: entry))
                }
                .width(100)
                TableColumn("涨跌") { entry in
                    Text(String(format: "%+.2f%%", entry.changePercent))
                        .monospacedDigit()
                        .foregroundStyle(color(for: entry))
                }
                .width(90)
                TableColumn("成交量") { entry in
                    Text(entry.volume > 0 ? entry.volume.formatted(.number.precision(.fractionLength(0))) : "—")
                        .monospacedDigit()
                }
                .width(110)
                TableColumn("市值") { entry in Text(marketCap(entry.marketCap)).monospacedDigit() }
                    .width(110)
                TableColumn("自选") { entry in
                    if store.watchlist.contains(entry.symbol) {
                        Label("已加入", systemImage: "star.fill").foregroundStyle(.yellow)
                    } else {
                        Text("—").foregroundStyle(.tertiary)
                    }
                }
                .width(80)
            }
            .environment(\.defaultMinListRowHeight, store.preferences.tableRowHeight)
        }
        .task {
            if store.marketEntries.isEmpty { store.loadMarketDirectory(page: 0) }
        }
    }

    private func addSelected() {
        guard let selectedSymbol else { return }
        store.addMarketSymbol(selectedSymbol)
    }

    private func color(for entry: MarketDirectoryEntry) -> Color {
        if entry.changePercent > 0 { return .green }
        if entry.changePercent < 0 { return .red }
        return .secondary
    }

    private func marketCap(_ value: Double) -> String {
        if value >= 1_000_000_000 { return String(format: "$%.1fB", value / 1_000_000_000) }
        if value >= 1_000_000 { return String(format: "$%.1fM", value / 1_000_000) }
        return "—"
    }
}
