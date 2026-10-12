#if os(macOS)
import Foundation
import Network

public struct TWSPositionSnapshot: Hashable, Sendable {
    public let account: String
    public let contractID: Int
    public let symbol: String
    public let securityType: String
    public let currency: String
    public let quantity: Double
    public let averageCost: Double

    public init(
        account: String,
        contractID: Int,
        symbol: String,
        securityType: String,
        currency: String,
        quantity: Double,
        averageCost: Double
    ) {
        self.account = account
        self.contractID = contractID
        self.symbol = symbol
        self.securityType = securityType
        self.currency = currency
        self.quantity = quantity
        self.averageCost = averageCost
    }
}

public struct TWSAccountSummary: Hashable, Sendable {
    public let account: String
    public let currency: String
    public let netLiquidation: Double?
    public let dailyPnL: Double?
    public let availableFunds: Double?
    public let buyingPower: Double?
    public let totalCashValue: Double?
    public let settledCash: Double?
    public let equityWithLoanValue: Double?
    public let grossPositionValue: Double?
    public let excessLiquidity: Double?
    public let initialMargin: Double?
    public let maintenanceMargin: Double?
    public let unrealizedPnL: Double?
    public let realizedPnL: Double?

    public init(
        account: String,
        currency: String = "USD",
        netLiquidation: Double? = nil,
        dailyPnL: Double? = nil,
        availableFunds: Double? = nil,
        buyingPower: Double? = nil,
        totalCashValue: Double? = nil,
        settledCash: Double? = nil,
        equityWithLoanValue: Double? = nil,
        grossPositionValue: Double? = nil,
        excessLiquidity: Double? = nil,
        initialMargin: Double? = nil,
        maintenanceMargin: Double? = nil,
        unrealizedPnL: Double? = nil,
        realizedPnL: Double? = nil
    ) {
        self.account = account
        self.currency = currency
        self.netLiquidation = netLiquidation
        self.dailyPnL = dailyPnL
        self.availableFunds = availableFunds
        self.buyingPower = buyingPower
        self.totalCashValue = totalCashValue
        self.settledCash = settledCash
        self.equityWithLoanValue = equityWithLoanValue
        self.grossPositionValue = grossPositionValue
        self.excessLiquidity = excessLiquidity
        self.initialMargin = initialMargin
        self.maintenanceMargin = maintenanceMargin
        self.unrealizedPnL = unrealizedPnL
        self.realizedPnL = realizedPnL
    }

    public func merging(pnl: TWSAccountPnL) -> Self {
        Self(
            account: account,
            currency: currency,
            netLiquidation: netLiquidation,
            dailyPnL: pnl.dailyPnL,
            availableFunds: availableFunds,
            buyingPower: buyingPower,
            totalCashValue: totalCashValue,
            settledCash: settledCash,
            equityWithLoanValue: equityWithLoanValue,
            grossPositionValue: grossPositionValue,
            excessLiquidity: excessLiquidity,
            initialMargin: initialMargin,
            maintenanceMargin: maintenanceMargin,
            unrealizedPnL: pnl.unrealizedPnL ?? unrealizedPnL,
            realizedPnL: pnl.realizedPnL ?? realizedPnL
        )
    }
}

public struct TWSAccountPnL: Hashable, Sendable {
    public let dailyPnL: Double?
    public let unrealizedPnL: Double?
    public let realizedPnL: Double?

    public init(dailyPnL: Double?, unrealizedPnL: Double?, realizedPnL: Double?) {
        self.dailyPnL = dailyPnL
        self.unrealizedPnL = unrealizedPnL
        self.realizedPnL = realizedPnL
    }
}

public enum TWSPositionClientError: LocalizedError, Sendable {
    case invalidHost
    case connectionFailed(String)
    case timedOut
    case unsupportedServer(Int)
    case malformedHandshake
    case apiError(code: Int, message: String)
    case connectionClosed
    case accountSummaryTimedOut
    case accountSummaryUnavailable(String)
    case pnlTimedOut
    case pnlUnavailable(String)

