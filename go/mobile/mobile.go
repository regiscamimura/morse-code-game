// Package mobile is the Android entry point, bound into an .aar by ebitenmobile. The app
// calls SetDataDir with its private files folder in onCreate, before the game's first frame.
package mobile

import (
	"path/filepath"
	"sync"

	"github.com/hajimehoshi/ebiten/v2"
	"github.com/hajimehoshi/ebiten/v2/mobile"

	"github.com/regiscamimura/morse-code-game/go/exchange"
	"github.com/regiscamimura/morse-code-game/go/gui"
	"github.com/regiscamimura/morse-code-game/go/morse"
)

var (
	mu              sync.Mutex
	dataDir         string
	opener          URLOpener
	painter         BackdropPainter
	painted         morse.Color // what painter last painted, unless windowUnpainted
	windowUnpainted bool        // painter's window is new and hasn't been painted yet
)

// BackdropPainter paints the window around the game in the game's background colour, so the
// strip beside a camera cutout matches it; MainActivity is one.
type BackdropPainter interface {
	PaintBackdrop(argb int32)
}

// SetBackdropPainter tells the game what to repaint as its background colour changes.
func SetBackdropPainter(p BackdropPainter) {
	mu.Lock()
	painter, windowUnpainted = p, true // a new window, painted on the next frame
	mu.Unlock()
}

// paintBackdrop has the window around the game repainted when the game's background changes.
func paintBackdrop(c morse.Color) {
	mu.Lock()
	p, changed := painter, windowUnpainted || c != painted
	painted, windowUnpainted = c, false
	mu.Unlock()
	if p != nil && changed {
		p.PaintBackdrop(int32(0xFF000000 | uint32(c.R)<<16 | uint32(c.G)<<8 | uint32(c.B)))
	}
}

// URLOpener opens a web page in the phone's browser; MainActivity is one.
type URLOpener interface {
	OpenURL(url string)
}

// SetURLOpener tells the game how to open a web page, for the privacy policy.
func SetURLOpener(o URLOpener) {
	mu.Lock()
	opener = o
	mu.Unlock()
}

func openURL(url string) {
	mu.Lock()
	o := opener
	mu.Unlock()
	if o != nil {
		o.OpenURL(url)
	}
}

// SetDataDir tells the game where to keep its save file.
func SetDataDir(dir string) {
	mu.Lock()
	dataDir = dir
	mu.Unlock()
}

// deferredGame starts the real game on its first frame: ebitenmobile needs a game from
// init(), before Java has had a chance to call SetDataDir.
type deferredGame struct{ app *gui.App }

func (d *deferredGame) started() *gui.App {
	if d.app == nil {
		mu.Lock()
		savePath := ""
		if dataDir != "" {
			savePath = filepath.Join(dataDir, "morse.json")
		}
		mu.Unlock()
		d.app = gui.New(savePath, .5, false, exchange.New(exchange.Address()), openURL)
	}
	return d.app
}

func (d *deferredGame) Update() error { return d.started().Update() }
func (d *deferredGame) Draw(screen *ebiten.Image) {
	app := d.started()
	app.Draw(screen)
	paintBackdrop(app.Backdrop())
}
func (d *deferredGame) Layout(w, h int) (int, int) { return d.started().Layout(w, h) }

func init() {
	mobile.SetGame(&deferredGame{})
}
