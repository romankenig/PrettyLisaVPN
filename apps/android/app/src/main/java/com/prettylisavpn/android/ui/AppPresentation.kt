package com.prettylisavpn.android.ui

import android.content.Context
import androidx.core.content.edit
import android.content.res.Configuration
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.google.gson.JsonParser
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.R
import com.prettylisavpn.android.network.RoutedHttpClient
import com.prettylisavpn.android.network.HttpRoutes
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.Locale
import java.util.concurrent.TimeUnit

internal enum class AppLanguage(val flag: String, val english: String, val native: String, val code: String) {
    CHINESE("🇨🇳", "Chinese", "中文", "zh"),
    ENGLISH("🇬🇧", "English", "English", "en"),
    FRENCH("🇫🇷", "French", "Français", "fr"),
    GERMAN("🇩🇪", "German", "Deutsch", "de"),
    RUSSIAN("🇷🇺", "Russian", "Русский", "ru"),
    SPANISH("🇪🇸", "Spanish", "Español", "es"),
}

/** Display only the release core of a valid SemVer; never concatenate digits from a SHA. */
internal fun releaseVersion(raw: String?): String? {
    if (raw == null || raw.length > 256) return null
    val number = "(?:0|[1-9][0-9]*)"
    val identifier = "(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    val version = Regex("($number\\.$number\\.$number)(?:-$identifier(?:\\.$identifier)*)?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?")
    return version.matchEntire(raw)?.groupValues?.get(1)?.takeIf { it.length <= 20 }
}

/** Only an explicit user choice is durable; a country suggestion is never a preference. */
internal class LanguagePreference(saved: String?, private val persist: (String) -> Unit) {
    private var manual = AppLanguage.entries.any { it.code == saved }
    private val mutable = MutableStateFlow(AppLanguage.entries.find { it.code == saved } ?: AppLanguage.ENGLISH)
    val language = mutable.asStateFlow()
    fun choose(value: AppLanguage) {
        manual = true
        runCatching { persist(value.code) }
        mutable.value = value
    }
    fun suggest(country: String?) {
        if (!manual) mutable.value = if (country == "RU") AppLanguage.RUSSIAN else AppLanguage.ENGLISH
    }
    val automatic get() = !manual
}

internal data class PublicLocation(val ip: String, val country: String?, val city: String?)

