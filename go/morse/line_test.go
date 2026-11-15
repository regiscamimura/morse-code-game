package morse

import (
	"strings"
	"testing"
)

// fakeExchange stands in for exchange/src/index.ts: it rings, connects, passes keys and hangs
// up between the games on it, all in memory.
type fakeExchange struct {
	lines map[int]*fakeWire
}

type fakeWire struct {
	exchange *fakeExchange
	number   int
	codename string
	open     bool
	state    string // "idle", "calling", "ringing" or "connected"
	peer     int
	inbox    []WireMessage
}

func (x *fakeExchange) line(number int) *fakeWire {
	w := &fakeWire{exchange: x, number: number, state: "idle"}
	x.lines[number] = w
	return w
}

func (w *fakeWire) Open(secret, codename string) {
	w.open, w.codename, w.state = true, codename, "idle"
	w.inbox = append(w.inbox, WireMessage{Type: "welcome", Number: w.number})
}

func (w *fakeWire) Close() { w.open = false }

func (w *fakeWire) Receive() []WireMessage {
	inbox := w.inbox
	w.inbox = nil
	return inbox
}

func (w *fakeWire) Send(m WireMessage) {
	if !w.open {
		return
	}
	peer := w.exchange.lines[w.peer]
	switch m.Type {
	case "dial":
		callee := w.exchange.lines[m.Number]
		if callee == nil || !callee.open || callee.state != "idle" {
			w.inbox = append(w.inbox, WireMessage{Type: "no_answer", Number: m.Number, Reason: "offline"})
			return
		}
		w.state, w.peer, callee.state, callee.peer = "calling", m.Number, "ringing", w.number
		callee.inbox = append(callee.inbox, WireMessage{Type: "ring", Number: w.number, Codename: w.codename})
	case "answer":
		w.state, peer.state = "connected", "connected"
		w.inbox = append(w.inbox, WireMessage{Type: "connected", Number: peer.number, Codename: peer.codename})
		peer.inbox = append(peer.inbox, WireMessage{Type: "connected", Number: w.number, Codename: w.codename})
	case "key", "lights", "reveal":
		if w.state == "connected" {
			peer.inbox = append(peer.inbox, m)
		}
	case "hangup":
		if peer != nil {
			peer.state, peer.peer = "idle", 0
			peer.inbox = append(peer.inbox, WireMessage{Type: "hung_up"})
		}
		w.state, w.peer = "idle", 0
	}
}

