package gui

import (
	"fmt"
	"image"
	"image/png"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/hajimehoshi/ebiten/v2"

	"github.com/regiscamimura/morse-code-game/go/morse"
)

// TestScreens plays the opening of chapter 1 through the real App on a phone-sized screen,
// from the cover through typed keys and the touch KEY, and saves a PNG of each screen to
// $SCREENSHOTS. It needs a display, and Ebitengine runs one game per process, so one size a run:
//
//	SCREENSHOTS=/tmp/shots SCREENSHOT_SIZE=1080x2400 xvfb-run go test ./gui -run Screens
func TestScreens(t *testing.T) {
	dir := os.Getenv("SCREENSHOTS")
	if dir == "" {
		t.Skip("set SCREENSHOTS to a folder to write screenshots")
	}
	size := image.Pt(1080, 2400)
	if s := os.Getenv("SCREENSHOT_SIZE"); s != "" {
		if _, err := fmt.Sscanf(s, "%dx%d", &size.X, &size.Y); err != nil {
			t.Fatal("SCREENSHOT_SIZE is WIDTHxHEIGHT: ", err)
		}
	}
	d := &screenDriver{t: t, app: New("", 0, false, nil), size: size, dir: dir}
	d.script()
	ebiten.SetWindowSize(size.X/3, size.Y/3)
	if err := ebiten.RunGame(d); err != nil && err != ebiten.Termination {
		t.Fatal(err)
	}
	if d.failed != "" {
		t.Fatal(d.failed)
	}
}

// TestLineScreens calls another player on the telegraph line, through a stand-in exchange the
// script rings in from and keys from, and saves each screen like TestScreens:
//
//	SCREENSHOTS=/tmp/shots SCREENSHOT_SIZE=1080x1620 xvfb-run go test ./gui -run LineScreens
func TestLineScreens(t *testing.T) {
	dir := os.Getenv("SCREENSHOTS")
	if dir == "" {
		t.Skip("set SCREENSHOTS to a folder to write screenshots")
	}
	size := image.Pt(1080, 2400)
	if s := os.Getenv("SCREENSHOT_SIZE"); s != "" {
		if _, err := fmt.Sscanf(s, "%dx%d", &size.X, &size.Y); err != nil {
			t.Fatal("SCREENSHOT_SIZE is WIDTHxHEIGHT: ", err)
		}
	}
	wire := &scriptedWire{}
	d := &screenDriver{t: t, app: New(t.TempDir()+"/save.json", 0, false, wire), size: size, dir: dir}
	d.app.onCover = false
	d.typeKey(morse.KeyEnter)
	d.tap("w")
	d.expectState("codename")
	for _, ch := range "coruja" {
		d.tap(string(ch))
	}
	d.screenshot("line-1-codename")
	d.tap(morse.KeyEnter)
	d.expectState("switchboard")
	d.tap("4")
	d.tap("0")
	d.then(12, func() {})
	d.screenshot("line-2-dialling")
	d.then(150, func() {})
	d.screenshot("line-3-switchboard")
	d.then(1, func() { wire.arrive(morse.WireMessage{Type: "ring", Number: 456, Codename: "AGUIA"}) })
	d.then(10, func() {})
	d.expectState("ringing")
	d.screenshot("line-4-ringing")
	d.tap(morse.KeyEnter)
	d.then(2, func() {})
	d.expectState("line")
	d.telegraphKey(18) // T from here
	d.then(1, func() {
		now := d.app.now()
		wire.arrive(morse.WireMessage{Type: "key", Down: true, At: now}, morse.WireMessage{Type: "key", Down: false, At: now + .3})
	})
	d.then(30, func() {})
	d.screenshot("line-5-on-the-line")
	d.then(60, func() {})
	d.screenshot("line-6-keyed")
	d.then(1, func() { d.done = true })
	ebiten.SetWindowSize(size.X/3, size.Y/3)
	if err := ebiten.RunGame(d); err != nil && err != ebiten.Termination {
		t.Fatal(err)
	}
	if d.failed != "" {
		t.Fatal(d.failed)
	}
}

// scriptedWire is an exchange that welcomes the line as MORSE 123, puts an answered call
// straight through, and otherwise only says what the script makes arrive.
type scriptedWire struct {
	inbox []morse.WireMessage
}

func (w *scriptedWire) Open(secret, codename string) {
	w.arrive(morse.WireMessage{Type: "welcome", Number: 123})
}
func (w *scriptedWire) Close() {}
func (w *scriptedWire) Send(m morse.WireMessage) {
	if m.Type == "answer" {
		w.arrive(morse.WireMessage{Type: "connected", Number: 456, Codename: "AGUIA"})
	}
}
func (w *scriptedWire) Receive() []morse.WireMessage {
	inbox := w.inbox
	w.inbox = nil
	return inbox
}
func (w *scriptedWire) arrive(messages ...morse.WireMessage) { w.inbox = append(w.inbox, messages...) }

type step struct {
	wait int // frames to wait before doing it
	do   func()
}

type screenDriver struct {
	t      *testing.T
	app    *App
	size   image.Point
	dir    string
	steps  []step
	frames int
	shot   string // save the next drawn frame under this name
	failed string
	done   bool
}

func (d *screenDriver) then(wait int, do func()) { d.steps = append(d.steps, step{wait, do}) }

func (d *screenDriver) screenshot(name string) {
	d.then(2, func() { d.shot = name })
}

func (d *screenDriver) expectState(state string) {
	d.then(1, func() {
		if got := d.app.game.State(); got != state && d.failed == "" {
			d.failed = "expected " + state + ", got " + got
		}
	})
}

