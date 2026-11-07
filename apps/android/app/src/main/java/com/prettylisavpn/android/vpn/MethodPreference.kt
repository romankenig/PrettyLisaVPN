package com.prettylisavpn.android.vpn

/** Optional device-local method ID. Never persist keys, account data or endpoints. */
class MethodPreference(
    read: () -> String? = { null }, private val write: (String) -> Unit = {},
    readFailures: () -> Map<String, Long> = { emptyMap() },
    private val writeFailures: (Map<String, Long>) -> Unit = {},
    private val now: () -> Long = System::currentTimeMillis,
    private val explore: () -> Boolean = { false },
    private val choose: (Int) -> Int = kotlin.random.Random::nextInt,
) {
    private var method = runCatching { read()?.takeIf { it.matches(Regex("[a-z][a-z0-9_]{0,63}")) } }.getOrNull()
    private val failures = runCatching { readFailures().filterKeys { it.matches(Regex("[a-z][a-z0-9_]{0,63}")) }.entries.take(64).associate { it.toPair() }.toMutableMap() }.getOrDefault(mutableMapOf())
    fun current(): String? = method
    fun remember(verifiedMethod: String) {
        method = verifiedMethod
        // Preference storage must not turn a working VPN into a failed connection.
        runCatching { write(verifiedMethod) }
    }
    fun failedAfterConnection(id: String) {
        failures[id] = now()
        persistFailures()
    }
    fun clear() {
        method = null; failures.clear()
        runCatching { write("") }
        persistFailures()
    }
    /** Explore only at connection boundaries; recent delayed failures go last for 30 minutes. */
    fun order(available: List<String>): List<String> {
        val instant = now()
        failures.entries.removeAll { instant - it.value !in 0 until 30 * 60_000L }
        val healthy = available.filterNot { it in failures }
        val preferred = healthy.firstOrNull { it == method }
        val alternatives = healthy.filterNot { it == preferred }
        val first = if (preferred != null && alternatives.isNotEmpty() && explore()) alternatives[choose(alternatives.size)] else preferred
        val priority = listOfNotNull(first, preferred).distinct()
        return priority + healthy.filterNot { it in priority } + available.filter { it in failures }
    }
    private fun persistFailures() { runCatching { writeFailures(failures.toMap()) } }
}
