package com.prettylisavpn.android.data

import java.time.Instant
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Ephemeral per-login popup state, never an inbox or durable notification history. */
class MessageVisit {
    private val mutable = MutableStateFlow<Set<String>>(emptySet())
    val seen = mutable.asStateFlow()
    fun defer(message: AccountMessage) { mutable.value += key(message) }
    fun reset() { mutable.value = emptySet() }
    fun next(messages: List<AccountMessage>, now: Instant): AccountMessage? = messages.firstOrNull {
        key(it) !in mutable.value && fresh(it, now)
    }
    companion object {
        fun key(message: AccountMessage) = "${message.id}:${message.revision}"
        fun fresh(message: AccountMessage, now: Instant): Boolean = message.expiresAt?.let {
            runCatching { Instant.parse(it).isAfter(now) }.getOrDefault(false)
        } ?: true
    }
}
