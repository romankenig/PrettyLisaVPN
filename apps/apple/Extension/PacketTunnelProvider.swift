import Foundation
import NetworkExtension
import PrettyLisaCore

final class PacketTunnelProvider: NEPacketTunnelProvider {
    private let bridge = PacketBridge()
    private let work = DispatchQueue(label: "com.prettylisavpn.provider")
    private var payload: TunnelPayload?
    private var expiry: DispatchSourceTimer?
    private var pathObservation: NSKeyValueObservation?
    private var stopped = false
    private var generation = 0

    override func startTunnel(options: [String: NSObject]?, completionHandler: @escaping (Error?) -> Void) {
        do {
            guard let configuration = protocolConfiguration as? NETunnelProviderProtocol,
                  let reference = configuration.passwordReference else { throw ClientError("MISSING_CONFIGURATION") }
            let value = try WireJSON.decode(TunnelPayload.self, from: KeychainStore.resolve(reference))
            guard value.expiresAt > Date(), !value.dns.isEmpty,
                  value.dns.allSatisfy(TunnelPayload.isIPv4) else { throw ClientError("LEASE_EXPIRED") }
            payload = value
            let settings = NEPacketTunnelNetworkSettings(tunnelRemoteAddress: value.profile.server)
            // Existing managed core terminates an inner IP stack. Server-assigned WG address stays in its outbound.
            let ipv4 = NEIPv4Settings(addresses: ["172.30.255.1"], subnetMasks: ["255.255.255.252"])
            ipv4.includedRoutes = [.default()]
            let ipv6 = NEIPv6Settings(addresses: ["fd7a:115c:a1e0::1"], networkPrefixLengths: [126])
            ipv6.includedRoutes = [.default()]
            settings.ipv4Settings = ipv4; settings.ipv6Settings = ipv6
            let dns = NEDNSSettings(servers: value.dns)
            dns.matchDomains = [""]; dns.matchDomainsNoSearch = true
            settings.dnsSettings = dns; settings.mtu = 1280
            setTunnelNetworkSettings(settings) { error in
                self.work.async {
                    if error != nil { completionHandler(self.failure("NETWORK_SETTINGS_FAILED")); return }
                    do {
                        try self.bridge.start(profile: value.profile, flow: self.packetFlow)
                        self.armExpiry(value.expiresAt)
                        self.pathObservation = self.observe(\.defaultPath, options: [.new]) { [weak self] _, _ in self?.pathChanged() }
                        completionHandler(nil)
                    } catch { completionHandler(self.failure("ENGINE_START_FAILED")) }
                }
            }
        } catch { completionHandler(failure((error as? ClientError)?.code ?? "INVALID_CONFIGURATION")) }
    }
    private func failure(_ code: String) -> NSError {
        NSError(domain: "PrettyLisaVPN", code: 1, userInfo: [NSLocalizedDescriptionKey: code])
    }
    private func armExpiry(_ date: Date) {
        let timer = DispatchSource.makeTimerSource(queue: work)
        timer.schedule(deadline: .now() + max(0, date.timeIntervalSinceNow), repeating: 1)
        timer.setEventHandler { [weak self] in
            guard let self, Date() >= date else { return }
            self.cancelTunnelWithError(self.failure("LEASE_EXPIRED"))
            try? self.bridge.stop(); self.expiry?.cancel(); self.expiry = nil
        }
        expiry = timer; timer.resume()
    }
    private func pathChanged() {
        work.async {
            guard !self.stopped, let payload = self.payload else { return }
            self.generation += 1
            let generation = self.generation
            self.reasserting = true
            guard self.defaultPath?.status == .satisfied else { return }
            guard payload.expiresAt > Date() else { self.cancelTunnelWithError(self.failure("LEASE_EXPIRED")); return }
            // Reset uplink sockets after Wi-Fi/cellular changes, retaining the same authorized peer.
            do {
                try self.bridge.stop(); try self.bridge.start(profile: payload.profile, flow: self.packetFlow)
                self.checkTunnelPath(generation: generation, attempt: 0)
            } catch { self.cancelTunnelWithError(self.failure("NETWORK_RECOVERY_FAILED")) }
        }
    }
    private func checkTunnelPath(generation: Int, attempt: Int) {
        guard !stopped, generation == self.generation, let payload else { return }
        // Provider's ordinary sockets bypass the VPN. This API explicitly verifies THROUGH the tunnel.
        let host = payload.apiBase.host!
        let connection = createTCPConnectionThroughTunnel(to: NWHostEndpoint(hostname: host, port: String(payload.apiBase.port ?? 443)),
                                                          enableTLS: true, tlsParameters: nil, delegate: nil)
        let request = Data("GET /health HTTP/1.1\r\nHost: \(host)\r\nConnection: close\r\n\r\n".utf8)
        // Bound both TLS and read; the completion guard prevents an old path from clearing reasserting.
        work.asyncAfter(deadline: .now() + 20) { connection.cancel() }
        connection.write(request) { error in
            if error != nil { connection.cancel(); self.retryPath(generation: generation, attempt: attempt); return }
            connection.readMinimumLength(12, maximumLength: 512) { data, error in
                connection.cancel()
                self.work.async {
                    guard !self.stopped, self.generation == generation else { return }
                    if error == nil, let data, String(decoding: data, as: UTF8.self).hasPrefix("HTTP/1.1 200") {
                        self.reasserting = false
                    } else { self.retryPath(generation: generation, attempt: attempt) }
                }
            }
        }
    }
    private func retryPath(generation: Int, attempt: Int) {
        work.asyncAfter(deadline: .now() + 3) {
            guard !self.stopped, self.generation == generation else { return }
            if attempt < 4 { self.checkTunnelPath(generation: generation, attempt: attempt + 1) }
            else { self.cancelTunnelWithError(self.failure("INTERNET_UNVERIFIED")) }
        }
    }
    override func stopTunnel(with reason: NEProviderStopReason, completionHandler: @escaping () -> Void) {
        work.async {
            self.stopped = true; self.generation += 1
            self.pathObservation = nil; self.expiry?.cancel(); self.expiry = nil
            try? self.bridge.stop(); self.payload = nil
            completionHandler()
        }
    }
    override func wake() {
        if payload?.expiresAt ?? .distantPast <= Date() { cancelTunnelWithError(failure("LEASE_EXPIRED")) }
        else { pathChanged() }
    }
    override func handleAppMessage(_ messageData: Data, completionHandler: ((Data?) -> Void)?) {
        completionHandler?(messageData == Data("status".utf8) ? bridge.status() : nil)
    }
}
