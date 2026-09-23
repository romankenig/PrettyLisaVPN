//go:build linux

// PrettyLisaVPN's Linux TUN adapter. RFC 9484 and all cryptography are supplied
// by connect-ip-go, quic-go and Go's TLS implementation.
package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log"
	"log/slog"
	"net/http"
	"net/netip"
	"os"
	"os/exec"
	"regexp"
	"sync"
	"syscall"
	"time"

	connectip "github.com/quic-go/connect-ip-go"
	"github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/http3"
	"github.com/yosida95/uritemplate/v3"
	"golang.org/x/sys/unix"
)

type config struct {
	Mode        string            `json:"mode"`
	Endpoint    string            `json:"endpoint"`
	ServerName  string            `json:"server_name"`
	Interface   string            `json:"interface"`
	Address     string            `json:"address"`
	Certificate string            `json:"certificate"`
	PrivateKey  string            `json:"private_key"`
	CA          string            `json:"ca"`
	Clients     map[string]string `json:"clients"` // SHA256 certificate -> assigned IPv4
	ClientsFile string            `json:"clients_file,omitempty"`
}

var invalid = errors.New("invalid configuration")

func readConfig(path string) (config, error) {
	var c config
	f, err := os.Open(path)
	if err != nil {
		return c, invalid
	}
	defer f.Close()
	d := json.NewDecoder(io.LimitReader(f, 1<<20))
	d.DisallowUnknownFields()
	if d.Decode(&c) != nil {
		return c, invalid
	}
	if c.ClientsFile != "" {
		registry, err := os.Open(c.ClientsFile)
		if err != nil {
			return c, invalid
		}
		defer registry.Close()
		if json.NewDecoder(io.LimitReader(registry, 1<<20)).Decode(&c.Clients) != nil {
			return c, invalid
		}
	}
	if !regexp.MustCompile(`^[a-zA-Z][a-zA-Z0-9_-]{0,14}$`).MatchString(c.Interface) {
		return c, invalid
	}
	a, err := netip.ParsePrefix(c.Address)
	if err != nil || !a.Addr().Is4() || !a.Addr().IsPrivate() {
		return c, invalid
	}
	ep, err := netip.ParseAddrPort(c.Endpoint)
	if err != nil || !ep.Addr().Is4() || ep.Port() != 443 {
		return c, invalid
	}
	if !regexp.MustCompile(`^[a-zA-Z0-9.-]{1,253}$`).MatchString(c.ServerName) {
		return c, invalid
	}
	if c.Mode != "server" && c.Mode != "client" {
		return c, invalid
	}
	seen := map[netip.Addr]bool{}
	for fingerprint, value := range c.Clients {
		hash, e := hex.DecodeString(fingerprint)
		ip, e2 := netip.ParseAddr(value)
		if e != nil || len(hash) != 32 || e2 != nil || !a.Contains(ip) || ip == a.Addr() || ip == a.Masked().Addr() || seen[ip] {
			return c, invalid
		}
		seen[ip] = true
	}
	if len(c.Clients) > 1024 {
		return c, invalid
	}
	return c, nil
}

func tlsConfig(c config) (*tls.Config, error) {
	pair, err := tls.LoadX509KeyPair(c.Certificate, c.PrivateKey)
	if err != nil {
		return nil, invalid
	}
	pem, err := os.ReadFile(c.CA)
	if err != nil {
		return nil, invalid
	}
	ca := x509.NewCertPool()
	if !ca.AppendCertsFromPEM(pem) {
		return nil, invalid
	}
	t := &tls.Config{MinVersion: tls.VersionTLS13, Certificates: []tls.Certificate{pair}, RootCAs: ca, ServerName: c.ServerName, NextProtos: []string{http3.NextProtoH3}}
	if c.Mode == "server" {
		t.ClientCAs = ca
		t.ClientAuth = tls.RequireAndVerifyClientCert
	}
	return t, nil
}

