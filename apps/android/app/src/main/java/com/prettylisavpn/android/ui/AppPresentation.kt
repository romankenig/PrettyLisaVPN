package com.prettylisavpn.android.ui

import android.content.Context
import android.content.ContextWrapper
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.google.gson.JsonParser
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.R
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

/** Independent public metadata only: no auth headers, email, session or installation ID. */
internal class PublicMetadata(
    private val versionUrl: String = "https://api.prettylisavpn.com/version",
    private val countryUrl: String = "https://ipwho.is/",
) {
    private val client = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).callTimeout(5, TimeUnit.SECONDS).build()
    private suspend fun read(url: String) = withContext(Dispatchers.IO) {
        runCatching {
            client.newCall(Request.Builder().url(url).header("Accept", "application/json").build()).execute().use {
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
    suspend fun version(): String? = read(versionUrl)?.let { value -> runCatching {
        value.get("application_version")?.asString?.takeIf {
            it.length <= 80 && it.matches(Regex("[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][A-Za-z0-9.+-]+)?"))
        }
    }.getOrNull() }
    suspend fun country(): String? = read(countryUrl)?.let { value -> runCatching {
        value.takeIf { it.get("success")?.asBoolean == true }?.get("country_code")?.asString
            ?.takeIf { it.matches(Regex("[A-Z]{2}")) }
    }.getOrNull() }
}

internal class PresentationState(context: Context, network: Boolean) {
    private val app = context.applicationContext as android.app.Application
    private val preferences = app.getSharedPreferences("presentation", Context.MODE_PRIVATE)
    val preference = LanguagePreference(runCatching { preferences.getString("language", null) }.getOrNull()) {
        preferences.edit { putString("language", it) }
    }
    private val mutableVersion = MutableStateFlow<String?>(null)
    val version = mutableVersion.asStateFlow()
    @Suppress("DEPRECATION")
    private fun vpnActive(): Boolean = runCatching {
        val connectivity = app.getSystemService(ConnectivityManager::class.java)
        connectivity.allNetworks.any { connectivity.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true }
    }.getOrDefault(true)
    init {
        if (network) {
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
            val metadata = PublicMetadata()
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
internal val LocalStrings = staticCompositionLocalOf<Strings> { error("Missing localized resources") }
internal val LocalPresentation = staticCompositionLocalOf<PresentationState> { error("Missing presentation state") }

/** Keep the Activity in the ContextWrapper chain for SAF launchers and external intents. */
private class LanguageContext(base: Context, configuration: Configuration) : ContextWrapper(base) {
    private val localizedResources = base.createConfigurationContext(configuration).resources
    override fun getResources(): android.content.res.Resources = localizedResources
}

@Composable
internal fun LocalizedApp(content: @Composable () -> Unit) {
    val context = LocalContext.current
    val configuration = LocalConfiguration.current
    val presentation = remember { PresentationStore.get(context) }
    val language by presentation.preference.language.collectAsState()
    val localized = remember(context, language, configuration) {
        LanguageContext(context, Configuration(configuration).apply { setLocale(Locale.forLanguageTag(language.code)) })
    }
    CompositionLocalProvider(LocalConfiguration provides localized.resources.configuration, LocalContext provides localized, LocalStrings provides Strings(localized), LocalPresentation provides presentation) { content() }
}

@Composable
internal fun AppHeader(fixture: Boolean) {
    val tr = LocalStrings.current
    val presentation = LocalPresentation.current
    val language by presentation.preference.language.collectAsState()
    val version by presentation.version.collectAsState()
    var expanded by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().background(Brand.Christalle)
        .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal))
        .padding(horizontal = 12.dp, vertical = 6.dp).testTag("app-header")) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Image(painterResource(R.drawable.brand_mark), null, modifier = Modifier.size(26.dp))
                Text("PrettyLisaVPN", style = MaterialTheme.typography.titleSmall, modifier = Modifier.testTag("header-logo"))
            }
            Box {
                TextButton(onClick = { expanded = true }, modifier = Modifier.testTag("language-picker"),
                    contentPadding = PaddingValues(horizontal = 4.dp), colors = ButtonDefaults.textButtonColors(contentColor = Brand.Mercury)) {
                    Column(horizontalAlignment = Alignment.Start) {
                        Text("${language.flag} ${language.english}", style = MaterialTheme.typography.labelSmall)
                        Text(language.native, style = MaterialTheme.typography.labelSmall)
                    }
                }
                DropdownMenu(expanded, { expanded = false }, modifier = Modifier.testTag("language-menu")) {
                    AppLanguage.entries.forEach { item -> DropdownMenuItem(
                        text = { Text("${item.flag} ${item.english} · ${item.native}") },
                        onClick = { presentation.preference.choose(item); expanded = false },
                        modifier = Modifier.testTag("language-${item.code}"),
                    ) }
                }
            }
        }
        Text(tr(R.string.component_versions, BuildConfig.VERSION_NAME, version ?: tr(R.string.unavailable)),
            style = MaterialTheme.typography.labelSmall, color = Brand.Viking, modifier = Modifier.testTag("component-versions"))
        if (fixture) Text(tr(R.string.test_data_notice), style = MaterialTheme.typography.labelSmall, color = Brand.Galliano,
            modifier = Modifier.testTag("test-banner"))
    }
}
