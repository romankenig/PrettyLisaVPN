import Foundation

/// UI boundary shared by the production coordinator and the Debug Simulator controller.
@MainActor public protocol VPNControlling: AnyObject {
    var state: ConnectionState { get }
    func connect(country: String, methods: [String])
    func disconnect() async
}
extension VPNCoordinator: VPNControlling {}