func tun(c config) (*os.File, error) {
	fd, err := unix.Open("/dev/net/tun", unix.O_RDWR|unix.O_CLOEXEC|unix.O_NONBLOCK, 0)
	if err != nil {
		return nil, err
	}
	req, err := unix.NewIfreq(c.Interface)
	if err != nil {
		unix.Close(fd)
		return nil, err
	}
	req.SetUint16(unix.IFF_TUN | unix.IFF_NO_PI)
	if err = unix.IoctlIfreq(fd, unix.TUNSETIFF, req); err != nil {
		unix.Close(fd)
		return nil, err
	}
	// Register with Go's poller only after TUNSETIFF. An unconfigured TUN fd
	// cannot be polled and os.OpenFile can permanently mark it non-pollable.
	f := os.NewFile(uintptr(fd), "/dev/net/tun")
	for _, args := range [][]string{{"address", "replace", c.Address, "dev", c.Interface}, {"link", "set", "dev", c.Interface, "mtu", "1280", "up"}} {
		if exec.Command("/usr/sbin/ip", args...).Run() != nil {
			f.Close()
			return nil, invalid
		}
	}
	return f, nil
}

func packet(p []byte) (netip.Addr, netip.Addr, bool) {
	if len(p) < 20 || len(p) > 1280 || p[0]>>4 != 4 {
		return netip.Addr{}, netip.Addr{}, false
	}
	h := int(p[0]&15) * 4
	if h < 20 || h > len(p) || int(binary.BigEndian.Uint16(p[2:4])) != len(p) {
		return netip.Addr{}, netip.Addr{}, false
	}
	return netip.AddrFrom4([4]byte(p[12:16])), netip.AddrFrom4([4]byte(p[16:20])), true
}

func public(ip netip.Addr) bool {
	if !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsLoopback() {
		return false
	}
	for _, s := range []string{"0.0.0.0/8", "100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4"} {
		if netip.MustParsePrefix(s).Contains(ip) {
			return false
		}
	}
	return true
}

type session struct {
	conn    *connectip.Conn
	packets chan []byte
	done    chan struct{}
}

func server(c config, t *tls.Config, f *os.File) error {
	var mu sync.Mutex
	sessions := map[netip.Addr]*session{}
	go func() {
		b := make([]byte, 65535)
		for {
			n, err := f.Read(b)
			if err != nil {
				return
			}
			_, dst, ok := packet(b[:n])
			if !ok {
				continue
			}
			mu.Lock()
			s := sessions[dst]
			mu.Unlock()
			if s != nil {
				select {
				case s.packets <- append([]byte(nil), b[:n]...):
				default:
				}
			}
		}
	}()
	template := uritemplate.MustNew("https://" + c.ServerName + "/vpn")
	proxy := connectip.Proxy{}
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/vpn" || r.TLS == nil || len(r.TLS.VerifiedChains) == 0 {
			w.WriteHeader(403)
			return
		}
		hash := sha256.Sum256(r.TLS.PeerCertificates[0].Raw)
		ip, err := netip.ParseAddr(c.Clients[hex.EncodeToString(hash[:])])
		if err != nil {
			w.WriteHeader(403)
			return
		}
		req, err := connectip.ParseProxyRequest(r, template)
		if err != nil {
			w.WriteHeader(400)
			return
		}
		mu.Lock()
		if sessions[ip] != nil {
			mu.Unlock()
			w.WriteHeader(409)
			return
		}
		s := &session{packets: make(chan []byte, 64), done: make(chan struct{})}
		sessions[ip] = s
		mu.Unlock()
		defer func() { mu.Lock(); delete(sessions, ip); mu.Unlock(); close(s.done) }()
		conn, err := proxy.Proxy(w, req)
		if err != nil {
			return
		}
		s.conn = conn
		defer conn.Close()
		if conn.AssignAddresses([]netip.Prefix{netip.PrefixFrom(ip, 32)}) != nil {
			return
		}
		if conn.AdvertiseRoute([]connectip.IPRoute{{StartIP: netip.MustParseAddr("0.0.0.0"), EndIP: netip.MustParseAddr("255.255.255.255")}}) != nil {
			return
		}
		go func() {
			for {
				select {
				case p := <-s.packets:
					icmp, err := conn.WritePacket(p)
					if len(icmp) > 0 {
						f.Write(icmp)
					}
					if err != nil {
						conn.Close()
						return
					}
				case <-s.done:
					return
				}
			}
		}()
		slog.Info("tunnel_established")
		b := make([]byte, 65535)
		endpoint := netip.MustParseAddrPort(c.Endpoint).Addr()
		for {
			n, err := conn.ReadPacket(b)
			if err != nil {
				return
			}
			src, dst, ok := packet(b[:n])
			if !ok || src != ip || !public(dst) || dst == endpoint {
				continue
			}
			if _, err = f.Write(b[:n]); err != nil {
				return
			}
		}
	})
	srv := http3.Server{Addr: c.Endpoint, TLSConfig: t, Handler: handler, EnableDatagrams: true, QUICConfig: &quic.Config{EnableDatagrams: true, MaxIncomingStreams: 4, MaxIdleTimeout: 60 * time.Second, HandshakeIdleTimeout: 10 * time.Second}, MaxHeaderBytes: 8192}
	return srv.ListenAndServe()
}

