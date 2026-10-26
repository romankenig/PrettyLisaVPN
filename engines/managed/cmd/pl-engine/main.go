// SPDX-License-Identifier: MIT
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"io"
	"log"
	"os"

	managed "github.com/romankenig/PrettyLisaVPN/engines/managed"
)

type command struct {
	Action  string          `json:"action"`
	Profile json.RawMessage `json:"profile,omitempty"`
}
type response struct {
	Status  string `json:"status"`
	Version string `json:"version,omitempty"`
}

func main() {
	// No core diagnostics, destination logs, config snapshots or crash recorders.
	log.SetOutput(io.Discard)
	if sink, err := os.OpenFile(os.DevNull, os.O_WRONLY, 0); err == nil {
		os.Stderr = sink
	}
	engine := managed.NewRuntime()
	defer engine.Stop()
	input := bufio.NewScanner(os.Stdin)
	input.Buffer(make([]byte, 4096), managed.MaxProfileBytes+1024)
	output := json.NewEncoder(os.Stdout)
	for input.Scan() {
		var c command
		decoder := json.NewDecoder(bytes.NewReader(input.Bytes()))
		decoder.DisallowUnknownFields()
		result := response{Status: "INVALID_COMMAND"}
		if decoder.Decode(&c) == nil && decoder.Decode(new(any)) == io.EOF {
			switch c.Action {
			case "version":
				result = response{Status: "OK", Version: managed.Version}
			case "start":
				if err := engine.Start(string(c.Profile)); err != nil {
					result.Status = err.Error()
				} else {
					result.Status = "RUNNING"
				}
			case "stop":
				if engine.Stop() != nil {
					result.Status = "ENGINE_STOP_FAILED"
				} else {
					result.Status = "DOWN"
				}
			case "status":
				result.Status = "DOWN"
				if engine.Running() {
					result.Status = "RUNNING"
				}
			}
		}
		clear(c.Profile)
		if output.Encode(result) != nil {
			return
		}
	}
	// EOF or malformed oversized frame ends this process and its tunnel.
}
