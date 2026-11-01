package com.prettylisavpn.android.vpn

internal const val VPN_DISCONNECT_ACTION = "com.prettylisavpn.action.DISCONNECT_VPN"

/** Notification uses the same cleanup-aware controller as the Home button. */
internal fun dispatchVpnNotificationAction(action: String?, vpn: VpnActions?): Boolean {
    if (action != VPN_DISCONNECT_ACTION || vpn == null) return false
    vpn.disconnect()
    return true
}