    public var errorDescription: String? {
        switch self {
        case .invalidHost:
            "TWS 主机地址无效。"
        case let .connectionFailed(message):
            "无法连接 TWS：\(message)"
        case .timedOut:
            "读取 TWS 持仓超时，请确认 TWS 已登录并启用 Socket API。"
        case let .unsupportedServer(version):
            "TWS API 版本过旧（服务器版本 \(version)），不支持持仓读取。"
        case .malformedHandshake:
            "TWS 返回了无法识别的连接握手。"
        case let .apiError(code, message):
            "TWS API \(code)：\(message)"
        case .connectionClosed:
            "TWS 在持仓同步完成前关闭了连接。"
        case .accountSummaryTimedOut:
            "读取 TWS 账户情况超时。"
        case let .accountSummaryUnavailable(account):
            account.isEmpty
                ? "TWS 未返回账户情况。"
                : "TWS 未返回账户 \(account) 的账户情况。"
        case .pnlTimedOut:
            "读取 TWS 账户盈亏超时。请在 TWS API 设置中启用“下载持仓时准备投资组合盈亏数据”。"
        case let .pnlUnavailable(account):
            account.isEmpty
                ? "需要明确的 TWS 账户才能读取实时盈亏。"
                : "TWS 未返回账户 \(account) 的实时盈亏。"
        }
    }
}

/// Read-only TWS Socket API client for positions and headline account balances.
public actor TWSPositionClient {
    public init() {}

    public func fetchPositions(
        host: String = "127.0.0.1",
        port: UInt16 = 7497,
        clientID: Int = 17,
        timeout: Duration = .seconds(12)
    ) async throws -> [TWSPositionSnapshot] {
        let seconds = max(1, timeout.components.seconds)
        let session = TWSPositionSession(host: host, port: port, clientID: clientID, timeout: .seconds(Int(seconds)))
        return try await session.fetch()
    }

    public func fetchAccountSummary(
        host: String = "127.0.0.1",
        port: UInt16 = 7497,
        clientID: Int = 118,
        accountID: String = "",
        timeout: Duration = .seconds(12)
    ) async throws -> TWSAccountSummary {
        let seconds = max(1, timeout.components.seconds)
        let session = TWSAccountSummarySession(
            host: host,
            port: port,
            clientID: clientID,
            accountID: accountID,
            timeout: .seconds(Int(seconds))
        )
        return try await session.fetch()
    }

    public func fetchPnL(
        host: String = "127.0.0.1",
        port: UInt16 = 7497,
        clientID: Int = 119,
        accountID: String,
        timeout: Duration = .seconds(6)
    ) async throws -> TWSAccountPnL {
        let seconds = max(1, timeout.components.seconds)
        let session = TWSPnLSession(
            host: host,
            port: port,
            clientID: clientID,
            accountID: accountID,
            timeout: .seconds(Int(seconds))
        )
        return try await session.fetch()
    }

    public nonisolated static func auxiliaryClientID(base: Int, offset: Int = 101) -> Int {
        let upperBound = Int64(Int32.max)
        return Int((Int64(max(0, base)) + Int64(max(1, offset))) % upperBound)
    }
}

private final class TWSPositionSession: @unchecked Sendable {
    private enum Phase { case handshake, apiReady, positions, finished }

    private let host: String
    private let port: UInt16
    private let clientID: Int
    private let timeout: DispatchTimeInterval
    private let queue = DispatchQueue(label: "com.mars9399.StockSignalMonitor.tws-positions")

    private var connection: NWConnection?
    private var continuation: CheckedContinuation<[TWSPositionSnapshot], Error>?
    private var timeoutWorkItem: DispatchWorkItem?
    private var receiveBuffer = Data()
    private var positions: [TWSPositionSnapshot] = []
    private var phase: Phase = .handshake
    private var serverVersion = 0
    private var requestedPositions = false

    init(host: String, port: UInt16, clientID: Int, timeout: DispatchTimeInterval) {
        self.host = host
        self.port = port
        self.clientID = clientID
        self.timeout = timeout
    }

