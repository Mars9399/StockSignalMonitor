import StockSignalCore
import SwiftUI

struct WatchlistEditorView: View {
    @Environment(MonitorStore.self) private var store
    @State private var newSymbol = ""
    @State private var validationMessage: String?
    @FocusState private var symbolFieldFocused: Bool

    private var normalizedSymbol: String {
        newSymbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    }

    var body: some View {
        List {
            Section("添加股票") {
                HStack {
                    TextField("例如 AAPL 或 0700.HK", text: $newSymbol)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .focused($symbolFieldFocused)
                        .submitLabel(.done)
                        .onSubmit(addSymbol)
                        .accessibilityLabel("要添加的股票代码")
                    Button("添加", action: addSymbol)
                        .disabled(normalizedSymbol.isEmpty)
                }

                if let validationMessage {
                    Text(validationMessage)
                        .font(.footnote)
                        .foregroundStyle(.orange)
                }
            }

            Section("监控列表") {
                if store.stocks.isEmpty {
                    Text("暂无股票")
                        .foregroundStyle(.secondary)
                }
                ForEach(store.stocks) { stock in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(stock.symbol)
                                .font(.headline)
                            if !stock.name.isEmpty {
                                Text(stock.name)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Text(DisplayFormatting.price(stock.quote?.price))
                            .font(.body.monospacedDigit())
                    }
                    .accessibilityElement(children: .combine)
                }
                .onDelete { offsets in
                    let symbols = offsets.compactMap { index in
                        store.stocks.indices.contains(index) ? store.stocks[index].symbol : nil
                    }
                    symbols.forEach(store.removeSymbol)
                }
            }

            Section {
                Text("向左滑动股票即可移除。增删只改变监控列表，不会操作券商账户。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("股票管理")
        .toolbar { EditButton() }
    }

    private func addSymbol() {
        guard !normalizedSymbol.isEmpty else { return }
        let allowed = CharacterSet.uppercaseLetters.union(.decimalDigits).union(CharacterSet(charactersIn: ".-"))
        guard normalizedSymbol.rangeOfCharacter(from: allowed.inverted) == nil else {
            validationMessage = "股票代码只能包含字母、数字、点或连字符。"
            return
        }
        guard !store.symbols.contains(normalizedSymbol) else {
            validationMessage = "\(normalizedSymbol) 已在监控列表中。"
            return
        }
        store.addSymbol(normalizedSymbol)
        newSymbol = ""
        validationMessage = nil
        symbolFieldFocused = false
    }
}
