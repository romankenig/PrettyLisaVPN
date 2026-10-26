// SPDX-License-Identifier: MIT
package managed

import (
	"bytes"
	"errors"
	"sync"

	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
)

var ErrRunning = errors.New("ENGINE_ALREADY_RUNNING")
var ErrStart = errors.New("ENGINE_START_FAILED")
var ErrStop = errors.New("ENGINE_STOP_FAILED")

// Xray keeps some state process-wide. A separate helper process owns exactly
// one Runtime, and cannot start another candidate before confirmed cleanup.
type Runtime struct {
	mu       sync.Mutex
	instance coreInstance
	create   func(*core.Config) (coreInstance, error)
}
type coreInstance interface {
	Start() error
	Close() error
}

func NewRuntime() *Runtime {
	return &Runtime{create: func(c *core.Config) (coreInstance, error) { return core.New(c) }}
}
func (r *Runtime) Start(profile string) error { return r.start(profile, false) }
func (r *Runtime) start(profile string, mobile bool) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.instance != nil {
		return ErrRunning
	}
	p, err := ParseProfile(profile)
	if err != nil {
		return ErrProfile
	}
	content, err := p.CoreConfig(mobile)
	if err != nil {
		return ErrProfile
	}
	c, err := serial.LoadJSONConfig(bytes.NewReader(content))
	clear(content)
	if err != nil {
		return ErrProfile
	}
	instance, err := r.create(c)
	if err != nil {
		return ErrStart
	}
	r.instance = instance
	if instance.Start() != nil {
		if instance.Close() == nil {
			r.instance = nil
		}
		return ErrStart
	}
	return nil
}
func (r *Runtime) Stop() error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.instance == nil {
		return nil
	}
	if r.instance.Close() != nil {
		return ErrStop
	}
	r.instance = nil
	return nil
}
func (r *Runtime) Running() bool { r.mu.Lock(); defer r.mu.Unlock(); return r.instance != nil }
