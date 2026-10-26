package gui

import (
	"bytes"
	_ "embed"
	"image"
	"image/color"
	"math"
	"slices"

	"github.com/hajimehoshi/ebiten/v2"
	"github.com/hajimehoshi/ebiten/v2/text/v2"
	"github.com/hajimehoshi/ebiten/v2/vector"

	"github.com/regiscamimura/morse-code-game/go/morse"
)

// JetBrains Mono (SIL Open Font License, fonts/OFL.txt): the usual terminal font.
//
//go:embed fonts/JetBrainsMono-Regular.ttf
var jetBrainsMono []byte

var monoFont = func() *text.GoTextFaceSource {
	source, err := text.NewGoTextFaceSource(bytes.NewReader(jetBrainsMono))
	if err != nil {
		panic(err)
	}
	return source
}()

// cellPainter keeps the canvas drawn on an image of its own and redraws only the rows that
// changed since the last frame: redrawing every glyph each frame is too slow for a phone.
type cellPainter struct {
	image *ebiten.Image
	rows  [][]morse.Cell // the rows as last drawn; nil after a resize
}

// draw draws the canvas as large as fits in area, centred, with cells twice as tall as wide
// so the half-block pixels come out square.
func (p *cellPainter) draw(screen *ebiten.Image, c *morse.Canvas, area image.Rectangle) {
	if p.image == nil || p.image.Bounds().Size() != area.Size() || len(p.rows) != c.H || len(p.rows[0]) != c.W {
		if p.image != nil {
			p.image.Deallocate()
		}
		p.image, p.rows = ebiten.NewImage(area.Dx(), area.Dy()), nil
	}
	cw := math.Min(float64(area.Dx())/float64(c.W), float64(area.Dy())/float64(2*c.H))
	ch := 2 * cw
	ox := (float64(area.Dx()) - cw*float64(c.W)) / 2
	oy := (float64(area.Dy()) - ch*float64(c.H)) / 2
	// cell edges on whole pixels, so neighbouring cells never leave a seam
	colX := func(i int) float32 { return float32(math.Floor(ox + float64(i)*cw)) }
	rowY := func(i int) float32 { return float32(math.Floor(oy + float64(i)*ch)) }
	face := &text.GoTextFace{Source: monoFont, Size: cw / 0.6} // JetBrains Mono's advance is 0.6 em

	for y, row := range c.Cells {
		if p.rows != nil && slices.Equal(row, p.rows[y]) {
			continue
		}
		// drawn clipped to its own row, so it never leaves ink on a row that isn't redrawn
		rowImage := p.image.SubImage(image.Rect(0, int(rowY(y)), area.Dx(), int(rowY(y+1)))).(*ebiten.Image)
		rowImage.Clear()
		// backgrounds as runs of one colour
		for x := 0; x < len(row); {
			end := x + 1
			for end < len(row) && row[end].Bg == row[x].Bg {
				end++
			}
			if row[x].Bg != c.Bg {
				vector.FillRect(rowImage, colX(x), rowY(y), colX(end)-colX(x), rowY(y+1)-rowY(y), rgba(row[x].Bg), false)
			}
			x = end
		}
		for x, cell := range row {
			if cell.Ch == ' ' {
				continue
			}
			box := cellBox{colX(x), rowY(y), colX(x+1) - colX(x), rowY(y+1) - rowY(y)}
			if !drawShape(rowImage, cell, box) {
				drawGlyph(rowImage, face, cell, box)
			}
		}
	}
	p.rows = c.Cells // a fresh canvas every frame, never changed after it's drawn
	op := &ebiten.DrawImageOptions{}
	op.GeoM.Translate(float64(area.Min.X), float64(area.Min.Y))
	screen.DrawImage(p.image, op)
}

type cellBox struct{ x, y, w, h float32 }

func drawGlyph(screen *ebiten.Image, face *text.GoTextFace, cell morse.Cell, box cellBox) {
	op := &text.DrawOptions{}
	op.PrimaryAlign, op.SecondaryAlign = text.AlignCenter, text.AlignCenter
	op.GeoM.Translate(float64(box.x+box.w/2), float64(box.y+box.h/2))
	op.ColorScale.ScaleWithColor(rgba(cell.Fg))
	text.Draw(screen, string(cell.Ch), face, op)
}

// drawShape draws the block and symbol characters as pixel-exact shapes: they must tile
// with no gaps, and JetBrains Mono lacks some of them. False means it's an ordinary glyph.
func drawShape(screen *ebiten.Image, cell morse.Cell, b cellBox) bool {
	fg := rgba(cell.Fg)
	switch cell.Ch {
	case '▀':
		vector.FillRect(screen, b.x, b.y, b.w, b.h/2, fg, false)
	case '▄':
		vector.FillRect(screen, b.x, b.y+b.h/2, b.w, b.h-b.h/2, fg, false)
	case '░', '▒':
		alpha := float32(.3)
		if cell.Ch == '▒' {
			alpha = .55
		}
		faded := fg
		faded.R, faded.G, faded.B, faded.A = uint8(float32(fg.R)*alpha), uint8(float32(fg.G)*alpha), uint8(float32(fg.B)*alpha), uint8(255*alpha)
		vector.FillRect(screen, b.x, b.y, b.w, b.h, faded, false)
	case '━':
		t := b.h * .16
		vector.FillRect(screen, b.x, b.y+(b.h-t)/2, b.w, t, fg, false)
	case '▬':
		t := b.h * .3
		vector.FillRect(screen, b.x+b.w*.08, b.y+(b.h-t)/2, b.w*.84, t, fg, false)
	case '▮':
		vector.FillRect(screen, b.x+b.w*.2, b.y+b.h*.2, b.w*.6, b.h*.6, fg, false)
	case '▯':
		vector.StrokeRect(screen, b.x+b.w*.2, b.y+b.h*.2, b.w*.6, b.h*.6, max(1, b.w*.1), fg, false)
	case '▲':
		fillTriangle(screen, fg, b.x+b.w/2, b.y+b.h*.25, b.x+b.w*.05, b.y+b.h*.8, b.x+b.w*.95, b.y+b.h*.8)
	case '♥':
		r := b.w * .22
		vector.FillCircle(screen, b.x+b.w*.3, b.y+b.h*.42, r, fg, true)
		vector.FillCircle(screen, b.x+b.w*.7, b.y+b.h*.42, r, fg, true)
		fillTriangle(screen, fg, b.x+b.w*.09, b.y+b.h*.46, b.x+b.w*.91, b.y+b.h*.46, b.x+b.w/2, b.y+b.h*.7)
	case '▸':
		fillTriangle(screen, fg, b.x+b.w*.2, b.y+b.h*.3, b.x+b.w*.2, b.y+b.h*.7, b.x+b.w*.85, b.y+b.h/2)
	default:
		return false
	}
	return true
}

func fillTriangle(screen *ebiten.Image, c color.Color, x0, y0, x1, y1, x2, y2 float32) {
	var path vector.Path
	path.MoveTo(x0, y0)
	path.LineTo(x1, y1)
	path.LineTo(x2, y2)
	path.Close()
	op := &vector.DrawPathOptions{AntiAlias: true}
	op.ColorScale.ScaleWithColor(c)
	vector.FillPath(screen, &path, nil, op)
}
