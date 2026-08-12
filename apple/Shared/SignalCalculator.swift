import Foundation

public enum SignalCalculator {
    public static func calculate(history: [DailyBar], livePrice: Double) throws -> SignalLevels {
        let bars = history
            .filter { $0.high.isFinite && $0.low.isFinite && $0.close.isFinite }
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
        switch historyDays {
        case 205...:
            (fastPeriod, slowPeriod, quality, modelName, isReady) = (50, 200, .standard, "SMA50 / SMA200", true)
        case 65...:
            (fastPeriod, slowPeriod, quality, modelName, isReady) = (20, 50, .medium, "SMA20 / SMA50", true)
        case 35...:
            (fastPeriod, slowPeriod, quality, modelName, isReady) = (10, 30, .low, "SMA10 / SMA30", true)
        default:
            fastPeriod = min(10, historyDays)
            slowPeriod = min(30, historyDays)
            quality = .observationOnly
            modelName = "仅 \(historyDays) 根日线"
            isReady = false
        }

        let closes = bars.map(\.close)
        let trendFast = average(Array(closes.suffix(fastPeriod)))
        let trendSlow = average(Array(closes.suffix(slowPeriod)))
        let buyPoint = isReady ? bars.suffix(min(20, historyDays)).map(\.high).max() ?? 0 : 0
        let stopPoint = isReady ? max(0.01, buyPoint - 2 * atr14) : 0
        let trendOK = isReady && livePrice > trendSlow && trendFast > trendSlow

        let status: SignalStatus
        if !isReady {
            status = .dataShort
        } else if trendOK && livePrice >= buyPoint {
            status = .buyAlert
        } else if trendOK {
            status = .watch
        } else {
            status = .noSignal
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
            isReady: isReady
        )
    }

    private static func average(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return 0 }
        return values.reduce(0, +) / Double(values.count)
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
        let initialRisk: Double
        let sizingPrice: Double
        let sizingStop: Double

        if hasPosition {
            let movingAverageFloor = levels.trendFast < price ? levels.trendFast : 0.01
            let trailingCandidate = max(price - 2 * atr, movingAverageFloor)
            riskReductionPoint = max(0.01, min(trailingCandidate, price - 0.5 * atr))
            initialRisk = max(position.averageCost - riskReductionPoint, atr)
            sizingPrice = price
            sizingStop = riskReductionPoint
        } else {
            riskReductionPoint = levels.stopPoint
            initialRisk = max(levels.buyPoint - levels.stopPoint, atr)
            sizingPrice = levels.buyPoint
            sizingStop = levels.stopPoint
        }

        let target2R = (hasPosition ? position.averageCost : levels.buyPoint) + 2 * initialRisk
        let target3R = (hasPosition ? position.averageCost : levels.buyPoint) + 3 * initialRisk
        let riskBudget = settings.accountValue * settings.riskPercent / 100
        let riskPerShare = max(sizingPrice - sizingStop, atr * 0.5, 0.01)
        let maxByRisk = Int(floor(riskBudget / riskPerShare))
        let maxByValue = Int(floor((settings.accountValue * settings.maxPositionPercent / 100) / max(sizingPrice, 0.01)))
        let maximumShares = max(0, min(maxByRisk, maxByValue))

        let action: PositionAction
        if hasPosition {
            if price <= riskReductionPoint {
                action = .reduceForRisk(shares: position.quantity)
            } else if position.quantity > maximumShares {
                action = .reduceForExposure(shares: position.quantity - maximumShares)
            } else if price >= target3R {
                action = .reduceAt3R(shares: max(1, Int(ceil(Double(position.quantity) * 0.5))))
            } else if price >= target2R {
                action = .reduceAt2R(shares: max(1, Int(ceil(Double(position.quantity) * 0.25))))
            } else if levels.status == .buyAlert && position.quantity < maximumShares {
                action = .addAfterBreakout(maximumShares: maximumShares - position.quantity)
            } else {
                action = .hold
            }
        } else if levels.status == .buyAlert {
            action = .openAfterBreakout(maximumShares: maximumShares)
        } else {
            action = .wait(candidateMaximumShares: maximumShares)
        }

        return PositionPlan(
            riskReductionPoint: riskReductionPoint,
            profitTarget2R: target2R,
            profitTarget3R: target3R,
            maximumShares: maximumShares,
            action: action
        )
    }
}
