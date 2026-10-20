package com.prettylisavpn.android.data

import android.content.Context
import android.os.Build
import com.prettylisavpn.android.auth.*

/** Auth-only integration: no fixture data is composed with a real account. */
class LiveSessionSource(private val sessions: SessionCoordinator) : ScreenSource {
    override val recoveryRequired get() = sessions.needsRecovery
    override val enabled = true
    override val fixture = false
    private var requestedEmail: String? = null
    override val initial: Snapshot get() = sessions.profile?.let {
        Snapshot(signedIn = true, email = it.email, plan = it.plan, activeDeviceCount = it.activeDevices)
    } ?: Snapshot()
    override suspend fun read(area: Area): Snapshot {
        if (area == Area.SESSION) sessions.restore() else sessions.refreshProfile()
        return initial
    }
    override suspend fun execute(command: Command): Snapshot {
        when (command) {
            is Command.RequestOtp -> { sessions.requestOtp(command.email); requestedEmail = command.email }
            is Command.VerifyOtp -> sessions.login(requestedEmail ?: throw AuthFailure("reauth_required"), command.code)
            Command.Logout -> { sessions.logout(); requestedEmail = null }
            Command.ForgetLocalSession -> { sessions.forgetLocalSession(); requestedEmail = null }
            else -> throw SourceFailure("This feature is not connected yet.")
        }
        return initial
    }
    override fun configure(scenario: Scenario) = Unit
}

object LiveSessionFactory {
    private var source: LiveSessionSource? = null
    @Synchronized fun create(context: Context): ScreenSource = source ?: LiveSessionSource(
        SessionCoordinator(HttpAuthApi("https://api.prettylisavpn.com/"), KeystoreVault(context.applicationContext),
            "${Build.MANUFACTURER} ${Build.MODEL}".trim().take(255))
    ).also { source = it }
}
