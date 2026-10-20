package com.prettylisavpn.android

import android.os.Bundle
import androidx.test.runner.AndroidJUnitRunner
import com.prettylisavpn.android.data.SourceFactory

/** Fixtures are opt-in only from instrumentation; the ordinary launcher uses the API. */
class AcceptanceRunner : AndroidJUnitRunner() {
    override fun onCreate(arguments: Bundle?) {
        SourceFactory.useFixturesForTests = true
        super.onCreate(arguments)
    }
}
