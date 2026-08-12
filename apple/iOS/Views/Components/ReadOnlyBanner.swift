import SwiftUI

struct ReadOnlyBanner: View {
    var body: some View {
        Label("只读监控 · 永不创建或提交订单", systemImage: "lock.shield")
            .font(.footnote.weight(.semibold))
            .foregroundStyle(.green)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal)
            .padding(.vertical, 10)
            .background(.green.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
            .accessibilityLabel("只读监控，本应用永不创建或提交订单")
    }
}