    func fetch() async throws -> [TWSPositionSnapshot] {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                queue.async { [weak self] in self?.start(continuation: continuation) }
            }
        } onCancel: {
            self.queue.async { [weak self] in self?.finish(.failure(CancellationError())) }
        }
    }

    private func start(continuation: CheckedContinuation<[TWSPositionSnapshot], Error>) {
        guard !host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let endpointPort = NWEndpoint.Port(rawValue: port) else {
            continuation.resume(throwing: TWSPositionClientError.invalidHost)
            return
        }

        self.continuation = continuation
        let connection = NWConnection(host: NWEndpoint.Host(host), port: endpointPort, using: .tcp)
        self.connection = connection
        connection.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            self.queue.async {
                switch state {
                case .ready:
                    self.send(TWSWireCodec.clientHandshake())
                    self.receiveNext()
                case let .failed(error):
                    self.finish(.failure(TWSPositionClientError.connectionFailed(error.localizedDescription)))
                case .cancelled:
                    if self.phase != .finished {
                        self.finish(.failure(TWSPositionClientError.connectionClosed))
                    }
                default:
                    break
                }
            }
        }
        connection.start(queue: queue)

        let timeoutWorkItem = DispatchWorkItem { [weak self] in
            self?.finish(.failure(TWSPositionClientError.timedOut))
        }
        self.timeoutWorkItem = timeoutWorkItem
        queue.asyncAfter(deadline: .now() + timeout, execute: timeoutWorkItem)
    }

    private func receiveNext() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [weak self] data, _, complete, error in
            guard let self else { return }
            self.queue.async {
                if let data, !data.isEmpty {
                    self.receiveBuffer.append(data)
                    self.processFrames()
                }
                if let error {
                    self.finish(.failure(TWSPositionClientError.connectionFailed(error.localizedDescription)))
                } else if complete {
                    self.finish(.failure(TWSPositionClientError.connectionClosed))
                } else if self.phase != .finished {
                    self.receiveNext()
                }
            }
        }
    }

    private func processFrames() {
        while let payload = TWSWireCodec.takeFrame(from: &receiveBuffer) {
            let fields = TWSWireCodec.fields(from: payload)
            guard !fields.isEmpty else { continue }

            if phase == .handshake {
                processHandshake(fields)
            } else {
                processMessage(fields)
            }
        }
    }

    private func processHandshake(_ fields: [String]) {
        guard fields.count >= 2, let version = Int(fields[0]) else {
            finish(.failure(TWSPositionClientError.malformedHandshake))
            return
        }
        guard version >= 67 else {
            finish(.failure(TWSPositionClientError.unsupportedServer(version)))
            return
        }

        serverVersion = version
        phase = .apiReady
        var startFields = ["71", "2", String(clientID)]
        if version >= 72 { startFields.append("") }
        send(TWSWireCodec.frame(fields: startFields))
    }

    private func processMessage(_ fields: [String]) {
        guard let messageID = Int(fields[0]) else { return }
        switch messageID {
        case 9: // nextValidId: the API session is ready for requests.
            guard !requestedPositions else { return }
            requestedPositions = true
            phase = .positions
            send(TWSWireCodec.frame(fields: ["61", "1"]))

        case 61:
            if let position = TWSWireCodec.position(from: fields, serverVersion: serverVersion) {
                positions.append(position)
            }

        case 62:
            send(TWSWireCodec.frame(fields: ["64", "1"]))
            finish(.success(positions))

        case 4:
            processError(fields)

        default:
            break
        }
    }

    private func processError(_ fields: [String]) {
        // id, version, request id, code, message, optional advanced rejection JSON
        guard fields.count >= 5, let code = Int(fields[3]) else { return }
        let informationalCodes: Set<Int> = [2104, 2106, 2107, 2108, 2158]
        guard !informationalCodes.contains(code) else { return }
        let message = fields[4]
        if code == 502 || code == 503 || code == 504 || code == 506 {
            finish(.failure(TWSPositionClientError.apiError(code: code, message: message)))
        }
    }

    private func send(_ data: Data) {
        connection?.send(content: data, completion: .contentProcessed { [weak self] error in
            guard let error else { return }
            self?.queue.async {
                self?.finish(.failure(TWSPositionClientError.connectionFailed(error.localizedDescription)))
            }
        })
    }

    private func finish(_ result: Result<[TWSPositionSnapshot], Error>) {
        guard phase != .finished else { return }
        phase = .finished
        timeoutWorkItem?.cancel()
        timeoutWorkItem = nil
        connection?.stateUpdateHandler = nil
        connection?.cancel()
        connection = nil
        continuation?.resume(with: result)
        continuation = nil
    }
}

private final class TWSAccountSummarySession: @unchecked Sendable {
    private enum Phase { case handshake, apiReady, summary, finished }

    private static let requestID = 9_101
    private static let tags = [
        "NetLiquidation",
        "TotalCashValue",
        "SettledCash",
        "BuyingPower",
        "AvailableFunds",
        "EquityWithLoanValue",
        "GrossPositionValue",
        "ExcessLiquidity",
        "InitMarginReq",
        "MaintMarginReq",
        "UnrealizedPnL",
        "RealizedPnL"
    ].joined(separator: ",")

