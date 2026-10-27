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
)

var (
	mu      sync.Mutex
	dataDir string
	opener  URLOpener
)

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

func (d *deferredGame) Update() error              { return d.started().Update() }
func (d *deferredGame) Draw(screen *ebiten.Image)  { d.started().Draw(screen) }
func (d *deferredGame) Layout(w, h int) (int, int) { return d.started().Layout(w, h) }

func init() {
	mobile.SetGame(&deferredGame{})
}
