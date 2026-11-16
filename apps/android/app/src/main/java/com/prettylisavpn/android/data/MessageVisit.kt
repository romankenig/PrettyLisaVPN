package com.prettylisavpn.android.data

import java.time.Instant
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Ephemeral per-login popup state, never an inbox or durable notification history. */
class MessageVisit {
    private val mutable = MutableStateFlow<Set<String>>(emptySet())
    val seen = mutable.asStateFlow()
    private val opened = MutableStateFlow<Set<String>>(emptySet())
    val openedLinks = opened.asStateFlow()
    fun canClose(message: AccountMessage) = message.dismissalMode != MessageDismissalMode.REQUIRE_LINK || key(message) in opened.value
    fun linkOpened(message: AccountMessage) { opened.value += key(message) }
    fun defer(message: AccountMessage) { if (canClose(message) && message.dismissalMode != MessageDismissalMode.ONCE) mutable.value += key(message) }
    fun acknowledged(message: AccountMessage) { if (message.dismissalMode in listOf(MessageDismissalMode.ONCE, MessageDismissalMode.LEGACY)) mutable.value += key(message) }
    fun reset() { mutable.value = emptySet(); opened.value = emptySet() }
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
