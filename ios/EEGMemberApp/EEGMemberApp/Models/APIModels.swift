import Foundation

struct LoginRequest: Encodable {
    let username: String
    let password: String
    let deviceId: String
    let deviceName: String
}
struct RefreshRequest: Encodable { let refreshToken: String }
struct MobileLinkRequest: Encodable { let email: String }
struct MobileLinkRequestResponse: Decodable { let accepted: Bool; let message: String }
struct MobileLinkRedeemRequest: Encodable {
    let code: String?
    let linkToken: String?
    let deviceId: String
    let deviceName: String
}

protocol AuthTokens {
    var accessToken: String { get }
    var refreshToken: String { get }
}

struct TokenResponse: Decodable, AuthTokens {
    let accessToken: String
    let refreshToken: String
    let expiresIn: Int
}

struct EmptyResponse: Decodable { }
struct DeviceRegistration: Encodable {
    let deviceToken: String
    let environment: String
    let appVersion: String?
}
struct DeviceRegistrationResponse: Decodable { let registered: Bool }
struct UpdateResponse: Decodable { let updated: Bool }
struct MemberFeedbackResponse: Decodable {
    let id: Int
    let received: Bool
    let attachmentCount: Int
    let emailRecipientCount: Int
}
struct NotificationPreferences: Codable {
    var notificationsEnabled: Bool
    var soundEnabled: Bool
    var invoiceNotifications: Bool
    var communityNotifications: Bool
}
struct NotificationPreferencesResponse: Decodable { let preferences: NotificationPreferences }

struct LoginResponse: Decodable, AuthTokens {
    struct User: Decodable { let id: Int; let username: String; let memberId: Int; let memberName: String }
    let accessToken: String
    let refreshToken: String
    let expiresIn: Int
    let user: User
}

struct Member: Codable, Identifiable {
    let id: Int
    var name: String
    var email: String?
    var phone: String?
    var addressStreet: String?
    var addressZip: String?
    var addressCity: String?
    var accountHolder: String?
    var iban: String?
    var bic: String?
    let bezugZp: String?
    let einspeiserZp: String?
    let teilnahme: Double?
    var newsletterOptout: Int?
    let active: Bool?
}

struct OrganizationInfo: Decodable {
    let name: String
    let address: String
    let legal: String
    let zvr: String
}

struct MeResponse: Decodable {
    let member: Member
    let organization: OrganizationInfo?
}

struct DataStatusResponse: Decodable { let dataStatus: HistoricalDataStatus }

struct HistoricalDataStatus: Codable {
    let isLive: Bool
    let label: String
    let availableFrom: String?
    let availableUntil: String?
    let lastImportedAt: String?
    let importDataStatus: String?
    let importStatus: String?
    let memberMeteringPointCount: Int
    let importedMeteringPointCount: Int
    let measurementCount: Int
    let estimatedMeasurementCount: Int
    let activeImportWarningCount: Int
    let notice: String
}

struct MeteringPointsResponse: Decodable { let meteringPoints: [MeteringPoint] }

struct MeteringPoint: Decodable, Identifiable {
    let id: String
    let maskedId: String
    let direction: String
    let role: String
    let validFrom: String?
    let validTo: String?
}

struct EnergyBalanceSplit: Decodable, Equatable {
    let totalKwh: Double
    let eegKwh: Double?
    let gridKwh: Double?
    let eegPercent: Double?
}

struct HistoricalEnergySummary: Decodable {
    struct Totals: Decodable {
        let consumptionKwh: Double
        let selfCoverageKwh: Double
        let generationKwh: Double
        let participationGenerationKwh: Double
        let publicFeedKwh: Double
    }
    struct Derived: Decodable {
        let residualGridKwh: Double?
        let communityFeedKwh: Double?
        let selfSufficiencyPercent: Double?
    }
    struct Balance: Decodable {
        let consumption: EnergyBalanceSplit
        let generation: EnergyBalanceSplit
    }
    let from: String
    let to: String
    let isLive: Bool
    let notice: String
    let totals: Totals
    let derived: Derived
    let balance: Balance
    let quality: [String: Int]
    let dataQualityErrors: [String]
}

struct HistoricalEnergySeriesResponse: Decodable {
    let from: String
    let to: String
    let resolution: String
    let isLive: Bool
    let unit: String
    let series: [HistoricalEnergyPoint]
}

