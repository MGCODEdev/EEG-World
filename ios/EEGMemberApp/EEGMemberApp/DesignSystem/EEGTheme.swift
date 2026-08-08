import SwiftUI

enum EEGTheme {
    static let accent = Color(red: 0.18, green: 0.56, blue: 0.54)
    static let positive = Color.green
    static let warning = Color.orange
    static let consumption = Color.blue
    static let generation = Color(red: 0.96, green: 0.68, blue: 0.08)
    static let community = Color(red: 0.18, green: 0.65, blue: 0.36)
    static let grid = Color(red: 0.94, green: 0.42, blue: 0.16)
}

/// A deliberately small typography scale based on Apple's system font.
/// It mirrors the calm hierarchy used by native energy apps and keeps
/// Dashboard, Energy and the embedded D3 charts visually consistent.
enum EEGTypography {
    static let eyebrow = Font.system(size: 12, weight: .medium)
    static let caption = Font.system(size: 12, weight: .regular)
    static let control = Font.system(size: 15, weight: .medium)
    static let body = Font.system(size: 15, weight: .regular)
    static let sectionTitle = Font.system(size: 17, weight: .semibold)
    static let greeting = Font.system(size: 19, weight: .semibold)
    static let value = Font.system(size: 20, weight: .semibold)
}

struct MetricCard: View {
    let title: String
    let value: String
    let symbol: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: symbol).foregroundStyle(EEGTheme.accent)
            Text(value).font(EEGTypography.value).contentTransition(.numericText())
            Text(title).font(EEGTypography.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}

struct CompactMetric: View {
    let title: String
    let value: String
    let symbol: String
    var color: Color = EEGTheme.accent

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: symbol)
                .font(.subheadline.bold())
                .foregroundStyle(color)
                .frame(width: 24, height: 24)
                .background(color.opacity(0.12), in: Circle())
            VStack(alignment: .leading, spacing: 1) {
                Text(value)
                    .font(.system(size: 15, weight: .semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                    .contentTransition(.numericText())
                Text(title)
                    .font(EEGTypography.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 10)
        .padding(.vertical, 9)
        .background(Color(.tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }
}

extension Double {
    var euro: String { formatted(.currency(code: "EUR")) }
    func kwh(_ digits: Int = 1) -> String {
        formatted(.number.precision(.fractionLength(digits))) + " kWh"
    }
}

enum DateText {
    private static let input: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
    private static let output: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "de_AT")
        formatter.dateStyle = .medium
        return formatter
    }()

    static func date(_ value: String) -> String {
        guard let parsed = input.date(from: String(value.prefix(10))) else { return value }
        return output.string(from: parsed)
    }

    static func dateTime(_ value: String) -> String {
        let iso = ISO8601DateFormatter()
        let database = DateFormatter()
        database.locale = Locale(identifier: "en_US_POSIX")
        database.timeZone = TimeZone(secondsFromGMT: 0)
        database.dateFormat = "yyyy-MM-dd HH:mm:ss"
        if let parsed = iso.date(from: value) ?? database.date(from: value) {
            return parsed.formatted(
                Date.FormatStyle(date: .abbreviated, time: .shortened)
                    .locale(Locale(identifier: "de_AT"))
            )
        }
        return date(value)
    }

    static func period(_ from: String, _ to: String) -> String {
        "\(date(from)) – \(date(to))"
    }

    static func parsedDate(_ value: String) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter.date(from: String(value.prefix(19)))
    }

    static func apiDate(_ value: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(identifier: "Europe/Vienna")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: value)
    }

    static func chartDate(_ value: String) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "Europe/Vienna")
        if value.count == 7 {
            formatter.dateFormat = "yyyy-MM"
        } else if value.count == 10 {
            formatter.dateFormat = "yyyy-MM-dd"
        } else {
            formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        }
        return formatter.date(from: value)
    }

    static func chartLabel(_ value: String) -> String {
        guard let parsed = chartDate(value) else { return value }
        if value.count > 10 {
            return parsed.formatted(
                Date.FormatStyle(date: .abbreviated, time: .shortened)
                    .locale(Locale(identifier: "de_AT"))
            )
        }
        return parsed.formatted(
            Date.FormatStyle(date: value.count == 7 ? .complete : .abbreviated, time: .omitted)
                .locale(Locale(identifier: "de_AT"))
        )
    }
}
