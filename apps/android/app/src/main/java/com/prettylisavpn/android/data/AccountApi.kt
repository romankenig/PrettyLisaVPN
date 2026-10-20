package com.prettylisavpn.android.data

import com.google.gson.*
import com.prettylisavpn.android.auth.AuthFailure
import com.prettylisavpn.android.auth.HttpAuthApi
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.time.Instant
import java.util.UUID

val routeIds = setOf("MIR", "BANK_CARD", "ALIPAY_WECHAT", "CRYPTO")
val billingActions = setOf("SUBSCRIBE", "RENEW", "CHANGE_METHOD", "CANCEL")
data class OfferPrice(val amount: Long, val original: Long? = null)
data class AccountOffer(val id: String, val prices: Map<String, OfferPrice>)
data class BillingOverview(
    val revision: String, val mode: String, val available: Boolean, val plan: String,
    val status: String, val paidUntil: String?, val autoRenew: Boolean,
    val method: String?, val currentPrice: String?, val routes: List<PaymentRoute>,
    val offers: List<AccountOffer>, val actions: Set<String>, val pendingId: String?,
) {
    fun permits(action: String) = mode == "LIVE" && available && routes.map { it.id }.toSet() == routeIds && action in actions && pendingId == null
}
data class BillingIntent(val request_id: String, val action: String, val expected_revision: String, val offer_id: String?, val payment_route: String?, val currency: String)
data class OperationReceipt(val id: String, val status: String, val redirect: String? = null)
data class SupportUpload(val media: String, val base64: String) {
    fun bytes(): ByteArray = java.util.Base64.getDecoder().decode(base64)
    override fun toString() = "SupportUpload([redacted])"
}
data class SupportSubmission(val requestId: String, val subject: String, val description: String, val email: String, val uploads: List<SupportUpload>) {
    override fun toString() = "SupportSubmission([redacted])"
}
data class SupportReceipt(val id: String, val status: String)
interface AccountApi {
    suspend fun devices(token: String): List<Device>
    suspend fun revoke(token: String, id: String): Device
    suspend fun messages(token: String): List<AccountMessage>
    suspend fun acknowledge(token: String, id: String, revision: Int)
    suspend fun overview(token: String): BillingOverview
    suspend fun start(token: String, intent: BillingIntent): OperationReceipt
    suspend fun operation(token: String, id: String): OperationReceipt
    suspend fun supportStatus(token: String, id: String): SupportReceipt?
    suspend fun supportSubmit(token: String, report: SupportSubmission): SupportReceipt
}

