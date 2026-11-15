package node

import (
	"net"
	"testing"
)

func TestServiceProbeRestrictsCatalogAndPublicAddresses(t *testing.T) {
	domains := []string{"service.example", "*.service.example"}
	for _, value := range []string{"https://service.example/news/new", "https://www.service.example/post?id=2"} {
		if !allowedServiceURL(value, domains) {
			t.Fatal("rejected service URL")
		}
	}
	for _, value := range []string{"http://service.example/a", "https://service.example.evil.test/a", "https://user@service.example/a", "https://service.example:444/a", "https://service.example/a#fragment"} {
		if allowedServiceURL(value, domains) {
			t.Fatal("accepted unsafe URL")
		}
	}
	for _, value := range []string{"127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1", "192.0.2.1", "240.0.0.1", "::1"} {
		if publicServiceIP(net.ParseIP(value)) {
			t.Fatal("accepted nonpublic address")
		}
	}
	if !publicServiceIP(net.ParseIP("1.1.1.1")) {
		t.Fatal("rejected public address")
	}
}
