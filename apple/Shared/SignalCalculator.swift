import Foundation

public enum SignalCalculator {
    private static let signalLookbackDays = 10
    private static let minimumHistoryDays = 20

    public static func calculate(history: [DailyBar], livePrice: Double) throws -> SignalLevels {
        guard livePrice.isFinite, livePrice > 0 else { throw MarketDataError.noData("有效价格") }
        let bars = history
            .filter { $0.high.isFinite && $0.low.isFinite && $0.close.isFinite && $0.low > 0 && $0.high >= $0.low && $0.close >= $0.low && $0.close <= $0.high }
            .sorted { $0.date < $1.date }
        guard !bars.isEmpty else { throw MarketDataError.noData("历史日线") }

        var trueRanges: [Double] = []
        trueRanges.reserveCapacity(bars.count)
        for index in bars.indices {
            let bar = bars[index]
            var candidates = [bar.high - bar.low]
            if index > 0 {
                let previousClose = bars[index - 1].close
                candidates.append(abs(bar.high - previousClose))
                candidates.append(abs(bar.low - previousClose))
            }
            trueRanges.append(candidates.max() ?? 0)
        }

        let historyDays = bars.count
        let atrPeriod = min(14, historyDays)
        let atr14 = average(Array(trueRanges.suffix(atrPeriod)))

        let fastPeriod: Int
        let slowPeriod: Int
        let quality: SignalQuality
        let modelName: String
        let isReady: Bool
        fastPeriod = min(5, historyDays)
        slowPeriod = min(20, historyDays)
        isReady = historyDays >= minimumHistoryDays
        quality = isReady ? .standard : .observationOnly
        modelName = "\(signalLookbackDays)日高低点"

        let closes = bars.map(\.close)
        let trendFast = average(Array(closes.suffix(fastPeriod)))
        let trendSlow = average(Array(closes.suffix(slowPeriod)))
        let signalWindow = bars.suffix(min(signalLookbackDays, historyDays))
        let buyPoint = isReady ? signalWindow.map(\.high).max() ?? 0 : 0
        let stopPoint = isReady ? signalWindow.map(\.low).min() ?? 0 : 0
        let momentum5DayPercent = momentum(closes: closes, period: 5)
        let momentum10DayPercent = momentum(closes: closes, period: 10)
        let rsi14 = rsi(closes: closes, period: 14)
        let recentVolumes = bars.suffix(min(20, historyDays)).map(\.volume).filter { $0 > 0 }
        let volumeRatio = recentVolumes.count >= 2
            ? (recentVolumes.last ?? 0) / max(average(recentVolumes), 0.01)
            : 1

        let status: SignalStatus
        if !isReady {
            status = .dataShort
        } else if livePrice >= buyPoint {
            status = .buyAlert
        } else if livePrice <= stopPoint {
            status = .sellAlert
        } else {
            status = .watch
        }

        return SignalLevels(
            status: status,
            price: livePrice,
            buyPoint: buyPoint,
            stopPoint: stopPoint,
            riskPercent: buyPoint > 0 ? ((buyPoint - stopPoint) / buyPoint) * 100 : 0,
            atr14: atr14,
            trendFast: trendFast,
            trendSlow: trendSlow,
            historyDays: historyDays,
            quality: quality,
            modelName: modelName,
            isReady: isReady,
            momentum5DayPercent: momentum5DayPercent,
            momentum10DayPercent: momentum10DayPercent,
            rsi14: rsi14,
            volumeRatio: volumeRatio
        )
    }

    private static func momentum(closes: [Double], period: Int) -> Double {
        guard closes.count > period else { return 0 }
        let baseline = closes[closes.count - period - 1]
        guard baseline > 0 else { return 0 }
        return (closes.last! / baseline - 1) * 100
    }

    private static func rsi(closes: [Double], period: Int) -> Double {
        guard closes.count >= 2 else { return 50 }
        let changes = zip(closes.dropFirst(), closes).map { current, previous in current - previous }
        let recent = changes.suffix(min(period, changes.count))
        let gains = recent.reduce(0) { $0 + max($1, 0) } / Double(recent.count)
        let losses = recent.reduce(0) { $0 + max(-$1, 0) } / Double(recent.count)
        if losses == 0 { return gains > 0 ? 100 : 50 }
        return 100 - 100 / (1 + gains / losses)
    }

