package com.prettylisavpn.android.data

/** No test source in release; a real API/runtime adapter is a separate task. */
object SourceFactory {
    fun create(): ScreenSource = object : ScreenSource {
        override val enabled = false
        override val initial = Snapshot()
        override suspend fun read(area: Area): Snapshot = throw SourceFailure("Integration is unavailable.")
        override suspend fun execute(command: Command): Snapshot = throw SourceFailure("Integration is unavailable.")
        override fun configure(scenario: Scenario) = Unit
    }
}
