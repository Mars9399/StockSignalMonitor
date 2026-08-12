import StockSignalCore
import SwiftUI

struct RootTabView: View {
    @State private var selectedTab: AppTab = .monitor

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                MonitorListView()
            }
            .tabItem { Label("监控", systemImage: "waveform.path.ecg") }
            .tag(AppTab.monitor)

            NavigationStack {
                WatchlistEditorView()
            }
            .tabItem { Label("股票", systemImage: "list.bullet") }
            .tag(AppTab.watchlist)

            NavigationStack {
                SettingsView()
            }
            .tabItem { Label("设置", systemImage: "gearshape") }
            .tag(AppTab.settings)
        }
    }
}
