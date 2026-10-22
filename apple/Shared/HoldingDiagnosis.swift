import Foundation

// Deterministic, offline holding diagnosis and action-plan engine.
// Rule-based, read-only analysis aid: it never creates orders, never calls a
// network service and no LLM participates in any decision. This is a port of
// holding_diagnosis.py and must stay numerically identical; both sides assert
// Tests/SharedTests/Fixtures/holding_diagnosis.json.

public enum HoldingDiagnosisText {
    public static let disclaimer = "规则化分析辅助，非投资建议；只读监控，不会创建或提交任何订单。"
}

public struct HoldingDiagnosisSettings: Codable, Hashable, Sendable {
    public var accountValue: Double
    public var riskPercent: Double
    public var maxPositionPercent: Double
    public var atrStopMultiplier: Double
    public var takeProfitATRMultiple: Double
    public var portfolioRiskPercent: Double
    public var maxAverageDownCount: Int
    public var averageDownFraction: Double
    public var averageDownMaxLossPercent: Double
    public var addPullbackATR: Double
    public var reduceFraction: Double
    public var scaleOutFraction: Double
    public var rsStableTolerancePercent: Double
    public var switchMinGapPercent: Double
    public var eventWindowDays: Int
    public var maxSectorPercent: Double
    public var breakevenATR: Double
    public var maxLeveragePercent: Double
    public var deleverageMinWeightPercent: Double
    public var watchDays: Int
    public var watchLineBreachDays: Int
    public var rsDeteriorationPP: Double
    public var averageDownTranches: Int

    public init(
        accountValue: Double = 100_000,
        riskPercent: Double = 1,
        maxPositionPercent: Double = 10,
        atrStopMultiplier: Double = 2,
        takeProfitATRMultiple: Double = 3,
        portfolioRiskPercent: Double = 6,
        maxAverageDownCount: Int = 2,
        averageDownFraction: Double = 0.5,
        averageDownMaxLossPercent: Double = 15,
        addPullbackATR: Double = 0.5,
        reduceFraction: Double = 0.5,
        scaleOutFraction: Double = 0.33,
        rsStableTolerancePercent: Double = 0.5,
        switchMinGapPercent: Double = 5,
        eventWindowDays: Int = 7,
        maxSectorPercent: Double = 35,
        breakevenATR: Double = 1.5,
        maxLeveragePercent: Double = 100,
        deleverageMinWeightPercent: Double = 10,
        watchDays: Int = 10,
        watchLineBreachDays: Int = 2,
        rsDeteriorationPP: Double = 5,
        averageDownTranches: Int = 2
    ) {
        self.accountValue = min(1e12, max(1, accountValue))
        self.riskPercent = min(10, max(0.1, riskPercent))
        self.maxPositionPercent = min(100, max(1, maxPositionPercent))
        self.atrStopMultiplier = min(5, max(0.5, atrStopMultiplier))
        self.takeProfitATRMultiple = min(10, max(1, takeProfitATRMultiple))
        self.portfolioRiskPercent = min(50, max(0.5, portfolioRiskPercent))
        self.maxAverageDownCount = min(10, max(0, maxAverageDownCount))
        self.averageDownFraction = min(2, max(0.05, averageDownFraction))
        self.averageDownMaxLossPercent = min(80, max(1, averageDownMaxLossPercent))
        self.addPullbackATR = min(3, max(0, addPullbackATR))
        self.reduceFraction = min(0.95, max(0.05, reduceFraction))
        self.scaleOutFraction = min(0.95, max(0.05, scaleOutFraction))
        self.rsStableTolerancePercent = min(10, max(0, rsStableTolerancePercent))
        self.switchMinGapPercent = min(50, max(0, switchMinGapPercent))
        self.eventWindowDays = min(60, max(0, eventWindowDays))
        self.maxSectorPercent = min(100, max(5, maxSectorPercent))
        self.breakevenATR = min(10, max(0, breakevenATR))
        self.maxLeveragePercent = min(400, max(10, maxLeveragePercent))
        self.deleverageMinWeightPercent = min(100, max(0, deleverageMinWeightPercent))
        self.watchDays = min(30, max(3, watchDays))
        self.watchLineBreachDays = min(5, max(1, watchLineBreachDays))
        self.rsDeteriorationPP = min(20, max(1, rsDeteriorationPP))
        self.averageDownTranches = min(3, max(1, averageDownTranches))
    }

    /// Engine options combined with the account risk and strategy settings already used by the monitor.
    public func resolved(risk: RiskSettings, strategy: MonitorStrategySettings) -> HoldingDiagnosisSettings {
        var copy = self
        copy.accountValue = min(1e12, max(1, risk.accountValue))
        copy.riskPercent = risk.riskPercent
        copy.maxPositionPercent = risk.maxPositionPercent
        copy.atrStopMultiplier = min(5, max(0.5, strategy.atrStopMultiplier))
        copy.takeProfitATRMultiple = min(10, max(1, strategy.takeProfitATRMultiple))
        return copy
    }

    public var positionBudget: Double { accountValue * riskPercent / 100 }
    public var portfolioBudget: Double { accountValue * portfolioRiskPercent / 100 }
    public var maxPositionValue: Double { accountValue * maxPositionPercent / 100 }
}

public struct HoldingMetrics: Codable, Hashable, Sendable {
    public var price: Double
    public var atr14: Double
    public var ma20: Double?
    public var ma50: Double?
    public var ma200: Double?
    public var channelLow10: Double?
    public var swingLow: Double?
    public var refClose5: Double?
    public var refClose20: Double?
    public var rsi14: Double
    public var historyDays: Int
    public var refClose60: Double?

    public init(
        price: Double,
        atr14: Double,
        ma20: Double? = nil,
        ma50: Double? = nil,
        ma200: Double? = nil,
        channelLow10: Double? = nil,
        swingLow: Double? = nil,
        refClose5: Double? = nil,
        refClose20: Double? = nil,
        rsi14: Double = 50,
        historyDays: Int = 0,
        refClose60: Double? = nil
    ) {
        self.price = price
        self.atr14 = atr14
        self.ma20 = Self.positive(ma20)
        self.ma50 = Self.positive(ma50)
        self.ma200 = Self.positive(ma200)
        self.channelLow10 = Self.positive(channelLow10)
        self.swingLow = Self.positive(swingLow)
        self.refClose5 = Self.positive(refClose5)
        self.refClose20 = Self.positive(refClose20)
        self.rsi14 = rsi14
        self.historyDays = historyDays
        self.refClose60 = Self.positive(refClose60)
    }

    public func change(from reference: Double?) -> Double? {
        guard let reference, reference > 0 else { return nil }
        return (price / reference - 1) * 100
    }

    public var ret5: Double? { change(from: refClose5) }
    public var ret20: Double? { change(from: refClose20) }
    public var ret60: Double? { change(from: refClose60) }

    public func withPrice(_ livePrice: Double) -> HoldingMetrics {
        var copy = self
        copy.price = livePrice
        return copy
    }