/** Independent public metadata only: no auth headers, email, session or installation ID. */
internal class PublicMetadata(
    private val versionUrl: String = "https://api.prettylisavpn.com/version",
    private val countryUrl: String = "https://ipwho.is/",
    private val fallbackCountryUrl: String? = if (countryUrl == "https://ipwho.is/") "https://ipinfo.io/json" else null,
    private val vpnIpUrl: String = "https://ifconfig.me/all.json",
    private val vpnCountryUrl: String = "https://ipwho.is/",
) {
    private val base = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).callTimeout(5, TimeUnit.SECONDS).build()
    private val client = RoutedHttpClient(base)
    private suspend fun read(url: String, http: OkHttpClient = client.current()) = withContext(Dispatchers.IO) {
        runCatching {
            http.newCall(Request.Builder().url(url).header("Accept", "application/json").build()).execute().use {
                if (!it.isSuccessful) return@use null
                val body = it.body ?: return@use null
                if (body.contentLength() > 16_384) return@use null
                val source = body.source()
                source.request(16_385)
                val bytes = source.buffer.readByteArray(minOf(source.buffer.size, 16_385L))
                if (bytes.size > 16_384) null else JsonParser.parseString(bytes.toString(Charsets.UTF_8)).asJsonObject
            }
        }.getOrNull()
    }
    suspend fun reachable(): Boolean = read(versionUrl) != null
    suspend fun version(): String? = read(versionUrl)?.let { value -> runCatching {
        releaseVersion(value.get("application_version")?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString)
    }.getOrNull() }
    suspend fun location(): PublicLocation? {
        for ((url, fallback) in listOfNotNull(countryUrl to false, fallbackCountryUrl?.let { it to true })) {
            currentCoroutineContext().ensureActive()
            val value = read(url) ?: continue
            parseLocation(value, fallback)?.let { return it }
        }
        return null
    }
    private fun parseLocation(value: com.google.gson.JsonObject, fallback: Boolean): PublicLocation? = runCatching {
        if (!fallback) require(value.get("success")?.asBoolean == true)
        require(!value.has("error") && value.get("bogon")?.asBoolean != true)
        val ip = value.get("ip").takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString ?: return null
        val ipv4 = ip.matches(Regex("[0-9]{1,3}(\\.[0-9]{1,3}){3}")) && ip.split('.').all { it.toInt() in 0..255 }
        val ipv6 = ip.contains(':') && ip.matches(Regex("[0-9a-fA-F:]{2,45}")) && runCatching { java.net.InetAddress.getByName(ip) is java.net.Inet6Address }.getOrDefault(false)
        require(ipv4 || ipv6)
        val country = value.get(if (fallback) "country" else "country_code")?.takeUnless { it.isJsonNull }?.asString?.takeIf { it.matches(Regex("[A-Z]{2}")) }
        val city = value.get("city")?.takeUnless { it.isJsonNull }?.asString?.trim()?.takeIf { it.length in 1..120 && it.none(Char::isISOControl) }
        PublicLocation(ip, country, city)
    }.getOrNull()
    suspend fun country(): String? = location()?.country

    suspend fun vpnLocation(): PublicLocation? {
        val route = HttpRoutes.current
        val sockets = route.sockets ?: return null
        val dns = route.dns ?: return null
        // Pin both requests to the VPN Network; never fall back to physical
        // sockets if disconnect changes HttpRoutes while a request is running.
        val http = base.newBuilder().socketFactory(sockets).dns(dns).proxy(java.net.Proxy.NO_PROXY)
            .connectionPool(okhttp3.ConnectionPool()).build()
        return try {
            val value = read(vpnIpUrl, http) ?: return null
            val ip = runCatching { value.get("ip_addr")?.asString }.getOrNull() ?: return null
            if (!ip.matches(Regex("[0-9]{1,3}(\\.[0-9]{1,3}){3}")) || ip.split('.').any { it.toInt() !in 0..255 }) return null
            val observed = PublicLocation(ip, null, null)
            currentCoroutineContext().ensureActive()
            if (HttpRoutes.current !== route) return null
            val location = read(vpnCountryUrl + ip, http)?.let { parseLocation(it, false) }?.takeIf { it.ip == ip } ?: observed
            if (HttpRoutes.current === route) location else null
        } finally { http.connectionPool.evictAll() }
    }
}

internal class PresentationState(context: Context, private val network: Boolean) {
    private val metadata = PublicMetadata()
    private val app = context.applicationContext as android.app.Application
    private val preferences = app.getSharedPreferences("presentation", Context.MODE_PRIVATE)
    val preference = LanguagePreference(runCatching { preferences.getString("language", null) }.getOrNull()) {
        preferences.edit { putString("language", it) }
    }
    private val mutableVersion = MutableStateFlow<String?>(null)
    val version = mutableVersion.asStateFlow()
    private val mutableLocation = MutableStateFlow<PublicLocation?>(null)
    val location = mutableLocation.asStateFlow()
    suspend fun refreshServer(): Boolean = metadata.reachable()
    suspend fun refreshLocation() {
        if (network) mutableLocation.value = metadata.location()
    }
    suspend fun vpnLocation(): PublicLocation? = if (network) metadata.vpnLocation() else null
    @Suppress("DEPRECATION")
    private fun vpnActive(): Boolean = runCatching {
        val connectivity = app.getSystemService(ConnectivityManager::class.java)
        connectivity.allNetworks.any { connectivity.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true }
    }.getOrDefault(true)
    init {
        if (network) {
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
            scope.launch { mutableVersion.value = metadata.version() }
            if (preference.automatic && !vpnActive()) scope.launch {
                val country = metadata.country()
                if (!vpnActive()) preference.suggest(country)
            }
        }
    }
}

/** Instrumentation disables both public lookups before Activity creation. */
internal object PresentationStore {
    var networkEnabled = true
    private var instance: PresentationState? = null
    fun get(context: Context): PresentationState = instance ?: PresentationState(context, networkEnabled).also { instance = it }
    fun reset() { instance = null }
}

