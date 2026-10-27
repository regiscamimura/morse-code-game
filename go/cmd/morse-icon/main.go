// Command morse-icon draws the Android launcher icon into the app's res folder: the Titanic
// going down by the bow, from the iceberg cover, under a navy sky. Given a second folder, it
// also draws the Play Store's 512x512 icon and its 1024x500 feature graphic (the whole cover).
//
//	go run ./cmd/morse-icon android/app/src/main/res android/store
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

// navy is the icon's sky, the iceberg cover's colour at the horizon; colors.xml repeats it as
// the adaptive icon's background.
var navy = morse.Color{R: 0x1c, G: 0x2a, B: 0x52}

// The liner on the iceberg cover is 50 pixels wide from x 26; the icon is centred on it, and
// takes nothing left of x 25, where the iceberg's tip would show as a stray shard.
const linerX, linerY, leftmostX = 51, 17, 25

func main() {
	if len(os.Args) != 2 && len(os.Args) != 3 {
		log.Fatal("usage: morse-icon RES_DIR [STORE_DIR]")
	}
	res := os.Args[1]
	titanic := plainSkyCoverPixels("iceberg")
	// the liner at 3 is 150 of 192 pixels; at 5, 250 of the 432 foreground, inside the 66 dp
	// circle a launcher may crop an adaptive icon to
	writePNG(filepath.Join(res, "mipmap-xxxhdpi", "ic_launcher.png"), drawAround(titanic, 192, 3))
	writePNG(filepath.Join(res, "drawable-xxxhdpi", "ic_launcher_foreground.png"), drawAround(titanic, 432, 5))
	if len(os.Args) == 3 {
		store := os.Args[2]
		ink := color.RGBA{morse.Ink.R, morse.Ink.G, morse.Ink.B, 255}
		// the liner at 8 is 400 of 512 pixels: inside the rounded square Play masks the icon to
		writePNG(filepath.Join(store, "icon-512.png"), drawAround(titanic, 512, 8))
		// the 80x32 cover at 13 is 1040x416, its sides just past the edges; Play crops the
		// graphic's edges on some screens, so nothing that matters sits there.
		writePNG(filepath.Join(store, "feature-graphic.png"), drawCentered(coverPixels("iceberg"), 1024, 500, 13, ink))
	}
}

// plainSkyCoverPixels is a chapter cover under a plain navy sky, one pixel per half cell.
func plainSkyCoverPixels(name string) *image.RGBA {
	c := morse.NewCanvas(80, 24, morse.Ink, morse.Ink)
	morse.DrawCoverArtPlainSky(c, name, navy)
	return canvasPixels(c, 80, 16)
}

// coverPixels is a chapter cover, 80x16 cells, one pixel per half cell, as it first appears.
func coverPixels(name string) *image.RGBA {
	c := morse.NewCanvas(80, 24, morse.Ink, morse.Ink)
	morse.DrawCoverArt(c, name, 0)
	return canvasPixels(c, 80, 16)
}

// canvasPixels turns the canvas's top-left width x height cells into pixels, two per cell.
func canvasPixels(c *morse.Canvas, width, height int) *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, width, 2*height))
	for y := range height {
		for x := range width {
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

// drawCentered scales art by scale onto a width x height image filled with background; art
// wider or taller than that is cropped evenly on both sides.
func drawCentered(art *image.RGBA, width, height, scale int, background color.RGBA) *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, width, height))
	for i := range img.Pix {
		img.Pix[i] = []uint8{background.R, background.G, background.B, background.A}[i%4]
	}
	w, h := art.Bounds().Dx()*scale, art.Bounds().Dy()*scale
	left, top := (width-w)/2, (height-h)/2
	for y := range h {
		for x := range w {
			img.Set(left+x, top+y, art.At(x/scale, y/scale))
		}
	}
	return img
}

// drawAround scales art by scale onto a size x size square centred on the liner; past art's
// edges it repeats the edge pixels, so the sky and the sea run on to the icon's borders.
func drawAround(art *image.RGBA, size, scale int) *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, size, size))
	b := art.Bounds()
	deep := darkestInRow(art, b.Max.Y-1) // below the art: the sea's floor, without its glints
	for y := range size {
		for x := range size {
			// from the scaled art's own corner, so no column or row is drawn twice
			ax := min(b.Max.X-1, max(leftmostX, (linerX*scale-size/2+x)/scale))
			ay := max(0, (linerY*scale-size/2+y)/scale)
			if ay >= b.Max.Y {
				img.Set(x, y, deep)
				continue
			}
			img.Set(x, y, art.At(ax, ay))
		}
	}
	return img
}

// darkestInRow is the darkest pixel of art's row y.
func darkestInRow(art *image.RGBA, y int) color.RGBA {
	darkest := art.RGBAAt(0, y)
	for x := range art.Bounds().Dx() {
		if p := art.RGBAAt(x, y); int(p.R)+int(p.G)+int(p.B) < int(darkest.R)+int(darkest.G)+int(darkest.B) {
			darkest = p
		}
	}
	return darkest
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