// typeKey is a key typed on the phone's keyboard.
func (d *screenDriver) typeKey(key string) {
	d.then(1, func() { d.app.game.Key(key, d.app.now()) })
}

// tap presses and releases the button under the game that sends key.
func (d *screenDriver) tap(key string) {
	d.then(1, func() {
		for _, c := range d.app.controls {
			if !c.telegraphKey && c.key == key {
				d.app.press(pointerEvent{id: 7, x: c.rect.Min.X + 4, y: c.rect.Min.Y + 4}, d.app.now())
				return
			}
		}
		if d.failed == "" {
			d.failed = "no button for " + key + " on " + d.app.game.State()
		}
	})
}

// telegraphKey holds the touch KEY down for `frames` frames.
func (d *screenDriver) telegraphKey(frames int) {
	d.then(1, func() {
		for _, c := range d.app.controls {
			if c.telegraphKey {
				d.app.press(pointerEvent{id: 3, x: c.rect.Min.X + 10, y: c.rect.Min.Y + 10}, d.app.now())
			}
		}
	})
	d.then(frames, func() {
		if d.app.keyPointer == 3 {
			d.app.keyPointer = noPointer
			d.app.game.SpaceUp(d.app.now())
		}
	})
}

// codeWord reads the message to send off the briefing screen: "CODE WORD:  TEA AT TEN".
func (d *screenDriver) codeWord() string {
	row := d.app.game.Draw(80, 24, d.app.now()).Cells[19]
	var b strings.Builder
	for _, c := range row {
		b.WriteRune(c.Ch)
	}
	_, word, _ := strings.Cut(b.String(), ":")
	return strings.TrimSpace(word)
}

// keyLetter keys one letter on the touch KEY and waits for it to lock in.
func (d *screenDriver) keyLetter(ch rune) {
	for _, e := range morse.Code[string(ch)] {
		if e == '-' {
			d.telegraphKey(18)
		} else {
			d.telegraphKey(4)
		}
		d.then(6, func() {})
	}
	d.then(30, func() {})
}

func (d *screenDriver) script() {
	d.screenshot("0-cover")
	d.then(1, func() { d.app.insertedAt = d.app.now() })
	d.then(20, func() {})
	d.screenshot("0-inserting")
	d.then(70, func() {
		if d.app.onCover && d.failed == "" {
			d.failed = "still on the cover"
		}
	})
	d.screenshot("1-language")
	d.typeKey(morse.KeyEnter)
	d.expectState("title")
	d.screenshot("2-title")
	d.typeKey(morse.KeyEnter)
	d.expectState("cover")
	d.then(70, func() {}) // past the cover's hold, so ENTER moves on
	d.screenshot("3a-cover")
	d.typeKey(morse.KeyEnter)
	d.expectState("chapter")
	for range 3 {
		for _, ch := range "ETAN" {
			d.keyLetter(ch)
		}
	}
	d.screenshot("3b-chapter")
	d.typeKey(morse.KeyEnter)
	d.expectState("brief")
	d.typeKey(morse.KeyEnter)
	d.screenshot("4-brief")
	d.then(1, func() {
		word := d.codeWord()
		d.typeKey(morse.KeyEnter)
		d.expectState("play")
		for i, ch := range word {
			if ch == ' ' {
				continue
			}
			for j, e := range morse.Code[string(ch)] {
				if e == '-' {
					d.telegraphKey(18)
				} else {
					d.telegraphKey(4)
				}
				if i == 0 && j == 0 {
					d.screenshot("5-sending")
				}
				d.then(6, func() {})
			}
			d.then(30, func() {})
		}
		d.expectState("win")
		d.screenshot("6-sent")
		d.then(70, func() {})
		d.typeKey(morse.KeyEnter)
		d.expectState("brief")
		d.typeKey(morse.KeyEnter) // skip the typing-out
		d.then(5, func() {})      // the game sees it all typed on its next draw
		d.typeKey(morse.KeyEnter)
		d.expectState("play")
		d.then(90, func() {})
		d.screenshot("7-receiving")
		d.tap(morse.KeyTab)
		d.then(30, func() {})
		d.screenshot("8-replayed")
		d.typeKey(morse.KeyEscape)
		d.expectState("title")
		d.tap("p")
		d.expectState("free")
		for range 2 {
			d.telegraphKey(18) // M
			d.then(6, func() {})
		}
		d.then(60, func() {})
		d.screenshot("9-practice")
		d.then(1, func() { d.done = true })
	})
}

func (d *screenDriver) Update() error {
	if err := d.app.Update(); err != nil {
		return err
	}
	if d.done || d.failed != "" {
		return ebiten.Termination
	}
	if len(d.steps) == 0 || d.shot != "" { // hold the script until the screenshot is drawn
		return nil
	}
	d.frames++
	if d.frames >= d.steps[0].wait {
		next := d.steps[0]
		d.steps, d.frames = d.steps[1:], 0
		next.do()
	}
	return nil
}

func (d *screenDriver) Draw(screen *ebiten.Image) {
	d.app.Draw(screen)
	if d.shot == "" {
		return
	}
	name := filepath.Join(d.dir, d.shot+"-"+map[bool]string{true: "landscape", false: "portrait"}[d.size.X > d.size.Y]+".png")
	d.shot = ""
	f, err := os.Create(name)
	if err != nil {
		d.failed = err.Error()
		return
	}
	defer f.Close()
	pixels := image.NewRGBA(screen.Bounds())
	screen.ReadPixels(pixels.Pix)
	if err := png.Encode(f, pixels); err != nil {
		d.failed = err.Error()
	}
}

func (d *screenDriver) Layout(int, int) (int, int) {
	d.app.width, d.app.height = d.size.X, d.size.Y
	return d.size.X, d.size.Y
}
