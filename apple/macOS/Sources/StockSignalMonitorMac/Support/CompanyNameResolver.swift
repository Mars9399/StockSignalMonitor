import Foundation

enum CompanyNameResolver {
    private static let commonNames: [String: String] = [
        "AAPL": "Apple Inc.",
        "AMZN": "Amazon.com, Inc.",
        "GOOG": "Alphabet Inc.",
        "GOOGL": "Alphabet Inc.",
        "META": "Meta Platforms, Inc.",
        "MSFT": "Microsoft Corporation",
        "NFLX": "Netflix, Inc.",
        "NVDA": "NVIDIA Corporation",
        "QQQ": "Invesco QQQ Trust",
        "SPY": "SPDR S&P 500 ETF Trust",
        "TSLA": "Tesla, Inc."
    ]

    static func resolve(symbol: String, suppliedName: String) -> String {
        if !suppliedName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return suppliedName
        }
        return commonNames[symbol.uppercased()] ?? "名称待数据源提供"
    }
}
