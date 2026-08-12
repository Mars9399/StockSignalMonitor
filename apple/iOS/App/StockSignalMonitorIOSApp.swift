import StockSignalCore
import SwiftUI

@main
@MainActor
struct StockSignalMonitorIOSApp: App {
    @State private var store: MonitorStore

    init() {
        _store = State(initialValue: MonitorStore(
            riskSettings: AppPreferences.restoredRiskSettings(),
            configuration: AppPreferences.restoredConfiguration()
        ))
    }

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environment(store)
                .tint(.blue)
        }
    }
}
