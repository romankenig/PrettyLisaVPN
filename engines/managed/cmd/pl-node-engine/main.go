// SPDX-License-Identifier: MIT
package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"time"

	"github.com/romankenig/PrettyLisaVPN/engines/managed/node"
	"github.com/xtls/xray-core/core"
)

func run() int {
	input := bufio.NewScanner(os.Stdin)
	input.Buffer(make([]byte, 1024), 8192)
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
	eof := make(chan struct{})
	go func() { _, _ = io.Copy(io.Discard, os.Stdin); close(eof) }()
	timer := time.NewTimer(time.Until(time.Unix(lease.Expires, 0)))
	defer timer.Stop()
	select {
	case <-eof:
	case <-timer.C:
	}
	return 0
}
func main() {
	if sink, err := os.OpenFile(os.DevNull, os.O_WRONLY, 0); err == nil {
		os.Stderr = sink
	}
	os.Exit(run()) // Process exit closes even connections which outlive core.Close.
}
