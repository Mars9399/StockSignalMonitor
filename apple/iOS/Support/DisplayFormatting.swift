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
        case .buyAlert: "突破提醒"
        case .watch: "等待突破"
        case .noSignal: "暂无信号"
        case .dataShort: "历史不足"
        case nil: "等待行情"
        }
    }

    static func statusColor(_ status: SignalStatus?) -> Color {
        switch status {
        case .buyAlert: .green
        case .watch: .orange
        case .noSignal: .secondary
        case .dataShort: .purple
        case nil: .secondary
        }
    }

    static func action(_ action: PositionAction?) -> String {
        switch action {
        case .insufficientHistory: "历史日线不足，仅观察，不提供仓位意见"
        case let .reduceForRisk(shares): "跌破风险线时减仓 \(shares) 股"
        case let .reduceForExposure(shares): "当前仓位超出上限，建议减仓 \(shares) 股"
        case let .reduceAt2R(shares): "到达 2R 盈利点后减仓 \(shares) 股"
        case let .reduceAt3R(shares): "到达 3R 盈利点后减仓 \(shares) 股"
        case let .addAfterBreakout(maximumShares): "突破确认后最多加仓 \(maximumShares) 股"
        case let .openAfterBreakout(maximumShares): "突破确认后最多建立 \(maximumShares) 股观察仓"
        case let .wait(candidateMaximumShares): "等待突破；候选仓位上限 \(candidateMaximumShares) 股"
        case .hold: "继续持有，留意风险线与盈利减仓点"
        case nil: "等待足够行情后生成意见"
        }
    }
}
