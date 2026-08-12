import StockSignalCore
import SwiftUI

struct PositionEditorView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(MonitorStore.self) private var store
    let symbol: String

    @State private var averageCost: Double
    @State private var quantity: Int
    @FocusState private var focusedField: Field?

    private enum Field {
        case averageCost
        case quantity
    }

    init(symbol: String) {
        self.symbol = symbol
        _averageCost = State(initialValue: 0)
        _quantity = State(initialValue: 0)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("当前持仓") {
                    TextField("平均成本（美元）", value: $averageCost, format: .number.precision(.fractionLength(0...4)))
                        .keyboardType(.decimalPad)
                        .focused($focusedField, equals: .averageCost)
                    TextField("持股数量", value: $quantity, format: .number)
                        .keyboardType(.numberPad)
                        .focused($focusedField, equals: .quantity)
                }

                Section {
                    Text("这些数据只用于计算风险线、盈利减仓点和仓位意见，不会发送给券商下单。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("编辑 \(symbol) 持仓")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        store.updatePosition(Position(
                            symbol: symbol,
                            averageCost: max(0, averageCost),
                            quantity: max(0, quantity)
                        ))
                        dismiss()
                    }
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("完成") { focusedField = nil }
                }
            }
            .onAppear {
                guard let position = store.stocks.first(where: { $0.symbol == symbol })?.position else { return }
                averageCost = position.averageCost
                quantity = position.quantity
            }
        }
        .presentationDetents([.medium, .large])
    }
}
