package com.prettylisavpn.android.data

import java.time.Instant
import java.time.temporal.ChronoUnit
import kotlinx.coroutines.delay

object SourceFactory {
    fun create(): ScreenSource = FixtureSource()
}

/** In-memory, deterministic and debug-only. Never creates VPN/auth/payment/support side effects. */
class FixtureSource(private val latencyMs: Long = 450) : ScreenSource {
    override val enabled = true
    private var snapshot = standard()
    override val initial get() = snapshot
    private var offline = false
    private var slow = false
    private var failNext = false
    private var delayPayments = false
    private var requestedEmail: String? = null
    private var pending: Command.Payment? = null
    private val payments = mutableSetOf<String>()
    private val receipts = mutableMapOf<String, Command.Support>()
    var mutationCount = 0
        private set

    private suspend fun respond() {
        val shouldFail = failNext
        failNext = false
        delay(if (slow) 2_000 else latencyMs)
        if (offline) throw SourceFailure("Test source is offline. No network request was made.")
        if (shouldFail) {
            throw SourceFailure("Simulated request failure. Retry is safe; nothing was changed.")
        }
    }
    override suspend fun read(area: Area): Snapshot { respond(); return snapshot }
    override suspend fun execute(command: Command): Snapshot {
        respond()
        if (command !is Command.RequestOtp && command !is Command.VerifyOtp && !snapshot.signedIn) {
            throw SourceFailure("Sign in to the test account first.")
        }
        when (command) {
            is Command.RequestOtp -> {
                if (!EMAIL.matches(command.email)) throw SourceFailure("Enter a valid email.")
                requestedEmail = command.email.trim().lowercase()
            }
            is Command.VerifyOtp -> {
                if (requestedEmail == null) throw SourceFailure("Request a new test code.")
                if (command.code == "000000") throw SourceFailure("Test code expired. Request a new code.")
                if (command.code != "123456") throw SourceFailure("Incorrect test code. Use 123456.")
                snapshot = snapshot.copy(signedIn = true, email = requestedEmail!!, messages = standard().messages)
                requestedEmail = null
            }
            Command.Logout -> {
                snapshot = standard().copy(signedIn = false, email = "", messages = emptyList())
                requestedEmail = null
                pending = null
                receipts.clear()
                payments.clear()
            }
            is Command.SelectCountry -> {
                if (snapshot.simulatedConnection) throw SourceFailure("Stop the simulation before changing country.")
                if (command.code != "AUTO") {
                    if (snapshot.plan == "Free") throw SourceFailure("Country selection requires Premium or Platinum.")
                    if (snapshot.countries.none { it.code == command.code && it.available }) throw SourceFailure("Country is unavailable.")
                }
                snapshot = snapshot.copy(selectedCountry = command.code)
            }
            Command.ToggleConnection -> {
                if (snapshot.stale) throw SourceFailure("Refresh stale test data before starting the simulation.")
                snapshot = snapshot.copy(simulatedConnection = !snapshot.simulatedConnection)
            }
            is Command.Revoke -> {
                val device = snapshot.devices.find { it.id == command.id } ?: throw SourceFailure("Device no longer exists.")
                snapshot = snapshot.copy(devices = snapshot.devices.map { if (it.id == device.id) it.copy(active = false) else it })
                if (device.current) snapshot = snapshot.copy(signedIn = false, email = "", simulatedConnection = false, messages = emptyList())
            }
            is Command.Acknowledge -> snapshot = snapshot.copy(messages = snapshot.messages.filterNot { it.id == command.id && it.revision == command.revision })
            is Command.Payment -> {
                if (command.id !in payments) {
                    if (pending != null) throw SourceFailure("Resolve the pending test operation first.")
                    if (command.kind !in setOf("SUBSCRIBE", "RENEW", "CHANGE_METHOD", "CANCEL")) throw SourceFailure("Unsupported test operation.")
                    if (command.kind in setOf("SUBSCRIBE", "RENEW", "CHANGE_METHOD")) {
                        val route = snapshot.routes.find { it.id == command.route && command.currency in it.currencies }
                            ?: throw SourceFailure("This test route does not support the selected currency.")
                        if (command.kind == "CHANGE_METHOD" && command.currency !in route.recurring) throw SourceFailure("This route does not support auto-renewal.")
                    }
                    if (delayPayments) { pending = command; snapshot = snapshot.copy(paymentPending = true) } else applyPayment(command)
                }
            }
            Command.ConfirmPayment -> {
                pending?.let { applyPayment(it) }
                pending = null
                snapshot = snapshot.copy(paymentPending = false)
            }
            is Command.Support -> {
                if (command.subject.isBlank() || command.subject.length > 120 || command.description.isBlank() || command.description.length > 4000 || !EMAIL.matches(command.email) || command.attachments !in 0..3) throw SourceFailure("Complete all support fields correctly.")
                val previous = receipts[command.id]
                if (previous != null && previous != command) throw SourceFailure("This test request ID already belongs to another draft.")
                receipts[command.id] = command
                snapshot = snapshot.copy(supportReceipt = command.id, supportDelivered = false)
            }
            Command.SupportStatus -> snapshot = snapshot.copy(supportDelivered = snapshot.supportReceipt != null)
        }
        mutationCount++
        return snapshot
    }
    private fun applyPayment(command: Command.Payment) {
        if (!payments.add(command.id)) return
        when (command.kind) {
            "CANCEL" -> snapshot = snapshot.copy(autoRenew = false)
            "CHANGE_METHOD" -> snapshot = snapshot.copy(paymentMethod = "Test method · ${command.route}", autoRenew = true)
            else -> {
                val now = Instant.parse("2026-10-20T00:00:00Z")
                val until = snapshot.paidUntil?.let(Instant::parse)?.takeIf { it > now } ?: now
                val recurring = snapshot.routes.find { it.id == command.route }?.recurring?.contains(command.currency) == true
                snapshot = snapshot.copy(plan = "Premium", paidUntil = until.plus(30, ChronoUnit.DAYS).toString(), autoRenew = recurring, paymentMethod = "Test method · ${command.route}")
            }
        }
    }
    override fun configure(scenario: Scenario) {
        if (scenario == Scenario.FAIL_NEXT) { failNext = true; return }
        offline = scenario == Scenario.OFFLINE
        slow = scenario == Scenario.SLOW
        delayPayments = scenario == Scenario.PAYMENT_PENDING
        failNext = false
        pending = null
        payments.clear()
        receipts.clear()
        val session = snapshot.signedIn
        val email = snapshot.email
        snapshot = standard().copy(signedIn = session, email = email)
        snapshot = when (scenario) {
            Scenario.FREE -> snapshot.copy(plan = "Free", paidUntil = null, autoRenew = false, paymentMethod = null)
            Scenario.EXPIRED -> snapshot.copy(plan = "Free", paidUntil = "2026-10-01T00:00:00Z", autoRenew = false, paymentMethod = null)
            Scenario.PLATINUM -> snapshot.copy(plan = "Platinum", autoRenew = false, paymentMethod = null)
            Scenario.EMPTY -> snapshot.copy(devices = emptyList(), countries = emptyList(), messages = emptyList())
            Scenario.DEVICE_LIMIT -> snapshot.copy(devices = snapshot.devices + (3..5).map { device(it, false) })
            Scenario.STALE -> snapshot.copy(stale = true)
            Scenario.PAYMENT_PENDING -> snapshot
            else -> snapshot
        }
    }
    companion object {
        private val EMAIL = Regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")
        private fun device(index: Int, current: Boolean) = Device(
            "00000000-0000-4000-8000-${index.toString().padStart(12, '0')}",
            if (current) "Android test phone" else "Test device $index", current,
            "2026-10-01 10:00 UTC", if (index == 2) null else "2026-10-20 09:00 UTC",
        )
        private fun standard() = Snapshot(
            signedIn = true, email = "demo@example.invalid", plan = "Premium", paidUntil = "2026-11-20T00:00:00Z",
            autoRenew = true, paymentMethod = "Test method · BANK_CARD",
            devices = listOf(device(1, true), device(2, false)),
            countries = listOf(Country("DE", "Germany", "Good", true), Country("NL", "Netherlands", "Excellent", true), Country("US", "United States", "Fair", true), Country("JP", "Japan", "Unavailable", false)),
            routes = listOf(PaymentRoute("MIR", "Mir card", setOf("RUB"), setOf("RUB")), PaymentRoute("BANK_CARD", "Bank card", setOf("RUB", "USD"), setOf("RUB", "USD")), PaymentRoute("ALIPAY_WECHAT", "Alipay / WeChat Pay", setOf("USD"), emptySet()), PaymentRoute("CRYPTO", "Cryptocurrency", setOf("RUB", "USD"), emptySet())),
            messages = listOf(AccountMessage("test-welcome", 1, "Welcome to PrettyLisaVPN", "This is an isolated test account. No email, payment or VPN service is contacted.", "SUBSCRIPTION"), AccountMessage("test-update", 2, "Android screen preview", "Review settings and support using test data.", "ABOUT")),
        )
    }
}
