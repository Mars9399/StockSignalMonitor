import Foundation

enum AppVersion {
    static let current = Bundle.main.object(
        forInfoDictionaryKey: "CFBundleShortVersionString"
    ) as? String ?? "2.6.0"

    static let display = "v\(current)"
}