    private let host: String
    private let port: UInt16
    private let clientID: Int
    private let accountID: String
    private let timeout: DispatchTimeInterval
    private let queue = DispatchQueue(label: "com.mars9399.StockSignalMonitor.tws-account-summary")

    private var connection: NWConnection?
    private var continuation: CheckedContinuation<TWSAccountSummary, Error>?
    private var timeoutWorkItem: DispatchWorkItem?
    private var receiveBuffer = Data()
    private var records: [String: [String: TWSAccountValue]] = [:]
    private var phase: Phase = .handshake
    private var requestedSummary = false

    init(host: String, port: UInt16, clientID: Int, accountID: String, timeout: DispatchTimeInterval) {
        self.host = host
        self.port = port
        self.clientID = clientID
        self.accountID = accountID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.timeout = timeout
    }

    func fetch() async throws -> TWSAccountSummary {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                queue.async { [weak self] in self?.start(continuation: continuation) }
            }
        } onCancel: {
            self.queue.async { [weak self] in self?.finish(.failure(CancellationError())) }
        }
    }

    private func start(continuation: CheckedContinuation<TWSAccountSummary, Error>) {
        guard !host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let endpointPort = NWEndpoint.Port(rawValue: port) else {
            continuation.resume(throwing: TWSPositionClientError.invalidHost)
            return
        }

        self.continuation = continuation
        let connection = NWConnection(host: NWEndpoint.Host(host), port: endpointPort, using: .tcp)
        self.connection = connection
        connection.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            self.queue.async {
                switch state {
                case .ready:
                    self.send(TWSWireCodec.clientHandshake())
                    self.receiveNext()
                case let .failed(error):
                    self.finish(.failure(TWSPositionClientError.connectionFailed(error.localizedDescription)))
                case .cancelled:
                    if self.phase != .finished {
                        self.finish(.failure(TWSPositionClientError.connectionClosed))
                    }
                default:
                    break
                }
            }
        }
        connection.start(queue: queue)

        let timeoutWorkItem = DispatchWorkItem { [weak self] in
            self?.finish(.failure(TWSPositionClientError.accountSummaryTimedOut))
        }
        self.timeoutWorkItem = timeoutWorkItem
        queue.asyncAfter(deadline: .now() + timeout, execute: timeoutWorkItem)
    }

    private func receiveNext() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [weak self] data, _, complete, error in
            guard let self else { return }
            self.queue.async {
                if let data, !data.isEmpty {
                    self.receiveBuffer.append(data)
                    self.processFrames()
                }
                if let error {
                    self.finish(.failure(TWSPositionClientError.connectionFailed(error.localizedDescription)))
                } else if complete {
                    self.finish(.failure(TWSPositionClientError.connectionClosed))
                } else if self.phase != .finished {
                    self.receiveNext()
                }
            }
        }
    }

    private func processFrames() {
        while let payload = TWSWireCodec.takeFrame(from: &receiveBuffer) {
            let fields = TWSWireCodec.fields(from: payload)
            guard !fields.isEmpty else { continue }
            if phase == .handshake {
                processHandshake(fields)
            } else {
                processMessage(fields)
            }
        }
    }

    private func processHandshake(_ fields: [String]) {
        guard fields.count >= 2, let version = Int(fields[0]) else {
            finish(.failure(TWSPositionClientError.malformedHandshake))
            return
        }
        guard version >= 67 else {
            finish(.failure(TWSPositionClientError.unsupportedServer(version)))
            return
        }

        phase = .apiReady
        var startFields = ["71", "2", String(clientID)]
        if version >= 72 { startFields.append("") }
        send(TWSWireCodec.frame(fields: startFields))
    }

    private func processMessage(_ fields: [String]) {
        guard let messageID = Int(fields[0]) else { return }
        switch messageID {
        case 9:
            guard !requestedSummary else { return }
            requestedSummary = true
            phase = .summary
            send(TWSWireCodec.frame(fields: [
                "62", "1", String(Self.requestID), "All", Self.tags
            ]))

        case 63:
            guard let value = TWSWireCodec.accountSummaryValue(from: fields) else { return }
            guard accountID.isEmpty || value.account.caseInsensitiveCompare(accountID) == .orderedSame else { return }
            var accountValues = records[value.account] ?? [:]
            if let existing = accountValues[value.tag] {
                if value.currencyPreference >= existing.currencyPreference {
                    accountValues[value.tag] = value
                }
            } else {
                accountValues[value.tag] = value
            }
            records[value.account] = accountValues

        case 64:
            guard requestedSummary else { return }
            do {
                finish(.success(try makeSummary()))
            } catch {
                finish(.failure(error))
            }

        case 4:
            processError(fields)

        default:
            break
        }
    }

    private func makeSummary() throws -> TWSAccountSummary {
        let selectedAccount: String
        if accountID.isEmpty {
            guard let first = records.keys.sorted().first else {
                throw TWSPositionClientError.accountSummaryUnavailable("")
            }
            selectedAccount = first
        } else if let match = records.keys.first(where: {
            $0.caseInsensitiveCompare(accountID) == .orderedSame
        }) {
            selectedAccount = match
        } else {
            throw TWSPositionClientError.accountSummaryUnavailable(accountID)
        }

        guard let values = records[selectedAccount] else {
            throw TWSPositionClientError.accountSummaryUnavailable(selectedAccount)
        }
        let currency = values["NetLiquidation"]?.currency
            ?? values["AvailableFunds"]?.currency
            ?? values.values.first?.currency
            ?? "USD"
        return TWSAccountSummary(
            account: selectedAccount,
            currency: currency == "BASE" || currency.isEmpty ? "USD" : currency,
            netLiquidation: values["NetLiquidation"]?.value,
            availableFunds: values["AvailableFunds"]?.value,
            buyingPower: values["BuyingPower"]?.value,
            totalCashValue: values["TotalCashValue"]?.value,
            settledCash: values["SettledCash"]?.value,
            equityWithLoanValue: values["EquityWithLoanValue"]?.value,
            grossPositionValue: values["GrossPositionValue"]?.value,
            excessLiquidity: values["ExcessLiquidity"]?.value,
            initialMargin: values["InitMarginReq"]?.value,
            maintenanceMargin: values["MaintMarginReq"]?.value,
            unrealizedPnL: values["UnrealizedPnL"]?.value,
            realizedPnL: values["RealizedPnL"]?.value
        )
    }

    private func processError(_ fields: [String]) {
        guard fields.count >= 5, let requestID = Int(fields[2]), let code = Int(fields[3]) else { return }
        let informationalCodes: Set<Int> = [2104, 2106, 2107, 2108, 2158, 2176]
        guard !informationalCodes.contains(code) else { return }
        if requestID == Self.requestID || [502, 503, 504, 506].contains(code) {
            finish(.failure(TWSPositionClientError.apiError(code: code, message: fields[4])))
        }
    }

    private func send(_ data: Data) {
        connection?.send(content: data, completion: .contentProcessed { [weak self] error in
            guard let error else { return }
            self?.queue.async {
                self?.finish(.failure(TWSPositionClientError.connectionFailed(error.localizedDescription)))
            }
        })
    }

    private func finish(_ result: Result<TWSAccountSummary, Error>) {
        guard phase != .finished else { return }
        phase = .finished
        timeoutWorkItem?.cancel()
        timeoutWorkItem = nil
        connection?.stateUpdateHandler = nil
        connection?.cancel()
        connection = nil
        continuation?.resume(with: result)
        continuation = nil
    }
}

