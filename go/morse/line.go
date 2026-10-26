package morse

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"math"
	"strconv"
	"strings"
)

// The telegraph line: two players on the telephone exchange key to each other. The player
// picks a codename, then sits at the switchboard with a line number (MORSE 123) where calls
// ring; dialling another number rings that player, and once they answer each side's key is
// heard at the other end. The exchange is a server (exchange/ at the repo root); a front end
// passes the game a Wire to it.
//
// What crosses the line is when the key went down and up, by the sender's clock, never
// sound. The far end replays them lineDelay late, so the spacing that tells a dit from a dah
// survives the network's hiccups, and decodes them with a Keyer of its own.

// Wire is the game's connection to the telephone exchange.
type Wire interface {
	Open(secret, codename string) // connect, and keep reconnecting until Close
	Close()
	Send(m WireMessage)     // dropped while not connected
	Receive() []WireMessage // what arrived since the last call
}

// WireMessage is one message to or from the exchange; exchange/src/index.ts lists them all.
// A Wire adds {"type":"offline"} of its own when the connection drops.
type WireMessage struct {
	Type     string  `json:"type"`
	Number   int     `json:"number,omitempty"`
	Codename string  `json:"codename,omitempty"`
	Reason   string  `json:"reason,omitempty"`
	Down     bool    `json:"down"`
	At       float64 `json:"at,omitempty"`
}

const (
	lineDelay       = .25 // how late the far end's key is replayed
	maxCodenameLen  = 10
	maxDialedDigits = 6
	callTimeout     = 30.0 // an unanswered call gives up after this long
)

// telegraphLine is the game's side of the telephone exchange.
type telegraphLine struct {
	codename, secret string
	number           int    // this game's line number; 0 until the exchange first gives it
	status           string // "connecting", "online" or "offline"
	dialed           string // digits typed at the switchboard
	turns            []dialTurn
	peerNumber       int
	peerCodename     string
	nextRing         float64 // when the bell or the ringback sounds again

	sentToneOn   bool   // what the far end was last told about this player's key
	remote       *Keyer // decodes the far end's key
	remoteText   string // the letters it has keyed
	remoteToneOn bool
	remoteKeys   []remoteKey // heard but not yet replayed
	remoteClock  float64     // add to the far end's times to get this game's
	remoteHeard  float64     // when its last key arrived
}

type remoteKey struct {
	down bool
	at   float64 // on this game's clock
}

// LineNumber is the player's number at the exchange as it's written: "MORSE 123", or just
// "MORSE" until the exchange has given one.
func (g *Game) LineNumber() string {
	if g.line.number == 0 {
		return "MORSE"
	}
	return fmt.Sprintf("MORSE %d", g.line.number)
}

// openLine leaves the title for the switchboard, or first for choosing a codename.
func (g *Game) openLine(now float64) {
	if g.line.secret == "" {
		secret := make([]byte, 16)
		_, _ = rand.Read(secret)
		g.line.secret = hex.EncodeToString(secret)
		g.storeProgress()
	}
	if g.line.codename == "" {
		g.setState("codename", now)
		return
	}
	g.openSwitchboard(now)
}

// openSwitchboard connects to the exchange and waits at the switchboard.
func (g *Game) openSwitchboard(now float64) {
	g.line.status, g.line.dialed, g.line.turns = "connecting", "", nil
	g.cfg.Wire.Open(g.line.secret, g.line.codename)
	g.setState("switchboard", now)
}

// backToSwitchboard ends a call, saying why.
func (g *Game) backToSwitchboard(why string, now float64) {
	g.line.dialed, g.line.turns = "", nil
	g.mixer.StopSignal()
	g.setState("switchboard", now)
	if why != "" {
		g.say(why, Amber, now)
	}
}

// lineKey handles a key on the line's screens; false leaves it to Key.
func (g *Game) lineKey(k string, now float64) bool {
	enter, escape := k == KeyEnter || k == "\r", k == KeyEscape
	switch g.state {
	case "codename":
		switch {
		case escape:
			g.toTitle(now)
		case enter && g.line.codename != "":
			g.storeProgress()
			g.openSwitchboard(now)
		case k == KeyBackspace || k == "\x08":
			g.line.codename = strings.TrimSuffix(g.line.codename, lastLetter(g.line.codename))
		case len(g.line.codename) < maxCodenameLen && isCodenameCharacter(k):
			g.line.codename += strings.ToUpper(k)
		}
	case "switchboard":
		switch {
		case escape:
			g.toTitle(now)
		case k == KeyTab:
			g.cfg.Wire.Close()
			g.setState("codename", now)
		case enter:
			g.dial(now)
		case k == KeyBackspace || k == "\x08":
			g.line.dialed = strings.TrimSuffix(g.line.dialed, lastLetter(g.line.dialed))
		case len(k) == 1 && k[0] >= '0' && k[0] <= '9' && len(g.line.dialed) < maxDialedDigits:
			g.line.dialed += k
			g.turnDial(k, now)
		}
	case "calling":
		if escape {
			g.cfg.Wire.Send(WireMessage{Type: "hangup"})
			g.backToSwitchboard("", now)
		}
	case "ringing":
		switch {
		case enter:
			g.cfg.Wire.Send(WireMessage{Type: "answer"})
		case escape:
			g.cfg.Wire.Send(WireMessage{Type: "hangup"})
			g.backToSwitchboard("", now)
		}
	case "line":
		switch {
		case escape:
			g.cfg.Wire.Send(WireMessage{Type: "hangup"})
			g.backToSwitchboard("", now)
		case k == KeyBackspace || k == "\x08":
			g.freeText, g.line.remoteText = "", ""
		default:
			return k != " " // a typed space keys, like anywhere else
		}
	default:
		return false
	}
	return true
}

