import SwiftUI

struct ContractsView: View {
    @EnvironmentObject private var auth: AuthManager
    @State private var contracts: [Contract] = []

    var body: some View {
        List(contracts) { contract in
            Label {
                VStack(alignment: .leading) {
                    Text(contract.filename).font(.headline)
                    Text("\(contract.type) · \(contract.uploadedAt)").font(.caption).foregroundStyle(.secondary)
                }
            } icon: { Image(systemName: "doc.richtext.fill").foregroundStyle(EEGTheme.accent) }
        }
        .overlay { if contracts.isEmpty { ContentUnavailableView("Keine Verträge", systemImage: "folder") } }
        .navigationTitle("Verträge")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        contracts = (try? await auth.authorized(ContractsResponse.self, path: "contracts").contracts) ?? []
    }
}