internal class Strings(private val context: Context) {
    operator fun invoke(id: Int, vararg arguments: Any?): String = context.getString(id, *arguments)
    fun error(message: String): String {
        val id = when (message) {
            "CLEANUP" -> R.string.vpn_cleanup
            "No network connection. Check your connection and retry." -> R.string.error_0
            "The code is invalid or expired. Request a new code." -> R.string.error_1
            "Too many requests. Please wait before requesting another code." -> R.string.error_2
            "The account already has five active devices." -> R.string.error_3
            "This device has been revoked. Sign in again." -> R.string.error_4
            "Account access is blocked." -> R.string.error_5
            "Your session has ended. Sign in again." -> R.string.error_6
            "Secure storage is unavailable. Please retry." -> R.string.error_7
            "Session renewal could not be confirmed. Sign in again to continue safely." -> R.string.error_8
            "The service is temporarily unavailable. Please retry." -> R.string.error_9
            "The price changed. Refresh and review the subscription before confirming again." -> R.string.error_10
            "The saved request conflicts with the server record. Check its status before continuing." -> R.string.error_11
            "Another billing operation is still pending. Refresh its status." -> R.string.error_12
            "Too many support requests. Please wait before trying again." -> R.string.error_13
            "The selected image was rejected. Choose PNG, JPEG or WebP within the size limits." -> R.string.error_14
            "Review the subject, description and reply address." -> R.string.error_15
            "This message changed or is no longer available. Refresh messages." -> R.string.error_16
            "This device is no longer available. Refresh the device list." -> R.string.error_17
            "The action completed, but fresh data is unavailable. Refresh to try again." -> R.string.error_18
            "This payment action is unavailable. Refresh subscription details." -> R.string.error_19
            "Test source is offline. No network request was made." -> R.string.error_20
            "Simulated request failure. Retry is safe; nothing was changed." -> R.string.error_21
            "Test code expired. Request a new code." -> R.string.error_22
            "Incorrect test code. Use 123456." -> R.string.error_23
            "Choose up to 3 PNG, JPEG or WebP images, at most 5 MB each and 10 MB total." -> R.string.detail_0
            "Service unavailable." -> R.string.detail_1
            "A unique offer is unavailable." -> R.string.detail_2
            "Choose New request before composing another support request." -> R.string.detail_3
            "Payments are unavailable for this provider." -> R.string.detail_4
            "Resolve the previous request before starting another one." -> R.string.detail_5
            "Saved operations are unavailable. Restore secure storage before starting a new request." -> R.string.detail_6
            "The price or subscription changed. Review the refreshed details before confirming again." -> R.string.detail_7
            "This currency is unavailable." -> R.string.detail_8
            "This feature is not connected yet." -> R.string.detail_9
            "This message changed. Refresh messages before confirming." -> R.string.detail_10
            "This payment route is unavailable for the selected currency." -> R.string.detail_11
            "Unable to save the operation securely. Retry before starting another operation." -> R.string.detail_12
            else -> null
        }
        return if (id == null) message else invoke(id)
    }
    fun route(id: String): String = invoke(when (id) {
        "MIR" -> R.string.detail_13
        "BANK_CARD" -> R.string.detail_14
        "ALIPAY_WECHAT" -> R.string.detail_15
        else -> R.string.detail_16
    })
    fun action(code: String): String = invoke(when (code) {
        "SUBSCRIBE" -> R.string.ui_subscribe
        "RENEW" -> R.string.ui_renew
        "CHANGE_METHOD" -> R.string.ui_change_method
        "CANCEL" -> R.string.ui_cancel
        else -> R.string.unavailable
    })
    fun area(area: com.prettylisavpn.android.data.Area): String = invoke(when (area) {
        com.prettylisavpn.android.data.Area.HOME -> R.string.home
        com.prettylisavpn.android.data.Area.DEVICES -> R.string.ui_devices
        com.prettylisavpn.android.data.Area.BILLING -> R.string.ui_subscription
        com.prettylisavpn.android.data.Area.SUPPORT -> R.string.ui_help_and_support
        com.prettylisavpn.android.data.Area.MESSAGES -> R.string.ui_account_messages
        com.prettylisavpn.android.data.Area.COUNTRIES -> R.string.ui_where_to_connect
        else -> R.string.ui_current_location
    })
}
internal val LocalStrings = staticCompositionLocalOf<Strings?> { null }

@Composable
internal fun strings(): Strings = LocalStrings.current ?: Strings(LocalContext.current)

@Composable
internal fun appString(id: Int): String = strings()(id)
internal val LocalPresentation = staticCompositionLocalOf<PresentationState> { error("Missing presentation state") }

@Composable
internal fun LocalizedApp(content: @Composable () -> Unit) {
    val context = LocalContext.current
    val configuration = LocalConfiguration.current
    val presentation = remember { PresentationStore.get(context) }
    val language by presentation.preference.language.collectAsState()
    val localized = remember(context, language, configuration) {
        context.createConfigurationContext(Configuration(configuration).apply { setLocale(Locale.forLanguageTag(language.code)) })
    }
    CompositionLocalProvider(LocalStrings provides Strings(localized), LocalPresentation provides presentation) { content() }
}