private final class TWSPnLSession: @unchecked Sendable {
    private enum Phase { case handshake, apiReady, pnl, finished }

    private static let requestID = 9_102

    private let host: String
    private let port: UInt16
    private let clientID: Int
    private let accountID: String
    private let timeout: DispatchTimeInterval
    private let queue = DispatchQueue(label: "com.mars9399.StockSignalMonitor.tws-pnl")

    private var connection: NWConnection?
    private var continuation: CheckedContinuation<TWSAccountPnL, Error>?
    private var timeoutWorkItem: DispatchWorkItem?
    private var receiveBuffer = Data()
    private var phase: Phase = .handshake
    private var serverVersion = 0
    private var requestedPnL = false

    init(host: String, port: UInt16, clientID: Int, accountID: String, timeout: DispatchTimeInterval) {
        self.host = host
        self.port = port
        self.clientID = clientID
        self.accountID = accountID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.timeout = timeout
    }

    func fetch() async throws -> TWSAccountPnL {
        guard !accountID.isEmpty else {
            throw TWSPositionClientError.pnlUnavailable("")
        }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                queue.async { [weak self] in self?.start(continuation: continuation) }
            }
        } onCancel: {
            self.queue.async { [weak self] in self?.finish(.failure(CancellationError())) }
        }
    }

    private func start(continuation: CheckedContinuation<TWSAccountPnL, Error>) {
        guard !host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let endpointPort = NWEndpoint.Port(rawValue: port) else {
            continuation.resume(throwing: TWSPositionClientError.invalidHost)
            return
        }

        self.continuation = continuation
        let connection = NWConnection(host: NWEndpoint.Host(host), port: endpointPort, using: .tcp)
        self.connection = connection
        connection.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            self.queue.async {
                switch state {
                case .ready:
                    self.send(TWSWireCodec.clientHandshake())
                    self.receiveNext()
                case let .failed(error):
                    self.finish(.failure(TWSPositionClientError.connectionFailed(error.localizedDescription)))
                case .cancelled:
                    if self.phase != .finished {
                        self.finish(.failure(TWSPositionClientError.connectionClosed))
                    }
                default:
                    break
                }
            }
        }
        connection.start(queue: queue)

        let timeoutWorkItem = DispatchWorkItem { [weak self] in
            self?.finish(.failure(TWSPositionClientError.pnlTimedOut))
        }
        self.timeoutWorkItem = timeoutWorkItem
        queue.asyncAfter(deadline: .now() + timeout, execute: timeoutWorkItem)
    }

    private func receiveNext() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [weak self] data, _, complete, error in
            guard let self else { return }
            self.queue.async {
                if let data, !data.isEmpty {
                    self.receiveBuffer.append(data)
                    self.processFrames()
                }
                if let error {
                    self.finish(.failure(TWSPositionClientError.connectionFailed(error.localizedDescription)))
                } else if complete {
                    self.finish(.failure(TWSPositionClientError.connectionClosed))
                } else if self.phase != .finished {
                    self.receiveNext()
                }
            }
        }
    }

    private func processFrames() {
        while let payload = TWSWireCodec.takeFrame(from: &receiveBuffer) {
            let fields = TWSWireCodec.fields(from: payload)
            guard !fields.isEmpty else { continue }
            if phase == .handshake {
                processHandshake(fields)
            } else {
                processMessage(fields)
            }
        }
    }

    private func processHandshake(_ fields: [String]) {
        guard fields.count >= 2, let version = Int(fields[0]) else {
            finish(.failure(TWSPositionClientError.malformedHandshake))
            return
        }
        guard version >= 127 else {
            finish(.failure(TWSPositionClientError.unsupportedServer(version)))
            return
        }

        serverVersion = version
        phase = .apiReady
        var startFields = ["71", "2", String(clientID)]
        if version >= 72 { startFields.append("") }
        send(TWSWireCodec.frame(fields: startFields))
    }

    private func processMessage(_ fields: [String]) {
        guard let messageID = Int(fields[0]) else { return }
        switch messageID {
        case 9:
            guard !requestedPnL else { return }
            requestedPnL = true
            phase = .pnl
            send(TWSWireCodec.frame(fields: [
                "92", String(Self.requestID), accountID, ""
            ]))

        case 94:
            guard let pnl = TWSWireCodec.pnl(from: fields, serverVersion: serverVersion) else { return }
            finish(.success(pnl))

        case 4:
            processError(fields)

        default:
            break
        }
    }

    private func processError(_ fields: [String]) {
        guard fields.count >= 5, let requestID = Int(fields[2]), let code = Int(fields[3]) else { return }
        let informationalCodes: Set<Int> = [2104, 2106, 2107, 2108, 2158, 2176]
        guard !informationalCodes.contains(code) else { return }
        if requestID == Self.requestID || [502, 503, 504, 506].contains(code) {
            finish(.failure(TWSPositionClientError.apiError(code: code, message: fields[4])))
        }
    }

    private func send(_ data: Data) {
        connection?.send(content: data, completion: .contentProcessed { [weak self] error in
            guard let error else { return }
            self?.queue.async {
                self?.finish(.failure(TWSPositionClientError.connectionFailed(error.localizedDescription)))
            }
        })
    }

    private func finish(_ result: Result<TWSAccountPnL, Error>) {
        guard phase != .finished else { return }
        phase = .finished
        timeoutWorkItem?.cancel()
        timeoutWorkItem = nil
        connection?.stateUpdateHandler = nil
        connection?.cancel()
        connection = nil
        continuation?.resume(with: result)
        continuation = nil
    }
}

