import SwiftUI
import StockSignalCore

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

                Picker(
                    "市场",
                    selection: Binding(
                        get: { store.marketRegion },
                        set: { store.selectMarketRegion($0) }
                    )
                ) {
                    ForEach(MarketRegion.allCases, id: \.self) { market in
                        Text(market.displayName).tag(market)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 130)
                .disabled(store.isLoadingMarketDirectory)

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
                        .priceMovementBackground(store.priceMovements[entry.symbol])
                }
                .width(90)

                TableColumn("名称") { entry in
                    Text(entry.name).lineLimit(1)
                        .priceMovementBackground(store.priceMovements[entry.symbol])
                }
                    .width(min: 180, ideal: 270)
                TableColumn("交易所") { entry in
                    Text(entry.exchange)
                        .priceMovementBackground(store.priceMovements[entry.symbol])
                }
                    .width(130)
                TableColumn("现价") { entry in
                    Text(price(entry))
                        .monospacedDigit()
                        .foregroundStyle(priceColor(for: entry))
                }
                .width(100)
                TableColumn("涨跌") { entry in
                    Text(String(format: "%+.2f%%", entry.changePercent))
                        .monospacedDigit()
                        .foregroundStyle(color(for: entry))
                        .priceMovementBackground(store.priceMovements[entry.symbol])
                }
                .width(90)
                TableColumn("成交量") { entry in
                    Text(entry.volume > 0 ? entry.volume.formatted(.number.precision(.fractionLength(0))) : "—")
                        .monospacedDigit()
                        .priceMovementBackground(store.priceMovements[entry.symbol])
                }
                .width(110)
                TableColumn("市值") { entry in
                    Text(marketCap(entry.marketCap, currency: entry.currency)).monospacedDigit()
                        .priceMovementBackground(store.priceMovements[entry.symbol])
                }
                    .width(110)
                TableColumn("自选") { entry in
                    Group {
                        if store.watchlist.contains(entry.symbol) {
                            Label("已加入", systemImage: "star.fill").foregroundStyle(.yellow)
                        } else {
                            Text("—").foregroundStyle(.tertiary)
                        }
                    }
                    .priceMovementBackground(store.priceMovements[entry.symbol])
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

    private func priceColor(for entry: MarketDirectoryEntry) -> Color {
        switch store.priceMovements[entry.symbol] {
        case .up: return .green
        case .down: return .red
        case .none: return color(for: entry)
        }
    }

    private func price(_ entry: MarketDirectoryEntry) -> String {
        guard entry.price > 0 else { return "—" }
        return entry.price.formatted(.currency(code: entry.currency))
    }

    private func marketCap(_ value: Double, currency: String) -> String {
        let prefix = currency == "HKD" ? "HK$" : "$"
        if value >= 1_000_000_000 { return String(format: "%@%.1fB", prefix, value / 1_000_000_000) }
        if value >= 1_000_000 { return String(format: "%@%.1fM", prefix, value / 1_000_000) }
        return "—"
    }
}
