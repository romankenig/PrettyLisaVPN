// SPDX-License-Identifier: MIT
package ratelimit

import (
	"sync"
	"testing"
	"time"
)

func TestBurstDebtAndRefill(t *testing.T) {
	b := NewBucketWithRate(100, 100)
	now := b.updated
	if b.reserve(100, now) != 0 {
		t.Fatal("initial burst throttled")
	}
	if b.reserve(250, now) != 2500*time.Millisecond {
		t.Fatal("large reservation lost debt")
	}
	if b.reserve(50, now.Add(time.Second)) != 2*time.Second {
		t.Fatal("overlapping request ignored debt")
	}
	if b.reserve(101, now.Add(time.Minute)) != 10*time.Millisecond {
		t.Fatal("idle refill exceeded capacity")
	}
}
func TestConcurrentReservationsShareOneBudget(t *testing.T) {
	b := NewBucketWithRate(100, 100)
	now := b.updated
	var wg sync.WaitGroup
	for range 20 {
		wg.Go(func() { b.reserve(10, now) })
	}
	wg.Wait()
	if delay := b.reserve(100, now); delay != 2*time.Second {
		t.Fatal("concurrent quota lost", delay)
	}
}
func TestWaitDoesNotBlockForUnusedOrAvailableTokens(t *testing.T) {
	b := NewBucketWithRate(100, 100)
	b.Wait(0)
	b.Wait(-1)
	b.Wait(10)
	if b.tokens < 90 {
		t.Fatal("unexpected debit")
	}
}
