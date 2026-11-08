package com.prettylisavpn.android.diagnostics

import com.google.gson.Gson
import com.prettylisavpn.android.vpn.connectionMethods
import java.io.File
import java.time.Instant
import java.time.Duration

enum class DiagnosticKind { APP_START, APP_FOREGROUND, APP_BACKGROUND, APP_ERROR, NETWORK_CHANGE, API_RESULT, VPN_CONNECT, VPN_ATTEMPT, VPN_RESULT, VPN_HEALTH, VPN_DISCONNECT, VPN_RESET, VPN_TRANSPORT_LOST, VPN_SERVICE_LOST, VPN_RECOVER, VPN_STATE, VPN_STAGE }
enum class DiagnosticOutcome { STARTED, SUCCESS, FAILED, CANCELLED, HEALTHY, UNREACHABLE, NO_NETWORK, UNKNOWN, SUSPENDED }
enum class DiagnosticFailure { TIMEOUT, NETWORK, DNS, TLS, PERMISSION, AUTH, STORAGE, CANCELLED, OTHER, METHODS_EXHAUSTED, CLEANUP, ACCESS, UNSTABLE, DEMO_LIMIT }
enum class DiagnosticApiCode { OFFLINE, NETWORK_UNCERTAIN, INVALID_RESPONSE, HTTP_ERROR, SERVICE_UNAVAILABLE, INVALID_ACCESS_TOKEN, INVALID_SESSION, INVALID_REFRESH_TOKEN, REAUTH_REQUIRED, AUTHENTICATION_REQUIRED, DEVICE_REVOKED, DEVICE_LIMIT_REACHED, USER_BLOCKED, OTP_INVALID_OR_EXPIRED, OTP_RATE_LIMITED, STORAGE_UNAVAILABLE, ROTATION_UNCERTAIN, VPN_SESSION_NOT_FOUND, VPN_SESSION_ALREADY_ACTIVE, VPN_UNAVAILABLE, COUNTRY_UNAVAILABLE, FREE_DAILY_LIMIT_REACHED, VPN_ADDRESS_POOL_EXHAUSTED, VPN_SETUP_FAILED, VPN_TERMINATION_UNAVAILABLE, VPN_SESSION_STATUS_UNAVAILABLE, DEMO_UNAVAILABLE, DEMO_RATE_LIMITED, DEMO_QUOTA_EXHAUSTED, REGISTRATION_REQUIRED, SUPPORT_NOT_FOUND, IDEMPOTENCY_CONFLICT, RATE_LIMITED, ATTACHMENT_REJECTED, INVALID_REQUEST, BILLING_DISABLED, BILLING_REVISION_CHANGED, BILLING_ACTION_UNAVAILABLE, BILLING_ROUTE_UNAVAILABLE, BILLING_OFFER_UNAVAILABLE, BILLING_CURRENCY_LOCKED, BILLING_IDEMPOTENCY_CONFLICT, BILLING_OPERATION_IN_PROGRESS, BILLING_OPERATION_NOT_FOUND, DEVICE_NOT_FOUND, MESSAGE_NOT_FOUND, OTHER }
fun diagnosticApiCode(value: String): DiagnosticApiCode = DiagnosticApiCode.entries.find { it.name == value.uppercase(java.util.Locale.ROOT) } ?: DiagnosticApiCode.OTHER
enum class DiagnosticOperation { AUTH, PROFILE, LOCATIONS, VPN, SUPPORT, BILLING, DEVICES, MESSAGES, OTHER }
enum class DiagnosticStage { IDLE, CONSENT, PERMISSION, RECOVERY, ADMISSION, PROVISIONING, LEASE, CONFIG, START, ENGINE, HANDSHAKE, NETWORK, VERIFY, DNS, HTTPS, EGRESS_MISMATCH, VERIFICATION_FAILED, VERIFIED, HEARTBEAT, STOP, CLEANUP, OTHER }
data class NetworkDiagnostic(val transports: List<String>, val internet: Boolean, val validated: Boolean, val captive_portal: Boolean, val metered: Boolean?)
data class DiagnosticFrame(val class_name: String, val method: String, val line: Int)

fun diagnosticFrames(error: Throwable): List<DiagnosticFrame> = generateSequence(error) { it.cause }.take(4)
    .flatMap { it.stackTrace.asSequence() }
    .filter { Regex("com\\.prettylisavpn\\.android\\.[A-Za-z0-9_.$]{1,200}").matches(it.className) && Regex("[A-Za-z0-9_$<>-]{1,100}").matches(it.methodName) }
    .map { DiagnosticFrame(it.className, it.methodName, it.lineNumber.coerceIn(-2,1_000_000)) }.distinct().take(24).toList()

