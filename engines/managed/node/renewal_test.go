// SPDX-License-Identifier: MIT
package node

import (
	"fmt"
	"testing"
	"time"
)

func TestRenewalCannotChangeAuthorizationOrReviveExpiredProcess(t *testing.T) {
	now := time.Unix(2000000000, 0)
	current := now.Add(time.Minute)
	for _, delta := range []time.Duration{30 * time.Second, MaxLeaseDuration} {
		want := now.Add(delta)
		got, err := Renewal([]byte(fmt.Sprintf(`{"expires":%d}`, want.Unix())), now, current)
		if err != nil || !got.Equal(want) {
			t.Fatal("bounded extension or reduction rejected", err)
		}
	}
	for _, raw := range []string{
		`{"expires":2000000181}`, `{"expires":2000000000}`, `{"expires":-1}`,
		`{"expires":2000000060,"secret":"replace"}`, `{"expires":2000000060}{}`, `{}`, `null`,
	} {
		if _, err := Renewal([]byte(raw), now, current); err == nil {
			t.Fatal("unsafe renewal accepted", raw)
		}
	}
	if _, err := Renewal([]byte(`{"expires":2000000060}`), now, now); err == nil {
		t.Fatal("expired grant revived")
	}
}
