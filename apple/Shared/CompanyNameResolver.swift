import Foundation

/// Offline fallback names for commonly monitored US stocks and ETFs.
/// Unknown symbols intentionally return `nil`; callers may later replace the
/// fallback with provider metadata without changing the watchlist model.
public enum CompanyNameResolver {
    public static let commonNames: [String: String] = [
        "AAPL": "Apple Inc.",
        "ABBV": "AbbVie Inc.",
        "ABNB": "Airbnb, Inc.",
        "ADBE": "Adobe Inc.",
        "AMD": "Advanced Micro Devices, Inc.",
        "AMGN": "Amgen Inc.",
        "AMZN": "Amazon.com, Inc.",
        "AVGO": "Broadcom Inc.",
        "BA": "The Boeing Company",
        "BAC": "Bank of America Corp.",
        "BRK.B": "Berkshire Hathaway Inc. Class B",
        "CAT": "Caterpillar Inc.",
        "COIN": "Coinbase Global, Inc.",
        "COST": "Costco Wholesale Corp.",
        "CRM": "Salesforce, Inc.",
        "CSCO": "Cisco Systems, Inc.",
        "CVX": "Chevron Corp.",
        "DIA": "SPDR Dow Jones Industrial Average ETF Trust",
        "DIS": "The Walt Disney Company",
        "GOOG": "Alphabet Inc. Class C",
        "GOOGL": "Alphabet Inc. Class A",
        "HD": "The Home Depot, Inc.",
        "IWM": "iShares Russell 2000 ETF",
        "JNJ": "Johnson & Johnson",
        "JPM": "JPMorgan Chase & Co.",
        "KO": "The Coca-Cola Company",
        "LLY": "Eli Lilly and Company",
        "MA": "Mastercard Inc.",
        "META": "Meta Platforms, Inc.",
        "MRK": "Merck & Co., Inc.",
        "MSFT": "Microsoft Corp.",
        "NFLX": "Netflix, Inc.",
        "NKE": "NIKE, Inc.",
        "NVDA": "NVIDIA Corp.",
        "ORCL": "Oracle Corp.",
        "PEP": "PepsiCo, Inc.",
        "PFE": "Pfizer Inc.",
        "PG": "The Procter & Gamble Company",
        "PLTR": "Palantir Technologies Inc.",
        "PYPL": "PayPal Holdings, Inc.",
        "QQQ": "Invesco QQQ Trust",
        "SBUX": "Starbucks Corp.",
        "SMH": "VanEck Semiconductor ETF",
        "SPY": "SPDR S&P 500 ETF Trust",
        "T": "AT&T Inc.",
        "TSLA": "Tesla, Inc.",
        "UNH": "UnitedHealth Group Inc.",
        "V": "Visa Inc.",
        "VTI": "Vanguard Total Stock Market ETF",
        "WMT": "Walmart Inc.",
        "XLE": "Energy Select Sector SPDR Fund",
        "XLF": "Financial Select Sector SPDR Fund",
        "XOM": "Exxon Mobil Corp."
    ]

    public static func name(for symbol: String) -> String? {
        let normalized = symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        return commonNames[normalized]
    }

    public static func displayName(for symbol: String) -> String {
        name(for: symbol) ?? symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    }
}