struct EnergyPricesResponse: Decodable {
    let current: EnergyPrice?
    let history: [EnergyPrice]
    let reference: EnergyReferencePrices
}

struct EnergyPrice: Decodable, Identifiable {
    let id: Int
    let validFrom: String
    let validTo: String
    let eegConsumptionCt: Double
    let eegGenerationCt: Double
    let description: String?
}

struct EnergyReferencePrices: Decodable {
    let gridConsumptionCt: Double
    let publicFeedCt: Double
    let isEstimate: Bool
}

struct HistoricalEnergyPoint: Decodable, Identifiable {
    var id: String { bucket }
    let bucket: String
    let consumptionKwh: Double
    let selfCoverageKwh: Double
    let generationKwh: Double
    let participationGenerationKwh: Double
    let publicFeedKwh: Double
    let residualGridKwh: Double?
    let communityFeedKwh: Double?
    let selfSufficiencyPercent: Double?
    let balance: HistoricalEnergySummary.Balance
    let containsEstimatedValues: Bool
    let dataQualityErrors: [String]

    var date: Date? { DateText.chartDate(bucket) }
}

struct ProfileUpdate: Encodable {
    let email: String
    let phone: String
    let addressStreet: String
    let addressZip: String
    let addressCity: String
    let accountHolder: String
    let iban: String
    let bic: String
    let newsletterOptout: Bool
}

struct EnergyStats: Codable {
    struct Month: Codable, Identifiable {
        var id: String { monthKey }
        let monthKey: String
        let label: String
        let consumption: Double
        let generation: Double
        let netEur: Double
    }
    let totalConsumptionKwh: Double
    let totalGenerationKwh: Double
    let co2SavedKg: Double
    let selfSufficiencyPct: Double
    let monthlyData: [Month]
    let netTotal: Double?
    let invoiceId: Int?
}

struct AccountSummary: Codable {
    let balance: Double
    let openClaims: Double
    let openCredits: Double
    let overdueClaims: Double
    let history: [AccountEvent]
}

struct AccountEvent: Codable, Identifiable {
    var id: String { "\(kind)-\(invoiceId)-\(date)-\(amount)" }
    let date: String
    let kind: String
    let label: String
    let invoiceId: Int
    let amount: Double
    let status: String
}

struct Invoice: Codable, Identifiable {
    let id: Int
    let periodFrom: String
    let periodTo: String
    let status: String
    let dataStatus: String?
    let createdAt: String
    let totalCons: Double
    let totalGen: Double
    let totalKwh: Double
    let netTotal: Double
    let paid: Bool
    let bookingDate: String

    var isPreliminary: Bool {
        dataStatus?.lowercased() != "final"
            || !["finalized", "sent"].contains(status.lowercased())
    }
}

struct DashboardResponse: Codable {
    let member: Member
    let account: AccountSummary
    let stats: EnergyStats?
    let recentInvoices: [Invoice]
    let unreadMessages: [AppMessage]
}

struct AppMessage: Codable, Identifiable {
    let id: Int
    let title: String
    let body: String
    let level: String
    let createdAt: String
    let expiresAt: String?
}

struct MessagesResponse: Decodable { let messages: [AppMessage] }

struct InvoicesResponse: Decodable { let invoices: [Invoice] }

struct InvoiceDetailResponse: Decodable {
    let invoice: InvoiceHeader
    let items: [InvoiceItem]
}

struct InvoiceHeader: Decodable, Identifiable {
    let id: Int
    let periodFrom: String
    let periodTo: String
    let status: String
    let dataStatus: String?
    let createdAt: String

    var isPreliminary: Bool {
        dataStatus?.lowercased() != "final"
            || !["finalized", "sent"].contains(status.lowercased())
    }
}

struct InvoiceItem: Decodable, Identifiable {
    let id: Int
    let type: String
    let kwh: Double
    let pricePerKwh: Double
    let amountEur: Double
    let paid: Int?
    let paidAt: String?
}

struct AccountResponse: Decodable { let account: AccountSummary }

struct Contract: Decodable, Identifiable {
    let id: Int
    let type: String
    let filename: String
    let uploadedAt: String
    let uploadedBy: String?
}
struct ContractsResponse: Decodable { let contracts: [Contract] }
