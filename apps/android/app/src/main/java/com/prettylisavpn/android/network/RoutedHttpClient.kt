package com.prettylisavpn.android.network

import okhttp3.ConnectionPool
import okhttp3.Dns
import okhttp3.OkHttpClient
import java.net.Proxy
import javax.net.SocketFactory

/** A route change must not reuse TCP/HTTP2 sockets opened before the VPN. */
internal class HttpRoute(val sockets: SocketFactory? = null, val dns: Dns? = null)

internal object HttpRoutes {
    @Volatile var current = HttpRoute()
        private set
    fun vpn(sockets: SocketFactory, dns: Dns) { current = HttpRoute(sockets, dns) }
    fun default() { current = HttpRoute() }
}

/** Preserve each caller's auth, timeout and replay policy; replace only its route and pool. */
internal class RoutedHttpClient(private val base: OkHttpClient) {
    private var route: HttpRoute? = null
    private var client = base

    @Synchronized fun current(): OkHttpClient {
        val next = HttpRoutes.current
        if (route !== next) {
            client.connectionPool.evictAll()
            client = base.newBuilder().connectionPool(ConnectionPool()).apply {
                if (next.sockets != null && next.dns != null) {
                    socketFactory(next.sockets)
                    dns(next.dns)
                    proxy(Proxy.NO_PROXY)
                }
            }.build()
            route = next
        }
        return client
    }
}