    private static func average(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return 0 }
        return values.reduce(0, +) / Double(values.count)
    }
}

public enum ActionProbabilityEstimator {
    public static func estimate(
        levels: SignalLevels,
        position: Position,
        settings: RiskSettings,
        portfolioValue: Double = 0,
        availableFunds: Double? = nil
    ) -> ActionProbabilityScore {
        guard levels.isReady else {
            return .init(buyProbability: 0, reduceProbability: 0, buyLabel: "数据不足", reduceLabel: "数据不足")
        }

        let price = max(0.01, levels.price)
        let buyPoint = max(0.01, levels.buyPoint)
        let stopPoint = max(0.01, levels.stopPoint)
        let atr = max(0.01, levels.atr14)
        let span = max(0.01, buyPoint - stopPoint)
        let channelPosition = clamp((price - stopPoint) / span, lower: 0, upper: 1)
        var buyScore = 12 + channelPosition * 32

        switch levels.status {
        case .buyAlert:
            let extensionPercent = max(0, (price / buyPoint - 1) * 100)
            buyScore += 20
            buyScore += extensionPercent <= 3 ? 5 : -min(30, (extensionPercent - 3) * 5)
        case .sellAlert:
            buyScore = min(buyScore, 10)
        default:
            let gapATR = (buyPoint - price) / atr
            if (0...1).contains(gapATR) { buyScore += 8 }
        }

        buyScore += price >= levels.trendFast ? 8 : -8
        buyScore += levels.trendFast >= levels.trendSlow ? 10 : -9
        buyScore += clamp(levels.momentum5DayPercent, lower: -5, upper: 5) * 1.4
        buyScore += clamp(levels.momentum10DayPercent, lower: -8, upper: 8) * 0.55
        if (48...68).contains(levels.rsi14) { buyScore += 8 }
        else if levels.rsi14 >= 78 { buyScore -= 13 }
        else if levels.rsi14 < 35 { buyScore -= 8 }
        if levels.volumeRatio >= 1.5 { buyScore += 7 }
        else if levels.volumeRatio >= 1.15 { buyScore += 3 }
        else if levels.volumeRatio < 0.55 { buyScore -= 4 }
        let channelRiskPercent = span / buyPoint * 100
        if channelRiskPercent <= 12 { buyScore += 5 }
        else if channelRiskPercent >= 22 { buyScore -= 9 }

        let quantity = max(0, position.quantity)
        let averageCost = max(0, position.averageCost)
        let accountValue = max(1, settings.accountValue)
        let allocationLimit = max(0.01, settings.maxPositionPercent / 100)
        let allocationLoad = (quantity * price / accountValue) / allocationLimit
        let portfolioRatio = max(0, portfolioValue) / accountValue
        let availableRatio = availableFunds.map { $0 / accountValue }
        if allocationLoad >= 1 { buyScore -= 28 }
        else if allocationLoad >= 0.8 { buyScore -= 14 }
        if portfolioRatio >= 1 { buyScore -= 12 }
        else if portfolioRatio >= 0.9 { buyScore -= 7 }
        if let availableRatio, availableRatio < 0.05 { buyScore -= 14 }
        let buyProbability = Int(clamp(buyScore, lower: 5, upper: 95).rounded())

        let reduceProbability: Int
        if quantity <= 0 || averageCost <= 0 {
            reduceProbability = 0
        } else {
            var reduceScore = 8.0
            let positionStop = max(stopPoint, position.initialStop.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? 0)
            if levels.status == .sellAlert { reduceScore += 48 }
            if price <= positionStop { reduceScore += 36 }
            reduceScore += price < levels.trendFast ? 10 : -3
            reduceScore += levels.trendFast < levels.trendSlow ? 9 : -3
            if levels.momentum5DayPercent < 0 { reduceScore += min(14, abs(levels.momentum5DayPercent) * 1.8) }
            if levels.momentum10DayPercent < 0 { reduceScore += min(10, abs(levels.momentum10DayPercent) * 0.8) }
            let profitPercent = (price / averageCost - 1) * 100
            if profitPercent <= -8 { reduceScore += 18 }
            else if profitPercent <= -3 { reduceScore += 10 }
            if profitPercent >= 10, levels.rsi14 >= 70 { reduceScore += 12 }
            if price > buyPoint, (price / buyPoint - 1) * 100 > 5 { reduceScore += 10 }
            if allocationLoad >= 1.25 { reduceScore += 27 }
            else if allocationLoad >= 1 { reduceScore += 19 }
            else if allocationLoad >= 0.8 { reduceScore += 9 }
            if portfolioRatio >= 1 { reduceScore += 13 }
            else if portfolioRatio >= 0.9 { reduceScore += 8 }
            if let availableRatio, availableRatio < 0.05 { reduceScore += 11 }
            if levels.status == .buyAlert, levels.trendFast >= levels.trendSlow, allocationLoad < 0.8 { reduceScore -= 14 }
            var score = Int(clamp(reduceScore, lower: 5, upper: 95).rounded())
            if price <= positionStop { score = max(score, 90) }
            reduceProbability = score
        }

        return .init(
            buyProbability: buyProbability,
            reduceProbability: reduceProbability,
            buyLabel: label(for: buyProbability),
            reduceLabel: quantity <= 0 ? "无持仓" : label(for: reduceProbability)
        )
    }

