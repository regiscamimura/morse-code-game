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
)

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
		d.app = gui.New(savePath, .5, false, exchange.New(exchange.Address()))
	}
	return d.app
}

func (d *deferredGame) Update() error              { return d.started().Update() }
func (d *deferredGame) Draw(screen *ebiten.Image)  { d.started().Draw(screen) }
func (d *deferredGame) Layout(w, h int) (int, int) { return d.started().Layout(w, h) }

func init() {
	mobile.SetGame(&deferredGame{})
}
