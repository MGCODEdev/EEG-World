package at.eeg.trabocherstrasse.member.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable data class LoginRequest(
    val username: String, val password: String,
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_name") val deviceName: String,
)
@Serializable data class RefreshRequest(@SerialName("refresh_token") val refreshToken: String)
@Serializable data class LinkRequest(val email: String)
@Serializable data class LinkResponse(val accepted: Boolean, val message: String)
@Serializable data class LinkRedeemRequest(
    val code: String? = null,
    @SerialName("link_token") val linkToken: String? = null,
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_name") val deviceName: String,
)
@Serializable data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("expires_in") val expiresIn: Int,
)
@Serializable data class LoginResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("expires_in") val expiresIn: Int,
    val user: LoginUser,
)
@Serializable data class LoginUser(
    val id: Int, val username: String,
    @SerialName("member_id") val memberId: Int,
    @SerialName("member_name") val memberName: String,
)

@Serializable data class Member(
    val id: Int,
    val name: String,
    val email: String? = null,
    val phone: String? = null,
    @SerialName("address_street") val addressStreet: String? = null,
    @SerialName("address_zip") val addressZip: String? = null,
    @SerialName("address_city") val addressCity: String? = null,
    @SerialName("account_holder") val accountHolder: String? = null,
    val iban: String? = null,
    val bic: String? = null,
    @SerialName("bezug_zp") val consumptionMeter: String? = null,
    @SerialName("einspeiser_zp") val generationMeter: String? = null,
    val teilnahme: Double? = null,
    @SerialName("newsletter_optout") val newsletterOptOut: Int? = null,
    val active: Boolean? = true,
)
@Serializable data class OrganizationInfo(val name: String, val address: String, val legal: String, val zvr: String)
@Serializable data class MeResponse(val member: Member, val organization: OrganizationInfo? = null)
@Serializable data class MemberResponse(val member: Member)
@Serializable data class ProfileUpdate(
    val email: String,
    val phone: String,
    @SerialName("address_street") val addressStreet: String,
    @SerialName("address_zip") val addressZip: String,
    @SerialName("address_city") val addressCity: String,
    @SerialName("account_holder") val accountHolder: String,
    val iban: String,
    val bic: String,
    @SerialName("newsletter_optout") val newsletterOptOut: Boolean,
)

@Serializable data class HistoricalDataStatus(
    @SerialName("is_live") val isLive: Boolean = false,
    val label: String = "",
    @SerialName("available_from") val availableFrom: String? = null,
    @SerialName("available_until") val availableUntil: String? = null,
    @SerialName("last_imported_at") val lastImportedAt: String? = null,
    @SerialName("member_metering_point_count") val memberMeteringPointCount: Int = 0,
    @SerialName("imported_metering_point_count") val importedMeteringPointCount: Int = 0,
    @SerialName("measurement_count") val measurementCount: Int = 0,
    @SerialName("estimated_measurement_count") val estimatedMeasurementCount: Int = 0,
    @SerialName("active_import_warning_count") val activeImportWarningCount: Int = 0,
    val notice: String = "",
)
@Serializable data class DataStatusResponse(@SerialName("data_status") val dataStatus: HistoricalDataStatus)
@Serializable data class MeteringPoint(
    val id: String, @SerialName("masked_id") val maskedId: String,
    val direction: String, val role: String,
    @SerialName("valid_from") val validFrom: String? = null,
    @SerialName("valid_to") val validTo: String? = null,
)
@Serializable data class MeteringPointsResponse(@SerialName("metering_points") val meteringPoints: List<MeteringPoint>)

