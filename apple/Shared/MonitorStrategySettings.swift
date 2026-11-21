import Foundation

public struct MonitorStrategySettings: Codable, Equatable, Sendable {
    public var filterVolumeEnabled: Bool
    public var filterVolumeMinRatio: Double
    public var filterRelativeStrengthEnabled: Bool
    public var filterChannelWidthEnabled: Bool
    public var filterChannelWidthMinPercent: Double
    public var filterChannelWidthMaxPercent: Double
    public var preferPullbackEntry: Bool
    public var volatilityAdaptiveLookback: Bool
    public var atrStopMultiplier: Double
    public var takeProfitATRMultiple: Double
    public var enableTakeProfitHint: Bool
    public var showFeedProfile: Bool
    public var benchmarkSymbol: String
    public var quotePollSeconds: Int

    public static let `default` = MonitorStrategySettings(
        filterVolumeEnabled: false,
        filterVolumeMinRatio: 1.15,
        filterRelativeStrengthEnabled: false,
        filterChannelWidthEnabled: false,
        filterChannelWidthMinPercent: 4,
        filterChannelWidthMaxPercent: 35,
        preferPullbackEntry: false,
        volatilityAdaptiveLookback: false,
        atrStopMultiplier: 2,
        takeProfitATRMultiple: 3,
        enableTakeProfitHint: true,
        showFeedProfile: true,
        benchmarkSymbol: "SPY",
        quotePollSeconds: 5
    )

    public init(
        filterVolumeEnabled: Bool = false,
        filterVolumeMinRatio: Double = 1.15,
        filterRelativeStrengthEnabled: Bool = false,
        filterChannelWidthEnabled: Bool = false,
        filterChannelWidthMinPercent: Double = 4,
        filterChannelWidthMaxPercent: Double = 35,
        preferPullbackEntry: Bool = false,
        volatilityAdaptiveLookback: Bool = false,
        atrStopMultiplier: Double = 2,
        takeProfitATRMultiple: Double = 3,
        enableTakeProfitHint: Bool = true,
        showFeedProfile: Bool = true,
        benchmarkSymbol: String = "SPY",
        quotePollSeconds: Int = 5
    ) {
        self.filterVolumeEnabled = filterVolumeEnabled
        self.filterVolumeMinRatio = filterVolumeMinRatio
        self.filterRelativeStrengthEnabled = filterRelativeStrengthEnabled
        self.filterChannelWidthEnabled = filterChannelWidthEnabled
        self.filterChannelWidthMinPercent = filterChannelWidthMinPercent
        self.filterChannelWidthMaxPercent = filterChannelWidthMaxPercent
        self.preferPullbackEntry = preferPullbackEntry
        self.volatilityAdaptiveLookback = volatilityAdaptiveLookback
        self.atrStopMultiplier = atrStopMultiplier
        self.takeProfitATRMultiple = takeProfitATRMultiple
        self.enableTakeProfitHint = enableTakeProfitHint
        self.showFeedProfile = showFeedProfile
        self.benchmarkSymbol = benchmarkSymbol.uppercased()
        self.quotePollSeconds = max(3, min(60, quotePollSeconds))
    }
}
