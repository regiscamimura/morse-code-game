// Command morse is MORSE CODE in a desktop window, played from the keyboard: space is the
// telegraph key.
package main

import (
	"flag"
	"log"

	"github.com/hajimehoshi/ebiten/v2"

	"github.com/regiscamimura/morse-code-game/go/exchange"
	"github.com/regiscamimura/morse-code-game/go/gui"
	"github.com/regiscamimura/morse-code-game/go/morse"
)

func main() {
	volume := flag.Float64("volume", .4, "0 (mute) to 1")
	fullscreen := flag.Bool("fullscreen", false, "start full screen")
	flag.Parse()
	ebiten.SetWindowTitle("SOS Morse - Hold the Line")
	ebiten.SetWindowSize(1280, 768) // 80x24 cells twice as tall as wide
	ebiten.SetWindowResizingMode(ebiten.WindowResizingModeEnabled)
	ebiten.SetFullscreen(*fullscreen)
	if err := ebiten.RunGame(gui.New(morse.DefaultSavePath(), *volume, true, exchange.New(exchange.Address()), nil)); err != nil {
		log.Fatal(err)
	}
}
