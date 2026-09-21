import StockSignalCore
import SwiftUI

struct StockDetailView: View {
    @Environment(MonitorStore.self) private var store
    let symbol: String
    @State private var editor: PositionEditorContext?

    private var stock: MonitoredStock? {
        store.stocks.first { $0.symbol == symbol }
    }

    private let columns = [GridItem(.adaptive(minimum: 145), spacing: 12)]

    var body: some View {
        Group {
            if let stock {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        ReadOnlyBanner()

                        VStack(alignment: .leading, spacing: 8) {
                            HStack(alignment: .firstTextBaseline) {
                                Text(DisplayFormatting.price(stock.quote?.price))
                                    .font(.largeTitle.bold().monospacedDigit())
                                    .minimumScaleFactor(0.7)
                                Spacer()
                                SignalStatusBadge(status: stock.levels?.status)
                            }
                            Text("行情时间：\(DisplayFormatting.date(stock.quote?.timestamp))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        signalSection(stock)
                        positionSection(stock)
                        modelSection(stock)

                        if let errorMessage = stock.errorMessage {
                            Label(errorMessage, systemImage: "exclamationmark.triangle")
                                .font(.callout)
                                .foregroundStyle(.orange)
                        }
                    }
                    .padding()
                    .frame(maxWidth: 900)
                    .frame(maxWidth: .infinity)
                }
                .navigationTitle(stock.name.isEmpty ? stock.symbol : "\(stock.symbol) · \(stock.name)")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("编辑持仓", systemImage: "square.and.pencil") {
                            editor = PositionEditorContext(symbol: stock.symbol)
                        }
                    }
                }
                .sheet(item: $editor) { context in
                    PositionEditorView(symbol: context.symbol)
                }
            } else {
                ContentUnavailableView("股票已移除", systemImage: "trash")
            }
        }
    }

    @ViewBuilder
    private func signalSection(_ stock: MonitoredStock) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("关键价格")
                .font(.title3.bold())
            LazyVGrid(columns: columns, spacing: 12) {
                MetricCard(
                    title: "突破买入线",
                    value: DisplayFormatting.price(stock.levels?.buyPoint),
                    detail: "实时价格向上触发时提示",
                    color: .green
                )
                MetricCard(
                    title: "卖出触发点",
                    value: DisplayFormatting.price(stock.plan?.riskReductionPoint ?? stock.levels?.stopPoint),
                    detail: "实时价格向下触发时提示",
                    color: .red
                )
            }
        }
    }

    @ViewBuilder
    private func positionSection(_ stock: MonitoredStock) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("持仓与意见")
                    .font(.title3.bold())
                Spacer()
                Button("编辑") {
                    editor = PositionEditorContext(symbol: stock.symbol)
                }
            }

            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    LabeledContent("当前均价", value: DisplayFormatting.price(stock.position.averageCost))
                    LabeledContent("持股数量", value: "\(stock.position.quantity) 股")
                    LabeledContent("模型仓位上限", value: "\(stock.plan?.maximumShares ?? 0) 股")
                    Divider()
                    Label(DisplayFormatting.action(stock.plan?.action), systemImage: "lightbulb")
                        .foregroundStyle(.primary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private func modelSection(_ stock: MonitoredStock) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("数据与模型")
                .font(.title3.bold())
            GroupBox {
                VStack(spacing: 10) {
                    LabeledContent("历史日线", value: "\(stock.levels?.historyDays ?? 0) 天")
                    LabeledContent("信号质量", value: stock.levels?.quality.rawValue ?? "等待数据")
                    LabeledContent("趋势模型", value: stock.levels?.modelName ?? "—")
                    LabeledContent("ATR(14)", value: DisplayFormatting.price(stock.levels?.atr14))
                    LabeledContent("价格风险", value: DisplayFormatting.percent(stock.levels?.riskPercent))
                }
            }
        }
    }
}

private struct PositionEditorContext: Identifiable {
    let symbol: String
    var id: String { symbol }
}
