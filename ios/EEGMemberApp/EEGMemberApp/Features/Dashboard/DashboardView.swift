import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var auth: AuthManager
    @State private var data: DashboardResponse?
    @State private var errorMessage: String?
    @State private var showingCachedData = false
    @State private var dataStatus: HistoricalDataStatus?
    @State private var historicalSummary: HistoricalEnergySummary?
    @State private var prices: EnergyPricesResponse?
    @State private var overviewPeriod: OverviewPeriod = .month
    @State private var displayUnit: EnergyDisplayUnit = .energy
    @State private var latestAvailableDate = Date()
    @State private var overviewDate = Date()
    @State private var didSelectAvailableOverviewDate = false

    var body: some View {
        ScrollView {
            if let data {
                VStack(alignment: .leading, spacing: 13) {
                    portalHeader(data)
                    overviewControls
                    if showingCachedData {
                        Label("Zuletzt geladene Daten", systemImage: "icloud.slash")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let historicalSummary {
                        energyFlowOverview(historicalSummary)
                    }
                    if let dataStatus { EnergyDataStatusLine(status: dataStatus) }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
            } else if let errorMessage {
                ContentUnavailableView(
                    "Daten nicht verfügbar", systemImage: "wifi.exclamationmark",
                    description: Text(errorMessage)
                )
            } else {
                ProgressView().padding(.top, 80)
            }
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Übersicht")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task {
            loadCached()
            await load()
        }
        .onChange(of: overviewPeriod) { _, _ in Task { await loadSummary() } }
        .onChange(of: overviewDate) { _, _ in Task { await loadSummary() } }
    }

    private func portalHeader(_ data: DashboardResponse) -> some View {
        HStack(spacing: 13) {
            Image(systemName: "sun.max.fill")
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(EEGTheme.accent)
                .frame(width: 46, height: 46)
                .background(EEGTheme.accent.opacity(0.10), in: Circle())
            VStack(alignment: .leading, spacing: 3) {
                Text("EEG Trabocherstraße")
                    .font(EEGTypography.eyebrow)
                    .foregroundStyle(.secondary)
                Text("Hallo, \(auth.memberName)")
                    .font(EEGTypography.greeting)
                    .lineLimit(2)
                    .minimumScaleFactor(0.82)
                    .fixedSize(horizontal: false, vertical: true)
                if data.member.active == false {
                    Text("Mitgliedschaft inaktiv")
                        .font(.caption.weight(.semibold)).foregroundStyle(.red)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 13).padding(.vertical, 12)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 17))
        .overlay { RoundedRectangle(cornerRadius: 17).stroke(Color(.separator).opacity(0.20)) }
        .accessibilityElement(children: .combine)
        .accessibilityHeading(.h1)
    }

    private var overviewControls: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                Picker("Zeitraum", selection: $overviewPeriod) {
                    ForEach(OverviewPeriod.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: .infinity)
                Picker("Einheit", selection: $displayUnit) {
                    ForEach(EnergyDisplayUnit.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .frame(width: 105)
            }
            .font(EEGTypography.control)

            PeriodNavigationRow(
                title: overviewPeriod.navigationTitle(for: overviewDate),
                selection: $overviewDate,
                maximumDate: latestAvailableDate,
                canMoveForward: canMoveOverviewForward,
                moveBackward: { shiftOverviewPeriod(-1) },
                moveForward: { shiftOverviewPeriod(1) }
            )
        }
        .padding(10)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 13))
    }

    private var canMoveOverviewForward: Bool {
        let next = overviewPeriod.shift(overviewDate, by: 1)
        return overviewPeriod.range(containing: next).from <= latestAvailableDate
    }

    private func shiftOverviewPeriod(_ amount: Int) {
        overviewDate = overviewPeriod.shift(overviewDate, by: amount)
    }

    private func energyFlowOverview(_ summary: HistoricalEnergySummary) -> some View {
        let currentPrice = prices?.current
        let reference = prices?.reference
        let consumption = summary.balance.consumption
        let generation = summary.balance.generation
        let consumptionEegEuro = if let currentPrice, let eeg = consumption.eegKwh {
            eeg * currentPrice.eegConsumptionCt / 100
        } else { nil as Double? }
        let consumptionGridEuro = if let reference, let grid = consumption.gridKwh {
            grid * reference.gridConsumptionCt / 100
        } else { nil as Double? }
        let generationEegEuro = if let currentPrice, let eeg = generation.eegKwh {
            eeg * currentPrice.eegGenerationCt / 100
        } else { nil as Double? }
        let generationGridEuro = if let reference, let grid = generation.gridKwh {
            grid * reference.publicFeedCt / 100
        } else { nil as Double? }
        func value(_ energy: Double?, _ money: Double?) -> Double? {
            displayUnit == .energy ? energy : money
        }
        var categories: [D3ChartPayload.Category] = []
        var eegValues: [Double?] = []
        var gridValues: [Double?] = []
        var eegColors: [String?] = []
        var gridColors: [String?] = []
        if consumption.totalKwh > 0 || generation.totalKwh <= 0 {
            categories.append(D3ChartPayload.Category(
                label: "Mein Verbrauch",
                detail: "Aufteilung des gemessenen Verbrauchs",
                estimated: false
            ))
            eegValues.append(value(consumption.eegKwh, consumptionEegEuro))
            gridValues.append(value(consumption.gridKwh, consumptionGridEuro))
            eegColors.append(EnergyPalette.consumptionEEG)
            gridColors.append(EnergyPalette.consumptionGrid)
        }
        if generation.totalKwh > 0 {
            categories.append(.init(
                label: "Meine Einspeisung",
                detail: "Aufteilung der berücksichtigten Erzeugung",
                estimated: false
            ))
            eegValues.append(value(generation.eegKwh, generationEegEuro))
            gridValues.append(value(generation.gridKwh, generationGridEuro))
            eegColors.append(EnergyPalette.generationEEG)
            gridColors.append(EnergyPalette.generationGrid)
        }
        let payload = D3ChartPayload(
            kind: "donuts",
            unit: displayUnit.rawValue,
            categories: categories,
            series: [
                .init(
                    label: "EEG", color: EnergyPalette.consumptionEEG,
                    stack: "Bilanz", values: eegValues, colors: eegColors
                ),
                .init(
                    label: "Öffentliches Netz", color: EnergyPalette.consumptionGrid,
                    stack: "Bilanz", values: gridValues, colors: gridColors
                ),
            ]
        )
        return VStack(alignment: .leading, spacing: 8) {
            D3ChartView(payload: payload)
                .frame(height: 260)
                .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 18))
                .overlay {
                    RoundedRectangle(cornerRadius: 18)
                        .stroke(Color(.separator).opacity(0.18), lineWidth: 1)
                }
                .shadow(color: Color.black.opacity(0.04), radius: 5, y: 2)
            HStack {
                if displayUnit == .money {
                    Label("Kosten und Erlöse sind Schätzwerte", systemImage: "eurosign.circle")
                        .font(EEGTypography.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Menu {
                    Text("Verbrauch: EEG-Eigendeckung und verbleibender Restnetzbezug.")
                    Text("Einspeisung: Lieferung an die EEG und verbleibende Netzeinspeisung.")
                    Text("Es werden keine nicht messbaren Haus-PV-Flüsse angenommen.")
                } label: {
                    Label("Berechnung", systemImage: "info.circle")
                        .font(EEGTypography.caption)
                }
            }
        }
    }

    private func load() async {
        do {
            async let dashboardRequest = auth.authorized(DashboardResponse.self, path: "dashboard")
            async let statusRequest = auth.authorized(DataStatusResponse.self, path: "data-status")
            let response = try await dashboardRequest
            let status = try? await statusRequest
            let priceResponse = try? await auth.authorized(
                EnergyPricesResponse.self, path: "prices"
            )
            data = response
            dataStatus = status?.dataStatus
            prices = priceResponse
            if let availableUntil = status?.dataStatus.availableUntil,
               let exclusiveEnd = DateText.parsedDate(availableUntil),
               let availableDate = Calendar.current.date(byAdding: .second, value: -1, to: exclusiveEnd) {
                latestAvailableDate = availableDate
                if !didSelectAvailableOverviewDate {
                    overviewDate = availableDate
                    didSelectAvailableOverviewDate = true
                }
                await loadSummary()
            }
            errorMessage = nil
            showingCachedData = false
            if let encoded = try? JSONEncoder().encode(response) {
                try? SensitiveCache.write(encoded, filename: "dashboard.json")
            }
        } catch {
            if data == nil { errorMessage = error.localizedDescription }
        }
    }

    private func loadSummary() async {
        var range = overviewPeriod.range(containing: overviewDate)
        if range.to > latestAvailableDate { range.to = latestAvailableDate }
        let path = "energy/summary?from=\(DateText.apiDate(range.from))&to=\(DateText.apiDate(range.to))"
        do {
            historicalSummary = try await auth.authorized(
                HistoricalEnergySummary.self, path: path
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private var cacheURL: URL {
        (try? SensitiveCache.url(for: "dashboard.json"))
            ?? URL.cachesDirectory.appending(path: "unavailable-dashboard-cache")
    }

    private func loadCached() {
        guard data == nil,
              let cached = try? Data(contentsOf: cacheURL),
              let decoded = try? JSONDecoder().decode(DashboardResponse.self, from: cached)
        else { return }
        data = decoded
        showingCachedData = true
    }
}

private enum OverviewPeriod: String, CaseIterable, Identifiable {
    case day = "Tag"
    case month = "Monat"
    case year = "Jahr"

    var id: Self { self }
    var title: String {
        switch self {
        case .day: "Tagesübersicht"
        case .month: "Monatsübersicht"
        case .year: "Jahresübersicht"
        }
    }

    private var calendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = Locale(identifier: "de_AT")
        calendar.timeZone = TimeZone(identifier: "Europe/Vienna") ?? .current
        return calendar
    }

    private var component: Calendar.Component {
        switch self {
        case .day: .day
        case .month: .month
        case .year: .year
        }
    }

    func range(containing value: Date) -> (from: Date, to: Date) {
        let day = calendar.startOfDay(for: value)
        switch self {
        case .day:
            return (day, day)
        case .month, .year:
            let interval = calendar.dateInterval(of: component, for: day)
            let start = interval?.start ?? day
            let exclusiveEnd = interval?.end ?? day
            let inclusiveEnd = calendar.date(byAdding: .day, value: -1, to: exclusiveEnd) ?? day
            return (start, inclusiveEnd)
        }
    }

    func shift(_ value: Date, by amount: Int) -> Date {
        calendar.date(byAdding: component, value: amount, to: value) ?? value
    }

    func navigationTitle(for value: Date) -> String {
        switch self {
        case .day:
            return value.formatted(.dateTime.day().month().year().locale(Locale(identifier: "de_AT")))
        case .month:
            return value.formatted(.dateTime.month(.wide).year().locale(Locale(identifier: "de_AT")))
        case .year:
            return value.formatted(.dateTime.year().locale(Locale(identifier: "de_AT")))
        }
    }
}

private enum EnergyDisplayUnit: String, CaseIterable, Identifiable {
    case energy = "kWh"
    case money = "€"
    var id: Self { self }
}

private struct UnifiedDatePicker: View {
    @Binding var selection: Date
    var maximumDate: Date = .distantFuture

    var body: some View {
        ZStack {
            Image(systemName: "calendar")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(EEGTheme.accent)
                .frame(width: 36, height: 36)
                .background(EEGTheme.accent.opacity(0.10), in: RoundedRectangle(cornerRadius: 9))
            DatePicker(
                "Datum", selection: $selection,
                in: Date.distantPast...maximumDate,
                displayedComponents: .date
            )
            .labelsHidden()
            .datePickerStyle(.compact)
            .opacity(0.02)
            .frame(width: 36, height: 36)
            .clipped()
        }
        .frame(width: 36, height: 36)
        .accessibilityLabel("Datum auswählen")
        .accessibilityHint("Öffnet den Kalender")
    }
}

private struct PeriodNavigationRow: View {
    let title: String
    @Binding var selection: Date
    let maximumDate: Date
    let canMoveForward: Bool
    let moveBackward: () -> Void
    let moveForward: () -> Void

    var body: some View {
        HStack(spacing: 6) {
            navigationButton(
                symbol: "chevron.left",
                label: "Vorheriger Zeitraum",
                action: moveBackward
            )
            Text(title)
                .font(EEGTypography.control)
                .lineLimit(1)
                .minimumScaleFactor(0.74)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
                .accessibilityAddTraits(.isHeader)
            navigationButton(
                symbol: "chevron.right",
                label: "Nächster Zeitraum",
                action: moveForward
            )
            .disabled(!canMoveForward)
            UnifiedDatePicker(selection: $selection, maximumDate: maximumDate)
        }
    }

    private func navigationButton(
        symbol: String,
        label: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 14, weight: .semibold))
                .frame(width: 36, height: 36)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(label)
    }
}

