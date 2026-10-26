// Command morse-icon draws the Android launcher icon: the MORSE CODE cartridge from the cover,
// as pixel art, into the app's res folder.
//
//	go run ./cmd/morse-icon android/app/src/main/res
package main

import (
	"image"
	"image/color"
	"image/png"
	"log"
	"os"
	"path/filepath"

	"github.com/regiscamimura/morse-code-game/go/morse"
)

// pixelSize is how many icon pixels each cartridge pixel takes at xxxhdpi: 26x30 pixels become
// 156x180, whose diagonal stays inside the 66 dp circle a launcher may crop the icon to.
const pixelSize = 6

func main() {
	if len(os.Args) != 2 {
		log.Fatal("usage: morse-icon RES_DIR")
	}
	res := os.Args[1]
	art := cartridgePixels()
	ink := morse.Ink
	writePNG(filepath.Join(res, "mipmap-xxxhdpi", "ic_launcher.png"), drawCentered(art, 192, color.RGBA{ink.R, ink.G, ink.B, 255}))
	writePNG(filepath.Join(res, "drawable-xxxhdpi", "ic_launcher_foreground.png"), drawCentered(art, 432, color.RGBA{}))
}

// cartridgePixels is the cartridge one pixel per half cell; text cells show their background.
func cartridgePixels() *image.RGBA {
	c := morse.NewCanvas(80, 24, morse.Ink, morse.Ink)
	morse.DrawCartridge(c, 0, 0)
	img := image.NewRGBA(image.Rect(0, 0, morse.CartridgeWidth, 2*morse.CartridgeHeight))
	for y := range morse.CartridgeHeight {
		for x := range morse.CartridgeWidth {
			cell := c.Cells[y+c.OY][x+c.OX]
			top, bottom := cell.Bg, cell.Bg
			switch cell.Ch {
			case '▀':
				top = cell.Fg
			case '▄':
				bottom = cell.Fg
			}
			img.Set(x, 2*y, color.RGBA{top.R, top.G, top.B, 255})
			img.Set(x, 2*y+1, color.RGBA{bottom.R, bottom.G, bottom.B, 255})
		}
	}
	return img
}

// drawCentered scales art by pixelSize onto a size x size square filled with background.
func drawCentered(art *image.RGBA, size int, background color.RGBA) *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, size, size))
	for i := range img.Pix {
		img.Pix[i] = []uint8{background.R, background.G, background.B, background.A}[i%4]
	}
	w, h := art.Bounds().Dx()*pixelSize, art.Bounds().Dy()*pixelSize
	left, top := (size-w)/2, (size-h)/2
	for y := range h {
		for x := range w {
			img.Set(left+x, top+y, art.At(x/pixelSize, y/pixelSize))
		}
	}
	return img
}

func writePNG(path string, img image.Image) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		log.Fatal(err)
	}
	f, err := os.Create(path)
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()
	if err := png.Encode(f, img); err != nil {
		log.Fatal(err)
	}
}
