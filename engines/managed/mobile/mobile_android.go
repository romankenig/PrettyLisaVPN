// SPDX-License-Identifier: MIT
package mobile

import (
	"errors"
	"net/netip"
	"os"
	"strconv"
	"strings"
	"sync"
	"syscall"

	managed "github.com/romankenig/PrettyLisaVPN/engines/managed"
	"github.com/xtls/xray-core/app/dns"
	"github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/transport/internet"
)

type Platform interface {
	Protect(fd int32) bool
	OpenTun(usePhysicalDNS bool) (int32, error)
	LookupPhysicalIPv4(host string) string
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
var fakeDNSPool = netip.MustParsePrefix("198.18.0.0/15")

func lookupPhysicalIPv4(host string) []net.IP {
	sockets.RLock()
	platform := sockets.platform
	sockets.RUnlock()
	if platform == nil {
		return nil
	}
	var ips []net.IP
	for _, answer := range strings.Fields(platform.LookupPhysicalIPv4(host)) {
		ip, err := netip.ParseAddr(answer)
		if err == nil && ip.Is4() && !ip.IsUnspecified() && !ip.IsMulticast() && !fakeDNSPool.Contains(ip) {
			ips = append(ips, net.IP(ip.AsSlice()))
		}
	}
	return ips
}

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
	parsed, err := managed.ParseProfile(profile)
	if err != nil {
		return managed.ErrProfile
	}
	controllers.Do(func() {
		controllerError = internet.RegisterDialerController(protect)
		if controllerError == nil {
			controllerError = internet.RegisterListenerController(protect)
		}
		dns.SetAndroidDirectDNSResolver(lookupPhysicalIPv4)
	})
	if controllerError != nil || host == nil {
		return managed.ErrStart
	}
	fd, err := host.OpenTun(parsed.Routing != nil && parsed.Routing.Mode != "all")
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
