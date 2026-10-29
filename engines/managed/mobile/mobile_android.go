// SPDX-License-Identifier: MIT
package mobile

import (
	"errors"
	"os"
	"strconv"
	"sync"
	"syscall"

	managed "github.com/romankenig/PrettyLisaVPN/engines/managed"
	"github.com/xtls/xray-core/transport/internet"
)

type Platform interface {
	Protect(fd int32) bool
	OpenTun() (int32, error)
}
type Engine struct{ runtime *managed.Runtime }

var owner struct {
	sync.Mutex
	engine *Engine
}
var sockets struct {
	sync.RWMutex
	platform Platform
}
var controllers sync.Once
var controllerError error

// One controller for this dedicated process. It fails closed while stopped and
// covers UDP listeners as well as TCP dialers.
func protect(_ string, _ string, c syscall.RawConn) error {
	sockets.RLock()
	defer sockets.RUnlock()
	if sockets.platform == nil {
		return errors.New("ENGINE_NOT_RUNNING")
	}
	ok := false
	if err := c.Control(func(fd uintptr) { ok = sockets.platform.Protect(int32(fd)) }); err != nil {
		return errors.New("SOCKET_PROTECTION_FAILED")
	}
	if !ok {
		return errors.New("SOCKET_PROTECTION_FAILED")
	}
	return nil
}
func NewEngine() *Engine { return &Engine{runtime: managed.NewRuntime()} }
func (e *Engine) Start(profile string, host Platform) error {
	owner.Lock()
	defer owner.Unlock()
	if owner.engine != nil {
		return managed.ErrRunning
	}
	if _, err := managed.ParseProfile(profile); err != nil {
		return managed.ErrProfile
	}
	controllers.Do(func() {
		controllerError = internet.RegisterDialerController(protect)
		if controllerError == nil {
			controllerError = internet.RegisterListenerController(protect)
		}
	})
	if controllerError != nil || host == nil {
		return managed.ErrStart
	}
	fd, err := host.OpenTun()
	if err != nil || fd <= 0 {
		return managed.ErrStart
	}
	if os.Setenv("XRAY_TUN_FD", strconv.Itoa(int(fd))) != nil {
		return managed.ErrStart
	}
	sockets.Lock()
	sockets.platform = host
	sockets.Unlock()
	owner.engine = e
	err = e.runtime.StartMobile(profile)
	if err != nil && !e.runtime.Running() {
		release()
	}
	return err
}
func release() {
	sockets.Lock()
	sockets.platform = nil
	sockets.Unlock()
	_ = os.Unsetenv("XRAY_TUN_FD")
	owner.engine = nil
}
func (e *Engine) Stop() error {
	owner.Lock()
	defer owner.Unlock()
	if owner.engine != nil && owner.engine != e {
		return managed.ErrStop
	}
	if e.runtime.Stop() != nil {
		return managed.ErrStop
	}
	if owner.engine == e {
		release()
	}
	return nil
}
func (e *Engine) Running() bool { return e.runtime.Running() }
func Version() string           { return managed.Version }