    /// Same bar filtering, ATR and RSI as `SignalCalculator`, so live levels and diagnosis agree.
    public static func compute(history: [DailyBar], livePrice: Double, rsi14: Double = 50) -> HoldingMetrics? {
        guard livePrice.isFinite, livePrice > 0 else { return nil }
        let bars = history
            .filter { $0.high.isFinite && $0.low.isFinite && $0.close.isFinite && $0.low > 0 && $0.high >= $0.low && $0.close >= $0.low && $0.close <= $0.high }
            .sorted { $0.date < $1.date }
        guard !bars.isEmpty else { return nil }
        var trueRanges: [Double] = []
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
        let window = Array(trueRanges.suffix(min(14, trueRanges.count)))
        let atr = window.reduce(0, +) / Double(window.count)
        return fields(highs: bars.map(\.high), lows: bars.map(\.low), closes: bars.map(\.close), price: livePrice, atr14: atr, rsi14: rsi14)
    }

    public static func fields(highs: [Double], lows: [Double], closes: [Double], price: Double, atr14: Double, rsi14: Double = 50) -> HoldingMetrics {
        let count = closes.count
        func meanTail(_ period: Int) -> Double? {
            guard count >= period else { return nil }
            return closes[(count - period)...].reduce(0, +) / Double(period)
        }
        let swing: Double? = count >= 30 ? lows[max(0, count - 60)..<(count - 10)].min() : nil
        let channel: Double? = count > 0 ? lows[(count - min(10, count))...].min() : nil
        return HoldingMetrics(
            price: price,
            atr14: atr14,
            ma20: meanTail(20),
            ma50: meanTail(50),
            ma200: meanTail(200),
            channelLow10: channel,
            swingLow: swing,
            refClose5: count >= 5 ? closes[count - 5] : nil,
            refClose20: count >= 20 ? closes[count - 20] : nil,
            rsi14: rsi14,
            historyDays: count,
            refClose60: count >= 60 ? closes[count - 60] : nil
        )
    }

    private static func positive(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0 else { return nil }
        return value
    }
}

public enum HoldingMode: String, Codable, Hashable, Sendable {
    case loss
    case profit
}

public enum HoldingTrendState: String, Codable, Hashable, Sendable {
    case intact
    case weakening
    case broken
    case unknown

    public var label: String {
        switch self {
        case .intact: "趋势完好"
        case .weakening: "趋势走弱"
        case .broken: "趋势破位"
        case .unknown: "数据不足"
        }
    }
}

public enum HoldingLossSource: String, Codable, Hashable, Sendable {
    case idio
    case sector
    case market
    case cost
    case unknown

    public var label: String {
        switch self {
        case .idio: "个股走弱"
        case .sector: "板块拖累"
        case .market: "大盘回撤"
        case .cost: "建仓成本偏高（近20日未走弱）"
        case .unknown: "数据不足（缺基准）"
        }
    }
}

public enum HoldingPlanKind: String, Codable, CaseIterable, Hashable, Sendable {
    case stopExit = "stop_exit"
    case holdWatch = "hold_watch"
    case averageDown = "average_down"
    case addOnStrength = "add_on_strength"
    case reduceRisk = "reduce_risk"
    case rallyReduce = "rally_reduce"
    case scaleOut = "scale_out"
    case switchPosition = "switch"

    public func name(for mode: HoldingMode) -> String {
        switch self {
        case .stopExit: mode == .profit ? "保护利润离场" : "止损离场"
        case .holdWatch: mode == .profit ? "持有并上移保护线" : "持有观察"
        case .averageDown: "分批补仓摊低"
        case .addOnStrength: "顺势加仓"
        case .reduceRisk: "减仓降风险"
        case .rallyReduce: "反弹减仓"
        case .scaleOut: "分批止盈"
        case .switchPosition: "换仓同板块更强标的"
        }
    }

    static let priority: [HoldingPlanKind] = [
        .stopExit, .reduceRisk, .rallyReduce, .scaleOut, .holdWatch, .switchPosition, .averageDown, .addOnStrength,
    ]
    static let lossOrder: [HoldingPlanKind] = [.stopExit, .holdWatch, .averageDown, .reduceRisk, .rallyReduce, .switchPosition]
    static let profitOrder: [HoldingPlanKind] = [.holdWatch, .addOnStrength, .scaleOut, .reduceRisk, .stopExit, .switchPosition]
}

public struct HoldingActionPlan: Codable, Hashable, Sendable, Identifiable {
    public enum Action: String, Codable, Hashable, Sendable {
        case sell, buy, hold
        case switchPosition = "switch"
    }

    public var kind: HoldingPlanKind
    public var name: String
    public var allowed: Bool
    public var blockedReason: String = ""
    public var action: Action = .hold
    public var trigger: String = ""
    public var price: Double?
    public var quantityChange: Double = 0
    public var quantityAfter: Double = 0
    public var averageCostAfter: Double?
    public var stopAfter: Double?
    public var worstLoss: Double = 0
    public var realizedPnL: Double = 0
    public var budgetPercent: Double = 0
    public var portfolioBudgetPercent: Double = 0
    public var score: Int = 0
    public var targetSymbol: String = ""
    public var steps: [HoldingPlanStep] = []

    public var id: String { kind.rawValue }
}

public struct HoldingPlanStep: Codable, Hashable, Sendable {
    public var side: String
    public var quantity: Double
    public var price: Double
    public var label: String

    public init(side: String, quantity: Double, price: Double, label: String) {
        self.side = side
        self.quantity = quantity
        self.price = price
        self.label = label
    }
}

public struct HoldingAttribution: Codable, Hashable, Sendable {
    public var stock: Double?
    public var market: Double?
    public var sector: Double?
    public var idio: Double?
}

public struct HoldingSwitchCondition: Codable, Hashable, Sendable {
    public var target: HoldingPlanKind
    public var targetName: String
    public var condition: String
}

public struct HoldingDiagnosis: Codable, Hashable, Sendable {
    public var symbol: String
    public var mode: HoldingMode
    public var dataReady: Bool
    public var price: Double
    public var averageCost: Double
    public var quantity: Double
    public var pnlPercent: Double
    public var pnlAmount: Double
    public var marketValue: Double
    public var weightPercent: Double
    public var trendState: HoldingTrendState
    public var trendFlags: [String]
    public var lossSource: HoldingLossSource
    public var lossSourceLabel: String
    public var attribution: HoldingAttribution
    public var rs5: Double?
    public var rs20: Double?
    public var rs60: Double?
    public var rsStable: Bool?
    public var leveragePercent: Double?
    public var overLeveraged: Bool
    public var sectorSymbol: String?
    public var sectorLabel: String
    public var atr: Double
    public var atrPercent: Double
    public var volatilityLabel: String
    public var earningsDays: Int?
    public var eventNear: Bool
    public var stop: Double
    public var stopBasis: String
    public var stopHit: Bool
    public var holdRisk: Double
    public var positionBudget: Double
    public var budgetRatio: Double
    public var overweight: Bool
    public var plans: [HoldingActionPlan]
    public var recommended: HoldingPlanKind
    public var confidence: String
    public var switchConditions: [HoldingSwitchCondition]
    public var summary: String
    public var watchLine: Double?
    public var hardStop: Double?
    public var watchDays: Int
    public var nonSellPlan: HoldingPlanKind?
    public var nonSellSummary: String
    public var disclaimer: String = HoldingDiagnosisText.disclaimer

    public func plan(_ kind: HoldingPlanKind) -> HoldingActionPlan? {
        plans.first { $0.kind == kind }
    }

