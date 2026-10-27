// Command morse-icon draws the Android launcher icon into the app's res folder: the Titanic
// going down by the bow under a navy sky, drawn large from the game's liner sprite. Given a second folder, it
// also draws the Play Store's 512x512 icon and its 1024x500 feature graphic (the whole cover).
//
//	go run ./cmd/morse-icon android/app/src/main/res android/store
package main

import (
	"image"
	"image/color"
	"image/png"
	"log"
	"math"
	"os"
	"path/filepath"

	"github.com/regiscamimura/morse-code-game/go/morse"
)

// navy is the icon's sky, the iceberg cover's colour at the horizon; colors.xml repeats it as
// the adaptive icon's background.
var navy = color.RGBA{0x1c, 0x2a, 0x52, 255}

// The sea under the icon's Titanic: its surface, a glint along it, and its depths.
var seaTop, seaGlint, seaDeep = color.RGBA{0x14, 0x30, 0x4a, 255}, color.RGBA{0x3a, 0x5f, 0x84, 255}, color.RGBA{0x08, 0x14, 0x22, 255}

// sinking is how far the icon's Titanic leans, bow down, in degrees.
const sinking = 30

func main() {
	if len(os.Args) != 2 && len(os.Args) != 3 {
		log.Fatal("usage: morse-icon RES_DIR [STORE_DIR]")
	}
	res := os.Args[1]
	writePNG(filepath.Join(res, "mipmap-xxxhdpi", "ic_launcher.png"), drawTitanic(192, 192))
	// 432 is the adaptive icon's 108 dp; a launcher may show only the 72 dp, 288 pixels, in the middle
	writePNG(filepath.Join(res, "drawable-xxxhdpi", "ic_launcher_foreground.png"), drawTitanic(432, 288))
	if len(os.Args) == 3 {
		store := os.Args[2]
		ink := color.RGBA{morse.Ink.R, morse.Ink.G, morse.Ink.B, 255}
		writePNG(filepath.Join(store, "icon-512.png"), drawTitanic(512, 512))
		// the 80x32 cover at 13 is 1040x416, its sides just past the edges; Play crops the
		// graphic's edges on some screens, so nothing that matters sits there.
		writePNG(filepath.Join(store, "feature-graphic.png"), drawCentered(coverPixels("iceberg"), 1024, 500, 13, ink))
	}
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

// drawTitanic is the icon, size pixels square, composed for the frame pixels in its middle
// that are sure to show: content.json's liner leaning bow down into the sea under a navy sky,
// the sea's surface below the middle, so the stern and its four funnels stand clear and the bow
// is already under. The masts and their wire are left out: at icon size they only box it in.
func drawTitanic(size, frame int) *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, size, size))
	w, h := morse.SpriteSize("cover_liner")
	cos, sin := math.Cos(sinking*math.Pi/180), math.Sin(sinking*math.Pi/180)
	f, middle := float64(frame), float64(size)/2
	scale := f / 40 // icon pixels to a sprite pixel: the visible stern is about 3/4 of the frame
	ox, oy := middle+.14*f, middle+.1*f
	surface := int(middle + .22*f)
	for y := range size {
		for x := range size {
			if y >= surface {
				img.Set(x, y, mixRGBA(seaTop, seaDeep, float64(y-surface)/float64(size-surface)))
				if y-surface < max(2, size/96) {
					img.Set(x, y, seaGlint)
				}
				continue
			}
			img.Set(x, y, navy)
			// back from the icon to the sprite: undo the lean about the sprite's middle
			dx, dy := (float64(x)-ox)/scale, (float64(y)-oy)/scale
			u := int(math.Floor(float64(w)/2 + dx*cos + dy*sin))
			v := int(math.Floor(float64(h)/2 - dx*sin + dy*cos))
			if p, ok := morse.SpritePixel("cover_liner", u, v); ok && p != morse.Dim && p != morse.Faint {
				img.Set(x, y, color.RGBA{p.R, p.G, p.B, 255})
			}
		}
	}
	return img
}

// mixRGBA is a + (b - a)·t.
func mixRGBA(a, b color.RGBA, t float64) color.RGBA {
	m := func(p, q uint8) uint8 { return uint8(float64(p) + (float64(q)-float64(p))*t) }
	return color.RGBA{m(a.R, b.R), m(a.G, b.G), m(a.B, b.B), 255}
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