struct EnergyDataStatusLine: View {
    let status: HistoricalDataStatus

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "clock")
            Text(dataStatusText)
            Spacer(minLength: 4)
            if status.activeImportWarningCount > 0 {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(EEGTheme.warning)
                    .accessibilityLabel("\(status.activeImportWarningCount) Hinweise zur Datenqualität")
            }
        }
        .font(EEGTypography.caption)
        .foregroundStyle(.secondary)
        .padding(.horizontal, 3)
        .accessibilityElement(children: .combine)
    }

    private var dataStatusText: String {
        guard let until = status.availableUntil else {
            return "Noch kein Energiedatenstand verfügbar"
        }
        guard let exclusiveEnd = DateText.parsedDate(until),
              let inclusiveEnd = Calendar.current.date(byAdding: .second, value: -1, to: exclusiveEnd)
        else { return "Energiedaten bis zum \(DateText.date(until))" }
        let date = inclusiveEnd.formatted(
            .dateTime.day().month().year().locale(Locale(identifier: "de_AT"))
        )
        return "Energiedaten bis zum \(date)"
    }
}

struct EnergyView: View {
    @EnvironmentObject private var auth: AuthManager
    @State private var dataStatus: HistoricalDataStatus?
    @State private var summary: HistoricalEnergySummary?
    @State private var series: [HistoricalEnergyPoint] = []
    @State private var points: [MeteringPoint] = []
    @State private var selectedPoint = ""
    @State private var period: HistoricalPeriod = .day
    @State private var selectedDate = Date()
    @State private var didSelectAvailableDate = false
    @State private var errorMessage: String?
    @State private var balanceMode: EnergyBalanceMode = .consumption
    @State private var displayUnit: EnergyDisplayUnit = .energy
    @State private var prices: EnergyPricesResponse?
    @State private var detailsExpanded = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 11) {
                if let dataStatus { EnergyDataStatusLine(status: dataStatus) }
                periodControls
                if let summary {
                    historicalSummary(summary)
                } else if errorMessage == nil {
                    ProgressView("Energiedaten werden geladen …")
                        .frame(maxWidth: .infinity).padding(.top, 30)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            if let errorMessage {
                ContentUnavailableView(
                    "Energiedaten nicht verfügbar", systemImage: "chart.xyaxis.line",
                    description: Text(errorMessage)
                )
            }
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Energie")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await loadContext() }
        .task { await loadContext() }
        .onChange(of: period) { _, _ in Task { await loadSummary() } }
        .onChange(of: selectedDate) { _, _ in Task { await loadSummary() } }
        .onChange(of: selectedPoint) { _, newValue in
            if let point = points.first(where: { $0.id == newValue }) {
                balanceMode = point.direction == "GENERATION" ? .generation : .consumption
            }
            Task { await loadSummary() }
        }
    }

    private var periodControls: some View {
        VStack(alignment: .leading, spacing: 9) {
            Picker("Zeitraum", selection: $period) {
                ForEach(HistoricalPeriod.allCases) { item in
                    Text(item.rawValue).tag(item)
                }
            }
            .pickerStyle(.segmented)

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) {
                    energyPeriodNavigation
                        .frame(minWidth: 205)
                    energyUnitPicker
                }
                VStack(spacing: 8) {
                    energyPeriodNavigation
                    HStack {
                        Spacer()
                        energyUnitPicker
                    }
                }
            }
            .font(EEGTypography.control)

            if points.count > 1 {
                Menu {
                    Picker("Zählpunkt", selection: $selectedPoint) {
                        Text("Alle Zählpunkte").tag("")
                        ForEach(points) { point in
                            Text("\(point.direction == "GENERATION" ? "Erzeugung" : "Verbrauch") · \(point.maskedId)")
                                .tag(point.id)
                        }
                    }
                } label: {
                    Label("Zählpunkt auswählen", systemImage: "gauge.with.dots.needle.50percent")
                        .font(EEGTypography.control)
                }
            }
        }
        .padding(11)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 13))
    }

    private var energyPeriodNavigation: some View {
        PeriodNavigationRow(
            title: period.compactNavigationTitle(for: selectedDate),
            selection: $selectedDate,
            maximumDate: latestEnergyDate,
            canMoveForward: canMoveForward,
            moveBackward: { shiftPeriod(-1) },
            moveForward: { shiftPeriod(1) }
        )
    }

    private var energyUnitPicker: some View {
        Picker("Einheit", selection: $displayUnit) {
            ForEach(EnergyDisplayUnit.allCases) { Text($0.rawValue).tag($0) }
        }
        .pickerStyle(.segmented)
        .frame(width: 90)
    }

    private var canMoveForward: Bool {
        guard let availableUntil = dataStatus?.availableUntil,
              let exclusiveEnd = DateText.parsedDate(availableUntil) else { return false }
        let next = period.shift(selectedDate, by: 1)
        return period.range(containing: next).from < exclusiveEnd
    }

    private var latestEnergyDate: Date {
        guard let availableUntil = dataStatus?.availableUntil,
              let exclusiveEnd = DateText.parsedDate(availableUntil) else { return Date() }
        return Calendar.current.date(byAdding: .second, value: -1, to: exclusiveEnd) ?? exclusiveEnd
    }

    private func shiftPeriod(_ amount: Int) {
        selectedDate = period.shift(selectedDate, by: amount)
    }

    private func historicalSummary(_ summary: HistoricalEnergySummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 9) {
                HStack {
                    Text("Energiebilanz").font(EEGTypography.sectionTitle)
                    Spacer()
                    Text(period.compactNavigationTitle(for: selectedDate))
                        .font(EEGTypography.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.82)
                }
                Picker("Bilanz", selection: $balanceMode) {
                    ForEach(EnergyBalanceMode.allCases) { mode in
                        Label(mode.rawValue, systemImage: mode.symbol).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                D3ChartView(payload: balanceDonutPayload(summary))
                    .frame(height: 260)
                    .accessibilityLabel("Interaktive Aufteilung der Energiebilanz")
                energyAndEuroValues(summary)
                if displayUnit == .money {
                    Label("Euro-Werte sind Tarifschätzungen", systemImage: "info.circle")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(11)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 18))
            .overlay {
                RoundedRectangle(cornerRadius: 18)
                    .stroke(Color(.separator).opacity(0.18), lineWidth: 1)
            }
            .shadow(color: Color.black.opacity(0.04), radius: 5, y: 2)
            if !series.isEmpty { historicalChart }
            DisclosureGroup("Weitere Werte", isExpanded: $detailsExpanded) {
                VStack(alignment: .leading, spacing: 8) {
                    LabeledContent("An die EEG geliefert", value: summary.derived.communityFeedKwh?.kwh() ?? "–")
                    LabeledContent("Verbleibende Einspeisung", value: summary.totals.publicFeedKwh.kwh())
                    if let percentage = summary.derived.selfSufficiencyPercent {
                        LabeledContent("Eigenversorgungsgrad", value: "\(percentage.formatted(.number.precision(.fractionLength(1)))) %")
                    }
                    Text(summary.notice).foregroundStyle(.secondary)
                    ForEach(summary.dataQualityErrors, id: \.self) {
                        Label($0, systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(EEGTheme.warning)
                    }
                }
                .font(.caption)
                .padding(.top, 8)
            }
            .font(.subheadline.weight(.semibold))
            .padding(11)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 13))
        }
    }

    private func balanceDonutPayload(_ summary: HistoricalEnergySummary) -> D3ChartPayload {
        let balance = balanceMode == .consumption
            ? summary.balance.consumption
            : summary.balance.generation
        let values = displayedBalanceValues(balance)
        let eegColor = balanceMode == .consumption
            ? EnergyPalette.consumptionEEG : EnergyPalette.generationEEG
        let gridColor = balanceMode == .consumption
            ? EnergyPalette.consumptionGrid : EnergyPalette.generationGrid
        return D3ChartPayload(
            kind: "donuts",
            unit: displayUnit.rawValue,
            categories: [
                .init(
                    label: balanceMode == .consumption ? "Mein Verbrauch" : "Meine Einspeisung",
                    detail: balanceMode == .consumption
                        ? "Aufteilung des gemessenen Verbrauchs"
                        : "Aufteilung der berücksichtigten Erzeugung",
                    estimated: false
                )
            ],
            series: [
                .init(
                    label: balanceMode == .consumption ? "Aus der EEG" : "An die EEG",
                    color: eegColor, stack: "Bilanz", values: [values.eeg]
                ),
                .init(
                    label: balanceMode == .consumption ? "Aus dem Netz" : "Ins Netz",
                    color: gridColor, stack: "Bilanz", values: [values.grid]
                ),
            ]
        )
    }

    private func energyAndEuroValues(_ summary: HistoricalEnergySummary) -> some View {
        let balance = balanceMode == .consumption
            ? summary.balance.consumption
            : summary.balance.generation
        let euros = estimatedEuroValues(balance, mode: balanceMode)
        let eegTitle = balanceMode == .consumption ? "Aus der EEG" : "An die EEG"
        let gridTitle = balanceMode == .consumption ? "Aus dem Netz" : "Ins Netz"
        let eegColor = balanceMode == .consumption
            ? EnergyPalette.consumptionEEGColor : EnergyPalette.generationEEGColor
        let gridColor = balanceMode == .consumption
            ? EnergyPalette.consumptionGridColor : EnergyPalette.generationGridColor
        return HStack(spacing: 8) {
            energyMoneyTile(
                title: eegTitle, energy: balance.eegKwh,
                money: euros.eeg, color: eegColor
            )
            energyMoneyTile(
                title: gridTitle, energy: balance.gridKwh,
                money: euros.grid, color: gridColor
            )
        }
    }

    private func energyMoneyTile(
        title: String, energy: Double?, money: Double?, color: Color
    ) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 5) {
                Circle().fill(color).frame(width: 7, height: 7)
                Text(title)
                    .font(EEGTypography.eyebrow)
                    .lineLimit(1).minimumScaleFactor(0.8)
            }
            Text(energy?.kwh(1) ?? "–")
                .font(.system(size: 16, weight: .semibold))
                .monospacedDigit()
            Text(money.map {
                $0.formatted(.number.precision(.fractionLength(2))) + " €"
            } ?? "–")
                .font(EEGTypography.caption.weight(.medium))
                .monospacedDigit().foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(color.opacity(0.09), in: RoundedRectangle(cornerRadius: 11))
        .accessibilityElement(children: .combine)
    }

    private func estimatedEuroValues(
        _ balance: EnergyBalanceSplit, mode: EnergyBalanceMode
    ) -> (eeg: Double?, grid: Double?) {
        guard let prices else { return (nil, nil) }
        if mode == .consumption {
            let eeg: Double? = if let kwh = balance.eegKwh,
                                  let rate = prices.current?.eegConsumptionCt {
                kwh * rate / 100
            } else { nil }
            return (
                eeg,
                balance.gridKwh.map { $0 * prices.reference.gridConsumptionCt / 100 }
            )
        }
        let eeg: Double? = if let kwh = balance.eegKwh,
                              let rate = prices.current?.eegGenerationCt {
            kwh * rate / 100
        } else { nil }
        return (
            eeg,
            balance.gridKwh.map { $0 * prices.reference.publicFeedCt / 100 }
        )
    }

    private func displayedBalanceValues(
        _ balance: EnergyBalanceSplit
    ) -> (eeg: Double?, grid: Double?) {
        guard displayUnit == .money else { return (balance.eegKwh, balance.gridKwh) }
        return estimatedEuroValues(balance, mode: balanceMode)
    }

    private var energyChartUnit: String { displayUnit.rawValue }

    private var historicalChart: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(period == .day ? "Tagesverlauf" : "Verlauf")
                    .font(EEGTypography.sectionTitle)
                Spacer()
                Text(energyChartUnit).font(EEGTypography.caption).foregroundStyle(.secondary)
            }
            D3ChartView(payload: historicalChartPayload)
                .frame(height: 300)
                .accessibilityLabel("D3-Energieverlauf in \(energyChartUnit)")
            if series.contains(where: \.containsEstimatedValues) {
                Label("Enthält Ersatzwerte (L2/L3)", systemImage: "info.circle")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(11)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 13))
    }

    private var historicalChartPayload: D3ChartPayload {
        let categories = series.map { point in
            D3ChartPayload.Category(
                label: period.axisLabel(point.date, fallback: point.bucket),
                detail: DateText.chartLabel(point.bucket),
                estimated: point.containsEstimatedValues
            )
        }
        let chartSeries: [D3ChartPayload.Series]
        if balanceMode == .consumption {
            chartSeries = [
                .init(
                    label: "EEG-Bezug", color: EnergyPalette.consumptionEEG, stack: "Verbrauch",
                    values: series.map { displayedBalanceValues($0.balance.consumption).eeg }
                ),
                .init(
                    label: "Restnetzbezug", color: EnergyPalette.consumptionGrid, stack: "Verbrauch",
                    values: series.map { displayedBalanceValues($0.balance.consumption).grid }
                ),
            ]
        } else {
            chartSeries = [
                .init(
                    label: "An die EEG", color: EnergyPalette.generationEEG, stack: "Einspeisung",
                    values: series.map { displayedBalanceValues($0.balance.generation).eeg }
                ),
                .init(
                    label: "Ins öffentliche Netz", color: EnergyPalette.generationGrid, stack: "Einspeisung",
                    values: series.map { displayedBalanceValues($0.balance.generation).grid }
                ),
            ]
        }
        return D3ChartPayload(
            kind: "bars", unit: energyChartUnit,
            categories: categories, series: chartSeries
        )
    }

    private func loadContext() async {
        do {
            async let statusRequest = auth.authorized(DataStatusResponse.self, path: "data-status")
            async let pointsRequest = auth.authorized(MeteringPointsResponse.self, path: "metering-points")
            async let pricesRequest = try? auth.authorized(EnergyPricesResponse.self, path: "prices")
            let statusResponse = try await statusRequest
            let pointsResponse = try await pointsRequest
            let priceResponse = await pricesRequest
            let status = statusResponse.dataStatus
            let loadedPoints = pointsResponse.meteringPoints
            dataStatus = status
            points = loadedPoints
            prices = priceResponse
            if selectedPoint.isEmpty,
               !loadedPoints.contains(where: { $0.direction == "CONSUMPTION" }),
               loadedPoints.contains(where: { $0.direction == "GENERATION" }) {
                balanceMode = .generation
            }
            if !didSelectAvailableDate,
               let availableUntil = status.availableUntil,
               let date = DateText.parsedDate(availableUntil) {
                selectedDate = Calendar.current.date(byAdding: .second, value: -1, to: date) ?? date
                didSelectAvailableDate = true
            }
            await loadSummary()
            errorMessage = nil
        } catch { errorMessage = error.localizedDescription }
    }

    private func loadSummary() async {
        let range = period.range(containing: selectedDate)
        let pointQuery = selectedPoint.isEmpty ? "" : "&metering_point=\(selectedPoint)"
        let from = DateText.apiDate(range.from)
        let to = DateText.apiDate(range.to)
        let path = "energy/summary?from=\(from)&to=\(to)\(pointQuery)"
        let seriesPath = "energy/series?from=\(from)&to=\(to)&resolution=\(period.resolution)\(pointQuery)"
        do {
            async let summaryRequest = auth.authorized(HistoricalEnergySummary.self, path: path)
            async let seriesRequest = auth.authorized(HistoricalEnergySeriesResponse.self, path: seriesPath)
            summary = try await summaryRequest
            let seriesResponse = try await seriesRequest
            series = seriesResponse.series
            errorMessage = nil
        } catch {
            summary = nil
            series = []
            errorMessage = error.localizedDescription
        }
    }
}

