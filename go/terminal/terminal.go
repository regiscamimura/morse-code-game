// Package terminal runs a game in a text terminal: raw input with the space bar's real
// press and release where the terminal can report them, truecolour output, and the size.
//
// Releases come from the Kitty keyboard protocol (Ghostty, Kitty, WezTerm, iTerm2...),
// else from /dev/input on Linux, else they're unknown and only presses arrive.
package terminal

import (
	"os"
	"regexp"
	"sync"
	"time"

	"golang.org/x/term"
)

type Terminal struct {
	in, out *os.File
	saved   *term.State
	kitty   bool
	input   chan []byte

	mu          sync.Mutex
	keyboards   *keyboards // nil without /dev/input
	keyboardHit bool       // a keyboard reported the space bar
}

// Open puts the terminal in raw mode on the alternate screen. useDevices lets it read the
// space bar from /dev/input when the terminal can't report releases.
func Open(useDevices bool) (*Terminal, error) {
	t := &Terminal{in: os.Stdin, out: os.Stdout, input: make(chan []byte, 64)}
	saved, err := term.MakeRaw(int(t.in.Fd()))
	if err != nil {
		return nil, err
	}
	t.saved = saved
	go t.readInput()
	t.kitty = t.terminalReportsReleases()
	if t.kitty {
		t.Write(kittyPush)
	} else if useDevices {
		t.keyboards = openKeyboards()
	}
	t.Write(setupScreen)
	return t, nil
}

func (t *Terminal) readInput() {
	for {
		buf := make([]byte, 256)
		n, err := t.in.Read(buf)
		if err != nil {
			close(t.input)
			return
		}
		t.input <- buf[:n]
	}
}

var (
	deviceAttributes = regexp.MustCompile(`\x1b\[\?[\d;]*c`)
	kittyFlags       = regexp.MustCompile(`\x1b\[\?\d+u`)
)

// terminalReportsReleases asks for the Kitty keyboard flags, then for the device attributes
// every terminal answers. A flags reply arriving first means the protocol works.
func (t *Terminal) terminalReportsReleases() bool {
	t.Write("\x1b[?u\x1b[c")
	var reply []byte
	deadline := time.After(500 * time.Millisecond)
	for !deviceAttributes.Match(reply) {
		select {
		case chunk := <-t.input:
			reply = append(reply, chunk...)
		case <-deadline:
			return false
		}
	}
	return kittyFlags.Match(reply)
}

// ReportsRelease: space releases are known, from Kitty or /dev/input.
func (t *Terminal) ReportsRelease() bool {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.kitty || t.keyboards != nil
}

func (t *Terminal) Write(s string) { t.out.WriteString(s) }

// Size is the terminal's width and height in cells.
func (t *Terminal) Size() (int, int) {
	w, h, err := term.GetSize(int(t.out.Fd()))
	if err != nil {
		return 80, 24
	}
	return w, h
}

// Read waits up to timeout for input and returns every event that has arrived.
func (t *Terminal) Read(timeout time.Duration) []Event {
	var events []Event
	wait := time.After(timeout)
	t.mu.Lock()
	var spaces <-chan bool
	if t.keyboards != nil {
		spaces = t.keyboards.spaces
	}
	t.mu.Unlock()
	for {
		select {
		case chunk, ok := <-t.input:
			if !ok {
				return append(events, Event{Key: KeyInterrupt})
			}
			for _, token := range tokens(string(chunk)) {
				events = append(events, t.decode(token)...)
			}
		case down := <-spaces:
			t.mu.Lock()
			t.keyboardHit = true
			t.mu.Unlock()
			events = append(events, Event{Space: true, Down: down})
		case <-wait:
			return events
		}
		if len(events) > 0 {
			wait = time.After(0) // got something: take what else is waiting, then return
		}
	}
}

func (t *Terminal) decode(token string) []Event {
	if token == " " && !t.kitty {
		t.mu.Lock()
		defer t.mu.Unlock()
		if t.keyboards != nil {
			if t.keyboardHit {
				return nil // the keyboards already reported this press
			}
			// the terminal saw a space the keyboards didn't: they aren't this keyboard
			t.keyboards.close()
			t.keyboards = nil
		}
	}
	return decodeToken(token)
}

// Restore leaves the terminal as it was found.
func (t *Terminal) Restore() {
	if t.kitty {
		t.Write(kittyPop)
	}
	t.Write(restoreScreen)
	_ = term.Restore(int(t.in.Fd()), t.saved)
	t.mu.Lock()
	if t.keyboards != nil {
		t.keyboards.close()
	}
	t.mu.Unlock()
}