// TestCallAcrossTheLine: one player picks a codename, dials the other, who answers; an E keyed
// at one end is decoded at the other, hidden there until the lights or the reveal are turned on,
// which the keying end sees; hanging up sends both back to the switchboard.
func TestCallAcrossTheLine(t *testing.T) {
	exchange := &fakeExchange{lines: map[int]*fakeWire{}}
	now := 0.0
	newPlayer := func(number int) *Game {
		cfg := DefaultConfig()
		cfg.Wire = exchange.line(number)
		g := NewGame(cfg, NewMixer(0), now)
		g.Key(KeyEnter, now) // language → title
		return g
	}
	caller, callee := newPlayer(100), newPlayer(101)
	run := func(seconds float64) {
		for end := now + seconds; now < end; now += 1.0 / 60 {
			caller.Tick(now)
			callee.Tick(now)
		}
	}
	pickCodename := func(g *Game, name string) {
		g.Key("w", now)
		for _, ch := range name {
			g.Key(string(ch), now)
		}
		g.Key(KeyEnter, now)
	}
	pickCodename(caller, "coruja")
	pickCodename(callee, "AGUIA")
	run(.1)
	if caller.State() != "switchboard" || caller.LineNumber() != "MORSE 100" || caller.line.codename != "CORUJA" {
		t.Fatalf("caller at %s as %s %s", caller.State(), caller.LineNumber(), caller.line.codename)
	}

	for _, digit := range "101" {
		caller.Key(string(digit), now)
	}
	caller.Key(KeyEnter, now)
	run(.1)
	if caller.State() != "calling" || callee.State() != "ringing" || callee.line.peerCodename != "CORUJA" {
		t.Fatalf("after dialling: caller %s, callee %s hearing %q", caller.State(), callee.State(), callee.line.peerCodename)
	}
	callee.Key(KeyEnter, now)
	run(.1)
	if caller.State() != "line" || callee.State() != "line" {
		t.Fatalf("after answering: caller %s, callee %s", caller.State(), callee.State())
	}

	caller.SpaceDown(now)
	run(.08)
	caller.SpaceUp(now)
	run(lineDelay - .03) // the middle of the dit, replayed lineDelay after it arrived
	if !callee.line.remoteToneOn {
		t.Error("the dit isn't sounding at the far end a moment after it was keyed")
	}
	run(1.5)
	if got := strings.TrimSpace(callee.line.remoteText); got != "E" {
		t.Errorf("far end decoded %q, want E", got)
	}
	if got := strings.TrimSpace(caller.freeText); got != "E" {
		t.Errorf("near end decoded %q, want E", got)
	}
	if callee.line.mine != (peek{}) || caller.peerPeeking() != "" {
		t.Error("the far end can see the keying before turning on the lights or revealing")
	}
	callee.Key("l", now)
	callee.Key("r", now)
	run(.1)
	if want := Dot + " /"; callee.line.remoteTape != want {
		t.Errorf("lights show %q, want %q", callee.line.remoteTape, want)
	}
	if want := "AGUIA: " + callee.text("peer_lights", nil) + " · " + callee.text("peer_reveal", nil); caller.peerPeeking() != want {
		t.Errorf("caller sees the callee peeking at %q, want %q", caller.peerPeeking(), want)
	}
	callee.Key("l", now)
	run(.1)
	if caller.peerPeeking() != "AGUIA: "+caller.text("peer_reveal", nil) {
		t.Errorf("after the lights went off, the caller sees %q", caller.peerPeeking())
	}

	callee.SpaceDown(now)   // the key held as the notes open...
	callee.Key(KeyTab, now) // the notes: the keyboard out, the key away
	if callee.keyer.Down() || callee.line.sentToneOn {
		t.Error("the key stayed down, its tone on, after the notes opened")
	}
	for _, k := range []string{"s", "o", " ", "s", KeyBackspace, "x"} {
		callee.Key(k, now)
	}
	callee.SpaceDown(now)
	if callee.line.notes != "SO X " || callee.Keying() || !callee.Typing() {
		t.Errorf("notes %q, keying %v", callee.line.notes, callee.Keying())
	}
	callee.Key(KeyTab, now)
	if !callee.Keying() || callee.line.notes != "SO X " {
		t.Errorf("back to the key: keying %v, notes %q", callee.Keying(), callee.line.notes)
	}

	caller.Key(KeyEscape, now)
	run(.1)
	if caller.State() != "switchboard" || callee.State() != "switchboard" || callee.msg != callee.text("line_closed", nil) {
		t.Errorf("after hanging up: caller %s, callee %s saying %q", caller.State(), callee.State(), callee.msg)
	}
}

func TestDialTurnsAndReturns(t *testing.T) {
	turn := dialTurn{digit: "0", start: 0}
	if got := turn.rotation(turn.windSeconds()); got != 330 {
		t.Errorf("0 winds the dial to %v°, want 330°", got)
	}
	if got := turn.rotation(turn.end() + .01); got != 0 {
		t.Errorf("after its ten pulses the dial is at %v°, want 0°", got)
	}
}

// TestTailOfWordsNeverCutsALetter: the lights' tape, too long to show, loses whole letters.
func TestTailOfWordsNeverCutsALetter(t *testing.T) {
	tape := "••• ━━━ ••• / •••• ••"
	for n, want := range map[int]string{30: tape, 9: "•••• ••", 8: "•••• ••", 5: "••"} {
		if got := tailOfWords(tape, n); got != want {
			t.Errorf("tailOfWords(%q, %d) = %q, want %q", tape, n, got, want)
		}
	}
}
