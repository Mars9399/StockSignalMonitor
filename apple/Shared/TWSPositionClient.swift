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

public enum TWSPositionClientError: LocalizedError, Sendable {
    case invalidHost
    case connectionFailed(String)
    case timedOut
    case unsupportedServer(Int)
    case malformedHandshake
    case apiError(code: Int, message: String)
    case connectionClosed

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
        }
    }
}

/// Read-only TWS Socket API client. It intentionally implements only the
/// connection handshake and reqPositions/cancelPositions messages.
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
}
#endif
