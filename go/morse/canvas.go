package morse

import (
	"fmt"
	"strings"
	"unicode/utf8"
)

type Color struct{ R, G, B uint8 }

type Cell struct {
	Ch     rune
	Fg, Bg Color
}

// Canvas is a grid of coloured cells; drawing coordinates are an 80x24 area centred in it.
type Canvas struct {
	W, H, OX, OY int
	Fg, Bg       Color
	Cells        [][]Cell
}

func NewCanvas(width, height int, fg, bg Color) *Canvas {
	c := &Canvas{W: width, H: height, OX: (width - 80) / 2, OY: (height - 24) / 2, Fg: fg, Bg: bg}
	c.Cells = make([][]Cell, height)
	for y := range c.Cells {
		c.Cells[y] = make([]Cell, width)
		for x := range c.Cells[y] {
			c.Cells[y][x] = Cell{' ', fg, bg}
		}
	}
	return c
}

func (c *Canvas) cell(x, y int) *Cell {
	X, Y := x+c.OX, y+c.OY
	if X < 0 || X >= c.W || Y < 0 || Y >= c.H {
		return nil
	}
	return &c.Cells[Y][X]
}

// Put writes text from (x, y), keeping each cell's background.
func (c *Canvas) Put(x, y int, text string, fg Color) {
	i := 0
	for _, ch := range text {
		if p := c.cell(x+i, y); p != nil {
			p.Ch, p.Fg = ch, fg
		}
		i++
	}
}

// PutOn writes text from (x, y) on a background of its own.
func (c *Canvas) PutOn(x, y int, text string, fg, bg Color) {
	i := 0
	for _, ch := range text {
		if p := c.cell(x+i, y); p != nil {
			*p = Cell{ch, fg, bg}
		}
		i++
	}
}

func (c *Canvas) BackgroundAt(x, y int) Color {
	if p := c.cell(x, y); p != nil {
		return p.Bg
	}
	return c.Bg
}

// Band paints rows y0..y1-1 across the whole canvas.
func (c *Canvas) Band(y0, y1 int, bg Color) {
	for y := y0; y < y1; y++ {
		Y := y + c.OY
		if Y < 0 || Y >= c.H {
			continue
		}
		for X := range c.Cells[Y] {
			c.Cells[Y][X] = Cell{' ', c.Fg, bg}
		}
	}
}

// Center writes text centred on the drawing area: 80 columns, or the whole width of a canvas
// narrower than that with no offset (see Rows and the phone's text).
func (c *Canvas) Center(y int, text string, fg Color) {
	c.Put((c.W-2*c.OX)/2-runeLen(text)/2, y, text, fg)
}

// Rows is rows y0..y1-1 of the drawing area as a canvas of their own, sharing its cells.
func (c *Canvas) Rows(y0, y1 int) *Canvas {
	return &Canvas{W: c.W, H: y1 - y0, Fg: c.Fg, Bg: c.Bg, Cells: c.Cells[y0+c.OY : y1+c.OY]}
}

// ANSI is the whole canvas as truecolour escape sequences, one row per cursor jump.
func (c *Canvas) ANSI() string {
	var b strings.Builder
	var last *Cell
	for Y, row := range c.Cells {
		fmt.Fprintf(&b, "\x1b[%d;1H", Y+1)
		for i := range row {
			cell := &row[i]
			if last == nil || cell.Fg != last.Fg || cell.Bg != last.Bg {
				fmt.Fprintf(&b, "\x1b[38;2;%d;%d;%d;48;2;%d;%d;%dm",
					cell.Fg.R, cell.Fg.G, cell.Fg.B, cell.Bg.R, cell.Bg.G, cell.Bg.B)
				last = cell
			}
			b.WriteRune(cell.Ch)
		}
	}
	return b.String()
}

func runeLen(s string) int { return utf8.RuneCountInString(s) }

// tail is the last n runes of s.
func tail(s string, n int) string {
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[len(r)-n:])
}

// lastLetter is the last non-space rune of s, or "".
func lastLetter(s string) string {
	return tail(strings.TrimRight(s, " "), 1)
}

// ---------------------------------------------------------------- 5x7 font

