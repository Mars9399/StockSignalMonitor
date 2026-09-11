import Foundation

public struct DailyBar: Codable, Hashable, Sendable, Identifiable {
    public let date: Date
    public let open: Double
    public let high: Double
    public let low: Double
    public let close: Double
    public let volume: Double

    public var id: Date { date }

    public init(date: Date, open: Double, high: Double, low: Double, close: Double, volume: Double = 0) {
        self.date = date
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
    }
}

public struct StockQuote: Codable, Hashable, Sendable, Identifiable {
    public let symbol: String
    public let price: Double
    public let timestamp: Date

    public var id: String { symbol }

    public init(symbol: String, price: Double, timestamp: Date = .now) {
        self.symbol = symbol.uppercased()
        self.price = price
        self.timestamp = timestamp
    }
}

public enum SignalStatus: String, Codable, CaseIterable, Hashable, Sendable {
    case dataShort = "DATA_SHORT"
    case buyAlert = "BUY_ALERT"
    case watch = "WATCH"
    case noSignal = "NO_SIGNAL"
}

public enum SignalQuality: String, Codable, Hashable, Sendable {
    case standard = "长周期模型"
    case medium = "中周期模型"
    case low = "短周期模型"
    case observationOnly = "不足·仅观察"
}

public struct SignalLevels: Codable, Hashable, Sendable {
    public var status: SignalStatus
    public let price: Double
    public let buyPoint: Double
    public let stopPoint: Double
    public let riskPercent: Double
    public let atr14: Double
    public let trendFast: Double
    public let trendSlow: Double
    public let historyDays: Int
    public let quality: SignalQuality
    public let modelName: String
    public let isReady: Bool

    public init(status: SignalStatus, price: Double, buyPoint: Double, stopPoint: Double, riskPercent: Double, atr14: Double, trendFast: Double, trendSlow: Double, historyDays: Int, quality: SignalQuality, modelName: String, isReady: Bool) {
        self.status = status
        self.price = price
        self.buyPoint = buyPoint
        self.stopPoint = stopPoint
        self.riskPercent = riskPercent
        self.atr14 = atr14
        self.trendFast = trendFast
        self.trendSlow = trendSlow
        self.historyDays = historyDays
        self.quality = quality
        self.modelName = modelName
        self.isReady = isReady
    }
}

public struct Position: Codable, Hashable, Sendable {
    public var symbol: String
    public var averageCost: Double
    public var quantity: Double
    public var initialStop: Double?

    public init(symbol: String, averageCost: Double = 0, quantity: Double = 0, initialStop: Double? = nil) {
        self.symbol = symbol.uppercased()
        self.averageCost = max(0, averageCost)
        self.quantity = max(0, quantity)
        self.initialStop = initialStop
    }
}

public struct RiskSettings: Codable, Hashable, Sendable {
    public var accountValue: Double
    public var riskPercent: Double
    public var maxPositionPercent: Double

    public init(accountValue: Double = 100_000, riskPercent: Double = 1, maxPositionPercent: Double = 10) {
        self.accountValue = max(0.01, accountValue)
        self.riskPercent = min(10, max(0.1, riskPercent))
        self.maxPositionPercent = min(100, max(1, maxPositionPercent))
    }
}

public struct PositionPlan: Codable, Hashable, Sendable {
    public let riskReductionPoint: Double
    public let profitTarget2R: Double
    public let profitTarget3R: Double
    public let maximumShares: Int
    public let action: PositionAction

    public init(riskReductionPoint: Double, profitTarget2R: Double, profitTarget3R: Double, maximumShares: Int, action: PositionAction) {
        self.riskReductionPoint = riskReductionPoint
        self.profitTarget2R = profitTarget2R
        self.profitTarget3R = profitTarget3R
        self.maximumShares = maximumShares
        self.action = action
    }
}

public enum PositionAction: Codable, Hashable, Sendable {
    case needsRiskBaseline
    case observationOnly(String)
    case insufficientHistory
    case reduceForRisk(shares: Double)
    case reduceForExposure(shares: Double)
    case reduceAt2R(shares: Double)
    case reduceAt3R(shares: Double)
    case addAfterBreakout(maximumShares: Int)
    case openAfterBreakout(maximumShares: Int)
    case wait(candidateMaximumShares: Int)
    case hold
}

public enum MarketDataProviderKind: String, Codable, CaseIterable, Hashable, Identifiable, Sendable {
    case yahoo
    case alpaca
    case massive
    case ibkrClientPortal

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .yahoo: "Yahoo Finance"
        case .alpaca: "Alpaca IEX"
        case .massive: "Massive / Polygon"
        case .ibkrClientPortal: "IBKR Client Portal Gateway"
        }
    }
}

public enum DataProviderConfiguration: Hashable, Sendable {
    case yahoo
    case alpaca(apiKey: String, apiSecret: String, feed: String = "iex")
    case massive(apiKey: String, baseURL: URL = URL(string: "https://api.massive.com")!)
    case ibkrClientPortal(baseURL: URL = URL(string: "https://localhost:5000/v1/api")!, accountID: String? = nil)

    public var kind: MarketDataProviderKind {
        switch self {
        case .yahoo: .yahoo
        case .alpaca: .alpaca
        case .massive: .massive
        case .ibkrClientPortal: .ibkrClientPortal
        }
    }
}

public struct MonitoredStock: Identifiable, Hashable, Sendable {
    public var id: String { symbol }
    public let symbol: String
    public var name: String
    public var quote: StockQuote?
    public var levels: SignalLevels?
    public var position: Position
    public var plan: PositionPlan?
    public var errorMessage: String?

    public init(symbol: String, name: String = "", position: Position? = nil) {
        let normalized = symbol.uppercased()
        self.symbol = normalized
        self.name = name
        self.position = position ?? Position(symbol: normalized)
    }
}

public enum MarketDataError: LocalizedError, Sendable {
    case invalidSymbol
    case invalidResponse
    case httpStatus(Int, String)
    case missingCredentials(String)
    case noData(String)
    case ibkrAuthenticationRequired

    public var errorDescription: String? {
        switch self {
        case .invalidSymbol: "股票代码无效"
        case .invalidResponse: "行情服务返回了无法识别的数据"
        case let .httpStatus(code, message): "行情服务错误 \(code)：\(message)"
        case let .missingCredentials(provider): "请配置 \(provider) 的只读行情凭据"
        case let .noData(symbol): "\(symbol) 没有可用行情"
        case .ibkrAuthenticationRequired: "IBKR Gateway 未登录或会话未认证"
        }
    }
}
