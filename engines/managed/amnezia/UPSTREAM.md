# AmneziaWG proxy adapter

`client.go`, `server.go` and `bind.go` are modified Xray-core files from
commit `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`, under MPL-2.0 (included).
`netstack.go` retains its upstream WireGuard MIT notice.

Changes: use the pinned MIT AmneziaWG v3 device implementation, use only the
userspace network stack, register a distinct typed factory, apply deterministic
node-specific public obfuscation parameters, and preserve all packet header
bytes instead of rewriting standard WireGuard reserved bytes. This adapter
does not load a kernel module or invoke GPL command-line tools.

`bridge.go` and `config.proto` are PrettyLisaVPN MIT code. `config.pb.go` is
generated using protoc 33.0 and protoc-gen-go 1.36.12. Corresponding modified
sources, original notices and dependency sources accompany binary artifacts.
