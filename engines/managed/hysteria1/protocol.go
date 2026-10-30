// SPDX-License-Identifier: MIT
// Hysteria v1 wire layout follows apernet/hysteria v1.3.5 (MIT); see UPSTREAM.md.
package hysteria1

import (
	"bytes"
	"encoding/binary"
	"errors"
	"io"
	"net"
	"strconv"
	"time"
)

var errProtocol = errors.New("HYSTERIA_PROTOCOL_FAILED")

const rate = uint64(30_000_000 / 8)
const maxDatagram = 1000

func write(w io.Writer, value any) error { return binary.Write(w, binary.BigEndian, value) }
func read(r io.Reader, value any) error  { return binary.Read(r, binary.BigEndian, value) }
func putString(w io.Writer, value string, limit int) error {
	if len(value) > limit {
		return errProtocol
	}
	if err := write(w, uint16(len(value))); err != nil {
		return err
	}
	_, err := io.WriteString(w, value)
	return err
}
func getString(r io.Reader, limit int) (string, error) {
	var size uint16
	if err := read(r, &size); err != nil {
		return "", err
	}
	if int(size) > limit {
		return "", errProtocol
	}
	value := make([]byte, size)
	_, err := io.ReadFull(r, value)
	return string(value), err
}
func hello(w io.Writer, secret string) error {
	if err := write(w, uint8(3)); err != nil {
		return err
	}
	if err := write(w, [2]uint64{rate, rate}); err != nil {
		return err
	}
	return putString(w, secret, 128)
}
func readHello(r io.Reader) (string, error) {
	var version uint8
	var speeds [2]uint64
	if read(r, &version) != nil || version != 3 || read(r, &speeds) != nil || speeds[0] == 0 || speeds[1] == 0 {
		return "", errProtocol
	}
	return getString(r, 128)
}
func helloResponse(w io.Writer, accepted bool) error {
	if err := write(w, accepted); err != nil {
		return err
	}
	if err := write(w, [2]uint64{rate, rate}); err != nil {
		return err
	}
	return putString(w, "", 0)
}
func readHelloResponse(r io.Reader) error {
	var accepted bool
	var speeds [2]uint64
	if read(r, &accepted) != nil || read(r, &speeds) != nil {
		return errProtocol
	}
	if _, err := getString(r, 1024); err != nil || !accepted || speeds[0] == 0 || speeds[1] == 0 {
		return errProtocol
	}
	return nil
}
func request(w io.Writer, udp bool, destination string) error {
	host, port := "", uint64(0)
	if !udp {
		var err error
		var raw string
		host, raw, err = net.SplitHostPort(destination)
		if err != nil {
			return errProtocol
		}
		port, err = strconv.ParseUint(raw, 10, 16)
		if err != nil || port == 0 {
			return errProtocol
		}
	}
	if err := write(w, udp); err != nil {
		return err
	}
	if err := putString(w, host, 253); err != nil {
		return err
	}
	return write(w, uint16(port))
}
func readRequest(r io.Reader) (bool, string, error) {
	var udp bool
	var port uint16
	if read(r, &udp) != nil {
		return false, "", errProtocol
	}
	host, err := getString(r, 253)
	if err != nil || read(r, &port) != nil {
		return false, "", errProtocol
	}
	if !udp && (host == "" || port == 0) {
		return false, "", errProtocol
	}
	return udp, net.JoinHostPort(host, strconv.Itoa(int(port))), nil
}
func response(w io.Writer, accepted bool, session uint32) error {
	if err := write(w, accepted); err != nil {
		return err
	}
	if err := write(w, session); err != nil {
		return err
	}
	return putString(w, "", 0)
}
func readResponse(r io.Reader) (uint32, error) {
	var ok bool
	var session uint32
	if read(r, &ok) != nil || read(r, &session) != nil {
		return 0, errProtocol
	}
	if _, err := getString(r, 1024); err != nil || !ok {
		return 0, errProtocol
	}
	return session, nil
}

type datagram struct {
	session      uint32
	host         string
	port         uint16
	id           uint16
	index, count uint8
	data         []byte
}

func (d datagram) encode() ([]byte, error) {
	if len(d.data) > 65507 || len(d.host) > 253 || d.port == 0 || d.count == 0 || d.index >= d.count {
		return nil, errProtocol
	}
	var w bytes.Buffer
	_ = write(&w, d.session)
	_ = putString(&w, d.host, 253)
	_ = write(&w, d.port)
	_ = write(&w, d.id)
	_ = write(&w, d.index)
	_ = write(&w, d.count)
	_ = write(&w, uint16(len(d.data)))
	_, _ = w.Write(d.data)
	return w.Bytes(), nil
}
func decodeDatagram(raw []byte) (datagram, error) {
	r := bytes.NewReader(raw)
	var d datagram
	var size uint16
	var err error
	if len(raw) > 65535 || read(r, &d.session) != nil {
		return d, errProtocol
	}
	d.host, err = getString(r, 253)
	if err != nil || read(r, &d.port) != nil || read(r, &d.id) != nil || read(r, &d.index) != nil || read(r, &d.count) != nil || read(r, &size) != nil || int(size) != r.Len() || d.port == 0 || d.count == 0 || d.index >= d.count {
		return d, errProtocol
	}
	d.data = make([]byte, size)
	_, err = io.ReadFull(r, d.data)
	return d, err
}

// One bounded in-flight fragmented message per UDP session, expiring after 2s.
// A new message replaces old fragments; mismatched destinations never coalesce.
type assembly struct {
	id              uint16
	host            string
	port            uint16
	count           uint8
	parts           [][]byte
	total, received int
	until           time.Time
}

func (a *assembly) accept(d datagram) ([]byte, bool) {
	if d.count == 1 {
		return d.data, true
	}
	if d.id == 0 {
		return nil, false
	}
	if a.id != d.id || a.host != d.host || a.port != d.port || a.count != d.count || time.Now().After(a.until) {
		*a = assembly{id: d.id, host: d.host, port: d.port, count: d.count, parts: make([][]byte, d.count), until: time.Now().Add(2 * time.Second)}
	}
	if a.parts[d.index] != nil {
		return nil, false
	}
	a.total += len(d.data)
	if a.total > 65507 {
		*a = assembly{}
		return nil, false
	}
	a.parts[d.index] = d.data
	a.received++
	if a.received != len(a.parts) {
		return nil, false
	}
	result := bytes.Join(a.parts, nil)
	*a = assembly{}
	return result, true
}
