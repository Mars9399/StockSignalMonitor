import Foundation

public enum DataReliability {
    private static var calendar: Calendar {
        var value = Calendar(identifier: .gregorian)
        value.timeZone = TimeZone(identifier: "America/New_York")!
        return value
    }

    public static func day(_ date: Date) -> String {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year!, c.month!, c.day!)
    }

    public static func barDay(_ date: Date) -> String {
        // Providers use either UTC midnight or the actual exchange session start.
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate]
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter.string(from: date)
    }

    public static func completedBars(_ bars: [DailyBar], now: Date = .now) -> [DailyBar] {
        var unique: [String: DailyBar] = [:]
        for bar in bars where barDay(bar.date) < day(now) { unique[barDay(bar.date)] = bar }
        return unique.values.sorted { $0.date < $1.date }
    }

    public static func reason(quote: StockQuote, history: [DailyBar], now: Date = .now) -> String? {
        guard quote.price.isFinite, quote.price > 0 else { return "价格无效" }
        let age = now.timeIntervalSince(quote.timestamp)
        guard age >= -30, age <= 180 else { return "行情过期或时间异常（超过 180 秒）" }
        let components = calendar.dateComponents([.weekday, .hour, .minute], from: now)
        let minutes = components.hour! * 60 + components.minute!
        guard (2...6).contains(components.weekday!), (240..<1200).contains(minutes) else {
            return "美股盘前、正常交易及盘后时段外"
        }
        guard let last = history.last else {
            return "日线未更新或交易日待核实"
        }
        let parts = barDay(last.date).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3,
              let lastDay = calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2])) else {
            return "日线未更新或交易日待核实"
        }
        let currentDay = calendar.startOfDay(for: now)
        let ageDays = calendar.dateComponents([.day], from: lastDay, to: currentDay).day ?? -1
        guard (1...4).contains(ageDays) else { return "日线未更新或交易日待核实" }
        return nil
    }
}
