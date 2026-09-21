import SwiftUI

struct ContentView: View {
    let store: MacMonitorStore
    @State private var didAutoStart = false

    var body: some View {
        @Bindable var store = store

        NavigationSplitView {
            SidebarView(store: store, selection: $store.selection)
                .navigationSplitViewColumnWidth(min: 210, ideal: 245, max: 320)
        } detail: {
            detail
                .navigationTitle(detailTitle)
                .toolbar { toolbar }
        }
        .sheet(isPresented: $store.isAddingSymbol) {
            AddSymbolView { store.addSymbol($0) }
        }
        .alert("行情连接失败", isPresented: errorBinding) {
            Button("好") { store.lastError = nil }
        } message: {
            Text(store.lastError ?? "未知错误")
        }
        .environment(\.dynamicTypeSize, dynamicTypeSize)
        .task {
            guard !didAutoStart else { return }
            didAutoStart = true
            if store.preferences.autoStartMonitoring { store.startMonitoring() }
        }
    }

    @ViewBuilder
    private var detail: some View {
        switch store.selection {
        case .overview, .none:
            SignalTableView(store: store)
        case .watchlist:
            WatchlistView(store: store)
        case .market:
            MarketDirectoryView(store: store)
        case .symbol:
            if let signal = store.selectedSignal {
                SignalDetailView(store: store, signal: signal)
            } else {
                ContentUnavailableView("没有选择股票", systemImage: "chart.line.uptrend.xyaxis")
            }
        }
    }

    private var detailTitle: String {
        switch store.selection {
        case .watchlist: "自选列表"
        case .market: "全市场股票"
        case .symbol: store.selectedSignal?.symbol ?? "股票详情"
        case .overview, .none: "监控概览"
        }
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            Button {
                store.refresh()
            } label: {
                Label("立即刷新", systemImage: "arrow.clockwise")
            }
            .help("立即刷新（⇧⌘R）")

            Button {
                store.toggleMonitoring()
            } label: {
                Label(
                    store.isMonitoring ? "停止" : "开始监控",
                    systemImage: store.isMonitoring ? "stop.fill" : "play.fill"
                )
            }
            .keyboardShortcut("r", modifiers: [.command])
            .help(store.isMonitoring ? "停止监控（⌘R）" : "开始监控（⌘R）")

            SettingsLink {
                Label("设置", systemImage: "gearshape")
            }
        }
    }

    private var errorBinding: Binding<Bool> {
        Binding(
            get: { store.lastError != nil },
            set: { if !$0 { store.lastError = nil } }
        )
    }

    private var dynamicTypeSize: DynamicTypeSize {
        switch store.preferences.interfaceScale {
        case ..<0.9: return .small
        case ..<1.05: return .medium
        case ..<1.2: return .large
        case ..<1.32: return .xLarge
        default: return .xxLarge
        }
    }
}
