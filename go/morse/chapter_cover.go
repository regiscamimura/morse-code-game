package morse

import (
	"encoding/json"
	"fmt"
	"math"
	"strconv"
)

// A chapter's cover is a pixel picture of its event, coverWidth x coverHeight pixels drawn two
// to a cell with half blocks. It's painted back to front from content.json's covers: sky and
// ground, stars and moon, then each layer in turn. Flames, smoke, searchlights, gunfire, stars
// and the sea move; everything else holds still, as on a printed cover.

const coverWidth, coverHeight = 80, 32

// CoverArt is one cover. Positions are in pixels.
type CoverArt struct {
	Sky     coverColors  `json:"sky"`     // from the top down to the horizon, blended between
	Ground  coverColors  `json:"ground"`  // from the horizon down to the bottom
	Horizon int          `json:"horizon"` // the pixel row where the ground starts
	Water   bool         `json:"water"`   // the ground is sea, with glints drifting on it
	Stars   bool         `json:"stars"`
	Moon    []int        `json:"moon"` // x, y of the moon, when it's out
	Layers  []CoverLayer `json:"layers"`
}

// CoverLayer is a sprite drawn at X, Y; or, without one, a searchlight (Beam) or a burst of
// gunfire (Flash) there.
type CoverLayer struct {
	Sprite    string    `json:"sprite"`
	X         int       `json:"x"`
	Y         int       `json:"y"`
	Tilt      float64   `json:"tilt"`      // pixels each column drops, left to right: a ship going down by the bow
	Waterline int       `json:"waterline"` // nothing at or below this row is drawn; 0 for none
	Fire      []float64 `json:"fire"`      // the stretch of the sprite's width that burns, as fractions: [0.4, 1]
	Smoke     [][]int   `json:"smoke"`     // points on the sprite that smoke rises from: funnels, chimneys
	Beam      *float64  `json:"beam"`      // a searchlight's angle from straight up, in degrees; it sways
	Flash     bool      `json:"flash"`
}

type coverPixels [coverHeight][coverWidth]Color

func (px *coverPixels) set(x, y int, c Color) { px.blend(x, y, c, 1) }

// blend mixes c into the pixel at x, y by a, from 0 (unchanged) to 1 (all c).
func (px *coverPixels) blend(x, y int, c Color, a float64) {
	if 0 <= x && x < coverWidth && 0 <= y && y < coverHeight {
		px[y][x] = mix(px[y][x], c, a)
	}
}

// disc blends c by a into every pixel within radius of cx, cy.
func (px *coverPixels) disc(cx, cy, radius float64, c Color, a float64) {
	for y := int(cy - radius); y <= int(cy+radius)+1; y++ {
		for x := int(cx - radius); x <= int(cx+radius)+1; x++ {
			if math.Hypot(float64(x)-cx, float64(y)-cy) <= radius {
				px.blend(x, y, c, a)
			}
		}
	}
}

func mix(a, b Color, t float64) Color {
	lerp := func(p, q uint8) uint8 { return uint8(float64(p) + (float64(q)-float64(p))*t + .5) }
	return Color{lerp(a.R, b.R), lerp(a.G, b.G), lerp(a.B, b.B)}
}

// coverColors are a gradient's stops, written "#rrggbb" in content.json and read as it loads.
type coverColors []Color

func (stops *coverColors) UnmarshalJSON(data []byte) error {
	var hex []string
	if err := json.Unmarshal(data, &hex); err != nil {
		return err
	}
	for _, s := range hex {
		v, err := strconv.ParseUint(s[min(1, len(s)):], 16, 32)
		if len(s) != 7 || s[0] != '#' || err != nil {
			return fmt.Errorf("colour %q isn't #rrggbb", s)
		}
		*stops = append(*stops, Color{uint8(v >> 16), uint8(v >> 8), uint8(v)})
	}
	return nil
}

