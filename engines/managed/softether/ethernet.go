// SPDX-License-Identifier: MIT
package softether

import (
	"bytes"
	"encoding/binary"
)

func (s *Session) addresses() ([]byte, []byte) {
	if s.server {
		return ServerIP, ClientIP
	}
	return ClientIP, ServerIP
}
func (s *Session) learnMAC(mac []byte) bool {
	if len(mac) != 6 || mac[0]&1 != 0 || bytes.Equal(mac, make([]byte, 6)) {
		return false
	}
	s.peerMu.Lock()
	defer s.peerMu.Unlock()
	select {
	case <-s.peerReady:
		return bytes.Equal(s.peerMAC[:], mac)
	default:
	}
	copy(s.peerMAC[:], mac)
	s.peerOnce.Do(func() { close(s.peerReady) })
	return true
}
func (s *Session) sendARP(operation uint16, target [6]byte) error {
	local, peer := s.addresses()
	f := make([]byte, 42)
	copy(f[:6], target[:])
	copy(f[6:12], s.mac[:])
	binary.BigEndian.PutUint16(f[12:14], 0x0806)
	a := f[14:]
	copy(a[:6], []byte{0, 1, 8, 0, 6, 4})
	binary.BigEndian.PutUint16(a[6:8], operation)
	copy(a[8:14], s.mac[:])
	copy(a[14:18], local)
	if operation == 2 {
		copy(a[18:24], target[:])
	}
	copy(a[24:28], peer)
	return s.writeFrame(f)
}
func (s *Session) acceptARP(f []byte) error {
	if len(f) < 42 {
		return ErrProtocol
	}
	a := f[14:42]
	local, peer := s.addresses()
	op := binary.BigEndian.Uint16(a[6:8])
	if !bytes.Equal(a[:6], []byte{0, 1, 8, 0, 6, 4}) || (op != 1 && op != 2) {
		return nil
	}
	if !bytes.Equal(a[14:18], peer) || !bytes.Equal(a[24:28], local) {
		return nil
	}
	if !bytes.Equal(f[6:12], a[8:14]) || !s.learnMAC(a[8:14]) {
		return ErrProtocol
	}
	if op == 1 {
		var target [6]byte
		copy(target[:], a[8:14])
		return s.sendARP(2, target)
	}
	return nil
}
func validIPv4(p []byte) ([]byte, bool) {
	if len(p) < 20 || p[0]>>4 != 4 {
		return nil, false
	}
	header := int(p[0]&15) * 4
	size := int(binary.BigEndian.Uint16(p[2:4]))
	if header < 20 || size < header || size > MTU || size > len(p) {
		return nil, false
	}
	return p[:size], true
}
func (s *Session) WritePacket(packet []byte) error {
	p, ok := validIPv4(packet)
	if !ok {
		return ErrProtocol
	}
	if (!s.server && !bytes.Equal(p[12:16], ClientIP)) || (s.server && !bytes.Equal(p[16:20], ClientIP)) {
		return ErrProtocol
	}
	select {
	case <-s.peerReady:
	default:
		return ErrProtocol
	}
	s.peerMu.Lock()
	target := s.peerMAC
	s.peerMu.Unlock()
	f := make([]byte, 14+len(p))
	copy(f[:6], target[:])
	copy(f[6:12], s.mac[:])
	binary.BigEndian.PutUint16(f[12:14], 0x0800)
	copy(f[14:], p)
	return s.writeFrame(f)
}
func (s *Session) readLoop() {
	defer s.Close()
	r := newBlockReader(s.br)
	for {
		f, err := r.next()
		if err != nil {
			return
		}
		if len(f) < 14 {
			continue
		}
		switch binary.BigEndian.Uint16(f[12:14]) {
		case 0x0806:
			if s.acceptARP(f) != nil {
				return
			}
		case 0x0800:
			if !bytes.Equal(f[:6], s.mac[:]) {
				continue
			}
			p, ok := validIPv4(f[14:])
			if !ok {
				continue
			}
			if (s.server && !bytes.Equal(p[12:16], ClientIP)) || (!s.server && !bytes.Equal(p[16:20], ClientIP)) {
				return
			}
			if !s.learnMAC(f[6:12]) {
				return
			}
			select {
			case s.packets <- append([]byte(nil), p...):
			case <-s.done:
				return
			default:
			}
		}
	}
}
