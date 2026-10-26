package exchange

import (
	"crypto/rand"
	"encoding/hex"
	"os"
	"testing"
	"time"

	"github.com/regiscamimura/morse-code-game/go/morse"
)

// TestCallThroughTheExchange rings one Client from another through a running exchange and
// sends a key press across. It needs one:
//
//	cd exchange && npm run dev                                  # in another terminal
//	MORSE_EXCHANGE=ws://localhost:8787 go test ./exchange
func TestCallThroughTheExchange(t *testing.T) {
	address := os.Getenv("MORSE_EXCHANGE")
	if address == "" {
		t.Skip("set MORSE_EXCHANGE to a running exchange")
	}
	caller, callee := New(address), New(address)
	caller.Open(newSecret(), "CORUJA")
	callee.Open(newSecret(), "AGUIA")
	defer caller.Close()
	defer callee.Close()
	calleeNumber := waitForMessage(t, callee, "welcome").Number
	waitForMessage(t, caller, "welcome")

	caller.Send(morse.WireMessage{Type: "dial", Number: calleeNumber})
	if ring := waitForMessage(t, callee, "ring"); ring.Codename != "CORUJA" {
		t.Errorf("the bell rang for %q, want CORUJA", ring.Codename)
	}
	callee.Send(morse.WireMessage{Type: "answer"})
	waitForMessage(t, caller, "connected")

	caller.Send(morse.WireMessage{Type: "key", Down: true, At: 3.5})
	if key := waitForMessage(t, callee, "key"); !key.Down || key.At != 3.5 {
		t.Errorf("the far end got %+v, want a press at 3.5", key)
	}
}

func newSecret() string {
	secret := make([]byte, 16)
	_, _ = rand.Read(secret)
	return hex.EncodeToString(secret)
}

func waitForMessage(t *testing.T, c *Client, messageType string) morse.WireMessage {
	t.Helper()
	for deadline := time.Now().Add(5 * time.Second); time.Now().Before(deadline); time.Sleep(20 * time.Millisecond) {
		for _, m := range c.Receive() {
			if m.Type == messageType {
				return m
			}
		}
	}
	t.Fatalf("no %q within 5 s", messageType)
	return morse.WireMessage{}
}