private enum HistoricalPeriod: String, CaseIterable, Identifiable {
    case day = "Tag"
    case week = "Woche"
    case month = "Monat"
    case year = "Jahr"

    var id: Self { self }

    var resolution: String {
        switch self {
        case .day: "hour"
        case .week, .month: "day"
        case .year: "month"
        }
    }

    private var calendar: Calendar {
        var value = Calendar(identifier: .iso8601)
        value.locale = Locale(identifier: "de_AT")
        value.timeZone = TimeZone(identifier: "Europe/Vienna") ?? .current
        return value
    }

    private var component: Calendar.Component {
        switch self {
        case .day: .day
        case .week: .weekOfYear
        case .month: .month
        case .year: .year
        }
    }

    func range(containing value: Date) -> (from: Date, to: Date) {
        let interval = calendar.dateInterval(of: component, for: value)
        let start = interval?.start ?? value
        let exclusiveEnd = interval?.end ?? value
        let inclusiveEnd = calendar.date(byAdding: .day, value: -1, to: exclusiveEnd) ?? value
        return (start, inclusiveEnd)
    }

    func shift(_ value: Date, by amount: Int) -> Date {
        calendar.date(byAdding: component, value: amount, to: value) ?? value
    }

    func navigationTitle(for value: Date) -> String {
        let range = range(containing: value)
        switch self {
        case .day:
            return value.formatted(.dateTime.weekday(.wide).day().month(.wide).year().locale(Locale(identifier: "de_AT")))
        case .week:
            let week = calendar.component(.weekOfYear, from: value)
            return "KW \(week) · \(DateText.period(DateText.apiDate(range.from), DateText.apiDate(range.to)))"
        case .month:
            return value.formatted(.dateTime.month(.wide).year().locale(Locale(identifier: "de_AT")))
        case .year:
            return value.formatted(.dateTime.year().locale(Locale(identifier: "de_AT")))
        }
    }

