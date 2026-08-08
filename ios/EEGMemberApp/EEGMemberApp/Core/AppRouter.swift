import Foundation

enum AppTab: Hashable { case overview, energy, prices, account }

enum DocumentRoute: Hashable {
    case invoice(Int)
    case invoicePDF(Int)
    case contractPDF(Int, String)
}

@MainActor
final class AppRouter: ObservableObject {
    @Published var selectedTab: AppTab = .overview
    @Published var documentPath: [DocumentRoute] = []

    func openInvoice(_ id: Int) {
        selectedTab = .account
        documentPath = [.invoice(id)]
    }

    func handleNotification(_ payload: [AnyHashable: Any]) {
        switch payload["route"] as? String {
        case "invoice":
            if let id = payload["invoice_id"] as? Int { openInvoice(id) }
            else if let text = payload["invoice_id"] as? String, let id = Int(text) { openInvoice(id) }
        case "message": selectedTab = .overview
        default: break
        }
    }
}