    public var recommendedPlan: HoldingActionPlan? { plan(recommended) }
}

public struct HoldingDiagnosisContext: Sendable {
    public var market: HoldingMetrics?
    public var sector: HoldingMetrics?
    public var peers: [String: HoldingMetrics]
    public var earningsDays: Int?
    /// Gross long market value / account net liquidation, in percent.
    public var leveragePercent: Double?

    public init(
        market: HoldingMetrics? = nil,
        sector: HoldingMetrics? = nil,
        peers: [String: HoldingMetrics] = [:],
        earningsDays: Int? = nil,
        leveragePercent: Double? = nil
    ) {
        self.market = market
        self.sector = sector
        self.peers = peers
        self.earningsDays = earningsDays
        self.leveragePercent = leveragePercent
    }
}

public struct SectorExposure: Codable, Hashable, Sendable {
    public var sectorSymbol: String?
    public var sectorLabel: String
    public var weightPercent: Double
}

public struct PortfolioDiagnosis: Codable, Hashable, Sendable {
    public var holdings: [HoldingDiagnosis]
    public var sectorExposure: [SectorExposure]
    public var topWeightPercent: Double
    public var top3WeightPercent: Double
    public var totalHoldRisk: Double
    public var portfolioBudget: Double
    public var notes: [String]
    public var leveragePercent: Double = 0
    public var overLeveraged = false
    public var deleverageAmount: Double = 0
    public var disclaimer: String = HoldingDiagnosisText.disclaimer
}

public enum HoldingDiagnosisEngine {
    private static let epsilon = 1e-9
    static let smallRiskRatio = 0.5
    static let mediumTermLeaderPP = 10.0
    static let minChannelStopATR = 0.5

    static func floorShares(_ value: Double) -> Double {
        value.isFinite ? (value + epsilon).rounded(.down) : 0
    }

    public static func trendState(_ metrics: HoldingMetrics) -> (HoldingTrendState, [String]) {
        let price = metrics.price
        guard metrics.historyDays >= 20, let ma20 = metrics.ma20 else { return (.unknown, ["历史日线不足 20 根"]) }
        let mid = metrics.ma50 ?? ma20
        let below20 = price < ma20
        let belowMid = price < mid
        // Without MA200 (young listings) a mid-MA break alone is only "weakening".
        let belowLong = metrics.ma200.map { price < $0 } ?? false
        let brokeChannel = metrics.channelLow10.map { price <= $0 } ?? false
        let brokeSwing = metrics.swingLow.map { price < $0 } ?? false
        var flags = ["\(below20 ? "低于" : "站上")MA20 $\(money(ma20))"]
        if let ma50 = metrics.ma50 { flags.append("\(price < ma50 ? "低于" : "站上")MA50 $\(money(ma50))") }
        if let ma200 = metrics.ma200 { flags.append("\(price < ma200 ? "低于" : "站上")MA200 $\(money(ma200))") }
        if brokeChannel, let low = metrics.channelLow10 { flags.append("触及/跌破10日通道下沿 $\(money(low))") }
        if brokeSwing, let swing = metrics.swingLow { flags.append("跌破前低 $\(money(swing))") }
        if brokeSwing || (belowMid && belowLong) || (brokeChannel && belowMid) { return (.broken, flags) }
        if below20 || belowMid || brokeChannel { return (.weakening, flags) }
        return (.intact, flags)
    }

    static func attribution(_ metrics: HoldingMetrics, context: HoldingDiagnosisContext) -> (HoldingLossSource, HoldingAttribution) {
        let stock20 = metrics.ret20
        let market20 = context.market?.ret20
        let sector20 = context.sector?.ret20
        guard let stock20, let market20 else {
            return (.unknown, HoldingAttribution(stock: stock20, market: nil, sector: nil, idio: nil))
        }
        let sectorComponent = sector20.map { $0 - market20 } ?? 0
        let idioComponent = stock20 - (sector20 ?? market20)
        let result = HoldingAttribution(stock: stock20, market: market20, sector: sectorComponent, idio: idioComponent)
        if stock20 >= 0 { return (.cost, result) }
        var source = HoldingLossSource.idio
        var lowest = idioComponent
        for (name, value) in [(HoldingLossSource.sector, sectorComponent), (.market, market20)] where value < lowest {
            source = name
            lowest = value
        }
        return (source, result)
    }

    static func relativeStrength(_ metrics: HoldingMetrics, context: HoldingDiagnosisContext) -> (Double?, Double?, Double?) {
        func spread(_ value: KeyPath<HoldingMetrics, Double?>) -> Double? {
            let reference = context.sector?[keyPath: value] ?? context.market?[keyPath: value]
            return metrics[keyPath: value].flatMap { stock in reference.map { stock - $0 } }
        }
        return (spread(\.ret5), spread(\.ret20), spread(\.ret60))
    }

