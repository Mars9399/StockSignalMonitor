#if os(macOS)
import XCTest
@testable import StockSignalCore

final class TWSLiveIntegrationTests: XCTestCase {
    func testReadsPositionsFromLocalTWSWhenEnabled() async throws {
        guard ProcessInfo.processInfo.environment["TWS_LIVE_TEST"] == "1" else {
            throw XCTSkip("Set TWS_LIVE_TEST=1 to test against a logged-in local TWS instance.")
        }

        let port = UInt16(ProcessInfo.processInfo.environment["TWS_PORT"] ?? "7497") ?? 7497
        let clientID = Int(ProcessInfo.processInfo.environment["TWS_CLIENT_ID"] ?? "117") ?? 117
        let positions = try await TWSPositionClient().fetchPositions(
            host: "127.0.0.1",
            port: port,
            clientID: clientID,
            timeout: .seconds(15)
        )

        XCTAssertFalse(positions.isEmpty, "TWS connected but returned no positions.")
        XCTAssertTrue(positions.allSatisfy { !$0.account.isEmpty && !$0.symbol.isEmpty })
    }
}
#endif
