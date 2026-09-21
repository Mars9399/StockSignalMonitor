import SwiftUI

struct ActivityLogView: View {
    let entries: [String]
    let height: Double
    @State private var isExpanded = true

    var body: some View {
        DisclosureGroup(isExpanded: $isExpanded) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        if entries.isEmpty {
                            Text("日志将在监控启动后显示。")
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(Array(entries.enumerated()), id: \.offset) { index, entry in
                                Text(entry)
                                    .font(.system(.caption, design: .monospaced))
                                    .textSelection(.enabled)
                                    .id(index)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                }
                .frame(height: isExpanded ? height : 0)
                .onChange(of: entries.count) { _, count in
                    if count > 0 { proxy.scrollTo(count - 1, anchor: .bottom) }
                }
            }
        } label: {
            Label("运行日志", systemImage: "text.alignleft")
                .font(.caption.weight(.medium))
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.bar)
    }
}
