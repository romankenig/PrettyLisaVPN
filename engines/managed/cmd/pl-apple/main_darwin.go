// SPDX-License-Identifier: MIT
package main

/*
#include <stdint.h>
*/
import "C"

import (
	"os"
	"runtime/debug"
	"strconv"
	"sync"

	managed "github.com/romankenig/PrettyLisaVPN/engines/managed"
)

var engine = managed.NewRuntime()
var lock sync.Mutex

// PLStart receives only the authenticated typed profile and a socketpair fd.
// Swift retains ownership of the fd; the pinned Darwin TUN duplicates it.
//
//export PLStart
func PLStart(profile *C.char, fd C.int32_t) C.int32_t {
	lock.Lock()
	defer lock.Unlock()
	if profile == nil || fd < 0 || engine.Running() {
		return 1
	}
	debug.SetMemoryLimit(32 << 20)
	debug.SetGCPercent(20)
	if os.Setenv("XRAY_TUN_FD", strconv.Itoa(int(fd))) != nil {
		return 2
	}
	defer os.Unsetenv("XRAY_TUN_FD")
	if engine.StartApple(C.GoString(profile)) != nil {
		_ = engine.Stop()
		return 3
	}
	return 0
}

//export PLStop
func PLStop() C.int32_t {
	lock.Lock()
	defer lock.Unlock()
	if engine.Stop() != nil {
		return 1
	}
	return 0
}

//export PLRunning
func PLRunning() C.int32_t {
	if engine.Running() {
		return 1
	}
	return 0
}

func main() {}
