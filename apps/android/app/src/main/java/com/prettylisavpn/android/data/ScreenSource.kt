package com.prettylisavpn.android.data

/** UI boundary. Credentials stay inside the auth coordinator, never in a Snapshot. */
enum class Area { SESSION, HOME, COUNTRIES, LOCATION, DEVICES, BILLING, MESSAGES, SUPPORT }
enum class Scenario { STANDARD, SLOW, FREE, EXPIRED, PLATINUM, EMPTY, DEVICE_LIMIT, STALE, OFFLINE, FAIL_NEXT, PAYMENT_PENDING }
data class Device(val id: String, val name: String, val current: Boolean, val added: String, val lastLogin: String?, val active: Boolean = true)
data class Country(val code: String, val name: String, val quality: String, val available: Boolean)
data class PaymentRoute(val id: String, val label: String, val currencies: Set<String>, val recurring: Set<String>)
data class AccountMessage(val id: String, val revision: Int, val title: String, val body: String, val destination: String?, val actionLabel: String? = null, val dismissLabel: String = "understood")
data class Snapshot(
    val operationsReady: Boolean = true,
    val billing: BillingOverview? = null,
    val billingRetryAvailable: Boolean = false,
    val billingOperation: OperationReceipt? = null,
    val supportStatus: String? = null,
    val supportFrozen: Boolean = false,
    val supportAwaiting: Boolean = false,
    val refreshWarning: String? = null,
    val activeDeviceCount: Int = 0,
    val signedIn: Boolean = false,
    val email: String = "",
    val plan: String = "Free",
    val paidUntil: String? = null,
    val autoRenew: Boolean = false,
    val paymentMethod: String? = null,
    val selectedCountry: String = "AUTO",
    val simulatedConnection: Boolean = false,
    val devices: List<Device> = emptyList(),
    val countries: List<Country> = emptyList(),
    val routes: List<PaymentRoute> = emptyList(),
    val messages: List<AccountMessage> = emptyList(),
    val stale: Boolean = false,
    val paymentPending: Boolean = false,
    val supportReceipt: String? = null,
    val supportDelivered: Boolean = false,
)
sealed interface Command {
    data class RequestOtp(val email: String) : Command
    data class VerifyOtp(val code: String) : Command
    data object Logout : Command
    data object ForgetLocalSession : Command
    data class SelectCountry(val code: String) : Command
    data object ToggleConnection : Command
    data class Revoke(val id: String) : Command
    data class Acknowledge(val id: String, val revision: Int) : Command
    data class Payment(val id: String, val kind: String, val route: String, val currency: String, val expectedRevision: String? = null) : Command
    data object ConfirmPayment : Command
    data class Support(val id: String, val subject: String, val description: String, val email: String, val attachments: Int, val uris: List<String> = emptyList()) : Command
    data object SupportStatus : Command
    data object NewSupport : Command
}
class SourceFailure(message: String) : Exception(message)
data class SupportTransfer(val phase: String = "IDLE", val fraction: Float = 0f)
interface ScreenSource {
    val supportTransfer: kotlinx.coroutines.flow.Flow<SupportTransfer> get() = kotlinx.coroutines.flow.flowOf(SupportTransfer())
    val recoveryRequired: Boolean get() = false
    val fixture: Boolean get() = true
    val enabled: Boolean
    val initial: Snapshot
    suspend fun read(area: Area): Snapshot
    suspend fun execute(command: Command): Snapshot
    fun configure(scenario: Scenario)
}
