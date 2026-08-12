import Foundation

enum SignalFormatting {
    static let currency: FloatingPointFormatStyle<Double>.Currency = .currency(code: "USD")
        .precision(.fractionLength(2))

    static let timestamp: Date.FormatStyle = .dateTime
        .hour(.twoDigits(amPM: .omitted))
        .minute(.twoDigits)
        .second(.twoDigits)
}

extension Optional where Wrapped == Double {
    var currencyText: String {
        guard let self else { return "—" }
        return self.formatted(SignalFormatting.currency)
    }
}
