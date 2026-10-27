package morse

import "strings"

// The cover is the SOS MORSE cartridge from the terminal version's picker (play.py), in its
// Atari 2600 colours, standing above the console's slot.

var (
	coverBlack   = Color{0, 0, 0}
	plastic      = Color{30, 30, 32}
	ridge        = Color{58, 58, 62}
	cartLabel    = Color{12, 12, 12}
	coverWhite   = Color{236, 236, 236}
	coverGrey    = Color{142, 142, 142}
	coverYellow  = Color{252, 224, 112}
	brass        = Color{214, 164, 62}
	woodLight    = Color{150, 92, 40}
	woodDark     = Color{84, 46, 18}
	consoleSlot  = Color{8, 8, 8}
	rainbow      = []Color{{200, 72, 72}, {227, 128, 44}, coverYellow, {92, 186, 92}, {84, 184, 204}, {45, 50, 184}, {120, 92, 214}}
	labelStripes = [3]Color{{227, 128, 44}, {200, 72, 72}, brass}
)

var telegraphKeyArt = []string{
	"..Y..............Y..", "...Y....KKKK....Y...", "........KKKK........",
	".........SS.........", "..AAAAAAAAAAAAAAA...", ".........SS....SS...",
	"........SSSS...SS...", "..NNNNNNNNNNNNNNNN..", "..NNNNNNNNNNNNNNNN..",
	"....................",
}

var cartridgePalette = map[byte]Color{'K': {16, 16, 16}, 'S': coverGrey, 'Y': coverYellow, 'A': brass, 'N': {110, 62, 24}}

// CartridgeWidth and CartridgeHeight are the cartridge's size in cells.
const CartridgeWidth, CartridgeHeight = 26, 15

// cartridgeX centres the cartridge on the 80-column screen.
const cartridgeX = (80 - CartridgeWidth) / 2

// InsertSeconds is how long the cartridge takes to slide in; CoverSeconds adds the power-on flicker.
const InsertSeconds, CoverSeconds = .7, 1.2

// DrawCartridge draws the cartridge with its top-left cell at (x, y): a ridged plastic grip,
// then the label with the title, the telegraph key and the subtitle.
func DrawCartridge(c *Canvas, x, y int) {
	for row := range CartridgeHeight {
		c.PutOn(x, y+row, strings.Repeat(" ", CartridgeWidth), coverWhite, plastic)
	}
	for row := range 3 {
		c.PutOn(x+1, y+row, strings.Repeat("▀", CartridgeWidth-2), ridge, plastic)
	}
	labelX, width := x+2, CartridgeWidth-4
	for row := 4; row < 13; row++ {
		c.PutOn(labelX, y+row, strings.Repeat(" ", width), coverWhite, cartLabel)
	}
	first, second, third := labelStripes[0], labelStripes[1], labelStripes[2]
	c.PutOn(labelX, y+4, centerIn("SOS MORSE", width), coverBlack, first)
	c.PutOn(labelX, y+5, strings.Repeat("▀", width), second, third)
	Sprite(c, x+3, y+6, telegraphKeyArt, cartridgePalette, false, nil)
	c.PutOn(labelX, y+11, centerIn("HOLD THE LINE", width), coverGrey, cartLabel)
	c.PutOn(labelX, y+12, strings.Repeat("▀", width), third, second)
}

func centerIn(text string, width int) string {
	left := (width - runeLen(text)) / 2
	return strings.Repeat(" ", left) + text + strings.Repeat(" ", width-left-runeLen(text))
}

// DrawCover draws the cover screen. inserted is the seconds since the player started the game
// (negative before): the cartridge slides into the slot, then the screen flickers on.
func DrawCover(width, height int, now, inserted float64) *Canvas {
	c := NewCanvas(width, height, coverWhite, coverBlack)
	if inserted > InsertSeconds {
		if inserted < InsertSeconds+.25 {
			c.Band(0, 24, rainbow[int(inserted*20)%len(rainbow)])
		}
		return c
	}
	for _, y := range []int{0, 5} {
		for i, color := range rainbow {
			c.Put(i*12-2, y, strings.Repeat("▀", 12), color)
		}
	}
	BigCenter(c, 1, "SOS MORSE", coverYellow)
	y := 5
	if inserted >= 0 {
		y += int(min(1, inserted/InsertSeconds) * 13)
	}
	DrawCartridge(c, cartridgeX, y)
	drawConsole(c)
	if int(now*1.5)%2 == 1 && inserted < 0 {
		c.Center(23, "TAP OR ENTER  ·  TOQUE OU ENTER", coverGrey)
	}
	return c
}

// drawConsole draws the woodgrain console top the cartridge slides into.
func drawConsole(c *Canvas) {
	c.Band(20, 21, coverBlack)
	c.PutOn(cartridgeX-1, 20, strings.Repeat(" ", CartridgeWidth+2), coverWhite, consoleSlot)
	for y, wood := range map[int][2]Color{21: {woodLight, woodDark}, 22: {woodDark, woodLight}} {
		light, dark := wood[0], wood[1]
		c.Band(y, y+1, dark)
		var grain strings.Builder
		for i := range 80 {
			if (i*7+y)%5 != 0 {
				grain.WriteString("▀")
			} else {
				grain.WriteString("▄")
			}
		}
		c.Put(0, y, grain.String(), light)
	}
	c.Band(23, 24, coverBlack)
}
