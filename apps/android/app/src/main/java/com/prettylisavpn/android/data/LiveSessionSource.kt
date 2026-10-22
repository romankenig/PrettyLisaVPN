package com.prettylisavpn.android.data

import android.content.Context
import android.os.Build
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.auth.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.util.UUID

/** Serializes cached projections and journals alongside the existing session coordinator. */
class LiveSessionSource(
    private val sessions: SessionCoordinator,
    private val accounts: AccountApi? = null,
    private val journalStore: JournalStore = MemoryJournal(),
    private val uploads: suspend (List<String>) -> List<SupportUpload> = { emptyList() },
) : ScreenSource {
    private val transfer = kotlinx.coroutines.flow.MutableStateFlow(SupportTransfer())
    override val supportTransfer: kotlinx.coroutines.flow.Flow<SupportTransfer> = transfer
    override val recoveryRequired get() = sessions.needsRecovery
    override val enabled = true
    override val fixture = false
    private val mutex = Mutex()
    private var journalReady = accounts == null
    private var requestedEmail: String? = null
    private var owner = ""
    private var snapshot = Snapshot()
    private var journal = AccountJournal("")
    override val initial: Snapshot get() {
        val p = sessions.profile ?: return Snapshot().also { snapshot = it; owner = "" }
        if (owner != p.id && p.id.isNotEmpty()) { snapshot = Snapshot(); owner = p.id }
        return snapshot.copy(operationsReady = journalReady, signedIn = true, email = p.email, plan = p.plan, activeDeviceCount = p.activeDevices)
    }
    private fun api() = accounts ?: throw SourceFailure("This feature is not connected yet.")
    private suspend fun disk(block: () -> Unit) {
        try { withContext(Dispatchers.IO) { block() } } catch (e: CancellationException) { throw e } catch (_: Exception) { throw SourceFailure("Unable to save the operation securely. Retry before starting another operation.") }
    }
    private suspend fun save(value: AccountJournal) { disk { journalStore.write(value) }; journal = value }
    private suspend fun restoreJournal() {
        if (accounts == null) return
        journalReady = false
        val id = sessions.profile?.id ?: return
        var stored: AccountJournal? = null; disk { stored = journalStore.read() }
        if (stored != null && stored!!.owner != id) disk { journalStore.clear() }
        journal = stored?.takeIf { it.owner == id } ?: AccountJournal(id)
        journalReady = true
        projectJournal()
    }
    private fun projectJournal() {
        snapshot = snapshot.copy(supportReceipt = journal.supportReceipt?.id ?: journal.support?.requestId,
            supportStatus = journal.supportReceipt?.status, supportDelivered = journal.supportReceipt?.status == "SENT",
            supportFrozen = journal.support != null || journal.supportReceipt != null, supportAwaiting = journal.support != null && journal.supportReceipt == null,
            billingRetryAvailable = journal.billing != null && journal.operation == null, billingOperation = journal.operation, paymentPending = journal.billing != null || journal.operation?.status == "PENDING")
    }
    override suspend fun read(area: Area): Snapshot = mutex.withLock {
        if (area == Area.SESSION) { sessions.restore(); snapshot = initial; restoreJournal() }
        else when (area) {
            Area.HOME -> { sessions.refreshProfile(); snapshot = initial }
            Area.DEVICES -> snapshot = initial.copy(devices = sessions.request { api().devices(it) })
            Area.COUNTRIES -> {
                val options = sessions.request { api().locations(it) }
                snapshot = initial.copy(countries = options.countries, autopilotQuality = options.autopilotQuality)
            }
            Area.MESSAGES -> snapshot = initial.copy(messages = sessions.request { api().messages(it) })
            Area.BILLING -> { if (!journalReady) restoreJournal(); refreshBilling() }
            Area.SUPPORT -> { if (!journalReady) restoreJournal(); recoverSupport(false) }
            else -> throw SourceFailure("This feature is not connected yet.")
        }
        initial
    }
    private suspend fun refreshBilling() {
        var overview = sessions.request { api().overview(it) }
        val operation = journal.operation?.takeIf { it.status == "PENDING" }?.id ?: overview.pendingId
        if (operation != null) {
            val receipt = sessions.request { api().operation(it, operation) }
            save(journal.copy(operation = receipt, billing = if (receipt.status == "PENDING") journal.billing else null))
            if (receipt.status != "PENDING") { overview = sessions.request { api().overview(it) }; sessions.refreshProfile() }
        }
        snapshot = initial.copy(stale = false, refreshWarning = null, billing = overview, paidUntil = overview.paidUntil, autoRenew = overview.autoRenew, paymentMethod = overview.method, routes = overview.routes)
        projectJournal()
    }
    private suspend fun refreshAfterAction(block: suspend () -> Unit) {
        try { block(); snapshot = initial.copy(refreshWarning = null, stale = false) } catch (e: CancellationException) { throw e } catch (e: AuthFailure) {
            if (sessions.profile == null) throw e
            snapshot = initial.copy(refreshWarning = "The action completed, but fresh data is unavailable. Refresh to try again.", stale = true)
        }
    }
    override suspend fun execute(command: Command): Snapshot = mutex.withLock {
        if (command is Command.Payment || command is Command.Support || command == Command.NewSupport || command == Command.SupportStatus || command == Command.ConfirmPayment) {
            if (!journalReady) restoreJournal()
            if (!journalReady) throw SourceFailure("Saved operations are unavailable. Restore secure storage before starting a new request.")
        }
        when (command) {
            is Command.RequestOtp -> { sessions.requestOtp(command.email); requestedEmail = command.email }
            is Command.VerifyOtp -> { sessions.login(requestedEmail ?: throw AuthFailure("reauth_required"), command.code); snapshot = initial; restoreJournal() }
            Command.Logout, Command.ForgetLocalSession -> {
                if (command == Command.Logout) sessions.logout() else sessions.forgetLocalSession()
                requestedEmail = null; snapshot = Snapshot(); owner = ""; journal = AccountJournal("")
                disk { journalStore.clear() }
            }
            is Command.Revoke -> {
                UUID.fromString(command.id)
                val result = sessions.request { api().revoke(it, command.id) }
                if (result.current) {
                    sessions.forgetLocalSession(); snapshot = Snapshot(); disk { journalStore.clear() }
                } else {
                    snapshot = initial.copy(devices = snapshot.devices.map { if (it.id == result.id) result else it })
                    refreshAfterAction { sessions.refreshProfile(); snapshot = initial.copy(devices = sessions.request { api().devices(it) }) }
                }
            }
            is Command.Acknowledge -> {
                val message = snapshot.messages.find { it.id == command.id && it.revision == command.revision } ?: throw SourceFailure("This message changed. Refresh messages before confirming.")
                sessions.request { api().acknowledge(it, message.id, message.revision) }
                snapshot = initial.copy(messages = snapshot.messages.filterNot { it.id == message.id && it.revision == message.revision })
                refreshAfterAction { snapshot = initial.copy(messages = sessions.request { api().messages(it) }) }
            }
            is Command.Payment -> pay(command)
            Command.ConfirmPayment -> { refreshBilling(); sessions.refreshProfile(); snapshot = initial }
            is Command.Support -> {
                UUID.fromString(command.id)
                if (journal.support == null) {
                    if (journal.supportReceipt != null) throw SourceFailure("Choose New request before composing another support request.")
                    require(command.subject.isNotBlank() && command.subject.length <= 120 && command.description.isNotBlank() && command.description.length <= 4000)
                    transfer.value = SupportTransfer("PREPARING")
                    val files = try { uploads(command.uris) } finally { transfer.value = SupportTransfer() }
                    require(files.size <= 3 && files.sumOf { it.bytes().size } <= 10*1024*1024 && files.all { it.bytes().size <= 5*1024*1024 })
                    save(journal.copy(support = SupportSubmission(command.id, command.subject, command.description, command.email, files), supportReceipt = null))
                    projectJournal()
                }
                recoverSupport(true)
            }
            Command.SupportStatus -> recoverSupport(false)
            Command.NewSupport -> {
                if (journal.support != null && journal.supportReceipt?.status !in setOf("SENT", "FAILED", "EXPIRED")) throw SourceFailure("Resolve the previous request before starting another one.")
                save(journal.copy(support = null, supportReceipt = null)); projectJournal()
            }
            else -> throw SourceFailure("This feature is not connected yet.")
        }
        initial
    }
    private suspend fun recoverSupport(allowSubmit: Boolean) {
        val pending = journal.support
        val id = pending?.requestId ?: journal.supportReceipt?.id ?: return
        val receipt = sessions.request { api().supportStatus(it, id) }
            ?: if (allowSubmit && pending != null) try { sessions.request { api().supportSubmit(it, pending) { sent, total -> transfer.value = SupportTransfer("UPLOADING", if (total > 0) (sent.toFloat() / total).coerceIn(0f, 1f) else 0f) } } } catch (e: AuthFailure) {
                if (e.code in setOf("INVALID_REQUEST", "ATTACHMENT_REJECTED")) { save(journal.copy(support = null, supportReceipt = null)); projectJournal() }
                throw e
            } finally { transfer.value = SupportTransfer() } else null
        if (receipt != null) save(journal.copy(supportReceipt = receipt, support = if (receipt.status in setOf("SENT", "FAILED", "EXPIRED")) null else pending))
        projectJournal()
    }
    private suspend fun startIntent(intent: BillingIntent): OperationReceipt = try { sessions.request { api().start(it, intent) } } catch (e: AuthFailure) {
        if (e.code in setOf("BILLING_REVISION_CHANGED", "BILLING_ACTION_UNAVAILABLE", "BILLING_ROUTE_UNAVAILABLE", "BILLING_OFFER_UNAVAILABLE", "BILLING_CURRENCY_LOCKED", "BILLING_DISABLED")) {
            save(journal.copy(billing = null, operation = null)); projectJournal(); snapshot = initial.copy(stale = true)
        }
        throw e
    }
    private suspend fun pay(command: Command.Payment) {
        // Refresh capabilities immediately before every new POST. A failed refresh never grants access.
        val acceptedRevision = command.expectedRevision ?: snapshot.billing?.revision
        val fresh = sessions.request { api().overview(it) }; snapshot = initial.copy(billing = fresh)
        if (fresh.mode != "LIVE" || !fresh.available || fresh.routes.map { it.id }.toSet() != routeIds) throw SourceFailure("Payments are unavailable for this provider.")
        val old = journal.billing
        if (old != null) {
            val known = journal.operation
            if (known != null) { refreshBilling(); return }
            val receipt = startIntent(old)
            save(journal.copy(operation = receipt, billing = if (receipt.status == "PENDING") old else null))
        } else {
            if (acceptedRevision != fresh.revision) throw SourceFailure("The price or subscription changed. Review the refreshed details before confirming again.")
            if (!fresh.permits(command.kind)) throw SourceFailure("This payment action is unavailable. Refresh subscription details.")
            val purchase = command.kind in setOf("SUBSCRIBE", "RENEW")
            val offer = if (purchase) fresh.offers.singleOrNull() ?: throw SourceFailure("A unique offer is unavailable.") else null
            if (command.currency !in setOf("RUB", "USD")) throw SourceFailure("This currency is unavailable.")
            if (purchase && fresh.routes.none { it.id == command.route && command.currency in it.currencies }) throw SourceFailure("This payment route is unavailable for the selected currency.")
            val intent = BillingIntent(command.id, command.kind, fresh.revision, offer?.id, if (purchase) command.route else null, command.currency)
            UUID.fromString(intent.request_id); save(journal.copy(billing = intent, operation = null)); projectJournal()
            val receipt = startIntent(intent)
            save(journal.copy(operation = receipt, billing = if (receipt.status == "PENDING") intent else null))
        }
        projectJournal()
        refreshAfterAction { refreshBilling(); sessions.refreshProfile(); snapshot = initial }
    }
    override fun configure(scenario: Scenario) = Unit
}

object LiveSessionFactory {
    private var source: LiveSessionSource? = null
    @Synchronized fun create(context: Context): ScreenSource = source ?: run {
        val app = context.applicationContext
        val http = HttpAuthApi("https://api.prettylisavpn.com/")
        LiveSessionSource(SessionCoordinator(http, KeystoreVault(app), "${Build.MANUFACTURER} ${Build.MODEL}".trim().take(255)),
            HttpAccountApi(http, BuildConfig.VERSION_NAME), EncryptedJournal(app), { uris -> readSupportImages(app, uris) })
    }.also { source = it }
}
