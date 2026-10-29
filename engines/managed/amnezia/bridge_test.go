// SPDX-License-Identifier: MIT
package amnezia

import (
	"strconv"
	"strings"
	"testing"
)

func TestObfuscationIsBoundedDistinctAndStablePerIdentity(t *testing.T) {
	a := obfuscation(strings.Repeat("ab", 32))
	if a != obfuscation(strings.Repeat("ab", 32)) || a == obfuscation(strings.Repeat("cd", 32)) {
		t.Fatal("node identity must determine stable distinct parameters")
	}
	values := map[string]uint64{}
	for _, line := range strings.Split(strings.TrimSpace(a), "\n") {
		key, value, ok := strings.Cut(line, "=")
		parsed, err := strconv.ParseUint(value, 10, 32)
		if !ok || err != nil {
			t.Fatal("invalid UAPI field")
		}
		values[key] = parsed
	}
	if len(values) != 9 || values["jc"] != 4 || values["jmin"] >= values["jmax"] || values["s1"]+148 == values["s2"]+92 {
		t.Fatal("invalid padding or noise bounds")
	}
	seen := map[uint64]bool{}
	for _, key := range []string{"h1", "h2", "h3", "h4"} {
		value := values[key]
		if value <= 4 || seen[value] {
			t.Fatal("colliding header")
		}
		seen[value] = true
	}
}
