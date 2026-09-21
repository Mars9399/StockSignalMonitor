import Foundation
import StockSignalCore
import SwiftUI

enum DisplayFormatting {
    static func price(_ value: Double?) -> String {
        guard let value, value.isFinite, value > 0 else { return "—" }
        return value.formatted(.currency(code: "USD").precision(.fractionLength(2)))
    }

    static func percent(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "—" }
        return "\(value.formatted(.number.precision(.fractionLength(2))))%"
    }

    static func date(_ value: Date?) -> String {
        guard let value else { return "尚未更新" }
        return value.formatted(date: .abbreviated, time: .standard)
    }

    static func statusTitle(_ status: SignalStatus?) -> String {
        switch status {
        case .buyAlert: "买入提示"
        case .sellAlert: "卖出提示"
        case .watch: "等待触发"
        case .noSignal: "暂无信号"
        case .dataShort: "历史不足"
        case nil: "等待行情"
        }
    }

    static func statusColor(_ status: SignalStatus?) -> Color {
        switch status {
        case .buyAlert: .green
        case .sellAlert: .red
        case .watch: .orange
        case .noSignal: .secondary
        case .dataShort: .purple
        case nil: .secondary
        }
    }

    static func action(_ action: PositionAction?) -> String {
        switch action {
        case .needsRiskBaseline: "请设置初始风险线；暂停仓位建议"
        case let .observationOnly(reason): "仅观察：\(reason)"
        case .insufficientHistory: "历史日线不足，仅观察，不提供仓位意见"
        case let .reduceForRisk(shares): "跌破风险线时减仓 \(shares) 股"
        case let .reduceForExposure(shares): "当前仓位超出上限，建议减仓 \(shares) 股"
        case let .reduceAt2R(shares): "到达 2R 盈利点后减仓 \(shares) 股"
        case let .reduceAt3R(shares): "到达 3R 盈利点后减仓 \(shares) 股"
        case let .addAfterBreakout(maximumShares): "突破确认后最多加仓 \(maximumShares) 股"
        case let .openAfterBreakout(maximumShares): "突破确认后最多建立 \(maximumShares) 股观察仓"
        case let .sellSignal(shares): "卖出提示：参考卖出 \(shares) 股"
        case .sellSignalNoPosition: "卖出提示：当前无持仓"
        case let .wait(candidateMaximumShares): "等待突破；候选仓位上限 \(candidateMaximumShares) 股"
        case .hold: "继续持有，等待买入或卖出触发点"
        case nil: "等待足够行情后生成意见"
        }
    }
}
