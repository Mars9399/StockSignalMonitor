import SwiftUI

struct AddSymbolView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var symbol = ""

    let onAdd: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("添加股票")
                .font(.title2.weight(.semibold))

            Text("输入美股代码，例如 AAPL 或 BRK.B。")
                .foregroundStyle(.secondary)

            TextField("股票代码", text: $symbol)
                .textFieldStyle(.roundedBorder)
                .onSubmit(add)

            HStack {
                Spacer()
                Button("取消", role: .cancel) { dismiss() }
                Button("添加", action: add)
                    .keyboardShortcut(.defaultAction)
                    .disabled(normalizedSymbol.isEmpty)
            }
        }
        .padding(24)
        .frame(width: 380)
    }

    private var normalizedSymbol: String {
        symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    }

    private func add() {
        guard !normalizedSymbol.isEmpty else { return }
        onAdd(normalizedSymbol)
        dismiss()
    }
}