/** Strict transport projection: unknown account fields are tolerated, invalid capabilities fail closed. */
class HttpAccountApi(private val http: HttpAuthApi, private val version: String) : AccountApi {
    private val gson = GsonBuilder().serializeNulls().create()
    private fun JsonObject.text(key: String) = get(key)?.takeUnless { it.isJsonNull }?.asString ?: throw AuthFailure("invalid_response")
    private fun JsonObject.optional(key: String) = get(key)?.takeUnless { it.isJsonNull }?.asString
    private fun JsonObject.flag(key: String, default: Boolean? = null): Boolean {
        val value = get(key) ?: return default ?: throw AuthFailure("invalid_response")
        require(value.isJsonPrimitive && value.asJsonPrimitive.isBoolean); return value.asBoolean
    }
    private fun uuid(value: String) = value.also { UUID.fromString(it) }
    private fun date(value: String?) = value?.also { Instant.parse(it) }
    private fun <T> parse(block: () -> T): T = try { block() } catch (_: Exception) { throw AuthFailure("invalid_response") }
    private suspend fun json(path: String, token: String, body: Any? = null, method: String = if (body == null) "GET" else "POST", query: Map<String,String> = emptyMap()) =
        http.request(path, method, body?.let { gson.toJson(it).toRequestBody("application/json".toMediaType()) }, token, query)
    private fun device(v: JsonObject) = Device(uuid(v.text("id")), v.text("device_name"), v.flag("is_current"), date(v.text("created_at"))!!, date(v.optional("last_login_at")), v.text("status").also { require(it in setOf("ACTIVE", "REVOKED")) } == "ACTIVE")
    override suspend fun devices(token: String): List<Device> { val v = json("devices", token); return parse { v.asJsonArray.map { device(it.asJsonObject) }.also { require(it.map { d -> d.id }.distinct().size == it.size) } } }
    override suspend fun revoke(token: String, id: String): Device {
        uuid(id); val v = json("devices/$id", token, method = "DELETE")
        return parse { val o = v.asJsonObject; require(o.text("status") == "revoked"); device(o.getAsJsonObject("device")).also { require(it.id == id && !it.active) } }
    }
    override suspend fun messages(token: String): List<AccountMessage> {
        val v = json("messages", token, query = mapOf("platform" to "ANDROID", "app_version" to version, "locale" to "en", "schema_version" to "1"))
        return parse {
            val o = v.asJsonObject; require(o.get("schema_version").asInt == 1)
            o.getAsJsonArray("messages").map { raw ->
                val m = raw.asJsonObject; val action = m.get("primary_action")?.takeUnless { it.isJsonNull }?.asJsonObject
                val blocks = m.getAsJsonArray("blocks").map { b ->
                    val block = b.asJsonObject
                    when (block.text("type")) {
                        "paragraph" -> block.text("text")
                        "list" -> block.getAsJsonArray("items").joinToString("\n") { "• ${it.asString}" }
                        else -> m.text("fallback_text")
                    }
                }.joinToString("\n\n")
                AccountMessage(uuid(m.text("id")), m.get("revision").asBigDecimal.intValueExact().also { require(it > 0) }, m.text("title"), blocks,
                    when (action?.optional("type")) { "OPEN_SUBSCRIPTION" -> "SUBSCRIPTION"; "OPEN_SETTINGS" -> "SETTINGS"; "OPEN_ABOUT" -> "ABOUT"; else -> null },
                    action?.optional("label"), m.optional("dismiss_label") ?: "understood")
            }.also { require(it.map { m -> m.id }.distinct().size == it.size) }
        }
    }
    override suspend fun acknowledge(token: String, id: String, revision: Int) {
        uuid(id); val raw = json("messages/$id/acknowledgements", token, mapOf("revision" to revision))
        parse { val v = raw.asJsonObject; require(v.text("id") == id && v.get("revision").asBigDecimal.intValueExact() == revision && v.flag("acknowledged")) }
    }
    override suspend fun overview(token: String): BillingOverview {
        val raw = json("billing/overview", token)
        return parse {
            val v = raw.asJsonObject
            val mode = (v.optional("provider_mode") ?: "DISABLED").also { require(it in setOf("DISABLED", "SANDBOX", "LIVE")) }
            val routes = v.getAsJsonArray("payment_routes")?.map { item ->
                val r = item.asJsonObject; val id = r.text("id"); require(id in routeIds)
                fun currencies(key: String): Set<String> { val a = r.getAsJsonArray(key).map { it.asString }; require(a.distinct().size == a.size && a.all { it in setOf("RUB", "USD") }); return a.toSet() }
                val allowed = currencies("currencies"); val recurring = currencies("recurring_currencies")
                require(allowed.containsAll(recurring) && (id !in setOf("CRYPTO", "ALIPAY_WECHAT") || recurring.isEmpty()))
                PaymentRoute(id, id, allowed, recurring)
            } ?: emptyList()
            require(routes.isEmpty() || (routes.size == 4 && routes.map { it.id }.toSet() == routeIds))
            fun price(p: JsonObject): OfferPrice {
                val amount = p.get("amount_minor").asBigDecimal.longValueExact(); require(amount in 1..1_000_000_000_000)
                val original = p.get("original_amount_minor")?.takeUnless { it.isJsonNull }?.asBigDecimal?.longValueExact()
                require(original == null || original > amount); return OfferPrice(amount, original)
            }
            val offers = v.getAsJsonArray("offers").map { item -> val offer = item.asJsonObject
                require(offer.text("plan") == "PREMIUM" && offer.text("period") == "MONTH")
                AccountOffer(uuid(offer.text("id")), setOf("RUB", "USD").associateWith { price(offer.getAsJsonObject("prices").getAsJsonObject(it)) })
            }
            require(offers.map { it.id }.distinct().size == offers.size)
            val actions = v.getAsJsonArray("actions").map { it.asString }.toSet(); require(billingActions.containsAll(actions))
            val plan = v.text("plan").also { require(it in setOf("FREE", "PREMIUM", "PLATINUM")) }
            val status = v.text("status").also { require(it in setOf("FREE", "ACTIVE", "CANCELED", "EXPIRED")) }
            val paid = date(v.optional("paid_until")); val renew = v.flag("auto_renew")
            require(status !in setOf("ACTIVE", "CANCELED") || paid != null)
            require(!renew || status !in setOf("FREE", "CANCELED"))
            val method = v.get("payment_method")?.takeUnless { it.isJsonNull }?.asJsonObject?.text("label")
            require(status != "CANCELED" || (!renew && method == null))
            val current = v.get("current_price")?.takeUnless { it.isJsonNull }?.asJsonObject?.let { p ->
                val currency = p.text("currency"); require(currency in setOf("RUB", "USD")); "$currency ${java.math.BigDecimal.valueOf(price(p).amount, 2).toPlainString()}"
            }
            BillingOverview(v.text("revision").also { require(it.isNotBlank() && it.length <= 128) }, mode, v.flag("payment_operations_available", false), plan, status, paid, renew, method, current, routes, offers, actions, v.optional("pending_operation_id")?.let(::uuid))
        }
    }
    private fun operation(raw: JsonElement) = parse { val o = raw.asJsonObject
        OperationReceipt(uuid(o.text("id")), o.text("status").also { require(it in setOf("PENDING", "SUCCEEDED", "FAILED", "CANCELED")) }, o.optional("redirect_url"))
    }
    override suspend fun start(token: String, intent: BillingIntent) = operation(json("billing/operations", token, intent))
    override suspend fun operation(token: String, id: String): OperationReceipt { uuid(id); return operation(json("billing/operations/$id", token)).also { require(it.id == id) } }
    private fun support(raw: JsonElement, id: String) = parse { val v = raw.asJsonObject
        SupportReceipt(v.text("request_id").also { require(it == id) }, v.text("status").also { require(it in setOf("ACCEPTED", "RETRYING", "SENT", "FAILED", "EXPIRED")) })
    }
    override suspend fun supportStatus(token: String, id: String): SupportReceipt? {
        uuid(id); return try { support(json("support/requests/$id", token), id) } catch (e: AuthFailure) { if (e.code == "SUPPORT_NOT_FOUND") null else throw e }
    }
    override suspend fun supportSubmit(token: String, report: SupportSubmission): SupportReceipt {
        val value = mapOf("request_id" to report.requestId, "subject" to report.subject, "description" to report.description, "reply_email" to report.email, "diagnostics" to null)
        val form = MultipartBody.Builder().setType(MultipartBody.FORM).addFormDataPart("report", gson.toJson(value)).apply {
            report.uploads.forEachIndexed { i, upload -> addFormDataPart("screenshots", "screenshot-${i+1}", upload.bytes().toRequestBody(upload.media.toMediaType())) }
        }.build()
        return support(http.request("support/requests", "POST", form, token), report.requestId)
    }
}