/** No free-form message, URL, exception text, credential or traffic destination field. */
data class DiagnosticEvent(
    val at: String, val elapsed_ms: Long, val event: DiagnosticKind,
    val method: String? = null, val phase: String? = null, val stage: DiagnosticStage? = null,
    val outcome: DiagnosticOutcome? = null, val failure: DiagnosticFailure? = null,
    val operation: DiagnosticOperation? = null, val duration_ms: Long? = null,
    val http_status: Int? = null, val network: NetworkDiagnostic? = null, val country: String? = null,
    val frames: List<DiagnosticFrame>? = null,
    val api_code: DiagnosticApiCode? = null,
) {
    fun checked(): DiagnosticEvent = apply {
        require(Instant.parse(at).toString() == at && elapsed_ms >= 0)
        require(event in DiagnosticKind.entries)
        require(method == null || connectionMethods.any { it.id == method })
        require(phase == null || com.prettylisavpn.android.vpn.VpnPhase.entries.any { it.name == phase })
        require(country == null || Regex("AUTO|[A-Z]{2}").matches(country))
        require(duration_ms == null || duration_ms >= 0)
        require(http_status == null || http_status in 100..599)
        require(network == null || (network.transports.size <= 5 && network.transports.all { it in setOf("WIFI", "CELLULAR", "ETHERNET", "VPN", "OTHER") }))
        require(frames == null || (event == DiagnosticKind.APP_ERROR && frames.size <= 24 && frames.all {
            Regex("com\\.prettylisavpn\\.android\\.[A-Za-z0-9_.$]{1,200}").matches(it.class_name) && Regex("[A-Za-z0-9_$<>-]{1,100}").matches(it.method) && it.line in -2..1_000_000
        }))
    }
}
data class DiagnosticLog(val events: List<DiagnosticEvent>, val omitted_events: Int, val retention_days: Int = 7, val storage_limit_bytes: Int = 2 * 1024 * 1024, val available: Boolean = true, val dropped_events: Int = 0)

/** Private app file, bounded even when the app is offline. Exports newest events only. */
class DiagnosticJournal(private val directory: File, private val now: () -> Instant = Instant::now,
    private val limitBytes: Int = 2 * 1024 * 1024) {
    private val gson = Gson()
    private val file = File(directory, "events.jsonl")
    private var lastPrune = Instant.EPOCH

    @Synchronized fun append(event: DiagnosticEvent) {
        event.checked()
        check(directory.mkdirs() || directory.isDirectory)
        val line = gson.toJson(event) + "\n"
        val bytes = line.toByteArray(Charsets.UTF_8).size
        require(bytes <= minOf(12 * 1024, limitBytes))
        if (file.length() + bytes > limitBytes || Duration.between(lastPrune, now()).seconds >= 3600) prune(minOf(limitBytes / 2, limitBytes - bytes))
        file.appendText(line, Charsets.UTF_8)
    }

    private fun read(): List<DiagnosticEvent> {
        if (!file.exists()) return emptyList()
        if (file.length() > limitBytes + 2048) { clear(); return emptyList() }
        val cutoff = now().minus(Duration.ofDays(7))
        return file.useLines(Charsets.UTF_8) { lines -> lines.mapNotNull { line ->
            runCatching { gson.fromJson(line, DiagnosticEvent::class.java).checked() }.getOrNull()
        }.filter { Instant.parse(it.at) >= cutoff }.toList() }
    }

    private fun prune(targetBytes: Int) {
        val kept = ArrayDeque<String>()
        var size = 0
        for (event in read().asReversed()) {
            val line = gson.toJson(event) + "\n"
            val bytes = line.toByteArray(Charsets.UTF_8).size
            if (size + bytes > targetBytes) break
            kept.addFirst(line); size += bytes
        }
        // Commit a compacted journal only after its replacement is completely written.
        val temporary = File(directory, "events.tmp")
        try {
            temporary.writeText(kept.joinToString(""), Charsets.UTF_8)
            java.nio.file.Files.move(temporary.toPath(), file.toPath(), java.nio.file.StandardCopyOption.REPLACE_EXISTING, java.nio.file.StandardCopyOption.ATOMIC_MOVE)
        } finally { temporary.delete() }
        lastPrune = now()
    }

    @Synchronized fun snapshot(): DiagnosticLog {
        check(directory.mkdirs() || directory.isDirectory)
        prune(limitBytes)
        val all = read()
        val selected = ArrayDeque<DiagnosticEvent>()
        var bytes = 0
        for (event in all.asReversed()) {
            val size = gson.toJson(event).toByteArray(Charsets.UTF_8).size + 1
            if (selected.size >= 400 || bytes + size > 128 * 1024) break
            selected.addFirst(event); bytes += size
        }
        return DiagnosticLog(selected.toList(), all.size - selected.size)
    }

    @Synchronized fun clear() {
        check(!file.exists() || file.delete())
        val temporary = File(directory, "events.tmp")
        check(!temporary.exists() || temporary.delete())
        lastPrune = Instant.EPOCH
    }
}

fun diagnosticFailure(error: Throwable): DiagnosticFailure = when (error) {
    is java.net.SocketTimeoutException, is kotlinx.coroutines.TimeoutCancellationException -> DiagnosticFailure.TIMEOUT
    is kotlinx.coroutines.CancellationException -> DiagnosticFailure.CANCELLED
    is java.net.UnknownHostException -> DiagnosticFailure.DNS
    is javax.net.ssl.SSLException -> DiagnosticFailure.TLS
    is java.io.IOException -> DiagnosticFailure.NETWORK
    is SecurityException -> DiagnosticFailure.PERMISSION
    is com.prettylisavpn.android.auth.AuthFailure -> when (error.code) {
        "storage_unavailable" -> DiagnosticFailure.STORAGE
        "offline", "network_uncertain" -> DiagnosticFailure.NETWORK
        else -> DiagnosticFailure.AUTH
    }
    else -> DiagnosticFailure.OTHER
}

fun diagnosticOperation(path: String): DiagnosticOperation = when (path.substringBefore('/')) {
    "auth" -> DiagnosticOperation.AUTH
    "me" -> DiagnosticOperation.PROFILE
    "vpn", "sessions" -> DiagnosticOperation.VPN
    "locations", "countries", "traffic" -> DiagnosticOperation.LOCATIONS
    "support" -> DiagnosticOperation.SUPPORT
    "billing" -> DiagnosticOperation.BILLING
    "devices" -> DiagnosticOperation.DEVICES
    "messages" -> DiagnosticOperation.MESSAGES
    else -> DiagnosticOperation.OTHER
}
