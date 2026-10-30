// SPDX-License-Identifier: MIT
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"time"

	"github.com/romankenig/PrettyLisaVPN/engines/managed/node"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/features/stats"
)

func run() int {
	if len(os.Args) == 2 && os.Args[1] == "--probe" {
		raw, err := io.ReadAll(io.LimitReader(os.Stdin, 131073))
		if err != nil {
			return 1
		}
		result := node.Probe(raw)
		clear(raw)
		if json.NewEncoder(os.Stdout).Encode(result) != nil {
			return 1
		}
		return 0
	}
	if len(os.Args) == 3 && os.Args[1] == "--identity" {
		identity, err := node.NewIdentity(os.Args[2], time.Now())
		if err != nil || json.NewEncoder(os.Stdout).Encode(identity) != nil {
			return 1
		}
		return 0
	}
	input := bufio.NewScanner(os.Stdin)
	input.Buffer(make([]byte, 1024), 65536)
	if !input.Scan() {
		return 1
	}
	lease, err := node.Parse(input.Bytes(), time.Now())
	if err != nil || len(os.Args) != 3 || os.Args[1] != "--lease" || os.Args[2] != lease.ID {
		return 1
	}
	config, err := lease.Config()
	if err != nil {
		return 1
	}
	instance, err := core.New(config)
	if err != nil {
		return 1
	}
	// This process owns one lease. Exit closes listeners AND established sockets;
	// waiting for a graceful core shutdown could otherwise delay revocation.
	if instance.Start() != nil {
		return 1
	}
	if _, err := fmt.Fprintln(os.Stdout, "READY"); err != nil {
		return 1
	}
	frames := make(chan []byte)
	go func() {
		defer close(frames)
		for input.Scan() {
			frames <- append([]byte(nil), input.Bytes()...)
		}
	}()
	expires := time.Unix(lease.Expires, 0)
	timer := time.NewTimer(time.Until(expires))
	defer timer.Stop()
	ticks := time.NewTicker(10 * time.Second)
	defer ticks.Stop()
	for {
		select {
		case frame, ok := <-frames:
			if !ok {
				return 0
			}
			renewed, err := node.Renewal(frame, time.Now(), expires)
			clear(frame)
			if err != nil {
				return 1
			}
			expires = renewed
			timer.Reset(time.Until(expires))
		case <-timer.C:
			return 0
		case <-ticks.C:
			// Aggregate byte counters only; no users, peer addresses or destinations.
			manager, ok := instance.GetFeature(stats.ManagerType()).(stats.Manager)
			if !ok {
				return 1
			}
			value := func(name string) int64 {
				if counter := manager.GetCounter("inbound>>>authorized>>>traffic>>>" + name); counter != nil {
					return counter.Value()
				}
				return 0
			}
			if json.NewEncoder(os.Stdout).Encode(map[string]int64{"rx_bytes": value("uplink"), "tx_bytes": value("downlink")}) != nil {
				return 1
			}
		}
	}
}
func main() {
	if sink, err := os.OpenFile(os.DevNull, os.O_WRONLY, 0); err == nil {
		os.Stderr = sink
	}
	os.Exit(run()) // Process exit closes even connections which outlive core.Close.
}
