import StockSignalCore
import SwiftUI

struct PositionEditorView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(MonitorStore.self) private var store
    let symbol: String

    @State private var averageCost: Double
    @State private var quantity: Double
    @State private var initialStop: Double?
    @State private var originalPosition: Position?
    @FocusState private var focusedField: Field?

    private enum Field {
        case averageCost
        case quantity
    }

    private var referencePrice: Double {
        if let originalPosition, averageCost == originalPosition.averageCost, quantity == originalPosition.quantity {
            return originalPosition.riskReferencePrice ?? averageCost
        }
        return averageCost
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
                    TextField("保护线（留空自动按 2×ATR 建立）", value: $initialStop, format: .number)
                        .keyboardType(.decimalPad)
                    TextField("平均成本（美元）", value: $averageCost, format: .number.precision(.fractionLength(0...4)))
                        .keyboardType(.decimalPad)
                        .focused($focusedField, equals: .averageCost)
                    TextField("持股数量", value: $quantity, format: .number)
                        .keyboardType(.decimalPad)
                        .focused($focusedField, equals: .quantity)
                }

                Section {
                    Text("留空将在可靠行情到达后按现价−2×ATR建立并保存。卖出点取价格通道与保护线中更严格的一条；只作提醒，不会发送订单。")
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
                            quantity: max(0, quantity),
                            initialStop: initialStop,
                            riskReferencePrice: initialStop == nil ? nil : referencePrice
                        ))
                        dismiss()
                    }
                    .disabled(!averageCost.isFinite || !quantity.isFinite || averageCost < 0 || quantity < 0 || (quantity > 0 && averageCost <= 0) || (initialStop != nil && (!initialStop!.isFinite || initialStop! <= 0 || initialStop! >= referencePrice)))
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
                initialStop = position.initialStop
                originalPosition = position
            }
        }
        .presentationDetents([.medium, .large])
    }
}