@Composable
internal fun AppHeader(fixture: Boolean) {
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current
    val window = LocalWindowInfo.current.containerSize
    val keyboard = WindowInsets.ime.getBottom(density) > 0
    // Give the focused field room above large landscape keyboards. No route/state changes.
    if (configuration.orientation == Configuration.ORIENTATION_LANDSCAPE && with(density) { window.height.toDp() } < 400.dp && keyboard) return
    val tr = strings()
    val presentation = LocalPresentation.current
    val language by presentation.preference.language.collectAsState()
    var expanded by remember { mutableStateOf(false) }
    key(language) {
        Column(Modifier.fillMaxWidth().background(Brand.Christalle)
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal))
            .padding(horizontal = 12.dp, vertical = 6.dp).testTag("app-header")) {
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                // Keep the brand readable rather than squeezing it beside the language control.
                if (maxWidth < 350.dp || density.fontScale > 1.15f) {
                    Column {
                        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.TopEnd) {
                            HeaderLanguage(language, expanded, { expanded = it }, presentation)
                        }
                        HeaderBrand()
                    }
                } else {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.weight(1f)) { HeaderBrand() }
                        HeaderLanguage(language, expanded, { expanded = it }, presentation)
                    }
                }
            }
            if (fixture) Text(tr(R.string.test_data_notice), style = MaterialTheme.typography.labelSmall, color = Brand.Galliano,
                modifier = Modifier.testTag("test-banner"))
        }
    }
}

@Composable
internal fun AppVersionFooter() {
    val tr = strings()
    val version by LocalPresentation.current.version.collectAsState()
    Box(Modifier.fillMaxWidth().background(Brand.Christalle).testTag("app-version-footer")
        .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal))
        .padding(horizontal = 12.dp, vertical = 3.dp)) {
        Text(tr(R.string.component_versions, BuildConfig.VERSION_NAME, version ?: tr(R.string.unavailable)),
            style = MaterialTheme.typography.labelSmall, color = Brand.Viking,
            modifier = Modifier.testTag("component-versions"))
    }
}

@Composable
private fun HeaderBrand() {
    val density = LocalDensity.current
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val stacked = maxWidth / density.fontScale < 210.dp
        val mark: @Composable () -> Unit = {
            Image(painterResource(R.drawable.brand_mark), null, modifier = Modifier.size(44.dp).testTag("header-mark"))
        }
        val name: @Composable () -> Unit = {
            Text("PrettyLisaVPN", style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.testTag("header-logo"))
        }
        if (stacked) Column { mark(); name() }
        else Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) { mark(); name() }
    }
}

@Composable
private fun HeaderLanguage(language: AppLanguage, expanded: Boolean, expand: (Boolean) -> Unit, presentation: PresentationState) {
    Box {
        TextButton(onClick = { expand(true) }, modifier = Modifier.testTag("language-picker"),
            contentPadding = PaddingValues(horizontal = 6.dp), colors = ButtonDefaults.textButtonColors(contentColor = Brand.Mercury)) {
            LanguageNames(language, Brand.Mercury)
        }
        DropdownMenu(expanded, { expand(false) }, modifier = Modifier.testTag("language-menu"), containerColor = Brand.Christalle) {
            AppLanguage.entries.forEach { item -> DropdownMenuItem(
                text = { LanguageNames(item, if (item == language) Brand.Viking else Brand.Mercury) },
                onClick = { presentation.preference.choose(item); expand(false) },
                modifier = Modifier.testTag("language-${item.code}"),
            ) }
        }
    }
}

@Composable
private fun LanguageNames(language: AppLanguage, color: androidx.compose.ui.graphics.Color) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        // Flag occupies its own column, centered beside both names.
        Text(language.flag, modifier = Modifier.width(24.dp * LocalDensity.current.fontScale).testTag("language-flag-${language.code}"),
            style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
        Column(Modifier.width(56.dp * LocalDensity.current.fontScale), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(language.english, color = color, style = MaterialTheme.typography.labelMedium,
                modifier = Modifier.testTag("language-english-${language.code}"))
            Text(language.native, color = color.copy(alpha = 0.72f), style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.testTag("language-native-${language.code}"))
        }
    }
}
