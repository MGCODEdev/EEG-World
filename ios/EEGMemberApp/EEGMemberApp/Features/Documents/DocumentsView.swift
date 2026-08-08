import SwiftUI

struct DocumentsView: View {
    @EnvironmentObject private var auth: AuthManager
    @State private var invoices: [Invoice] = []
    @State private var contracts: [Contract] = []
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        List {
            if !invoices.isEmpty {
                Section("Abrechnungen") {
                    ForEach(invoices) { invoice in
                        NavigationLink {
                            InvoiceDetailView(invoiceID: invoice.id)
                        } label: {
                            InvoiceRow(invoice: invoice)
                        }
                    }
                }
            }
            if !contracts.isEmpty {
                Section("Verträge") {
                    ForEach(contracts) { contract in
                        NavigationLink {
                            ProtectedPDFPreviewView(
                                path: "contracts/\(contract.id)/pdf",
                                title: contract.filename
                            )
                        } label: {
                            Label {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(contract.filename).font(.headline)
                                    Text("\(contract.type.capitalized) · \(DateText.date(contract.uploadedAt))")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            } icon: {
                                Image(systemName: "doc.richtext.fill").foregroundStyle(EEGTheme.accent)
                            }
                        }
                    }
                }
            }
        }
        .overlay {
            if isLoading { ProgressView() }
            else if invoices.isEmpty && contracts.isEmpty {
                ContentUnavailableView(
                    "Keine Dokumente", systemImage: "folder",
                    description: Text(errorMessage ?? "Sobald Dokumente verfügbar sind, erscheinen sie hier.")
                )
            }
        }
        .navigationTitle("Dokumente")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let invoiceRequest = auth.authorized(InvoicesResponse.self, path: "invoices")
            async let contractRequest = auth.authorized(ContractsResponse.self, path: "contracts")
            let result = try await (invoiceRequest, contractRequest)
            invoices = result.0.invoices
            contracts = result.1.contracts
            errorMessage = nil
        } catch { errorMessage = error.localizedDescription }
    }
}
