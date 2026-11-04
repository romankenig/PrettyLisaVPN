// SPDX-License-Identifier: MIT
package managed

// StartApple uses a descriptor supplied by the PacketFlow bridge. NetworkExtension
// alone owns system routes and DNS; the engine never creates a second utun device.
func (r *Runtime) StartApple(profile string) error { return r.start(profile, true) }
