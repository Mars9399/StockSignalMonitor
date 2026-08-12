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
                    title: "买入 / 突破加仓点",
                    value: DisplayFormatting.price(stock.levels?.buyPoint),
                    detail: "到价并确认趋势后观察",
                    color: .green
                )
                MetricCard(
                    title: "风险减仓点",
                    value: DisplayFormatting.price(stock.plan?.riskReductionPoint ?? stock.levels?.stopPoint),
                    detail: "跌破时优先控制风险",
                    color: .red
                )
                MetricCard(
                    title: "盈利减仓点 2R",
                    value: DisplayFormatting.price(stock.plan?.profitTarget2R),
                    detail: "分批锁定盈利",
                    color: .blue
                )
                MetricCard(
                    title: "盈利减仓点 3R",
                    value: DisplayFormatting.price(stock.plan?.profitTarget3R),
                    detail: "继续分批锁定盈利",
                    color: .blue
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
