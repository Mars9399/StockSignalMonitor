import StockSignalCore
import SwiftUI

struct SignalStatusBadge: View {
    let status: SignalStatus?

    var body: some View {
        Text(DisplayFormatting.statusTitle(status))
            .font(.caption.weight(.semibold))
            .foregroundStyle(DisplayFormatting.statusColor(status))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(DisplayFormatting.statusColor(status).opacity(0.12), in: Capsule())
            .accessibilityLabel("状态：\(DisplayFormatting.statusTitle(status))")
    }
}
