import SwiftUI

struct MainTabView: View {
    @EnvironmentObject private var router: AppRouter

    var body: some View {
        TabView(selection: $router.selectedTab) {
            NavigationStack { DashboardView() }
                .tabItem { Label("Übersicht", systemImage: "house.fill") }
                .tag(AppTab.overview)
            NavigationStack { EnergyView() }
                .tabItem { Label("Energie", systemImage: "chart.xyaxis.line") }
                .tag(AppTab.energy)
            NavigationStack { EnergyPricesView() }
                .tabItem { Label("Preise", systemImage: "eurosign.arrow.circlepath") }
                .tag(AppTab.prices)
            NavigationStack(path: $router.documentPath) {
                MyAccountView()
                    .navigationDestination(for: DocumentRoute.self) { route in
                        switch route {
                        case .invoice(let id): InvoiceDetailView(invoiceID: id)
                        case .invoicePDF(let id): InvoicePDFPreviewView(invoiceID: id)
                        case .contractPDF(let id, let name):
                            ProtectedPDFPreviewView(path: "contracts/\(id)/pdf", title: name)
                        }
                    }
            }
                .tabItem { Label("Mein Konto", systemImage: "person.crop.circle.fill") }
                .tag(AppTab.account)
        }
    }
}