// gradient is the colour t of the way down the stops, 0 to 1.
func gradient(stops coverColors, t float64) Color {
	if len(stops) == 1 {
		return stops[0]
	}
	t = min(1, max(0, t)) * float64(len(stops)-1)
	i := min(int(t), len(stops)-2)
	return mix(stops[i], stops[i+1], t-float64(i))
}

// pixelNoise is a steady random number in [0, 1) for a pixel and a moment.
func pixelNoise(x, y, tick int) float64 {
	h := uint32(x)*374761393 + uint32(y)*668265263 + uint32(tick)*2147483647
	h = (h ^ h>>13) * 1274126177
	return float64((h^h>>16)&0xffff) / 65536
}

// DrawCoverArt paints content.json's cover called name, as a chapter opens on it.
func DrawCoverArt(c *Canvas, name string, now float64) {
	drawChapterCoverArt(c, content.Covers[name], now)
}

// DrawCoverArtPlainSky paints the cover called name under a one-colour sky with no stars:
// the app icon, where a gradient and stars would only blur at launcher size.
func DrawCoverArtPlainSky(c *Canvas, name string, sky Color) {
	art := content.Covers[name]
	art.Sky, art.Stars = coverColors{sky}, false
	drawChapterCoverArt(c, art, 0)
}

// drawChapterCoverArt paints the chapter's cover over the canvas's rows 0 to coverHeight/2.
func drawChapterCoverArt(c *Canvas, art CoverArt, now float64) {
	var px coverPixels
	for y := range coverHeight {
		color := gradient(art.Sky, float64(y)/float64(max(1, art.Horizon-1)))
		if y >= art.Horizon {
			color = gradient(art.Ground, float64(y-art.Horizon)/float64(max(1, coverHeight-art.Horizon-1)))
		}
		for x := range coverWidth {
			px[y][x] = color
		}
	}
	if art.Stars {
		r := seeded("stars")
		for range 40 {
			x, y, phase, brightness := r.IntN(coverWidth), r.IntN(max(1, art.Horizon-3)), r.Float64(), r.Float64()
			if math.Mod(now*.4+phase, 1) > .15 {
				px.blend(x, y, Paper, .3+.5*brightness)
			}
		}
	}
	if len(art.Moon) == 2 {
		mx, my := art.Moon[0], art.Moon[1]
		px.disc(float64(mx), float64(my), 6, Paper, .12) // its glow
		px.disc(float64(mx), float64(my), 3.2, Paper, 1)
		px.set(mx-1, my, Dim)
		px.set(mx+1, my+1, Dim)
	}
	if art.Water {
		r := seeded("water")
		for range 26 {
			y := art.Horizon + 1 + r.IntN(max(1, coverHeight-art.Horizon-1))
			depth := float64(y-art.Horizon) / float64(coverHeight-art.Horizon)
			x0, length := int(r.Float64()*coverWidth+now*(1+3*depth)), 2+r.IntN(4)
			for i := range length {
				px.blend((x0+i)%coverWidth, y, Paper, .1+.25*depth)
			}
		}
	}
	for i, l := range art.Layers {
		switch {
		case l.Beam != nil:
			drawSearchlight(&px, l.X, l.Y, *l.Beam+9*math.Sin(now*.35+float64(i)))
		case l.Flash:
			drawGunfire(&px, l.X, l.Y, math.Mod(now*.9+pixelNoise(i, 1, 0), 1))
		default:
			drawCoverSprite(&px, l, now)
		}
	}
	for y := 0; y < coverHeight; y += 2 {
		for x := range coverWidth {
			c.PutOn(x, y/2, "▀", px[y][x], px[y+1][x])
		}
	}
}

