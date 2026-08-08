import PDFKit
import SwiftUI

struct InvoiceListView: View {
    @EnvironmentObject private var auth: AuthManager
    @State private var invoices: [Invoice] = []
    @State private var errorMessage: String?

    var body: some View {
        List {
            ForEach(invoices.sorted { $0.periodFrom > $1.periodFrom }) { invoice in
                NavigationLink(value: invoice.id) { InvoiceRow(invoice: invoice) }
            }
        }
        .overlay { if invoices.isEmpty && errorMessage == nil { ContentUnavailableView("Keine Abrechnungen", systemImage: "doc.text") } }
        .navigationTitle("Abrechnungen")
        .navigationDestination(for: Int.self) { InvoiceDetailView(invoiceID: $0) }
        .refreshable { await load() }
        .task { await load() }
        .alert("Fehler", isPresented: Binding(
            get: { errorMessage != nil },
            set: { if !$0 { errorMessage = nil } }
        )) {
            Button("OK") { errorMessage = nil }
        } message: { Text(errorMessage ?? "") }
    }

    private func load() async {
        do { invoices = try await auth.authorized(InvoicesResponse.self, path: "invoices").invoices }
        catch { errorMessage = error.localizedDescription }
    }
}

struct InvoiceDetailView: View {
    @EnvironmentObject private var auth: AuthManager
    let invoiceID: Int
    @State private var detail: InvoiceDetailResponse?
    @State private var errorMessage: String?
    @State private var showPreliminaryWarning = false

    var body: some View {
        List {
            if let detail {
                if detail.invoice.isPreliminary {
                    Section {
                        Label {
                            Text("Vorläufig – Beträge können sich noch ändern")
                                .font(.subheadline.weight(.semibold))
                        } icon: {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(EEGTheme.warning)
                        }
                    }
                }
                Section("Zeitraum") {
                    LabeledContent("Von", value: detail.invoice.periodFrom)
                    LabeledContent("Bis", value: detail.invoice.periodTo)
                    LabeledContent(
                        "Status",
                        value: detail.invoice.isPreliminary ? "Vorläufig" : "Endgültig"
                    )
                }
                Section("Positionen") {
                    ForEach(detail.items) { item in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Label(
                                    item.type == "consumption" ? "Verbrauch" : "Erzeugung",
                                    systemImage: item.type == "consumption" ? "bolt.fill" : "sun.max.fill"
                                )
                                Spacer()
                                Text(item.amountEur.euro).fontWeight(.semibold)
                            }
                            Text("\(item.kwh.kwh()) · \(item.pricePerKwh.formatted()) ct/kWh")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                Section {
                    NavigationLink {
                        InvoicePDFPreviewView(invoiceID: invoiceID)
                    } label: {
                        Label("PDF-Vorschau öffnen", systemImage: "doc.richtext")
                    }
                }
            } else if errorMessage == nil {
                ProgressView()
            }
        }
        .navigationTitle("Abrechnung")
        .task { await load() }
        .alert("Vorläufige Abrechnung", isPresented: $showPreliminaryWarning) {
            Button("Verstanden", role: .cancel) { }
        } message: {
            Text("Diese Abrechnung ist noch nicht endgültig. Die Beträge können sich noch ändern. Bitte noch keine Überweisung tätigen.")
        }
        .alert("Fehler", isPresented: Binding(
            get: { errorMessage != nil },
            set: { if !$0 { errorMessage = nil } }
        )) {
            Button("OK") { errorMessage = nil }
        } message: { Text(errorMessage ?? "") }
    }

    private func load() async {
        do {
            detail = try await auth.authorized(
                InvoiceDetailResponse.self, path: "invoices/\(invoiceID)"
            )
            showPreliminaryWarning = detail?.invoice.isPreliminary == true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct InvoicePDFPreviewView: View {
    let invoiceID: Int

    var body: some View {
        ProtectedPDFPreviewView(path: "invoices/\(invoiceID)/pdf", title: "Abrechnung")
    }
}

struct ProtectedPDFPreviewView: View {
    @EnvironmentObject private var auth: AuthManager
    let path: String
    let title: String
    @State private var pdfData: Data?
    @State private var shareURL: URL?
    @State private var errorMessage: String?

    var body: some View {
        Group {
            if let pdfData {
                PDFKitView(data: pdfData)
            } else if let errorMessage {
                ContentUnavailableView("PDF nicht verfügbar", systemImage: "doc.badge.xmark", description: Text(errorMessage))
            } else {
                ProgressView("Abrechnung wird geladen …")
            }
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .toolbar {
            if let shareURL {
                ToolbarItem(placement: .topBarTrailing) {
                    ShareLink(item: shareURL) { Label("Teilen", systemImage: "square.and.arrow.up") }
                }
            }
        }
        .onDisappear {
            SensitiveCache.remove(shareURL)
            shareURL = nil
        }
    }

    private func load() async {
        do {
            let data = try await auth.authorizedData(path: path)
            pdfData = data
            let safeName = title.replacingOccurrences(of: "/", with: "-")
                + "-\(UUID().uuidString).pdf"
            shareURL = try SensitiveCache.write(data, filename: safeName)
        }
        catch { errorMessage = error.localizedDescription }
    }
}

struct PDFKitView: UIViewRepresentable {
    let data: Data

    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.displayDirection = .vertical
        return view
    }

    func updateUIView(_ view: PDFView, context: Context) {
        if view.document == nil { view.document = PDFDocument(data: data) }
    }
}

struct InvoiceRow: View {
    let invoice: Invoice
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: invoice.isPreliminary ? "doc.badge.clock" : (invoice.paid ? "checkmark.seal.fill" : "doc.text.fill"))
                .font(.title3)
                .foregroundStyle(invoice.isPreliminary ? EEGTheme.warning : (invoice.paid ? EEGTheme.positive : EEGTheme.accent))
            VStack(alignment: .leading, spacing: 4) {
                Text(DateText.period(invoice.periodFrom, invoice.periodTo))
                    .font(.system(.subheadline, design: .rounded, weight: .semibold))
                HStack(spacing: 6) {
                    Text(invoice.totalKwh.kwh())
                    Text(invoice.isPreliminary ? "VORLÄUFIG" : (invoice.paid ? "BEZAHLT" : "OFFEN"))
                        .font(.caption2.bold())
                        .foregroundStyle(invoice.isPreliminary ? EEGTheme.warning : .secondary)
                }
                .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Text(invoice.netTotal.euro)
                .font(.system(.subheadline, design: .monospaced, weight: .bold))
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }
}