func isCodenameCharacter(k string) bool {
	return len(k) == 1 && strings.ContainsAny(strings.ToUpper(k), "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
}

// dial calls the number typed at the switchboard.
func (g *Game) dial(now float64) {
	number, err := strconv.Atoi(g.line.dialed)
	switch {
	case err != nil:
		return
	case g.line.status != "online":
		g.say(g.text("offline", nil), Alert, now)
		return
	}
	g.cfg.Wire.Send(WireMessage{Type: "dial", Number: number})
	g.line.peerNumber, g.line.peerCodename = number, ""
	g.setState("calling", now)
	g.line.nextRing = now + .5
}

// tickLine reads the exchange and keeps the line's sounds and the far end's key going.
func (g *Game) tickLine(now float64) {
	for _, m := range g.cfg.Wire.Receive() {
		g.hearExchange(m, now)
	}
	g.line.turns = dialTurnsLeft(g.line.turns, now)
	switch g.state {
	case "calling":
		if now-g.stateStart > callTimeout {
			g.cfg.Wire.Send(WireMessage{Type: "hangup"})
			g.backToSwitchboard(g.text("no_answer", map[string]any{"n": g.line.peerNumber}), now)
		} else if now >= g.line.nextRing {
			g.mixer.Play(ringbackSound(), Sig, true)
			g.line.nextRing = now + 3
		}
	case "ringing":
		if now >= g.line.nextRing {
			g.mixer.Play(bellSound(), Sig, true)
			g.line.nextRing = now + 3
		}
	case "line":
		g.freeText, _ = typeKeyedLetters(g.keyer, g.freeText, g.cfg.LetterGap, now)
		g.sendToneDownTheLine(now)
		g.replayRemoteKeys(now)
		g.line.remoteText, _ = typeKeyedLetters(g.line.remote, g.line.remoteText, g.cfg.LetterGap, now)
	}
}

// hearExchange acts on one message from the exchange.
func (g *Game) hearExchange(m WireMessage, now float64) {
	s := g.state
	switch m.Type {
	case "welcome":
		g.line.status = "online"
		if m.Number != g.line.number {
			g.line.number = m.Number
			g.storeProgress()
		}
	case "offline":
		g.line.status = "offline"
		if s == "calling" || s == "ringing" || s == "line" {
			g.backToSwitchboard(g.text("line_down", nil), now)
		}
	case "no_answer":
		if s == "calling" {
			g.backToSwitchboard(g.text("no_answer_"+m.Reason, map[string]any{"n": m.Number}), now)
		}
	case "ring":
		if s != "switchboard" { // busy typing a codename: the exchange thinks this line is free
			g.cfg.Wire.Send(WireMessage{Type: "hangup"})
			return
		}
		g.line.peerNumber, g.line.peerCodename = m.Number, m.Codename
		g.setState("ringing", now)
		g.line.nextRing = now
	case "connected":
		if s == "calling" || s == "ringing" {
			g.line.peerNumber, g.line.peerCodename = m.Number, m.Codename
			g.mixer.StopSignal()
			g.startLine(now)
		}
	case "hung_up":
		switch s {
		case "calling":
			g.backToSwitchboard(g.text("no_answer", map[string]any{"n": g.line.peerNumber}), now)
		case "ringing", "line":
			g.backToSwitchboard(g.text("line_closed", nil), now)
		}
	case "key":
		if s == "line" {
			g.hearRemoteKey(m.Down, m.At, now)
		}
	}
}

func (g *Game) startLine(now float64) {
	g.setState("line", now)
	g.freeText = ""
	g.line.remote = NewKeyer(Config{Releases: true, DahTime: g.cfg.DahTime, LetterGap: g.cfg.LetterGap})
	g.line.remoteText, g.line.remoteKeys, g.line.remoteToneOn, g.line.sentToneOn = "", nil, false, false
	g.line.remoteHeard = math.Inf(-1)
}

// sendToneDownTheLine tells the far end when this player's tone starts or stops.
func (g *Game) sendToneDownTheLine(now float64) {
	if g.state != "line" {
		return
	}
	if on := g.keyer.Sounding(); on != g.line.sentToneOn {
		g.line.sentToneOn = on
		g.cfg.Wire.Send(WireMessage{Type: "key", Down: on, At: now})
	}
}

// sendBlipDownTheLine sends a tap whose length isn't known yet, keyed without key releases,
// as the short tone this end plays for it.
func (g *Game) sendBlipDownTheLine(now, seconds float64) {
	if g.state == "line" && !g.line.sentToneOn {
		g.cfg.Wire.Send(WireMessage{Type: "key", Down: true, At: now})
		g.cfg.Wire.Send(WireMessage{Type: "key", Down: false, At: now + seconds})
	}
}

// hearRemoteKey queues the far end's key, moved onto this game's clock lineDelay late. The
// clocks are matched again after a pause, or when a key arrives too late to keep its place.
func (g *Game) hearRemoteKey(down bool, at, now float64) {
	if now-g.line.remoteHeard > 2 || at+g.line.remoteClock < now {
		g.line.remoteClock = now + lineDelay - at
	}
	g.line.remoteHeard = now
	g.line.remoteKeys = append(g.line.remoteKeys, remoteKey{down, at + g.line.remoteClock})
}

// replayRemoteKeys plays the far end's keys that are due and feeds them to its keyer.
func (g *Game) replayRemoteKeys(now float64) {
	for len(g.line.remoteKeys) > 0 && g.line.remoteKeys[0].at <= now {
		k := g.line.remoteKeys[0]
		g.line.remoteKeys = g.line.remoteKeys[1:]
		g.line.remoteToneOn = k.down
		g.mixer.SetRemoteKey(k.down)
		if k.down {
			g.line.remote.Press(k.at)
		} else {
			g.line.remote.Release(k.at)
		}
	}
}

// ---- the rotary dial

// dialTurn is one digit dialled: the dial winds round to the finger stop, then runs back,
// clicking once per pulse (ten for 0) at ten pulses a second.
type dialTurn struct {
	digit string
	start float64
}

const dialWindSpeed = 600.0 // degrees a second

// pulses is how many clicks a digit sends: its value, and ten for 0.
func pulses(digit string) int {
	n, _ := strconv.Atoi(digit)
	if n == 0 {
		return 10
	}
	return n
}

// windDegrees is how far the dial turns for the digit: 1 is 60°, each digit after it 30° more.
func (t dialTurn) windDegrees() float64 { return float64(pulses(t.digit)+1) * 30 }
func (t dialTurn) windSeconds() float64 { return t.windDegrees() / dialWindSpeed }
func (t dialTurn) end() float64         { return t.start + t.windSeconds() + float64(pulses(t.digit))*.1 }

// rotation is how far round the dial is at now, in degrees clockwise.
func (t dialTurn) rotation(now float64) float64 {
	elapsed := now - t.start
	back := float64(pulses(t.digit)) * .1
	switch {
	case elapsed < 0 || elapsed > t.windSeconds()+back:
		return 0
	case elapsed < t.windSeconds():
		return t.windDegrees() * elapsed / t.windSeconds()
	}
	return t.windDegrees() * (1 - (elapsed-t.windSeconds())/back)
}

// turnDial queues the dial's turn for a digit after any still running, with its clicks.
func (g *Game) turnDial(digit string, now float64) {
	start := now
	if n := len(g.line.turns); n > 0 {
		start = max(now, g.line.turns[n-1].end())
	}
	turn := dialTurn{digit, start}
	g.line.turns = append(g.line.turns, turn)
	clicks := Rest(start - now + turn.windSeconds())
	for range pulses(digit) {
		clicks = Concat(clicks, Noise(.006, .5, 1), Rest(.094))
	}
	g.mixer.Play(clicks, FX, false)
}

func dialTurnsLeft(turns []dialTurn, now float64) []dialTurn {
	for len(turns) > 0 && turns[0].end() < now {
		turns = turns[1:]
	}
	return turns
}

// dialRotation is the dial's angle now, and the digit whose turn it is ("" when at rest).
func (g *Game) dialRotation(now float64) (float64, string) {
	if len(g.line.turns) == 0 || g.line.turns[0].start > now {
		return 0, ""
	}
	return g.line.turns[0].rotation(now), g.line.turns[0].digit
}

// ---- sounds

// bellSound is the telephone bell: two trills of a hammer between two gongs.
func bellSound() Sound {
	var trill Sound
	for i := range 16 {
		trill = Concat(trill, Square([]float64{1400, 1100}[i%2], .025, .09))
	}
	return Concat(trill, Rest(.25), trill)
}

// ringbackSound is what the caller hears while the far end rings.
func ringbackSound() Sound {
	return Concat(Square(425, .4, .06), Rest(.2), Square(425, .4, .06))
}
