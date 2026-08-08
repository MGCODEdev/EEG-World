import SwiftUI

struct EnergyPricesView: View {
    @EnvironmentObject private var auth: AuthManager
    @State private var prices: EnergyPricesResponse?
    @State private var errorMessage: String?
    @State private var historyRange: PriceHistoryRange = .twelveMonths

    var body: some View {
        List {
            if let prices {
                if let current = prices.current {
                    Section("Aktueller EEG-Tarif") {
                        PriceRow(
                            title: "Strom aus der EEG",
                            subtitle: "Preis für bezogene Energie",
                            value: current.eegConsumptionCt,
                            symbol: "bolt.fill",
                            color: EEGTheme.community
                        )
                        PriceRow(
                            title: "Strom an die EEG",
                            subtitle: "Vergütung für gelieferte Energie",
                            value: current.eegGenerationCt,
                            symbol: "sun.max.fill",
                            color: EEGTheme.generation
                        )
                        LabeledContent(
                            "Gültig",
                            value: DateText.period(current.validFrom, current.validTo)
                        )
                        .font(.subheadline)
                        if let description = current.description, !description.isEmpty {
                            Text(description).font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                } else {
                    Section {
                        ContentUnavailableView(
                            "Kein EEG-Tarif hinterlegt",
                            systemImage: "eurosign.circle"
                        )
                    }
                }

                if !prices.history.isEmpty {
                    Section("Preisentwicklung") {
                        Picker("Zeitraum", selection: $historyRange) {
                            ForEach(PriceHistoryRange.allCases) { range in
                                Text(range.rawValue).tag(range)
                            }
                        }
                        .pickerStyle(.segmented)
                        .font(.system(.subheadline, design: .rounded, weight: .semibold))

                        D3ChartView(payload: priceChartPayload(prices.history))
                            .frame(height: 320)
                            .accessibilityLabel("EEG-Preisentwicklung für Bezug und Einspeisung")
                        Label("Bezug und Einspeisung in Cent pro Kilowattstunde", systemImage: "chart.xyaxis.line")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }

                if prices.history.count > 1 {
                    Section("Frühere EEG-Tarife") {
                        ForEach(prices.history.dropFirst()) { price in
                            VStack(alignment: .leading, spacing: 5) {
                                Text(DateText.period(price.validFrom, price.validTo))
                                    .font(.body.weight(.semibold))
                                HStack {
                                    Text("Bezug \(price.eegConsumptionCt.pricePerKwh)")
                                    Spacer()
                                    Text("Lieferung \(price.eegGenerationCt.pricePerKwh)")
                                }
                                .font(.footnote).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            } else if let errorMessage {
                ContentUnavailableView(
                    "Preise nicht verfügbar",
                    systemImage: "wifi.exclamationmark",
                    description: Text(errorMessage)
                )
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Strompreise")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        do {
            prices = try await auth.authorized(EnergyPricesResponse.self, path: "prices")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func priceChartPayload(_ allPrices: [EnergyPrice]) -> D3ChartPayload {
        let sorted = allPrices.sorted { $0.validFrom < $1.validFrom }
        let visible: [EnergyPrice]
        if let months = historyRange.months,
           let newest = sorted.last.flatMap({ DateText.chartDate($0.validFrom) }),
           let cutoff = Calendar.current.date(byAdding: .month, value: -months, to: newest) {
            visible = sorted.filter {
                (DateText.chartDate($0.validFrom) ?? .distantPast) >= cutoff
            }
        } else {
            visible = sorted
        }
        return D3ChartPayload(
            kind: "lines",
            unit: "ct/kWh",
            categories: visible.map {
                .init(
                    label: DateText.chartDate($0.validFrom)?.formatted(
                        .dateTime.month(.abbreviated).year().locale(Locale(identifier: "de_AT"))
                    ) ?? DateText.date($0.validFrom),
                    detail: DateText.period($0.validFrom, $0.validTo),
                    estimated: false
                )
            },
            series: [
                .init(
                    label: "EEG-Bezug", color: "#2EA65C", stack: "Preis",
                    values: visible.map { $0.eegConsumptionCt }
                ),
                .init(
                    label: "EEG-Einspeisung", color: "#2878D0", stack: "Preis",
                    values: visible.map { $0.eegGenerationCt }
                ),
            ]
        )
    }
}

private enum PriceHistoryRange: String, CaseIterable, Identifiable {
    case threeMonths = "3 M"
    case sixMonths = "6 M"
    case twelveMonths = "12 M"
    case maximum = "Max"

    var id: Self { self }
    var months: Int? {
        switch self {
        case .threeMonths: 3
        case .sixMonths: 6
        case .twelveMonths: 12
        case .maximum: nil
        }
    }
}

private struct PriceRow: View {
    let title: String
    let subtitle: String
    let value: Double
    let symbol: String
    let color: Color

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .foregroundStyle(color)
                .frame(width: 30, height: 30)
                .background(color.opacity(0.13), in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body.weight(.semibold))
                Text(subtitle).font(.footnote).foregroundStyle(.secondary)
            }
            Spacer()
            Text(value.pricePerKwh).font(.headline.monospacedDigit())
        }
        .accessibilityElement(children: .combine)
    }
}

private extension Double {
    var pricePerKwh: String {
        formatted(.number.precision(.fractionLength(2))) + " ct/kWh"
    }
}
