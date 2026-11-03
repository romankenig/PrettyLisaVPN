// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PrettyLisaCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "PrettyLisaCore", targets: ["PrettyLisaCore"])],
    targets: [
        .target(name: "PrettyLisaCore", path: "Core"),
        .executableTarget(name: "LiveAPIProbe", dependencies: ["PrettyLisaCore"], path: "Tools/LiveAPIProbe"),
        .testTarget(name: "PrettyLisaCoreTests", dependencies: ["PrettyLisaCore"], path: "Tests/Core")
    ]
)
