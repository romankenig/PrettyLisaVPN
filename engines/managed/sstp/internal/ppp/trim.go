// SPDX-License-Identifier: MIT
// Extracted from veepin dataplane/shape.go; see ../../UPSTREAM.md.
package ppp

import "encoding/binary"

func trimToIP(plain []byte) []byte {
	if len(plain) == 0 {
		return nil // keepalive
	}
	switch plain[0] >> 4 {
	case 4:
		if len(plain) < 20 {
			return nil
		}
		total := int(binary.BigEndian.Uint16(plain[2:4]))
		if total < 20 || total > len(plain) {
			return nil
		}
		return plain[:total]
	case 6:
		if len(plain) < 40 {
			return nil
		}
		total := 40 + int(binary.BigEndian.Uint16(plain[4:6]))
		if total > len(plain) {
			return nil
		}
		return plain[:total]
	}
	return nil
}