// drawCoverSprite draws a layer's sprite, sheared down by Tilt, then its flames and smoke.
func drawCoverSprite(px *coverPixels, l CoverLayer, now float64) {
	rows := content.Sprites[l.Sprite]
	width := len(rows[0])
	burnFrom, burnTo := width, width
	if len(l.Fire) == 2 {
		burnFrom, burnTo = int(l.Fire[0]*float64(width)), int(l.Fire[1]*float64(width))
	}
	toCover := func(i, j int) (int, int) { return l.X + i, l.Y + j + int(math.Round(float64(i)*l.Tilt)) }
	tick := int(now * 8)
	var flameFrom [coverWidth]int // each cover column's highest burning pixel, +1; 0 where none burns
	for j, row := range rows {
		for i := range width {
			p := row[i]
			x, y := toCover(i, j)
			if p == '.' || (l.Waterline > 0 && y >= l.Waterline) {
				continue
			}
			color := spritePalette[p]
			if burnFrom <= i && i < burnTo { // the burning skin glows and flickers
				color = []Color{Ember, Ember, Alert, Flame, Lamp, color, color}[int(pixelNoise(i, j, tick)*7)]
				if 0 <= x && x < coverWidth && flameFrom[x] == 0 {
					flameFrom[x] = y + 1
				}
			}
			px.set(x, y, color)
		}
	}
	var burning []int
	for x, top := range flameFrom {
		if top == 0 {
			continue
		}
		burning = append(burning, x)
		height := 2 + int(pixelNoise(x, 0, tick)*5)
		for k := 1; k <= height; k++ {
			px.set(x, top-1-k, []Color{Lamp, Flame, Flame, Alert}[min(3, 4*(k-1)/height)])
		}
	}
	for n := range 6 * min(1, len(burning)) {
		x := burning[int(pixelNoise(n, 2, 0)*float64(len(burning)))]
		drawSmoke(px, x, flameFrom[x]-4, n, 18, Faint, now)
	}
	for n, s := range l.Smoke {
		x, y := toCover(s[0], s[1])
		drawSmoke(px, x, y, n, 10, Dim, now)
	}
}

// drawSmoke sends puffs up from x, y, drifting downwind as they rise height pixels and thin out.
func drawSmoke(px *coverPixels, x, y, seed int, height float64, color Color, now float64) {
	const puffs = 5
	for k := range puffs {
		age := math.Mod(now*.25+float64(k)/puffs+float64(seed)*.37, 1)
		cx := float64(x) + age*height*.8 + math.Sin(now+float64(k+seed))*.8
		cy := float64(y) - age*height
		px.disc(cx, cy, 1+age*2.5, color, .7*(1-age))
	}
}

// drawSearchlight lights a narrow cone from x, y at angle degrees from straight up.
func drawSearchlight(px *coverPixels, x, y int, angle float64) {
	left, right := math.Tan((angle-2.5)*math.Pi/180), math.Tan((angle+2.5)*math.Pi/180)
	for row := range y {
		rise := float64(y - row)
		for column := int(math.Ceil(float64(x) + rise*left)); float64(column) <= float64(x)+rise*right; column++ {
			px.blend(column, row, Paper, .45*(1-rise/float64(y+8)))
		}
	}
}

// drawGunfire shows a burst at x, y for the first part of each cycle; phase is where in its
// cycle it is, 0 to 1.
func drawGunfire(px *coverPixels, x, y int, phase float64) {
	if phase > .18 {
		return
	}
	px.disc(float64(x), float64(y), 4, Flame, .15) // its glow, brighter toward the middle
	px.disc(float64(x), float64(y), 2.5, Flame, .25)
	for _, d := range [][2]int{{1, 1}, {-1, -1}, {1, -1}, {-1, 1}} {
		px.set(x+d[0], y+d[1], Flame)
	}
	for _, d := range [][2]int{{0, 1}, {0, -1}, {1, 0}, {-1, 0}, {2, 0}, {-2, 0}} {
		px.set(x+d[0], y+d[1], Lamp)
	}
	px.set(x, y, Paper)
}
