import Foundation
import NetworkExtension
import Darwin
import PrettyLisaEngine
import PrettyLisaCore

/// Public packetFlow API ↔ bounded datagram socketpair ↔ the existing Darwin Xray TUN adapter.
/// Four-byte AF headers match upstream DarwinTun. No private packetFlow KVC or utun discovery.
final class PacketBridge {
    private let queue = DispatchQueue(label: "com.prettylisavpn.packet-flow")
    private var socket: Int32 = -1
    private var source: DispatchSourceRead?
    private var running = false
    private var generation = 0
    private var received: UInt64 = 0
    private var sent: UInt64 = 0
    private weak var flow: NEPacketTunnelFlow?

    func start(profile: EngineProfile, flow: NEPacketTunnelFlow) throws {
        try queue.sync {
            guard !running else { throw ClientError("TUNNEL_BUSY") }
            var fds: [Int32] = [-1, -1]
            guard socketpair(AF_UNIX, SOCK_DGRAM, 0, &fds) == 0 else { throw ClientError("PACKET_BRIDGE_FAILED") }
            let payload = try WireJSON.encode(profile)
            let result = String(decoding: payload, as: UTF8.self).withCString { PLStart(UnsafeMutablePointer(mutating: $0), fds[1]) }
            close(fds[1])
            guard result == 0 else { close(fds[0]); throw ClientError("ENGINE_START_FAILED") }
            socket = fds[0]; self.flow = flow; running = true; generation += 1; received = 0; sent = 0
            _ = fcntl(socket, F_SETFL, O_NONBLOCK)
            let source = DispatchSource.makeReadSource(fileDescriptor: socket, queue: queue)
            source.setEventHandler { [weak self] in self?.drain() }
            let ownedSocket = socket
            source.setCancelHandler { close(ownedSocket) }
            self.source = source; source.resume()
            read()
        }
    }
    private func read() {
        guard running else { return }
        let generation = self.generation
        flow?.readPackets { [weak self] packets, _ in
            guard let self else { return }
            self.queue.async {
                guard self.running, self.generation == generation else { return }
                for packet in packets {
                    guard let first = packet.first, packet.count <= 65535 else { continue }
                    let family: UInt8 = first >> 4 == 4 ? UInt8(AF_INET) : UInt8(AF_INET6)
                    var framed = Data([0, 0, 0, family]); framed.append(packet)
                    let count = framed.withUnsafeBytes { Darwin.send(self.socket, $0.baseAddress, $0.count, MSG_DONTWAIT) }
                    if count == framed.count { self.sent += UInt64(packet.count) }
                    // Bounded queue: congestion drops a packet; TCP retransmits. Never fall back to direct sockets.
                }
                self.read()
            }
        }
    }
    private func drain() {
        guard running else { return }
        var packets: [Data] = []; var families: [NSNumber] = []
        var buffer = [UInt8](repeating: 0, count: 65540)
        for _ in 0..<64 {
            let size = recv(socket, &buffer, buffer.count, MSG_DONTWAIT)
            if size <= 4 { break }
            let packet = Data(buffer[4..<size])
            guard let first = packet.first, first >> 4 == 4 || first >> 4 == 6 else { continue }
            received += UInt64(packet.count)
            packets.append(packet); families.append(NSNumber(value: first >> 4 == 4 ? AF_INET : AF_INET6))
        }
        if !packets.isEmpty { _ = flow?.writePackets(packets, withProtocols: families) }
    }
    func stop() throws {
        try queue.sync {
            running = false; generation += 1
            let result = PLStop()
            source?.cancel(); source = nil; socket = -1; flow = nil
            guard result == 0 else { throw ClientError("ENGINE_STOP_FAILED") }
        }
    }
    func status() -> Data {
        queue.sync {
            (try? JSONSerialization.data(withJSONObject: ["running": running && PLRunning() == 1,
                                                          "received": received, "sent": sent])) ?? Data()
        }
    }
}
