// SPDX-License-Identifier: MIT
// Independently implemented compatibility adapter for the two token-bucket
// methods used by the pinned REALITY dependency. No upstream implementation is
// included. This is not a general replacement for the juju/ratelimit package.
package ratelimit

import (
	"math"
	"sync"
	"time"
)

type Bucket struct {
	mu       sync.Mutex
	rate     float64
	capacity float64
	tokens   float64
	updated  time.Time
}

func NewBucketWithRate(rate float64, capacity int64) *Bucket {
	if rate <= 0 || math.IsNaN(rate) || math.IsInf(rate, 0) || capacity <= 0 {
		panic("invalid token bucket")
	}
	return &Bucket{rate: rate, capacity: float64(capacity), tokens: float64(capacity), updated: time.Now()}
}

func (b *Bucket) Wait(count int64) {
	if count <= 0 {
		return
	}
	if delay := b.reserve(count, time.Now()); delay > 0 {
		time.Sleep(delay)
	}
}

func (b *Bucket) reserve(count int64, now time.Time) time.Duration {
	b.mu.Lock()
	defer b.mu.Unlock()
	if count <= 0 {
		return 0
	}
	if elapsed := now.Sub(b.updated).Seconds(); elapsed > 0 {
		b.tokens = math.Min(b.capacity, b.tokens+elapsed*b.rate)
		b.updated = now
	}
	b.tokens -= float64(count)
	if b.tokens >= 0 {
		return 0
	}
	delay := math.Ceil(-b.tokens / b.rate * float64(time.Second))
	if delay >= float64(math.MaxInt64) {
		return time.Duration(math.MaxInt64)
	}
	return time.Duration(delay)
}