struct TWSAccountValue: Hashable, Sendable {
    let account: String
    let tag: String
    let value: Double
    let currency: String

    var currencyPreference: Int {
        switch currency.uppercased() {
        case "USD": 2
        case "BASE": 1
        default: 0
        }
    }
}

enum TWSWireCodec {
    static let minimumClientVersion = 100
    static let maximumClientVersion = 157

    static func clientHandshake() -> Data {
        var output = Data("API\0".utf8)
        output.append(frame(payload: Data("v\(minimumClientVersion)..\(maximumClientVersion)".utf8)))
        return output
    }

    static func frame(fields: [String]) -> Data {
        var payload = Data()
        for field in fields {
            payload.append(Data(field.utf8))
            payload.append(0)
        }
        return frame(payload: payload)
    }

    static func frame(payload: Data) -> Data {
        let length = UInt32(payload.count)
        var output = Data([
            UInt8((length >> 24) & 0xff),
            UInt8((length >> 16) & 0xff),
            UInt8((length >> 8) & 0xff),
            UInt8(length & 0xff)
        ])
        output.append(payload)
        return output
    }

    static func takeFrame(from buffer: inout Data) -> Data? {
        guard buffer.count >= 4 else { return nil }
        let header = Array(buffer.prefix(4))
        let length = Int(header[0]) << 24 | Int(header[1]) << 16 | Int(header[2]) << 8 | Int(header[3])
        guard length >= 0, length <= 16_777_216, buffer.count >= length + 4 else { return nil }
        // Data slices do not guarantee a zero-based startIndex after bytes have
        // been removed. Derive both bounds from startIndex so consecutive TWS
        // frames in the same TCP receive buffer are decoded safely.
        let payloadStart = buffer.index(buffer.startIndex, offsetBy: 4)
        let payloadEnd = buffer.index(payloadStart, offsetBy: length)
        let payload = Data(buffer[payloadStart..<payloadEnd])
        buffer.removeFirst(length + 4)
        return payload
    }