    private static func clamp(_ value: Double, lower: Double, upper: Double) -> Double {
        max(lower, min(upper, value))
    }

    private static func label(for score: Int) -> String {
        if score >= 75 { return "高" }
        if score >= 55 { return "中高" }
        if score >= 35 { return "观察" }
        return "低"
    }
}

public enum PositionPlanner {
    public static func makePlan(levels: SignalLevels, position: Position, settings: RiskSettings) -> PositionPlan {
        guard levels.isReady else {
            return PositionPlan(
                riskReductionPoint: 0,
                profitTarget2R: 0,
                profitTarget3R: 0,
                maximumShares: 0,
                action: .insufficientHistory
            )
        }

        let price = levels.price
        let atr = max(0.01, levels.atr14)
        let hasPosition = position.quantity > 0 && position.averageCost > 0
        let riskReductionPoint: Double
        let riskEntryPrice: Double
        let riskReferenceStop: Double
        let exposurePrice: Double

        if hasPosition {
            let savedStop = position.initialStop.flatMap { stop in
                stop.isFinite && stop > 0 && stop < position.averageCost ? stop : nil
            }
            riskReductionPoint = max(levels.stopPoint, savedStop ?? 0)
            riskEntryPrice = position.averageCost
            riskReferenceStop = savedStop ?? min(levels.stopPoint, position.averageCost - 0.01)
            exposurePrice = price
        } else {
            riskReductionPoint = levels.stopPoint
            riskEntryPrice = levels.buyPoint
            riskReferenceStop = levels.stopPoint
            exposurePrice = levels.buyPoint
        }

        let riskBudget = settings.accountValue * settings.riskPercent / 100
        let riskPerShare = max(riskEntryPrice - riskReferenceStop, atr * 0.5, 0.01)
        let maxByRisk = Int(floor(riskBudget / riskPerShare))
        let maxByValue = Int(floor((settings.accountValue * settings.maxPositionPercent / 100) / max(exposurePrice, 0.01)))
        let maximumShares = max(0, min(maxByRisk, maxByValue))

        let action: PositionAction
        if hasPosition {
            if price <= riskReductionPoint || levels.status == .sellAlert {
                action = .sellSignal(shares: position.quantity)
            } else if levels.status == .buyAlert {
                let additionalShares = max(0, Int(floor(Double(maximumShares) - position.quantity)))
                action = additionalShares > 0 ? .addAfterBreakout(maximumShares: additionalShares) : .hold
            } else if position.quantity > Double(maximumShares) {
                action = .reduceForExposure(shares: position.quantity - Double(maximumShares))
            } else {
                action = .hold
            }
        } else if levels.status == .buyAlert {
            action = .openAfterBreakout(maximumShares: maximumShares)
        } else if levels.status == .sellAlert {
            action = .sellSignalNoPosition
        } else {
            action = .wait(candidateMaximumShares: maximumShares)
        }

        return PositionPlan(
            riskReductionPoint: riskReductionPoint,
            profitTarget2R: 0,
            profitTarget3R: 0,
            maximumShares: maximumShares,
            action: action
        )
    }
}