    // swiftlint:disable:next function_body_length cyclomatic_complexity
    public static func diagnose(
        symbol rawSymbol: String,
        quantity: Double,
        averageCost cost: Double,
        initialStop: Double? = nil,
        averageDownCount adds: Int = 0,
        metrics: HoldingMetrics,
        context: HoldingDiagnosisContext = .init(),
        settings: HoldingDiagnosisSettings = .init()
    ) -> HoldingDiagnosis? {
        let symbol = rawSymbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let price = metrics.price
        guard quantity > 0, cost > 0, price > 0 else { return nil }
        let savedStop = initialStop.flatMap { $0.isFinite && $0 > 0 ? $0 : nil }

        let pnlPercent = (price / cost - 1) * 100
        let pnlAmount = (price - cost) * quantity
        let mode: HoldingMode = pnlPercent < 0 ? .loss : .profit
        let atr = metrics.atr14 > 0 ? metrics.atr14 : price * 0.01
        let atrPercent = atr / price * 100
        let volatility = atrPercent < 2 ? "低" : atrPercent < 4 ? "中" : "高"
        let highVol = atrPercent >= 4

        let (trend, flags) = trendState(metrics)
        let dataReady = trend != .unknown
        let (source, attribution) = attribution(metrics, context: context)
        let (rs5, rs20, rs60) = relativeStrength(metrics, context: context)
        let tolerance = settings.rsStableTolerancePercent
        let rsStable: Bool? = rs5.map { $0 >= -tolerance }
        let earningsDays = context.earningsDays
        let eventNear = earningsDays.map { $0 >= 0 && $0 <= settings.eventWindowDays } ?? false
        let leveragePercent = context.leveragePercent
        let overLeveraged = leveragePercent.map { $0 > settings.maxLeveragePercent } ?? false
        let leverageReason = overLeveraged
            ? "账户杠杆 \(String(format: "%.0f", leveragePercent ?? 0))% > \(plain(settings.maxLeveragePercent))%，先降杠杆，禁止补仓/加仓/建仓"
            : ""

        let k = settings.atrStopMultiplier
        let stopHit = savedStop.map { price <= $0 } ?? false
        let atrStop = price - k * atr
        let channel = metrics.channelLow10
        var candidates: [(Double, String)] = []
        if mode == .loss {
            // A saved stop is the hard line; a channel low hugging the price is only a watch line.
            if let savedStop, savedStop < price {
                candidates.append((savedStop, "已保存保护线"))
            } else if let channel, channel < price - minChannelStopATR * atr {
                candidates.append((channel, "10日通道下沿"))
            }
        } else {
            if let savedStop, savedStop < price { candidates.append((savedStop, "已保存保护线")) }
            if let channel, channel < price { candidates.append((channel, "10日通道下沿")) }
            if atrStop > 0 { candidates.append((atrStop, "现价−\(plain(k))×ATR 跟踪")) }
            if price - cost >= settings.breakevenATR * atr, cost < price { candidates.append((cost, "成本保本线")) }
        }
        var stop: Double
        var stopBasis: String
        if let first = candidates.first {
            (stop, stopBasis) = first
            for (value, basis) in candidates.dropFirst() where value > stop {
                stop = value
                stopBasis = basis
            }
        } else if atrStop > 0 {
            stop = atrStop
            stopBasis = "现价−\(plain(k))×ATR"
        } else {
            stop = price * 0.9
            stopBasis = "现价−10%"
        }

        let budget = settings.positionBudget
        let portfolioBudget = settings.portfolioBudget
        let maxValue = settings.maxPositionValue
        let holdRisk = (price - stop) * quantity
        let budgetRatio = holdRisk / budget
        let overBudget = budgetRatio > 1
        let marketValue = quantity * price
        let weightPercent = marketValue / settings.accountValue * 100
        let overweight = weightPercent > settings.maxPositionPercent
        let deep = pnlPercent <= -settings.averageDownMaxLossPercent
        let intact = trend == .intact
        let weakening = trend == .weakening
        let broken = trend == .broken

        func finish(_ plan: HoldingActionPlan) -> HoldingActionPlan {
            var plan = plan
            plan.budgetPercent = plan.worstLoss / budget * 100
            plan.portfolioBudgetPercent = plan.worstLoss / portfolioBudget * 100
            return plan
        }
        func blocked(_ kind: HoldingPlanKind, _ reason: String) -> HoldingActionPlan {
            HoldingActionPlan(kind: kind, name: kind.name(for: mode), allowed: false, blockedReason: reason)
        }
        func make(_ kind: HoldingPlanKind) -> HoldingActionPlan {
            HoldingActionPlan(kind: kind, name: kind.name(for: mode), allowed: true)
        }

        let midMA = metrics.ma50 ?? metrics.ma20
        var watchLine: Double? = nil
        if mode == .loss, let channel, stop < channel, channel < price {
            watchLine = channel
        } else if mode == .loss, let midMA, stop < midMA, midMA < price {
            watchLine = midMA
        }
        let watchDays = mode == .loss ? settings.watchDays : 0

        var plans: [HoldingPlanKind: HoldingActionPlan] = [:]
        var exit = make(.stopExit)
        exit.action = .sell
        exit.trigger = "现价附近卖出全部 \(plain(quantity)) 股；或收盘跌破硬止损 $\(money(stop))"
        exit.price = price
        exit.quantityChange = -quantity
        exit.quantityAfter = 0
        exit.realizedPnL = (price - cost) * quantity
        exit.steps = [HoldingPlanStep(side: "SELL", quantity: quantity, price: price, label: "现价离场")]
        plans[.stopExit] = finish(exit)

        var hold = make(.holdWatch)
        var holdSteps: [HoldingPlanStep] = []
        if mode == .loss {
            let half = quantity >= 2 ? floorShares(quantity / 2) : 0
            if let watchLine, half >= 1 {
                holdSteps.append(.init(side: "SELL", quantity: half, price: watchLine, label: "连续\(settings.watchLineBreachDays)日收盘低于观察线则减半"))
                holdSteps.append(.init(side: "SELL", quantity: quantity - half, price: stop, label: "硬止损"))
            } else {
                holdSteps.append(.init(side: "SELL", quantity: quantity, price: stop, label: "硬止损"))
            }
            var trigger = ""
            if let watchLine {
                let basis = channel == watchLine ? "（10日通道下沿）" : "（中期均线）"
                trigger = "观察线 $\(money(watchLine))\(basis)，硬止损 $\(money(stop))；观察 \(watchDays) 个交易日；"
                if half >= 1 { trigger += "连续 \(settings.watchLineBreachDays) 日收盘低于观察线减半，" }
            } else {
                trigger = "硬止损 $\(money(stop))；观察 \(watchDays) 个交易日；"
            }
            trigger += "触及硬止损或近5日相对强弱再走弱 \(plain(settings.rsDeteriorationPP))pp 全部止损"
            hold.trigger = trigger
            hold.price = watchLine ?? stop
        } else {
            hold.trigger = "保护线上移至 $\(money(stop))，收盘跌破则离场"
            hold.price = stop
            holdSteps = [.init(side: "SELL", quantity: quantity, price: stop, label: "上移后保护线")]
        }
        hold.quantityAfter = quantity
        hold.averageCostAfter = cost
        hold.stopAfter = stop
        hold.worstLoss = holdRisk
        hold.steps = holdSteps
        plans[.holdWatch] = finish(hold)

        func sizeAdd(_ entry: Double, openQty: Double, openRisk: Double, capFraction: Double) -> Double {
            guard entry > stop else { return 0 }
            let room = budget - openRisk
            let byRisk = room > 0 ? floorShares(room / (entry - stop)) : 0
            let headroom = maxValue - openQty * price
            let byValue = headroom > 0 ? floorShares(headroom / entry) : 0
            return floorShares(min(quantity * capFraction, byRisk, byValue))
        }

        if mode == .loss {
            var trancheLevels: [(Double, String)] = []
            let pullback = price - settings.addPullbackATR * atr
            var first: Double?
            var firstLabel = ""
            if let midMA, stop < midMA, midMA < price {
                first = midMA
                firstLabel = metrics.ma50 != nil ? "MA50" : "MA20"
            } else if pullback > stop {
                first = pullback
                firstLabel = "现价−\(plain(settings.addPullbackATR))×ATR"
            }
            if let first {
                trancheLevels.append((first, firstLabel))
                if settings.averageDownTranches >= 2 {
                    let second = first - atr
                    if second > stop { trancheLevels.append((second, "\(firstLabel)−1×ATR")) }
                }
            }

            var addReasons: [String] = []
            if overLeveraged { addReasons.append(leverageReason) }
            if !dataReady { addReasons.append("历史不足，无法确认趋势") }
            else if broken { addReasons.append("趋势已破位，禁止摊低") }
            if rsStable == nil { addReasons.append("缺少基准/板块数据，无法确认相对强弱") }
            else if rsStable == false { addReasons.append("近5日相对强弱 \(signed(rs5 ?? 0))pp 未企稳") }
            if adds >= settings.maxAverageDownCount {
                addReasons.append("已补仓 \(adds) 次，达到上限 \(settings.maxAverageDownCount)")
            }
            if deep {
                addReasons.append("浮亏 \(String(format: "%.1f", pnlPercent))% 超过 \(plain(settings.averageDownMaxLossPercent))%，不再摊低")
            }
            if eventNear { addReasons.append("约 \(earningsDays ?? 0) 天后财报，事件前不补仓") }
            if trancheLevels.isEmpty { addReasons.append("无可用回踩价位（均线/ATR 回踩不高于保护线）") }

            let remainingBatches = max(1, settings.maxAverageDownCount - adds)
            let nLevels = max(1, min(trancheLevels.count == 0 ? 1 : trancheLevels.count, remainingBatches, settings.averageDownTranches))
            let trancheCap = settings.averageDownFraction / Double(nLevels)
            var steps: [HoldingPlanStep] = []
            var runningQty = quantity
            var runningCostValue = cost * quantity
            var runningRisk = holdRisk
            for (level, label) in trancheLevels.prefix(nLevels) {
                var qty = sizeAdd(level, openQty: runningQty, openRisk: runningRisk, capFraction: trancheCap)
                if qty < 1 {
                    qty = (level > stop && (maxValue - runningQty * price) >= level) ? 1 : 0
                }
                guard qty >= 1 else { continue }
                steps.append(.init(side: "BUY", quantity: qty, price: level, label: "限价第\(steps.count + 1)批·\(label)"))
                runningRisk += (level - stop) * qty
                runningCostValue += level * qty
                runningQty += qty
            }
            if !trancheLevels.isEmpty, steps.isEmpty, !addReasons.contains(where: { $0.contains("风险预算") }) {
                addReasons.append("风险预算或单股上限剩余不足")
            }
            let reason = addReasons.joined(separator: "；")
            let addQty = steps.reduce(0) { $0 + $1.quantity }
            let addPrice = steps.first?.price ?? trancheLevels.first?.0
            let newQty = steps.isEmpty ? quantity : runningQty
            let newAvg = steps.isEmpty ? cost : runningCostValue / newQty
            let worstAfter = steps.isEmpty ? holdRisk : runningRisk
            let priceText = trancheLevels.prefix(nLevels).map { "$\(money($0.0))" }.joined(separator: "/")
            var trigger = "仅在价格回踩 \(priceText.isEmpty ? "—" : priceText) 且收盘不破 $\(money(stop))、近5日相对强弱不再恶化时执行"
            if !steps.isEmpty {
                trigger += "（计划 \(steps.count) 批，累计第 \(adds + 1)/\(settings.maxAverageDownCount) 轮）"
            }
            var plan = HoldingActionPlan(
                kind: .averageDown, name: HoldingPlanKind.averageDown.name(for: mode),
                allowed: reason.isEmpty && !steps.isEmpty, blockedReason: reason, action: .buy
            )
            plan.trigger = trigger
            plan.price = addPrice
            plan.quantityChange = addQty
            plan.quantityAfter = newQty
            plan.averageCostAfter = newAvg
            plan.stopAfter = stop
            plan.worstLoss = worstAfter
            plan.steps = steps
            plans[.averageDown] = finish(plan)
        } else {
            var reason = ""
            if overLeveraged {
                reason = leverageReason
            } else if !dataReady {
                reason = "历史不足，无法确认趋势"
            } else if !intact {
                reason = "\(trend.label)，不顺势加仓"
            } else if rs20 == nil {
                reason = "缺少基准/板块数据，无法确认相对强弱"
            } else if let rs20, rs20 <= 0 {
                reason = "20日相对强弱 \(signed(rs20))pp 未转正"
            } else if metrics.rsi14 >= 70 {
                reason = "RSI \(String(format: "%.0f", metrics.rsi14)) 超买"
            } else if let ma20 = metrics.ma20, price > ma20 + 2 * atr {
                reason = "偏离 MA20 超过 2×ATR，追高风险"
            } else if eventNear {
                reason = "约 \(earningsDays ?? 0) 天后财报，事件前不加仓"
            }
            let addQuantity = reason.isEmpty ? sizeAdd(price, openQty: quantity, openRisk: holdRisk, capFraction: settings.averageDownFraction) : 0
            if reason.isEmpty, addQuantity < 1 { reason = "风险预算或单股上限剩余不足" }
            if !reason.isEmpty {
                plans[.addOnStrength] = blocked(.addOnStrength, reason)
            } else {
                let newQuantity = quantity + addQuantity
                var plan = make(.addOnStrength)
                plan.action = .buy
                plan.trigger = "现价附近加 \(plain(addQuantity)) 股，统一保护线 $\(money(stop))"
                plan.price = price
                plan.quantityChange = addQuantity
                plan.quantityAfter = newQuantity
                plan.averageCostAfter = (cost * quantity + price * addQuantity) / newQuantity
                plan.stopAfter = stop
                plan.worstLoss = holdRisk + (price - stop) * addQuantity
                plan.steps = [.init(side: "BUY", quantity: addQuantity, price: price, label: "顺势加仓")]
                plans[.addOnStrength] = finish(plan)
            }
        }

        if quantity < 2 {
            plans[.reduceRisk] = blocked(.reduceRisk, "持股不足 2 股，无法分批")
        } else {
            let keep = min(
                floorShares(quantity * (1 - settings.reduceFraction)),
                floorShares(budget / (price - stop)),
                floorShares(maxValue / price)
            )
            if keep <= 0 {
                plans[.reduceRisk] = blocked(.reduceRisk, "需全部卖出才能回到预算/上限内，等同离场")
            } else {
                let sell = quantity - keep
                var plan = make(.reduceRisk)
                plan.action = .sell
                plan.trigger = "现价附近卖出 \(plain(sell)) 股，保留 \(plain(keep)) 股，保护线 $\(money(stop))"
                plan.price = price
                plan.quantityChange = -sell
                plan.quantityAfter = keep
                plan.averageCostAfter = cost
                plan.stopAfter = stop
                plan.worstLoss = (price - stop) * keep
                plan.realizedPnL = (price - cost) * sell
                plans[.reduceRisk] = finish(plan)
            }
        }

        let takeProfit = cost + settings.takeProfitATRMultiple * atr
        if mode == .loss {
            if quantity < 2 {
                plans[.rallyReduce] = blocked(.rallyReduce, "持股不足 2 股，无法分批")
            } else {
                let rebound: Double
                let reboundBasis: String
                if let ma20 = metrics.ma20, price < ma20, ma20 <= price + 2 * atr {
                    rebound = ma20
                    reboundBasis = "MA20"
                } else {
                    rebound = price + atr
                    reboundBasis = "现价+1×ATR"
                }
                let keep = floorShares(quantity * (1 - settings.reduceFraction))
                let sell = quantity - keep
                var plan = make(.rallyReduce)
                plan.action = .sell
                plan.trigger = "反弹至 $\(money(rebound))（\(reboundBasis)）附近卖出 \(plain(sell)) 股；未反弹先跌破 $\(money(stop)) 则止损（仍属不主动清仓路径）"
                plan.price = rebound
                plan.quantityChange = -sell
                plan.quantityAfter = keep
                plan.averageCostAfter = cost
                plan.stopAfter = stop
                plan.worstLoss = holdRisk
                plan.realizedPnL = (rebound - cost) * sell
                plan.steps = [
                    .init(side: "SELL", quantity: sell, price: rebound, label: "反弹·\(reboundBasis)"),
                    .init(side: "SELL", quantity: keep, price: stop, label: "余仓硬止损"),
                ]
                plans[.rallyReduce] = finish(plan)
            }
        } else {
            let reached = price >= takeProfit
            if quantity < 2 {
                plans[.scaleOut] = blocked(.scaleOut, "持股不足 2 股，无法分批")
            } else {
                let keep = floorShares(quantity * (1 - settings.scaleOutFraction))
                let sell = quantity - keep
                let level = reached ? price : takeProfit
                var plan = make(.scaleOut)
                plan.action = .sell
                plan.trigger = reached
                    ? "已达止盈参考 $\(money(takeProfit))，现价附近卖出 \(plain(sell)) 股"
                    : "价格达到 $\(money(takeProfit))（成本+\(plain(settings.takeProfitATRMultiple))×ATR）时卖出 \(plain(sell)) 股"
                plan.price = level
                plan.quantityChange = -sell
                plan.quantityAfter = keep
                plan.averageCostAfter = cost
                plan.stopAfter = stop
                plan.worstLoss = reached ? (price - stop) * keep : holdRisk
                plan.realizedPnL = (level - cost) * sell
                plans[.scaleOut] = finish(plan)
            }
        }

        let sectorSymbol = SectorMap.sector(for: symbol)
        var best: (String, HoldingMetrics, Double)?
        if let sectorSymbol, let stock20 = metrics.ret20 {
            for peerSymbol in context.peers.keys.sorted() {
                guard let peer = context.peers[peerSymbol],
                      peerSymbol != symbol, peerSymbol != sectorSymbol,
                      SectorMap.sector(for: peerSymbol) == sectorSymbol,
                      let peer20 = peer.ret20,
                      trendState(peer).0 == .intact else { continue }
                let gap = peer20 - stock20
                if gap >= settings.switchMinGapPercent, best == nil || gap > best!.2 {
                    best = (peerSymbol, peer, gap)
                }
            }
        }
        var switchGap = 0.0
        if overLeveraged {
            plans[.switchPosition] = blocked(.switchPosition, leverageReason)
        } else if sectorSymbol == nil {
            plans[.switchPosition] = blocked(.switchPosition, "未识别所属板块")
        } else if let (peerSymbol, peer, gap) = best {
            switchGap = gap
            let peerATR = peer.atr14 > 0 ? peer.atr14 : peer.price * 0.01
            let riskPerShare = k * peerATR
            let buy = min(floorShares(quantity * price / peer.price), floorShares(budget / riskPerShare))
            if buy < 1 {
                plans[.switchPosition] = blocked(.switchPosition, "\(peerSymbol) 单价过高或风险预算不足")
            } else {
                var plan = make(.switchPosition)
                plan.action = .switchPosition
                plan.trigger = "卖出 \(plain(quantity)) 股 \(symbol)，换入约 \(plain(buy)) 股 \(peerSymbol)（同板块近20日强 \(String(format: "%+.1f", gap))pp）"
                plan.price = peer.price
                plan.quantityChange = -quantity
                plan.quantityAfter = buy
                plan.averageCostAfter = peer.price
                plan.stopAfter = peer.price - riskPerShare
                plan.worstLoss = buy * riskPerShare
                plan.realizedPnL = (price - cost) * quantity
                plan.targetSymbol = peerSymbol
                plans[.switchPosition] = finish(plan)
            }
        } else {
            plans[.switchPosition] = blocked(.switchPosition, "监控列表中无同板块、趋势完好且明显更强的标的")
        }

        if !dataReady {
            for kind in [HoldingPlanKind.reduceRisk, .rallyReduce, .scaleOut, .switchPosition] where plans[kind]?.allowed == true {
                plans[kind] = blocked(kind, "历史不足，仅给出持有/离场")
            }
        }

        func b(_ condition: Bool) -> Int { condition ? 1 : 0 }
        let notIntact = weakening || broken
        let deleverage = overLeveraged && weightPercent >= settings.deleverageMinWeightPercent
        let smallRisk = budgetRatio <= smallRiskRatio && !broken
        let leader = (rs60 ?? -.infinity) >= mediumTermLeaderPP && !broken
        var scores: [HoldingPlanKind: Int] = [:]
        if mode == .loss {
            scores[.stopExit] = 25 + 40 * b(broken) + 10 * b(weakening) + 15 * b(source == .idio && notIntact)
                + 15 * b(deep) + 20 * b(stopHit) + 10 * b(overBudget) + 5 * b(eventNear && notIntact) - 20 * b(intact)
                - 10 * b(smallRisk) - 10 * b(leader)
            scores[.reduceRisk] = 30 + 25 * b(overBudget) + 15 * b(overweight) + 15 * b(weakening) + 10 * b(broken)
                + 10 * b(eventNear) + 5 * b(highVol) + 20 * b(deleverage)
                - 10 * b(intact && !overBudget && !overweight) - 10 * b(smallRisk && !overweight)
            scores[.rallyReduce] = 25 + 20 * b(weakening) + 10 * b(broken && !deep)
                + 10 * b(source == .sector || source == .market) - 10 * b(intact) - 15 * b(stopHit)
                - 10 * b(smallRisk)
            scores[.holdWatch] = 40 + 20 * b(intact) + 10 * b(source == .market) + 5 * b(source == .cost)
                + 5 * b(rsStable == true) - 30 * b(broken) - 10 * b(weakening) - 20 * b(overBudget)
                - 10 * b(overweight) - 10 * b(eventNear) - 25 * b(stopHit)
                + 10 * b(smallRisk) + 5 * b(leader) - 10 * b(deleverage)
            scores[.averageDown] = 35 + 15 * b(intact) + 10 * b(source == .market) + 5 * b(source == .sector)
                - 10 * b(pnlPercent <= -8) - 5 * adds - 10 * b(highVol)
            scores[.switchPosition] = 30 + 20 * b(source == .idio && notIntact) + 10 * b(switchGap >= 10) - 15 * b(intact)
        } else {
            scores[.holdWatch] = 50 + 15 * b(intact) - 25 * b(broken) - 10 * b(weakening) - 10 * b(overweight) - 10 * b(overBudget)
                - 10 * b(deleverage)
            scores[.addOnStrength] = 30 + 15 * b(intact) + 5 * b((rs20 ?? -.infinity) >= 3) - 10 * b(pnlPercent >= 20)
            scores[.scaleOut] = 25 + 25 * b(price >= takeProfit) + 15 * b(metrics.rsi14 >= 70) + 10 * b(weakening)
                + 10 * b(overweight) + 5 * b(eventNear)
            scores[.reduceRisk] = 20 + 25 * b(overweight) + 20 * b(overBudget) + 10 * b(eventNear) + 5 * b(highVol)
                + 20 * b(deleverage)
            scores[.stopExit] = 10 + 40 * b(broken) + 15 * b(stopHit) + 10 * b(weakening && price - cost < atr)
            scores[.switchPosition] = 20 + 10 * b(source == .idio && notIntact)
        }

        let order = mode == .loss ? HoldingPlanKind.lossOrder : HoldingPlanKind.profitOrder
        let ordered: [HoldingActionPlan] = order.compactMap { kind in
            guard var plan = plans[kind] else { return nil }
            plan.score = plan.allowed ? max(0, min(100, scores[kind] ?? 0)) : 0
            return plan
        }
        let ranked = ordered.filter(\.allowed).sorted { lhs, rhs in
            if lhs.score != rhs.score { return lhs.score > rhs.score }
            return (HoldingPlanKind.priority.firstIndex(of: lhs.kind) ?? 0) < (HoldingPlanKind.priority.firstIndex(of: rhs.kind) ?? 0)
        }
        let recommended = ranked[0]
        let margin = ranked.count > 1 ? recommended.score - ranked[1].score : 100
        let confidence = margin >= 15 ? "高" : margin >= 7 ? "中" : "低"

        var conditions: [HoldingSwitchCondition] = []
        func condition(_ target: HoldingPlanKind, _ text: String) {
            conditions.append(.init(target: target, targetName: target.name(for: mode), condition: text))
        }
        let rec = recommended.kind
        if rec != .stopExit { condition(.stopExit, "收盘跌破保护线 $\(money(stop))") }
        if mode == .loss {
            if [.stopExit, .reduceRisk, .rallyReduce, .switchPosition].contains(rec), let ma20 = metrics.ma20 {
                condition(.holdWatch, "重新站上 MA20 $\(money(ma20)) 且近5日相对强弱 ≥ -\(plain(tolerance))pp")
            }
            if rec != .averageDown, let mid = metrics.ma50 ?? metrics.ma20,
               adds < settings.maxAverageDownCount, !deep {
                let pull = plans[.averageDown]?.price
                let pullTxt = pull.map { "回踩 $\(money($0))" } ?? "回踩 \(metrics.ma50 != nil ? "MA50" : "MA20") $\(money(mid))"
                let gate = overLeveraged ? "且杠杆回到上限内、" : "且"
                condition(.averageDown, "相对强弱企稳并\(pullTxt)\(gate)收盘不破 $\(money(stop)) 后可评估补仓")
            }
            if rec != .rallyReduce, let rally = plans[.rallyReduce], rally.allowed {
                condition(.rallyReduce, "反弹至 $\(money(rally.price ?? 0)) 附近（不主动清仓）")
            }
            if let watchLine {
                condition(.stopExit, "连续 \(settings.watchLineBreachDays) 日收盘低于观察线 $\(money(watchLine)) 后仍走弱，或触及硬止损 $\(money(stop))")
            }
        } else {
            if rec != .scaleOut, plans[.scaleOut]?.allowed == true {
                condition(.scaleOut, "价格达到止盈参考 $\(money(takeProfit)) 或 RSI ≥ 70")
            }
            if rec != .addOnStrength, plans[.addOnStrength]?.allowed == false, !broken, let ma20 = metrics.ma20, !overLeveraged {
                condition(.addOnStrength, "回踩 MA20 $\(money(ma20)) 不破且20日相对强弱转正")
            }
        }
        if overLeveraged {
            if rec != .reduceRisk, plans[.reduceRisk]?.allowed == true {
                condition(.reduceRisk, "账户杠杆 \(String(format: "%.0f", leveragePercent ?? 0))% 未降到 \(plain(settings.maxLeveragePercent))% 以内前，优先执行减仓")
            }
            condition(.holdWatch, "杠杆回到 \(plain(settings.maxLeveragePercent))% 以内后，再重新评估补仓/加仓/换仓")
        } else if rec != .reduceRisk, plans[.reduceRisk]?.allowed == true, !(overBudget || overweight) {
            condition(.reduceRisk, "最坏亏损超过单票预算 $\(money(budget, digits: 0)) 或仓位超过 \(plain(settings.maxPositionPercent))%")
        }
        if eventNear { condition(.holdWatch, "财报（约 \(earningsDays ?? 0) 天后）落地后重新评估全部方案") }

        let sourceLabel: String
        if mode == .loss || source == .unknown {
            sourceLabel = source.label
        } else {
            sourceLabel = "近20日" + (source != .cost ? "走弱：" + source.label : "未走弱")
        }
        var nonSellPlan: HoldingPlanKind? = nil
        var nonSellSummary = ""
        if mode == .loss {
            // Use scored `ordered` plans (dictionary copies still have score 0).
            let nonSellKinds: [HoldingPlanKind] = [.holdWatch, .averageDown, .rallyReduce]
            var candidates = ordered.filter { nonSellKinds.contains($0.kind) && ($0.allowed || $0.kind == .holdWatch) }
            var pick = candidates.max { lhs, rhs in
                if lhs.allowed != rhs.allowed { return !lhs.allowed && rhs.allowed }
                let ls = lhs.allowed ? lhs.score : -1
                let rs = rhs.allowed ? rhs.score : -1
                if ls != rs { return ls < rs }
                return (HoldingPlanKind.priority.firstIndex(of: lhs.kind) ?? 99) > (HoldingPlanKind.priority.firstIndex(of: rhs.kind) ?? 99)
            }
            if [.stopExit, .reduceRisk, .switchPosition].contains(rec) {
                pick = ordered.first { $0.kind == .holdWatch }
            }
            nonSellPlan = pick?.kind
            if pick?.kind == .holdWatch {
                let watchTxt = watchLine.map { "观察线 $\(money($0))" } ?? "硬止损"
                nonSellSummary = "持有观察：守\(watchTxt) / 硬止损 $\(money(stop))，\(watchDays) 个交易日；到止损最坏 $\(money(holdRisk, digits: 0))（预算 \(String(format: "%.0f", budgetRatio * 100))%）"
            } else if pick?.kind == .averageDown, let avg = pick, let newCost = avg.averageCostAfter {
                nonSellSummary = "分批补仓：\(avg.trigger)；补后成本 $\(money(newCost))，到保护线最坏 $\(money(avg.worstLoss, digits: 0))"
            } else if let pick {
                nonSellSummary = pick.trigger
            }
        }

        return HoldingDiagnosis(
            symbol: symbol, mode: mode, dataReady: dataReady, price: price, averageCost: cost, quantity: quantity,
            pnlPercent: pnlPercent, pnlAmount: pnlAmount, marketValue: marketValue, weightPercent: weightPercent,
            trendState: trend, trendFlags: flags, lossSource: source, lossSourceLabel: sourceLabel,
            attribution: attribution, rs5: rs5, rs20: rs20, rs60: rs60, rsStable: rsStable,
            leveragePercent: leveragePercent, overLeveraged: overLeveraged,
            sectorSymbol: sectorSymbol,
            sectorLabel: SectorMap.name(for: sectorSymbol) + (sectorSymbol.map { "(\($0))" } ?? ""),
            atr: atr, atrPercent: atrPercent, volatilityLabel: volatility,
            earningsDays: earningsDays, eventNear: eventNear,
            stop: stop, stopBasis: stopBasis, stopHit: stopHit, holdRisk: holdRisk,
            positionBudget: budget, budgetRatio: budgetRatio, overweight: overweight,
            plans: ordered, recommended: rec, confidence: confidence, switchConditions: conditions,
            summary: "\(recommended.name)（\(confidence)）· \(trend.label) · \(sourceLabel)",
            watchLine: watchLine, hardStop: stop, watchDays: watchDays,
            nonSellPlan: nonSellPlan, nonSellSummary: nonSellSummary
        )
    }

