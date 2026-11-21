import Foundation

/// Static symbol -> SPDR sector ETF map; tests/test_holding_diagnosis.py checks it equals sector_map.py.
public enum SectorMap {
    public static let etfNames: [String: String] = [
        "XLK": "信息技术",
        "XLC": "通信服务",
        "XLY": "可选消费",
        "XLP": "必需消费",
        "XLV": "医疗保健",
        "XLF": "金融",
        "XLE": "能源",
        "XLI": "工业",
        "XLB": "原材料",
        "XLU": "公用事业",
        "XLRE": "房地产",
    ]

    public static let symbols: [String: String] = [
        "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AVGO": "XLK", "ORCL": "XLK",
        "CRM": "XLK", "ADBE": "XLK", "AMD": "XLK", "INTC": "XLK", "CSCO": "XLK",
        "QCOM": "XLK", "TXN": "XLK", "IBM": "XLK", "MU": "XLK", "AMAT": "XLK",
        "NOW": "XLK", "INTU": "XLK", "PLTR": "XLK", "LRCX": "XLK", "KLAC": "XLK",
        "GOOGL": "XLC", "GOOG": "XLC", "META": "XLC", "NFLX": "XLC", "DIS": "XLC",
        "TMUS": "XLC", "VZ": "XLC", "T": "XLC",
        "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY", "NKE": "XLY",
        "SBUX": "XLY", "LOW": "XLY", "BKNG": "XLY",
        "WMT": "XLP", "PG": "XLP", "KO": "XLP", "PEP": "XLP", "COST": "XLP", "PM": "XLP",
        "UNH": "XLV", "JNJ": "XLV", "LLY": "XLV", "PFE": "XLV", "MRK": "XLV",
        "ABBV": "XLV", "TMO": "XLV",
        "JPM": "XLF", "BAC": "XLF", "WFC": "XLF", "GS": "XLF", "MS": "XLF",
        "V": "XLF", "MA": "XLF", "BRK.B": "XLF", "C": "XLF", "AXP": "XLF",
        "XOM": "XLE", "CVX": "XLE", "COP": "XLE", "SLB": "XLE",
        "CAT": "XLI", "BA": "XLI", "GE": "XLI", "HON": "XLI", "UPS": "XLI",
        "RTX": "XLI", "DE": "XLI", "LMT": "XLI",
        "LIN": "XLB", "FCX": "XLB", "NEM": "XLB",
        "NEE": "XLU", "DUK": "XLU", "SO": "XLU",
        "PLD": "XLRE", "AMT": "XLRE", "O": "XLRE",
    ]

    /// Sector ETF for a symbol; sector ETFs map to themselves.
    public static func sector(for symbol: String) -> String? {
        let normalized = symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        if etfNames[normalized] != nil { return normalized }
        return symbols[normalized]
    }

    public static func name(for etf: String?) -> String {
        guard let etf else { return "未分类" }
        return etfNames[etf] ?? etf
    }
}
