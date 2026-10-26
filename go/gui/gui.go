// Package gui runs MORSE CODE in an Ebitengine window or on a phone: it draws the game's
// cell grid, turns touch, mouse and keyboard into game input, and plays the game's sound.
//
// On a desktop the game fills the window and is played from the keyboard alone, like the
// terminal version. A phone held upright shows the cartridge cover first, then the game at the
// top of the screen in its phone layout (larger words between 80-column pictures, see
// morse.Game.DrawPhone) and the controls below it: the flat red telegraph key while keying,
// a keyboard while receiving, else just the screen's buttons.
package gui

import (
	"image"
	"image/color"
	"math"
	"time"

	"github.com/hajimehoshi/ebiten/v2"
	"github.com/hajimehoshi/ebiten/v2/audio"
	"github.com/hajimehoshi/ebiten/v2/inpututil"

	"github.com/regiscamimura/morse-code-game/go/morse"
)

// noPointer: nobody is holding the telegraph key.
const noPointer = math.MinInt

// mousePointer is the mouse's id among touch ids, which are never negative.
const mousePointer = -1

type App struct {
	game    *morse.Game
	mixer   *morse.Mixer
	player  *audio.Player
	start   time.Time
	desktop bool // keyboard only, no control panel; ESC on the title screen closes the window

	width, height int             // screen size in device pixels
	keyPointer    int             // the touch or mouse holding the telegraph key
	buttonPointer int             // the touch or mouse holding down a keyboard key or button
	heldButton    image.Rectangle // that key, drawn pressed in
	controls      []control
	strips        []strip       // what the screen shows, top to bottom
	gameBottom    int           // where the game's strips end and the controls begin
	painters      []cellPainter // one per strip
	panel         panelPainter
	onCover       bool    // the phone's cartridge cover is showing
	insertedAt    float64 // when the cover was tapped; negative until then
}

// New starts the game. savePath "" plays without saving; desktop plays from the keyboard
// alone and lets the game close the window, else it's a phone with on-screen controls. wire
// is the telephone exchange for the telegraph line; nil plays alone.
func New(savePath string, volume float64, desktop bool, wire morse.Wire) *App {
	cfg := morse.DefaultConfig()
	cfg.SavePath, cfg.Wire = savePath, wire
	mixer := morse.NewMixer(volume)
	a := &App{mixer: mixer, start: time.Now(), desktop: desktop, onCover: !desktop, insertedAt: -1, keyPointer: noPointer, buttonPointer: noPointer}
	a.game = morse.NewGame(cfg, mixer, 0)
	a.startSound()
	return a
}

func (a *App) startSound() {
	ctx := audio.CurrentContext() // one per process
	if ctx == nil {
		ctx = audio.NewContext(morse.OutRate)
	}
	player, err := ctx.NewPlayerF32(a.mixer.Stream(2))
	if err != nil {
		return // no sound card: play silently
	}
	// short buffer: the sidetone must start the moment the key goes down. A phone's own audio
	// path already adds tens of milliseconds, so it gets a shorter one; 15 ms crackled on a
	// BlackBerry KEYone.
	buffer := 40 * time.Millisecond
	if !a.desktop {
		buffer = 30 * time.Millisecond
	}
	player.SetBufferSize(buffer)
	player.Play()
	a.player = player
}

func (a *App) now() float64 { return time.Since(a.start).Seconds() }

func (a *App) Layout(outsideWidth, outsideHeight int) (int, int) {
	scale := ebiten.Monitor().DeviceScaleFactor()
	a.width, a.height = int(float64(outsideWidth)*scale), int(float64(outsideHeight)*scale)
	return a.width, a.height
}

func (a *App) Update() error {
	now := a.now()
	if a.onCover {
		a.insertCartridgeOnTap(now)
		a.layoutScreen(now)
		return nil
	}
	a.readKeyboard(now)
	a.layoutScreen(now)
	if !a.desktop {
		a.controls = a.layoutControls()
		a.readPointers(now)
	}
	a.game.Tick(now)
	if a.game.Quit {
		a.game.Quit = false
		if a.desktop {
			return ebiten.Termination
		}
	}
	return nil
}

// insertCartridgeOnTap starts the game from the cover on a tap or ENTER, after the cartridge
// has slid in.
func (a *App) insertCartridgeOnTap(now float64) {
	if a.insertedAt < 0 {
		if inpututil.IsKeyJustPressed(ebiten.KeyEnter) || inpututil.IsMouseButtonJustPressed(ebiten.MouseButtonLeft) ||
			len(inpututil.AppendJustPressedTouchIDs(nil)) > 0 {
			a.insertedAt = now
		}
		return
	}
	if now-a.insertedAt > morse.CoverSeconds {
		a.onCover = false
	}
}

// phoneColumns is how many columns a phone sets the game's words in: fewer than the pictures'
// 80, so they read larger.
const phoneColumns = 40

// strip is one canvas of the screen and the area it's drawn in.
type strip struct {
	canvas *morse.Canvas
	rect   image.Rectangle
}

