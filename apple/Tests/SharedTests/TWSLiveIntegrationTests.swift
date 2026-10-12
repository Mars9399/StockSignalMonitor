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
        let client = TWSPositionClient()
        let positions = try await client.fetchPositions(
            host: "127.0.0.1",
            port: port,
            clientID: clientID,
            timeout: .seconds(15)
        )

        XCTAssertFalse(positions.isEmpty, "TWS connected but returned no positions.")
        XCTAssertTrue(positions.allSatisfy { !$0.account.isEmpty && !$0.symbol.isEmpty })

        let summary = try await client.fetchAccountSummary(
            host: "127.0.0.1",
            port: port,
            clientID: TWSPositionClient.auxiliaryClientID(base: clientID),
            accountID: ProcessInfo.processInfo.environment["TWS_ACCOUNT_ID"] ?? "",
            timeout: .seconds(15)
        )
        XCTAssertFalse(summary.account.isEmpty)
        XCTAssertGreaterThan(summary.netLiquidation ?? 0, 0)

        let pnl = try await client.fetchPnL(
            host: "127.0.0.1",
            port: port,
            clientID: TWSPositionClient.auxiliaryClientID(base: clientID, offset: 102),
            accountID: summary.account,
            timeout: .seconds(15)
        )
        XCTAssertNotNil(pnl.dailyPnL)
    }
}
#endif
