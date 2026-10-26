package terminal

import (
	"reflect"
	"testing"
)

func TestDecodeToken(t *testing.T) {
	cases := []struct {
		token string
		want  []Event
	}{
		{"\x1b[32u", []Event{{Space: true, Down: true}}},
		{"\x1b[32;1:3u", []Event{{Space: true, Down: false}}},
		{"\x1b[32;1:2u", nil},
		{"\x1b[97;2u", []Event{{Key: "a"}}},
		{"\x1b[103;5u", []Event{{Key: "\x07"}}},
		{"\x1b[99;5u", []Event{{Key: KeyInterrupt}}},
		{"\x1b[13u", []Event{{Key: "\n"}}},
		{"\x1b[57441;2u", nil},
		{"\x1b[D", []Event{{Key: "LEFT"}}},
		{"\x1b[1;1:3C", nil},
		{"\x1b", []Event{{Key: "ESC"}}},
		{"\r", []Event{{Key: "\n"}}},
		{"\x03", []Event{{Key: KeyInterrupt}}},
		{"ç", []Event{{Key: "ç"}}},
	}
	for _, c := range cases {
		if got := decodeToken(c.token); !reflect.DeepEqual(got, c.want) {
			t.Errorf("decodeToken(%q) = %v, want %v", c.token, got, c.want)
		}
	}
}

func TestTokens(t *testing.T) {
	got := tokens("a\x1b[32;1:3ub")
	if want := []string{"a", "\x1b[32;1:3u", "b"}; !reflect.DeepEqual(got, want) {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestHasSpaceKey(t *testing.T) {
	// a real keyboard's bitmap (bit 57 is in the last word) and a power button's
	if !hasSpaceKey("1000000000007 ff9f207ac14057ff febeffdfffefffff fffffffffffffffe") {
		t.Error("keyboard not recognised")
	}
	if hasSpaceKey("10000000000000 0") {
		t.Error("power button taken for a keyboard")
	}
}
