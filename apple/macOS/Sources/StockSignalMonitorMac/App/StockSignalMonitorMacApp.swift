import SwiftUI

@main
struct StockSignalMonitorMacApp: App {
    @State private var store = MacMonitorStore()

    var body: some Scene {
        WindowGroup("美股信号监控", id: "monitor") {
            ContentView(store: store)
                .frame(minWidth: 920, minHeight: 600)
        }
        .commands {
            MonitorCommands(store: store)
        }

        Settings {
            SettingsView(store: store)
        }
    }
}

private struct MonitorCommands: Commands {
    let store: MacMonitorStore

    var body: some Commands {
        CommandMenu("监控") {
            Button(store.isMonitoring ? "停止监控" : "开始监控") {
                store.toggleMonitoring()
            }
            .keyboardShortcut("r", modifiers: [.command])

            Button("立即刷新") {
                store.refresh()
            }
            .keyboardShortcut("r", modifiers: [.command, .shift])

            Button("重新读取 TWS 持仓") {
                store.syncPositionsFromTWS()
            }
            .disabled(store.preferences.provider != .ibkr || store.isSyncingTWSPositions)

            Divider()

            Button("添加股票…") {
                store.isAddingSymbol = true
            }
            .keyboardShortcut("n", modifiers: [.command])

            Button("移除所选股票") {
                store.removeSelectedSymbol()
            }
            .keyboardShortcut(.delete, modifiers: [.command])
            .disabled(store.selectedSignal == nil)
        }
    }
}