const fontData = `
A .###. #...# #...# ##### #...# #...# #...#
B ####. #...# #...# ####. #...# #...# ####.
C .###. #...# #.... #.... #.... #...# .###.
D ####. #...# #...# #...# #...# #...# ####.
E ##### #.... #.... ####. #.... #.... #####
F ##### #.... #.... ####. #.... #.... #....
G .###. #...# #.... #.### #...# #...# .####
H #...# #...# #...# ##### #...# #...# #...#
I .###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.
J ..### ...#. ...#. ...#. ...#. #..#. .##..
K #...# #..#. #.#.. ##... #.#.. #..#. #...#
L #.... #.... #.... #.... #.... #.... #####
M #...# ##.## #.#.# #.#.# #...# #...# #...#
N #...# #...# ##..# #.#.# #..## #...# #...#
O .###. #...# #...# #...# #...# #...# .###.
P ####. #...# #...# ####. #.... #.... #....
Q .###. #...# #...# #...# #.#.# #..#. .##.#
R ####. #...# #...# ####. #.#.. #..#. #...#
S .#### #.... #.... .###. ....# ....# ####.
T ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
U #...# #...# #...# #...# #...# #...# .###.
V #...# #...# #...# #...# #...# .#.#. ..#..
W #...# #...# #...# #.#.# #.#.# #.#.# .#.#.
X #...# #...# .#.#. ..#.. .#.#. #...# #...#
Y #...# #...# .#.#. ..#.. ..#.. ..#.. ..#..
Z ##### ....# ...#. ..#.. .#... #.... #####
0 .###. #...# #..## #.#.# ##..# #...# .###.
1 ..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.
2 .###. #...# ....# ...#. ..#.. .#... #####
3 ##### ...#. ..#.. ...#. ....# #...# .###.
4 ...#. ..##. .#.#. #..#. ##### ...#. ...#.
5 ##### #.... ####. ....# ....# #...# .###.
6 ..##. .#... #.... ####. #...# #...# .###.
7 ##### ....# ...#. ..#.. .#... .#... .#...
8 .###. #...# #...# .###. #...# #...# .###.
9 .###. #...# #...# .#### ....# ...#. .##..
! ..#.. ..#.. ..#.. ..#.. ..#.. ..... ..#..
? .###. #...# ....# ...#. ..#.. ..... ..#..
_ ..... ..... ..... ..... ..... ..... #####
`

var Font = func() map[rune][]string {
	font := map[rune][]string{}
	for _, line := range strings.Split(strings.TrimSpace(fontData), "\n") {
		font[rune(line[0])] = strings.Fields(line[2:])
	}
	return font
}()

// unaccented maps the Portuguese capitals to the letter the font draws for them.
var unaccented = map[rune]rune{
	'Á': 'A', 'À': 'A', 'Â': 'A', 'Ã': 'A', 'É': 'E', 'Ê': 'E', 'Í': 'I',
	'Ó': 'O', 'Ô': 'O', 'Õ': 'O', 'Ú': 'U', 'Ü': 'U', 'Ç': 'C',
}

func BigTextWidth(text string) int { return runeLen(text)*6 - 1 }

// Big draws text in the 5x7 pixel font, 4 cells tall.
func Big(c *Canvas, x, y int, text string, color Color) {
	n := -1
	for _, ch := range text {
		n++
		glyph, ok := Font[ch]
		if !ok {
			glyph, ok = Font[unaccented[ch]]
		}
		if !ok {
			continue
		}
		rows := append(append([]string{}, glyph...), ".....")
		for r := 0; r < 8; r += 2 {
			for i := 0; i < 5; i++ {
				a, b := rows[r][i] == '#', rows[r+1][i] == '#'
				X, Y := x+n*6+i, y+r/2
				if a {
					bg := c.BackgroundAt(X, Y)
					if b {
						bg = color
					}
					c.PutOn(X, Y, "▀", color, bg)
				} else if b {
					c.Put(X, Y, "▄", color)
				}
			}
		}
	}
}

func BigCenter(c *Canvas, y int, text string, color Color) {
	Big(c, 40-BigTextWidth(text)/2, y, text, color)
}

// DrawTypedLines centres lines from row y, revealed 40 characters a second; true once all are shown.
func DrawTypedLines(c *Canvas, y int, lines []string, elapsed float64, color Color) bool {
	budget := int(elapsed * 40)
	for i, line := range lines {
		r := []rune(line)
		shown := string(r[:max(0, min(budget, len(r)))])
		c.Center(y+i, shown+strings.Repeat(" ", len(r)-runeLen(shown)), color)
		budget -= len(r) + 8 // a short pause between lines
	}
	return budget >= 0
}

// Sprite draws pixel art packed two rows per cell with half blocks; '.' is transparent.
// flicker swaps the O and Y pixels (flames); faded, when set, draws every pixel in that colour.
func Sprite(c *Canvas, x, y int, rows []string, palette map[byte]Color, flicker bool, faded *Color) {
	if len(rows)%2 == 1 {
		rows = append(append([]string{}, rows...), strings.Repeat(".", len(rows[0])))
	}
	pixel := func(p byte, under Color) Color {
		switch {
		case p == '.':
			return under
		case faded != nil:
			return *faded
		case flicker && p == 'O':
			p = 'Y'
		case flicker && p == 'Y':
			p = 'O'
		}
		return palette[p]
	}
	for r := 0; r < len(rows); r += 2 {
		for i := 0; i < len(rows[r]); i++ {
			a, b := rows[r][i], rows[r+1][i]
			if a == '.' && b == '.' {
				continue
			}
			under := c.BackgroundAt(x+i, y+r/2)
			c.PutOn(x+i, y+r/2, "▀", pixel(a, under), pixel(b, under))
		}
	}
}
