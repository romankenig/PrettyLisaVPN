package com.prettylisavpn.android.ui

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/** An old route's lookup cannot overwrite a newer connection's location. */
internal class LocationRefresh<T>(private val lookup: suspend () -> T?) {
    private var generation = 0L
    private val mutable = MutableStateFlow<T?>(null)
    private val busy = MutableStateFlow(false)
    val value = mutable.asStateFlow()
    val loading = busy.asStateFlow()

    fun invalidate(updating: Boolean) {
        generation++
        mutable.value = null
        busy.value = updating
    }

    suspend fun refresh() {
        val request = ++generation
        mutable.value = null
        busy.value = true
        try {
            val result = lookup()
            currentCoroutineContext().ensureActive()
            if (generation == request) mutable.value = result
        } finally {
            if (generation == request) busy.value = false
        }
    }
}