@Serializable data class EnergyBalanceSplit(
    @SerialName("total_kwh") val totalKwh: Double = 0.0,
    @SerialName("eeg_kwh") val eegKwh: Double? = null,
    @SerialName("grid_kwh") val gridKwh: Double? = null,
    @SerialName("eeg_percent") val eegPercent: Double? = null,
)
@Serializable data class EnergyTotals(
    @SerialName("consumption_kwh") val consumptionKwh: Double = 0.0,
    @SerialName("self_coverage_kwh") val selfCoverageKwh: Double = 0.0,
    @SerialName("generation_kwh") val generationKwh: Double = 0.0,
    @SerialName("participation_generation_kwh") val participationGenerationKwh: Double = 0.0,
    @SerialName("public_feed_kwh") val publicFeedKwh: Double = 0.0,
)
@Serializable data class EnergyDerived(
    @SerialName("residual_grid_kwh") val residualGridKwh: Double? = null,
    @SerialName("community_feed_kwh") val communityFeedKwh: Double? = null,
    @SerialName("self_sufficiency_percent") val selfSufficiencyPercent: Double? = null,
)
@Serializable data class EnergyBalance(val consumption: EnergyBalanceSplit, val generation: EnergyBalanceSplit)
@Serializable data class HistoricalEnergySummary(
    val from: String, val to: String,
    @SerialName("is_live") val isLive: Boolean = false,
    val notice: String = "",
    val totals: EnergyTotals,
    val derived: EnergyDerived,
    val balance: EnergyBalance,
    val quality: Map<String, Int> = emptyMap(),
    @SerialName("data_quality_errors") val dataQualityErrors: List<String> = emptyList(),
)
@Serializable data class HistoricalEnergyPoint(
    val bucket: String,
    @SerialName("consumption_kwh") val consumptionKwh: Double = 0.0,
    @SerialName("self_coverage_kwh") val selfCoverageKwh: Double = 0.0,
    @SerialName("generation_kwh") val generationKwh: Double = 0.0,
    @SerialName("participation_generation_kwh") val participationGenerationKwh: Double = 0.0,
    @SerialName("public_feed_kwh") val publicFeedKwh: Double = 0.0,
    @SerialName("residual_grid_kwh") val residualGridKwh: Double? = null,
    @SerialName("community_feed_kwh") val communityFeedKwh: Double? = null,
    @SerialName("self_sufficiency_percent") val selfSufficiencyPercent: Double? = null,
    val balance: EnergyBalance,
    @SerialName("contains_estimated_values") val containsEstimatedValues: Boolean = false,
    @SerialName("data_quality_errors") val dataQualityErrors: List<String> = emptyList(),
)
@Serializable data class HistoricalSeriesResponse(
    val from: String, val to: String, val resolution: String,
    @SerialName("is_live") val isLive: Boolean = false,
    val unit: String, val series: List<HistoricalEnergyPoint>,
)

@Serializable data class EnergyPrice(
    val id: Int,
    @SerialName("valid_from") val validFrom: String,
    @SerialName("valid_to") val validTo: String,
    @SerialName("eeg_consumption_ct") val eegConsumptionCt: Double,
    @SerialName("eeg_generation_ct") val eegGenerationCt: Double,
    val description: String? = null,
)
@Serializable data class EnergyReferencePrices(
    @SerialName("grid_consumption_ct") val gridConsumptionCt: Double,
    @SerialName("public_feed_ct") val publicFeedCt: Double,
    @SerialName("is_estimate") val isEstimate: Boolean,
)
@Serializable data class EnergyPricesResponse(
    val current: EnergyPrice? = null,
    val history: List<EnergyPrice> = emptyList(),
    val reference: EnergyReferencePrices,
)

