// SPDX-License-Identifier: MIT
package managed

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/xtls/xray-core/core"
)

type fakeCore struct {
	startError error
	stopError  error
	starts     int
	stops      int
}

func (c *fakeCore) Start() error { c.starts++; return c.startError }
func (c *fakeCore) Close() error { c.stops++; return c.stopError }
func fixtureRuntime(fake *fakeCore) (*Runtime, string) {
	r := &Runtime{create: func(*core.Config) (coreInstance, error) { return fake, nil }}
	profile, _ := json.Marshal(sample("TROJAN_TLS"))
	return r, string(profile)
}
func TestOwnershipRemainsUntilStopIsConfirmed(t *testing.T) {
	core := new(fakeCore)
	r, profile := fixtureRuntime(core)
	if r.Start(profile) != nil || !r.Running() {
		t.Fatal("engine not owned")
	}
	if r.Start(profile) != ErrRunning || core.starts != 1 {
		t.Fatal("overlapping engine")
	}
	core.stopError = errors.New("private native diagnostic")
	if r.Stop() != ErrStop || !r.Running() {
		t.Fatal("unconfirmed stop advertised DOWN")
	}
	if r.Start(profile) != ErrRunning {
		t.Fatal("start after failed cleanup")
	}
	core.stopError = nil
	if r.Stop() != nil || r.Running() {
		t.Fatal("cleanup retry failed")
	}
	if r.Stop() != nil || core.stops != 2 {
		t.Fatal("stop not idempotent")
	}
}
func TestFailedStartCleansPartialCoreAndRedactsError(t *testing.T) {
	core := &fakeCore{startError: errors.New("credential must not escape")}
	r, profile := fixtureRuntime(core)
	if r.Start(profile) != ErrStart || r.Running() || core.stops != 1 {
		t.Fatal("partial start not cleaned")
	}
	core.stopError = errors.New("failed cleanup")
	if r.Start(profile) != ErrStart || !r.Running() {
		t.Fatal("partial start lost ownership")
	}
	if r.Start(profile) != ErrRunning {
		t.Fatal("overlapping partial start")
	}
}
func TestMalformedProfileCannotCreateEngine(t *testing.T) {
	core := new(fakeCore)
	r, _ := fixtureRuntime(core)
	if r.Start(`{"version":1,"script":"secret"}`) != ErrProfile || core.starts != 0 || r.Running() {
		t.Fatal("invalid profile affected native state")
	}
}
