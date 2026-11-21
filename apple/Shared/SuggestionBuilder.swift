import Foundation

public struct TradeSuggestion: Equatable, Hashable, Sendable {
    public let symbol: String
    public let side: String
    public let title: String
    public let triggers: [String]
    public let buyScore: Int
    public let reduceScore: Int
    public let confidence: String
    public let risks: [String]
    public let positionHint: String
    public let alertTier: String
    public let feedProfile: String
    public let historyDate: String
    public let disclaimer: String

    public var explainText: String {
        var lines = [
            "【建议】\(symbol) · \(title)",
            "方向：\(side) · 置信度：\(confidence) · 告警级：\(alertTier)",
            "买入操作评分：\(buyScore) · 减持评分：\(reduceScore)",
        ]
        if !triggers.isEmpty {
            lines.append("触发条件：")
            lines.append(contentsOf: triggers.map { "  - \($0)" })
        }
        if !risks.isEmpty {
            lines.append("风险提示：")
            lines.append(contentsOf: risks.map { "  - \($0)" })
        }
        if !positionHint.isEmpty { lines.append("仓位参考：\(positionHint)") }
        if !feedProfile.isEmpty { lines.append("行情画像：\(feedProfile)") }
        if !historyDate.isEmpty { lines.append("通道基准日：\(historyDate)") }
        lines.append(disclaimer)
        return lines.joined(separator: "\n")
    }
}

public enum SuggestionBuilder {
    public static let disclaimer =
        "本输出为技术监控与仓位辅助规则结果，不构成投资建议，不保证收益，也不代表券商指令；请自行判断并在券商端操作。"

    public static func build(
        symbol: String,
        filtered: FilteredSignal,
        score: ActionProbabilityScore,
        plan: PositionPlan,
        observation: String?,
        feedProfile: String,
        quoteAgeSeconds: Double?
    ) -> TradeSuggestion {
        let levels = filtered.levels
        var triggers: [String] = []
        var risks = filtered.notes
        if levels.isReady {
            triggers.append(String(format: "10日通道：买入线 $%.2f / 卖出线 $%.2f", levels.buyPoint, levels.stopPoint))
            triggers.append(String(format: "现价 $%.2f", levels.price))
            if filtered.rawStatus == .buyAlert { triggers.append("现价达到或突破通道高点") }
            if filtered.rawStatus == .sellAlert { triggers.append("现价达到或跌破通道低点") }
            triggers.append(String(format: "量比 %.2f · RSI %.0f", levels.volumeRatio, levels.rsi14))
        }

        let side: String
        let title: String
        let tier: String
        if let observation {
            side = "observe"; title = "仅观察：\(observation)"; tier = "silent"; risks.append(observation)
        } else if !levels.isReady {
            side = "observe"; title = "历史不足"; tier = "silent"
        } else if filtered.suppressed {
            side = "observe"; title = "过滤后暂不提示（原触发已降级）"; tier = "secondary"
        } else if levels.status == .buyAlert {
            side = "buy"; title = "买入提示（通道突破）"; tier = "primary"
        } else if levels.status == .sellAlert {
            side = "reduce"; title = "卖出/减持提示"; tier = "primary"
        } else if score.reduceProbability >= 75 {
            side = "reduce"; title = "建议关注减持（高评分）"; tier = "secondary"
        } else {
            side = "hold"; title = actionText(plan.action); tier = "silent"
        }

        let confidence: String
        if observation != nil || filtered.suppressed {
            confidence = "low"
        } else if (quoteAgeSeconds ?? 0) > 30 || filtered.breakoutExtensionPercent > 3 {
            confidence = "medium"
        } else {
            confidence = "high"
        }

        return TradeSuggestion(
            symbol: symbol,
            side: side,
            title: title,
            triggers: triggers,
            buyScore: score.buyProbability,
            reduceScore: score.reduceProbability,
            confidence: confidence,
            risks: risks,
            positionHint: actionText(plan.action),
            alertTier: tier,
            feedProfile: feedProfile,
            historyDate: "",
            disclaimer: disclaimer
        )
    }

    private static func actionText(_ action: PositionAction) -> String {
        switch action {
        case .needsRiskBaseline: return "等待建立保护线"
        case .observationOnly(let reason): return "仅观察：\(reason)"
        case .insufficientHistory: return "历史不足"
        case .reduceForRisk(let shares): return String(format: "风险减仓参考 %.4g 股", shares)
        case .reduceForExposure(let shares): return String(format: "超限减仓参考 %.4g 股", shares)
        case .reduceAt2R(let shares): return String(format: "2R 减仓参考 %.4g 股", shares)
        case .reduceAt3R(let shares): return String(format: "3R 减仓参考 %.4g 股", shares)
        case .addAfterBreakout(let maximumShares): return "突破后参考加仓上限 \(maximumShares) 股"
        case .openAfterBreakout(let maximumShares): return "突破后参考开仓上限 \(maximumShares) 股"
        case .sellSignal(let shares): return String(format: "卖出提示：参考 %.4g 股", shares)
        case .sellSignalNoPosition: return "卖出提示：当前无持仓"
        case .wait(let candidateMaximumShares): return "等待触发；参考上限 \(candidateMaximumShares) 股"
        case .hold: return "持有"
        }
    }
}
