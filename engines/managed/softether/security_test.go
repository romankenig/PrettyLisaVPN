// SPDX-License-Identifier: MIT
package softether

import (
	"bufio"
	"context"
	"crypto/tls"
	"encoding/binary"
	"net"
	"testing"
	"time"

	"github.com/romankenig/PrettyLisaVPN/engines/managed/internal/pinnedtls"
)

func TestControlRejectsDuplicateFieldsAndTrailingData(t *testing.T) {
	p := NewPack()
	p.Add("authtype", TypeInt, IntValue(0))
	p.Add("authtype", TypeInt, IntValue(1))
	raw, _ := p.Encode()
	if _, err := Decode(raw); err == nil {
		t.Fatal("ambiguous authentication accepted")
	}
	p = NewPack()
	p.Add("authtype", TypeInt, IntValue(1))
	raw, _ = p.Encode()
	if _, err := Decode(append(raw, 0)); err == nil {
		t.Fatal("trailing control data accepted")
	}
	if _, err := Decode(make([]byte, MaxPackSize+1)); err == nil {
		t.Fatal("oversized control accepted")
	}
}

func TestNoFramesBeforeAuthenticationAndNoChallengeReplay(t *testing.T) {
	cert, pin := certificate(t)
	var previous [sha0Size]byte
	for _, mode := range []string{"frames", "replay", "anonymous"} {
		t.Run(mode, func(t *testing.T) {
			l, accepted := listener(t, cert)
			cfg, err := pinnedtls.Config("vpn.example.com", pin)
			if err != nil {
				t.Fatal(err)
			}
			c, err := tls.DialWithDialer(&net.Dialer{Timeout: time.Second}, "tcp", l.Addr().String(), cfg)
			if err != nil {
				t.Fatal(err)
			}
			defer c.Close()
			_ = c.SetDeadline(time.Now().Add(2 * time.Second))
			if err = writeSignature(c, "vpn.example.com"); err != nil {
				t.Fatal(err)
			}
			br := bufio.NewReader(c)
			hello, err := recvPackHTTP(br, false)
			if err != nil {
				t.Fatal(err)
			}
			var challenge [sha0Size]byte
			copy(challenge[:], hello.GetData("random"))
			if mode == "frames" {
				previous = challenge
				_ = writeBlocks(c, [][]byte{make([]byte, 64)})
			} else {
				chosen := previous
				if mode == "anonymous" {
					chosen = challenge
				}
				digest := securePassword(hashPassword("vpn", "test-authorization-123"), chosen)
				p := NewPack()
				for k, v := range map[string]string{"method": "login", "hubname": "DEFAULT", "username": "vpn"} {
					p.Add(k, TypeStr, StrValue(v))
				}
				kind := uint32(1)
				if mode == "anonymous" {
					kind = 0
				}
				p.Add("authtype", TypeInt, IntValue(kind))
				p.Add("secure_password", TypeData, DataValue(digest[:]))
				p.Add("use_encrypt", TypeInt, IntValue(1))
				p.Add("max_connection", TypeInt, IntValue(1))
				_ = sendPackHTTP(c, p, false, "vpn.example.com")
			}
			var b [1]byte
			if _, err = br.Read(b[:]); err == nil {
				t.Fatal("server answered unauthorized session")
			}
			select {
			case s := <-accepted:
				_ = s.Close()
				t.Fatal("data plane exposed without current authentication")
			default:
			}
		})
	}
}

func TestAuthenticatedClientCannotSpoofInnerSource(t *testing.T) {
	cert, pin := certificate(t)
	l, accepted := listener(t, cert)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	c, err := Dial(ctx, l.Addr().String(), "test-authorization-123", "vpn.example.com", pin, (&net.Dialer{}).DialContext)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	s := <-accepted
	defer s.Close()
	p := ipPacket(net.IPv4(10, 0, 0, 7), net.IPv4(1, 1, 1, 1))
	if c.WritePacket(p) == nil {
		t.Fatal("client accepted spoofed source")
	}
	f := make([]byte, 14+len(p))
	copy(f[:6], s.mac[:])
	copy(f[6:12], c.mac[:])
	binary.BigEndian.PutUint16(f[12:14], 0x0800)
	copy(f[14:], p)
	if err = c.writeFrame(f); err != nil {
		t.Fatal(err)
	}
	select {
	case <-s.Done():
	case <-ctx.Done():
		t.Fatal("server accepted spoofed source")
	}
}
