// SPDX-License-Identifier: MIT
package node

import (
	"bytes"
	"encoding/json"
	"io"
	"time"
)

const MaxLeaseDuration = 180 * time.Second

// A renewal can only move the deadline of the already authenticated process.
// It cannot replace credentials, listeners or routes, or revive an expired grant.
func Renewal(raw []byte, now, current time.Time) (time.Time, error) {
	var command struct {
		Expires int64 `json:"expires"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if len(raw) > 128 || !current.After(now) || decoder.Decode(&command) != nil || decoder.Decode(new(any)) != io.EOF {
		return time.Time{}, ErrConfiguration
	}
	expires := time.Unix(command.Expires, 0)
	if !expires.After(now) || expires.After(now.Add(MaxLeaseDuration)) {
		return time.Time{}, ErrConfiguration
	}
	return expires, nil
}
