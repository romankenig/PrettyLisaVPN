package com.prettylisavpn.android.vpn

import com.wireguard.crypto.KeyPair

/** Java-only key generation. Native tunnels run exclusively in :engine. */
internal class WireGuardKey : TunnelKey {
    val pair = KeyPair()
    override val publicKey: String get() = pair.publicKey.toBase64()
    override fun toString() = "WireGuardKey([redacted])"
}