    func compactNavigationTitle(for value: Date) -> String {
        switch self {
        case .day:
            return value.formatted(.dateTime.day().month().year().locale(Locale(identifier: "de_AT")))
        case .week:
            return "KW \(calendar.component(.weekOfYear, from: value))"
        case .month:
            return value.formatted(.dateTime.month(.wide).year().locale(Locale(identifier: "de_AT")))
        case .year:
            return value.formatted(.dateTime.year().locale(Locale(identifier: "de_AT")))
        }
    }

    func axisLabel(_ value: Date?, fallback: String) -> String {
        guard let value else { return fallback }
        let locale = Locale(identifier: "de_AT")
        switch self {
        case .day:
            return value.formatted(.dateTime.hour().minute().locale(locale))
        case .week, .month:
            return value.formatted(.dateTime.day().month().locale(locale))
        case .year:
            return value.formatted(.dateTime.month(.abbreviated).locale(locale))
        }
    }
}

private enum EnergyBalanceMode: String, CaseIterable, Identifiable {
    case consumption = "Verbrauch"
    case generation = "Einspeisung"

    var id: Self { self }
    var symbol: String { self == .consumption ? "bolt.fill" : "sun.max.fill" }
}

private enum EnergyPalette {
    static let consumptionEEG = "#2EA65C"
    static let consumptionGrid = "#F06B29"
    static let generationEEG = "#2878D0"
    static let generationGrid = "#F2AD14"
    static let consumptionEEGColor = Color(red: 46 / 255, green: 166 / 255, blue: 92 / 255)
    static let consumptionGridColor = Color(red: 240 / 255, green: 107 / 255, blue: 41 / 255)
    static let generationEEGColor = Color(red: 40 / 255, green: 120 / 255, blue: 208 / 255)
    static let generationGridColor = Color(red: 242 / 255, green: 173 / 255, blue: 20 / 255)
}