    public static func diagnose(position: Position, metrics: HoldingMetrics, context: HoldingDiagnosisContext, settings: HoldingDiagnosisSettings, averageDownCount: Int = 0) -> HoldingDiagnosis? {
        diagnose(
            symbol: position.symbol,
            quantity: position.quantity,
            averageCost: position.averageCost,
            initialStop: position.initialStop,
            averageDownCount: averageDownCount,
            metrics: metrics,
            context: context,
            settings: settings
        )
    }

    /// Diagnose every held symbol; `metrics` may include the benchmark, sector ETFs and peers.
    public static func diagnosePortfolio(
        positions: [Position],
        metrics: [String: HoldingMetrics],
        settings: HoldingDiagnosisSettings = .init(),
        benchmarkSymbol: String = "SPY",
        earningsDays: [String: Int] = [:],
        averageDownCounts: [String: Int] = [:],
        netLiquidation: Double? = nil,
        grossPositionValue: Double? = nil
    ) -> PortfolioDiagnosis {
        let benchmark = benchmarkSymbol.uppercased()
        let market = metrics[benchmark]
        func positive(_ value: Double?) -> Double? { value.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } }
        let net = positive(netLiquidation) ?? settings.accountValue
        let gross = positive(grossPositionValue) ?? positions.sorted(by: { $0.symbol < $1.symbol })
            .filter { $0.quantity > 0 }
            .reduce(0) { total, position in total + position.quantity * (metrics[position.symbol]?.price ?? position.averageCost) }
        let leveragePercent = gross / net * 100
        let overLeveraged = leveragePercent > settings.maxLeveragePercent
        var diagnoses: [HoldingDiagnosis] = []
        for position in positions.sorted(by: { $0.symbol < $1.symbol }) {
            guard let held = metrics[position.symbol] else { continue }
            let sectorSymbol = SectorMap.sector(for: position.symbol)
            let sector = sectorSymbol.flatMap { $0 != position.symbol ? metrics[$0] : nil }
            let context = HoldingDiagnosisContext(
                market: position.symbol == benchmark ? nil : market,
                sector: sector,
                peers: metrics,
                earningsDays: earningsDays[position.symbol],
                leveragePercent: leveragePercent
            )
            if let result = diagnose(
                position: position,
                metrics: held,
                context: context,
                settings: settings,
                averageDownCount: averageDownCounts[position.symbol] ?? position.averageDownCount
            ) {
                diagnoses.append(result)
            }
        }

