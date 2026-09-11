import Foundation

enum PresentationSignalStatus: String, Codable, CaseIterable, Sendable {
    case loading
    case dataShort
    case noSignal
    case watch
    case buyAlert
    case riskReduction
    case profitTaking
    case unavailable

    var title: String {
        switch self {
        case .loading: "加载中"
        case .dataShort: "历史不足"
        case .noSignal: "暂无信号"
        case .watch: "观察"
        case .buyAlert: "突破加仓"
        case .riskReduction: "风险减仓"
        case .profitTaking: "盈利减仓"
        case .unavailable: "不可用"
        }
    }

    var systemImage: String {
        switch self {
        case .loading: "clock"
        case .dataShort: "exclamationmark.triangle"
        case .noSignal: "minus.circle"
        case .watch: "eye"
        case .buyAlert: "arrow.up.circle.fill"
        case .riskReduction: "shield.lefthalf.filled"
        case .profitTaking: "dollarsign.circle.fill"
        case .unavailable: "wifi.slash"
        }
    }
}

struct SignalPresentation: Identifiable, Hashable, Sendable {
    var id: String { symbol }

    let symbol: String
    var companyName: String
    var currentPrice: Double?
    var buyTrigger: Double?
    var riskReductionPoint: Double?
    var profitTarget2R: Double?
    var profitTarget3R: Double?
    var status: PresentationSignalStatus
    var signalQuality: String
    var action: String
    var updatedAt: Date?
    var historyDays: Int

    static func placeholder(symbol: String) -> Self {
        .init(
            symbol: symbol,
            companyName: "正在等待行情",
            currentPrice: nil,
            buyTrigger: nil,
            riskReductionPoint: nil,
            profitTarget2R: nil,
            profitTarget3R: nil,
            status: .loading,
            signalQuality: "—",
            action: "连接数据源后计算",
            updatedAt: nil,
            historyDays: 0
        )
    }
}

struct PositionInput: Codable, Hashable, Sendable {
    var averageCost: Double = 0
    var quantity: Double = 0

    var isEmpty: Bool { averageCost <= 0 || quantity <= 0 }
}

enum SignalListScope: String, CaseIterable, Identifiable {
    case all
    case positions

    var id: Self { self }

    var title: String {
        switch self {
        case .all: "显示全部"
        case .positions: "只显示持仓"
        }
    }
}

enum SidebarSelection: Hashable {
    case overview
    case watchlist
    case symbol(String)
}
