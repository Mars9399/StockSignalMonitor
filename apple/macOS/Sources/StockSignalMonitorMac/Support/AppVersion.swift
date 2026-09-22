import Foundation

enum AppVersion {
    static let current = Bundle.main.object(
        forInfoDictionaryKey: "CFBundleShortVersionString"
    ) as? String ?? "2.5.2"

    static let display = "v\(current)"
}