@Serializable data class AccountEvent(
    val date: String, val kind: String, val label: String,
    @SerialName("invoice_id") val invoiceId: Int,
    val amount: Double, val status: String,
)
@Serializable data class AccountSummary(
    val balance: Double = 0.0,
    @SerialName("open_claims") val openClaims: Double = 0.0,
    @SerialName("open_credits") val openCredits: Double = 0.0,
    @SerialName("overdue_claims") val overdueClaims: Double = 0.0,
    val history: List<AccountEvent> = emptyList(),
)
@Serializable data class AccountResponse(val account: AccountSummary)
@Serializable data class Invoice(
    val id: Int,
    @SerialName("period_from") val periodFrom: String,
    @SerialName("period_to") val periodTo: String,
    val status: String,
    @SerialName("data_status") val dataStatus: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("total_cons") val totalCons: Double = 0.0,
    @SerialName("total_gen") val totalGen: Double = 0.0,
    @SerialName("total_kwh") val totalKwh: Double = 0.0,
    @SerialName("net_total") val netTotal: Double = 0.0,
    val paid: Boolean = false,
    @SerialName("booking_date") val bookingDate: String = "",
) {
    val isPreliminary: Boolean get() = dataStatus?.lowercase() != "final" || status.lowercase() !in setOf("finalized", "sent")
}
@Serializable data class InvoicesResponse(val invoices: List<Invoice>)
@Serializable data class InvoiceHeader(
    val id: Int, @SerialName("period_from") val periodFrom: String,
    @SerialName("period_to") val periodTo: String, val status: String,
    @SerialName("data_status") val dataStatus: String? = null,
    @SerialName("created_at") val createdAt: String,
)
@Serializable data class InvoiceItem(
    val id: Int, val type: String, val kwh: Double,
    @SerialName("price_per_kwh") val pricePerKwh: Double,
    @SerialName("amount_eur") val amountEur: Double,
    val paid: Int? = null, @SerialName("paid_at") val paidAt: String? = null,
)
@Serializable data class InvoiceDetailResponse(val invoice: InvoiceHeader, val items: List<InvoiceItem>)
@Serializable data class Contract(
    val id: Int, val type: String, val filename: String,
    @SerialName("uploaded_at") val uploadedAt: String,
    @SerialName("uploaded_by") val uploadedBy: String? = null,
)
@Serializable data class ContractsResponse(val contracts: List<Contract>)
@Serializable data class AppMessage(
    val id: Int, val title: String, val body: String,
    val level: String, @SerialName("created_at") val createdAt: String,
    @SerialName("expires_at") val expiresAt: String? = null,
)
@Serializable data class EnergyMonth(
    @SerialName("month_key") val monthKey: String, val label: String,
    val consumption: Double, val generation: Double,
    @SerialName("net_eur") val netEur: Double,
)
@Serializable data class EnergyStats(
    @SerialName("total_consumption_kwh") val totalConsumptionKwh: Double,
    @SerialName("total_generation_kwh") val totalGenerationKwh: Double,
    @SerialName("co2_saved_kg") val co2SavedKg: Double,
    @SerialName("self_sufficiency_pct") val selfSufficiencyPct: Double,
    @SerialName("monthly_data") val monthlyData: List<EnergyMonth>,
)
@Serializable data class DashboardResponse(
    val member: Member, val account: AccountSummary,
    val stats: EnergyStats? = null,
    @SerialName("recent_invoices") val recentInvoices: List<Invoice> = emptyList(),
    @SerialName("unread_messages") val unreadMessages: List<AppMessage> = emptyList(),
)
@Serializable data class NotificationPreferences(
    @SerialName("notifications_enabled") val notificationsEnabled: Boolean = true,
    @SerialName("sound_enabled") val soundEnabled: Boolean = true,
    @SerialName("invoice_notifications") val invoiceNotifications: Boolean = true,
    @SerialName("community_notifications") val communityNotifications: Boolean = true,
)
@Serializable data class NotificationPreferencesResponse(val preferences: NotificationPreferences)
@Serializable data class UpdateResponse(val updated: Boolean = true)
@Serializable data class DeviceRegistration(
    @SerialName("device_token") val deviceToken: String,
    val platform: String = "android",
    val environment: String = "production",
    @SerialName("app_version") val appVersion: String? = null,
)
@Serializable data class DeviceRegistrationResponse(val registered: Boolean)
@Serializable data class MemberFeedbackResponse(
    val id: Int, val received: Boolean,
    @SerialName("attachment_count") val attachmentCount: Int,
    @SerialName("email_recipient_count") val emailRecipientCount: Int,
)
@Serializable data class ApiErrorEnvelope(val error: ApiErrorDetail)
@Serializable data class ApiErrorDetail(val code: String, val message: String)

data class UploadAttachment(val filename: String, val mimeType: String, val bytes: ByteArray)