        var exposure: [String: Double] = [:]
        for item in diagnoses {
            exposure[item.sectorSymbol ?? "", default: 0] += item.weightPercent
        }
        let sectorRows = exposure
            .sorted { lhs, rhs in lhs.value != rhs.value ? lhs.value > rhs.value : lhs.key < rhs.key }
            .map { key, value in
                SectorExposure(sectorSymbol: key.isEmpty ? nil : key, sectorLabel: SectorMap.name(for: key.isEmpty ? nil : key), weightPercent: value)
            }
        let weights = diagnoses.map(\.weightPercent).sorted(by: >)
        let topWeight = weights.first ?? 0
        let top3 = weights.prefix(3).reduce(0, +)
        let totalRisk = diagnoses.reduce(0) { $0 + $1.holdRisk }
        let budget = settings.portfolioBudget

        var notes: [String] = []
        let deleverageAmount = max(0, gross - net * settings.maxLeveragePercent / 100)
        if overLeveraged {
            let released = diagnoses.reduce(0.0) { total, item in
                guard let plan = item.plan(.reduceRisk), plan.allowed else { return total }
                return total - plan.quantityChange * (plan.price ?? 0)
            }
            notes.append(
                "杠杆优先：持仓市值 $\(money(gross, digits: 0)) = 净值的 \(String(format: "%.0f", leveragePercent))%，"
                + "降到 \(plain(settings.maxLeveragePercent))% 需卖出约 $\(money(deleverageAmount, digits: 0))；"
                + "各票减仓方案合计可释放约 $\(money(released, digits: 0))。杠杆回到上限内前不执行任何补仓/加仓/建仓。"
            )
        }
        for row in sectorRows {
            if let symbol = row.sectorSymbol, row.weightPercent > settings.maxSectorPercent {
                notes.append("行业暴露：\(row.sectorLabel)(\(symbol)) 约 \(String(format: "%.0f", row.weightPercent))% > \(plain(settings.maxSectorPercent))%")
            }
        }
        let byWeight = diagnoses.sorted { lhs, rhs in
            lhs.weightPercent != rhs.weightPercent ? lhs.weightPercent > rhs.weightPercent : lhs.symbol < rhs.symbol
        }
        for item in byWeight where item.overweight {
            notes.append("单票集中：\(item.symbol) 占 \(String(format: "%.1f", item.weightPercent))% > 上限 \(plain(settings.maxPositionPercent))%")
        }
        if diagnoses.count >= 3, top3 >= 60 {
            notes.append("前三持仓合计约 \(String(format: "%.0f", top3))%，组合集中度偏高。")
        }
        if !diagnoses.isEmpty {
            if totalRisk > budget {
                notes.append("合计最坏亏损 $\(money(totalRisk, digits: 0)) 超过组合风险预算 $\(money(budget, digits: 0))（\(plain(settings.portfolioRiskPercent))%）。")
            } else {
                notes.append("合计最坏亏损 $\(money(totalRisk, digits: 0))，占组合风险预算 \(String(format: "%.0f", totalRisk / budget * 100))%。")
            }
        }
        let brokenLosers = diagnoses.filter { $0.mode == .loss && $0.trendState == .broken }.map(\.symbol)
        if !brokenLosers.isEmpty {
            notes.append("\(brokenLosers.count) 只亏损仓趋势破位：\(brokenLosers.joined(separator: "、"))。")
        }
        if diagnoses.isEmpty { notes.append("暂无可诊断的持仓（需要持仓数量、成本与行情）。") }
        return PortfolioDiagnosis(
            holdings: diagnoses,
            sectorExposure: sectorRows,
            topWeightPercent: topWeight,
            top3WeightPercent: top3,
            totalHoldRisk: totalRisk,
            portfolioBudget: budget,
            notes: notes,
            leveragePercent: leveragePercent,
            overLeveraged: overLeveraged,
            deleverageAmount: deleverageAmount
        )
    }

    /// Extra symbols (benchmark + sector ETFs of holdings) the engine needs quotes for.
    public static func contextSymbols(positions: [Position], benchmarkSymbol: String = "SPY") -> [String] {
        var extra = [benchmarkSymbol.uppercased()]
        for position in positions.sorted(by: { $0.symbol < $1.symbol }) where position.quantity > 0 {
            if let sector = SectorMap.sector(for: position.symbol), !extra.contains(sector) { extra.append(sector) }
        }
        return extra
    }

    static func money(_ value: Double, digits: Int = 2) -> String {
        let text = String(format: "%.\(digits)f", abs(value))
        let parts = text.split(separator: ".", maxSplits: 1)
        var integer = String(parts[0])
        var grouped = ""
        while integer.count > 3 {
            grouped = "," + integer.suffix(3) + grouped
            integer.removeLast(3)
        }
        let fraction = parts.count > 1 ? "." + parts[1] : ""
        return (value < 0 ? "-" : "") + integer + grouped + fraction
    }

    static func plain(_ value: Double) -> String {
        if value == value.rounded(), abs(value) < 1e15 { return String(Int(value)) }
        return String(format: "%g", value)
    }

    static func signed(_ value: Double) -> String {
        String(format: "%+.2f", value)
    }
}