func client(c config, t *tls.Config, f *os.File) error {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	tr := connectip.Transport{TLSClientConfig: t, QUICConfig: &quic.Config{EnableDatagrams: true, InitialPacketSize: 1350, KeepAlivePeriod: 10 * time.Second, MaxIdleTimeout: 60 * time.Second}, DialAddr: func(ctx context.Context, _ string, t *tls.Config, q *quic.Config) (*quic.Conn, error) {
		return quic.DialAddr(ctx, c.Endpoint, t, q)
	}}
	req, err := connectip.NewRequest(ctx, uritemplate.MustNew("https://"+c.ServerName+"/vpn"))
	if err != nil {
		return err
	}
	conn, _, err := tr.Dial(req)
	if err != nil {
		slog.Error("connect_ip_failed")
		return err
	}
	defer conn.Close()
	check, stop := context.WithTimeout(ctx, 10*time.Second)
	defer stop()
	prefixes, err := conn.LocalPrefixes(check)
	if err != nil {
		slog.Error("address_assignment_failed")
		return err
	}
	assigned := netip.MustParsePrefix(c.Address).Addr()
	if len(prefixes) != 1 || prefixes[0] != netip.PrefixFrom(assigned, 32) {
		return invalid
	}
	// Host/default routes are deliberately owned by the isolated external runner.
	slog.Info("tunnel_established")
	go func() {
		b := make([]byte, 65535)
		for {
			n, err := f.Read(b)
			if err != nil {
				var code syscall.Errno
				errors.As(err, &code)
				slog.Error("tun_read_failed", "errno", int(code), "eof", errors.Is(err, io.EOF))
				conn.Close()
				return
			}
			_, _, ok := packet(b[:n])
			if !ok {
				continue
			}
			icmp, err := conn.WritePacket(b[:n])
			if len(icmp) > 0 {
				f.Write(icmp)
			}
			if err != nil {
				slog.Error("datagram_write_failed")
				conn.Close()
				return
			}
		}
	}()
	b := make([]byte, 65535)
	for {
		n, err := conn.ReadPacket(b)
		if err != nil {
			slog.Error("datagram_read_failed")
			return err
		}
		_, dst, ok := packet(b[:n])
		if ok && dst == assigned {
			if _, err = f.Write(b[:n]); err != nil {
				return err
			}
		}
	}
}

func main() {
	// Upstream logs can contain rejected packet addresses. Never emit these.
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stderr, nil)))
	log.SetOutput(io.Discard)
	if len(os.Args) != 2 {
		slog.Error("configuration_failed")
		os.Exit(1)
	}
	c, err := readConfig(os.Args[1])
	if err == nil {
		var t *tls.Config
		t, err = tlsConfig(c)
		if err == nil {
			var f *os.File
			f, err = tun(c)
			if err == nil {
				defer f.Close()
				if c.Mode == "server" {
					err = server(c, t, f)
				} else {
					err = client(c, t, f)
				}
			}
		}
	}
	if err != nil {
		slog.Error("adapter_failed")
		os.Exit(1)
	}
}
