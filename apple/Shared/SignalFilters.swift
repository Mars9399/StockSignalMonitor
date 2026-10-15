import Foundation

public struct FilteredSignal {
    public var levels: SignalLevels
    public var rawStatus: SignalStatus
    public var suppressed: Bool
    public var notes: [String]
    public var breakoutExtensionPercent: Double
    public var relativeStrengthSpread: Double?

    public init(
        levels: SignalLevels,
        rawStatus: SignalStatus,
        suppressed: Bool,
        notes: [String],
        breakoutExtensionPercent: Double,
        relativeStrengthSpread: Double?
    ) {
        self.levels = levels
        self.rawStatus = rawStatus
        self.suppressed = suppressed
        self.notes = notes
        self.breakoutExtensionPercent = breakoutExtensionPercent
        self.relativeStrengthSpread = relativeStrengthSpread
    }
}

public enum SignalFilterEngine {
    public static func apply(
        levels: SignalLevels,
        settings: MonitorStrategySettings,
        symbolChangePercent: Double? = nil,
        benchmarkChangePercent: Double? = nil
    ) -> FilteredSignal {
        var result = levels
        var notes: [String] = []
        var blocked: [String] = []
        let raw = levels.status
        let width = levels.buyPoint > 0 ? max(0, (levels.buyPoint - levels.stopPoint) / levels.buyPoint * 100) : 0
        let extensionPercent = levels.buyPoint > 0 ? max(0, (levels.price / levels.buyPoint - 1) * 100) : 0

        guard levels.isReady else {
            return FilteredSignal(
                levels: result,
                rawStatus: raw,
                suppressed: false,
                notes: notes,
                breakoutExtensionPercent: extensionPercent,
                relativeStrengthSpread: nil
            )
        }

        if settings.filterChannelWidthEnabled {
            if width < settings.filterChannelWidthMinPercent {
                blocked.append(String(format: "通道过窄 %.1f%%", width))
            } else if width > settings.filterChannelWidthMaxPercent {
                blocked.append(String(format: "通道过宽 %.1f%%", width))
            }
        }

        if raw == .buyAlert, settings.filterVolumeEnabled, levels.volumeRatio < settings.filterVolumeMinRatio {
            blocked.append(String(format: "量比不足 %.2f", levels.volumeRatio))
        }

        var rsSpread: Double?
        if let symbolChangePercent, let benchmarkChangePercent {
            rsSpread = symbolChangePercent - benchmarkChangePercent
            if settings.filterRelativeStrengthEnabled, raw == .buyAlert, symbolChangePercent < benchmarkChangePercent {
                blocked.append("弱于基准（相对强弱未通过）")
            }
        } else if settings.filterRelativeStrengthEnabled, raw == .buyAlert {
            notes.append("相对强弱暂缺基准数据，未强制过滤")
        }

        if raw == .buyAlert, settings.preferPullbackEntry, extensionPercent > 3 {
            blocked.append(String(format: "突破已延伸 +%.1f%%，偏好回踩确认", extensionPercent))
        }

        let suppressed = !blocked.isEmpty && (raw == .buyAlert || raw == .sellAlert)
        if suppressed {
            result.status = .watch
            notes.append(contentsOf: blocked)
        } else {
            notes.append(contentsOf: blocked)
        }

        return FilteredSignal(
            levels: result,
            rawStatus: raw,
            suppressed: suppressed,
            notes: notes,
            breakoutExtensionPercent: extensionPercent,
            relativeStrengthSpread: rsSpread
        )
    }
}
