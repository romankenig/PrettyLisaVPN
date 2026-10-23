// SPDX-License-Identifier: MIT
package managed

// The companion owns the original TUN fd; Xray duplicates it. Neither global
// routes nor system DNS settings are changed by the core on Android.
func (r *Runtime) StartMobile(profile string) error { return r.start(profile, true) }