// layoutScreen decides what the screen shows and where: on a desktop the 80x24 game filling
// the window; on a phone the cover, or the game's strips stacked from the top.
func (a *App) layoutScreen(now float64) {
	screen := image.Rect(0, 0, a.width, a.height)
	switch {
	case a.desktop:
		a.strips, a.gameBottom = []strip{{a.game.Draw(80, 24, now), screen}}, a.height
	case a.onCover:
		inserted := -1.0
		if a.insertedAt >= 0 {
			inserted = now - a.insertedAt
		}
		a.strips, a.gameBottom = []strip{{morse.DrawCover(80, 24, now, inserted), screen}}, a.height
	default:
		a.strips, a.gameBottom = stackStrips(a.game.DrawPhone(phoneColumns, now), a.width, a.height-a.controlsMinHeight())
	}
}

// stackStrips places canvases top to bottom, each as wide as the screen with cells twice as
// tall as wide, all shrunk alike if they'd be taller than maxHeight. It returns them and
// where they end.
func stackStrips(canvases []*morse.Canvas, width, maxHeight int) ([]strip, int) {
	stripHeight := func(c *morse.Canvas) float64 { return float64(width) / float64(c.W) * 2 * float64(c.H) }
	total := 0.0
	for _, c := range canvases {
		total += stripHeight(c)
	}
	scale := min(1, float64(maxHeight)/total)
	strips, y := make([]strip, len(canvases)), 0.0
	for i, c := range canvases {
		h := stripHeight(c) * scale
		strips[i] = strip{c, image.Rect(0, int(y), width, int(y+h))}
		y += h
	}
	return strips, int(y)
}

// controlsMinHeight is the least room the phone's controls need below the game.
func (a *App) controlsMinHeight() int {
	switch {
	case a.game.Typing():
		return a.width * 62 / 100 // a keyboard and a row of buttons
	case a.game.Keying():
		return a.width * 50 / 100 // the telegraph key and a row of buttons
	}
	return a.width / 5 // a row of buttons
}

var namedKeys = map[ebiten.Key]string{
	ebiten.KeyEnter: morse.KeyEnter, ebiten.KeyNumpadEnter: morse.KeyEnter, ebiten.KeyTab: morse.KeyTab,
	ebiten.KeyEscape: morse.KeyEscape, ebiten.KeyBackspace: morse.KeyBackspace,
}

func (a *App) readKeyboard(now float64) {
	if inpututil.IsKeyJustPressed(ebiten.KeySpace) {
		a.game.SpaceDown(now)
	}
	if inpututil.IsKeyJustReleased(ebiten.KeySpace) {
		a.game.SpaceUp(now)
	}
	for key, name := range namedKeys {
		if inpututil.IsKeyJustPressed(key) {
			a.game.Key(name, now)
		}
	}
	for _, r := range ebiten.AppendInputChars(nil) {
		if r != ' ' {
			a.game.Key(string(r), now)
		}
	}
}

type pointerEvent struct {
	id   int
	x, y int
}

func (a *App) readPointers(now float64) {
	var pressed, released []pointerEvent
	if inpututil.IsMouseButtonJustPressed(ebiten.MouseButtonLeft) {
		x, y := ebiten.CursorPosition()
		pressed = append(pressed, pointerEvent{mousePointer, x, y})
	}
	if inpututil.IsMouseButtonJustReleased(ebiten.MouseButtonLeft) {
		released = append(released, pointerEvent{id: mousePointer})
	}
	for _, id := range inpututil.AppendJustPressedTouchIDs(nil) {
		x, y := ebiten.TouchPosition(id)
		pressed = append(pressed, pointerEvent{int(id), x, y})
	}
	for _, id := range inpututil.AppendJustReleasedTouchIDs(nil) {
		released = append(released, pointerEvent{id: int(id)})
	}
	for _, p := range pressed {
		a.press(p, now)
	}
	for _, p := range released {
		if p.id == a.keyPointer {
			a.keyPointer = noPointer
			a.game.SpaceUp(now)
		}
		if p.id == a.buttonPointer {
			a.buttonPointer, a.heldButton = noPointer, image.Rectangle{}
		}
	}
}

func (a *App) press(p pointerEvent, now float64) {
	at := image.Pt(p.x, p.y)
	for _, c := range a.controls {
		if !at.In(c.rect) {
			continue
		}
		if c.telegraphKey {
			if a.keyPointer == noPointer {
				a.keyPointer = p.id
				a.game.SpaceDown(now)
			}
		} else {
			a.buttonPointer, a.heldButton = p.id, c.rect
			a.game.Key(c.key, now)
		}
		return
	}
	// a tap on the game itself moves on from screens that only wait for ENTER
	if a.game.WaitsForEnter() {
		a.game.Key(morse.KeyEnter, now)
	}
}

func (a *App) Draw(screen *ebiten.Image) {
	screen.Fill(rgba(morse.Ink))
	for len(a.painters) < len(a.strips) {
		a.painters = append(a.painters, cellPainter{})
	}
	for i, s := range a.strips {
		a.painters[i].draw(screen, s.canvas, s.rect)
	}
	if !a.desktop && !a.onCover {
		a.drawControls(screen)
	}
}

func rgba(c morse.Color) color.RGBA { return color.RGBA{c.R, c.G, c.B, 255} }
