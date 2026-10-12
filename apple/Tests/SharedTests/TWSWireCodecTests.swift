#if os(macOS)
import XCTest
@testable import StockSignalCore

final class TWSWireCodecTests: XCTestCase {
    func testFramesAndExtractsNullTerminatedFields() {
        var buffer = TWSWireCodec.frame(fields: ["61", "1"])
        let payload = TWSWireCodec.takeFrame(from: &buffer)

        XCTAssertEqual(payload.map(TWSWireCodec.fields), ["61", "1"])
        XCTAssertTrue(buffer.isEmpty)
    }

    func testExtractsConsecutiveFramesAfterAdvancingDataStartIndex() {
        var buffer = TWSWireCodec.frame(fields: ["9", "1", "100"])
        buffer.append(TWSWireCodec.frame(fields: ["62", "1"]))

        let first = TWSWireCodec.takeFrame(from: &buffer)
        let second = TWSWireCodec.takeFrame(from: &buffer)

        XCTAssertEqual(first.map(TWSWireCodec.fields), ["9", "1", "100"])
        XCTAssertEqual(second.map(TWSWireCodec.fields), ["62", "1"])
        XCTAssertTrue(buffer.isEmpty)
    }

    func testDecodesStockPositionWithFractionalQuantity() throws {
        let fields = [
            "61", "3", "DU123456", "265598", "AAPL", "STK", "", "0", "", "",
            "SMART", "USD", "AAPL", "NMS", "12.5", "187.25"
        ]

        let position = try XCTUnwrap(TWSWireCodec.position(from: fields, serverVersion: 157))
        XCTAssertEqual(position.account, "DU123456")
        XCTAssertEqual(position.symbol, "AAPL")
        XCTAssertEqual(position.securityType, "STK")
        XCTAssertEqual(position.currency, "USD")
        XCTAssertEqual(position.quantity, 12.5)
        XCTAssertEqual(position.averageCost, 187.25)
    }

    func testHandshakeAdvertisesOnlyTheImplementedProtocolRange() {
        let handshake = TWSWireCodec.clientHandshake()
        XCTAssertTrue(String(decoding: handshake, as: UTF8.self).contains("v100..157"))
    }

    func testDecodesAccountSummaryValue() throws {
        let fields = ["63", "1", "9101", "DU123456", "NetLiquidation", "123,456.78", "USD"]

        let value = try XCTUnwrap(TWSWireCodec.accountSummaryValue(from: fields))

        XCTAssertEqual(value.account, "DU123456")
        XCTAssertEqual(value.tag, "NetLiquidation")
        XCTAssertEqual(value.value, 123_456.78, accuracy: 0.001)
        XCTAssertEqual(value.currency, "USD")
    }

    func testDecodesRealtimeAccountPnL() throws {
        let fields = ["94", "9102", "125.50", "420.25", "-32.75"]

        let pnl = try XCTUnwrap(TWSWireCodec.pnl(from: fields, serverVersion: 157))

        XCTAssertEqual(pnl.dailyPnL, 125.50)
        XCTAssertEqual(pnl.unrealizedPnL, 420.25)
        XCTAssertEqual(pnl.realizedPnL, -32.75)
    }

    func testPnLDecoderTreatsIBKRMaxDoubleAsMissing() throws {
        let fields = ["94", "9102", "1.7976931348623157E308", "48.25", "1.7976931348623157E308"]

        let pnl = try XCTUnwrap(TWSWireCodec.pnl(from: fields, serverVersion: 157))

        XCTAssertNil(pnl.dailyPnL)
        XCTAssertEqual(pnl.unrealizedPnL, 48.25)
        XCTAssertNil(pnl.realizedPnL)
    }

    func testAccountSummaryMergesRealtimePnL() {
        let summary = TWSAccountSummary(account: "DU123456", netLiquidation: 100_000)
        let merged = summary.merging(
            pnl: TWSAccountPnL(dailyPnL: 150, unrealizedPnL: 500, realizedPnL: -25)
        )

        XCTAssertEqual(merged.netLiquidation, 100_000)
        XCTAssertEqual(merged.dailyPnL, 150)
        XCTAssertEqual(merged.unrealizedPnL, 500)
        XCTAssertEqual(merged.realizedPnL, -25)
    }

    func testAuxiliaryClientIDDoesNotCollideWithPositionClient() {
        XCTAssertEqual(TWSPositionClient.auxiliaryClientID(base: 17), 118)
        XCTAssertNotEqual(TWSPositionClient.auxiliaryClientID(base: Int(Int32.max)), Int(Int32.max))
    }
}
#endif
