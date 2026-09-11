// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "StockSignalCore",
    defaultLocalization: "zh-Hans",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "StockSignalCore", targets: ["StockSignalCore"])],
    targets: [
        .target(name: "StockSignalCore", path: "Shared"),
        .testTarget(
            name: "StockSignalCoreTests",
            dependencies: ["StockSignalCore"],
            path: "Tests/SharedTests",
            resources: [.copy("Fixtures")]
        )
    ]
)