    static func fields(from payload: Data) -> [String] {
        var fields = payload.split(separator: 0, omittingEmptySubsequences: false).map {
            String(decoding: $0, as: UTF8.self)
        }
        if fields.last == "" { fields.removeLast() }
        return fields
    }

    static func position(from fields: [String], serverVersion: Int) -> TWSPositionSnapshot? {
        guard fields.count >= 15,
              fields[0] == "61",
              let version = Int(fields[1]),
              let contractID = Int(fields[3]) else { return nil }

        let positionIndex = version >= 2 ? 14 : 13
        guard fields.indices.contains(positionIndex),
              let quantity = Double(fields[positionIndex]) else { return nil }
        let averageCostIndex = positionIndex + 1
        let averageCost = version >= 3 && fields.indices.contains(averageCostIndex)
            ? Double(fields[averageCostIndex]) ?? 0
            : 0

        return TWSPositionSnapshot(
            account: fields[2],
            contractID: contractID,
            symbol: fields[4],
            securityType: fields[5],
            currency: fields[11],
            quantity: serverVersion >= 101 ? quantity : quantity.rounded(),
            averageCost: averageCost
        )
    }

    static func accountSummaryValue(from fields: [String]) -> TWSAccountValue? {
        guard fields.count >= 7,
              fields[0] == "63",
              let value = normalizedDouble(fields[5]) else { return nil }
        return TWSAccountValue(
            account: fields[3],
            tag: fields[4],
            value: value,
            currency: fields[6]
        )
    }

    static func pnl(from fields: [String], serverVersion: Int) -> TWSAccountPnL? {
        guard fields.count >= 3,
              fields[0] == "94",
              Int(fields[1]) != nil else { return nil }
        return TWSAccountPnL(
            dailyPnL: normalizedDouble(fields[2]),
            unrealizedPnL: serverVersion >= 129 && fields.indices.contains(3)
                ? normalizedDouble(fields[3])
                : nil,
            realizedPnL: serverVersion >= 135 && fields.indices.contains(4)
                ? normalizedDouble(fields[4])
                : nil
        )
    }

    private static func normalizedDouble(_ rawValue: String) -> Double? {
        guard let value = Double(rawValue.replacingOccurrences(of: ",", with: "")),
              value.isFinite,
              abs(value) < 1e300 else { return nil }
        return value
    }
}
#endif
