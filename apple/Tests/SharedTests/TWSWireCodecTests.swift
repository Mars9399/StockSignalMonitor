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
}
#endif
