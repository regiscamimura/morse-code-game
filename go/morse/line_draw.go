package morse

import (
	"math"
	"strconv"
	"strings"
)

// The telegraph line's screens: a switchboard of brass and bakelite.

var (
	brassPlate = Color{176, 136, 64}
	bakelite   = Color{30, 28, 30}
	dialFace   = Color{226, 214, 184}
)

// dialCenterX, dialCenterY: the rotary dial's middle on the 80x24 screen. It's a circle 20
// columns wide and 10 rows tall, which is round because cells are twice as tall as wide.
const dialCenterX, dialCenterY = 22.0, 16.5

func (g *Game) drawCodename(c *Canvas, now float64) {
	g.drawExchangeBand(c, Band, g.text("exchange", nil))
	c.Center(3, g.text("choose_codename", nil), Paper)
	c.Center(4, g.text("codename_hint", nil), Dim)
	name := g.line.codename
	if blinkOn(now) && len(name) < maxCodenameLen {
		name += "_"
	}
	BigCenter(c, 8, name, Amber)
	c.Center(23, g.text("codename_help", nil), Faint)
}

// drawSwitchboard draws the switchboard, ringing or calling: the brass plate with this line's
// number, the dial, and on its right the number dialled, or the lamp of a call coming in.
func (g *Game) drawSwitchboard(c *Canvas, now float64) {
	g.drawExchangeBand(c, Band, g.text("exchange", nil))
	g.drawNumberPlate(c, 2)
	c.Center(8, g.text("codename_is", map[string]any{"name": g.line.codename}), Paper)
	status, color := g.lineStatusText()
	c.Center(9, status, color)

	rotation, turning := g.dialRotation(now)
	drawRotaryDial(c, rotation, turning)
	switch g.state {
	case "ringing":
		lit := int(now*4)%2 == 0
		lamp := Faint
		if lit {
			lamp = Lamp
		}
		fillEllipse(c, 61, 16, 8, 3.2, lamp)
		c.Put(52, 21, centerIn("MORSE "+strconv.Itoa(g.line.peerNumber), 18), Paper)
	default:
		label := g.text("dial_label", nil)
		if g.state == "calling" {
			label = g.text("calling_label", nil)
		}
		c.Put(44, 12, label, Dim)
		digits := g.line.dialed
		if g.state == "calling" {
			digits = strconv.Itoa(g.line.peerNumber)
		} else if blinkOn(now) && len(digits) < maxDialedDigits {
			digits += "_"
		}
		Big(c, 44, 14, digits, Amber)
	}
	if now < g.msgUntil {
		c.Center(22, g.msg, g.msgColor)
	}
	c.Center(23, g.text(g.state+"_help", nil), Faint)
}

// lineStatusText says where this line stands with the exchange, or the call in progress.
func (g *Game) lineStatusText() (string, Color) {
	switch {
	case g.state == "ringing":
		return g.text("ringing", map[string]any{"n": g.line.peerNumber, "name": g.line.peerCodename}), Lamp
	case g.state == "calling":
		return g.text("calling", map[string]any{"n": g.line.peerNumber}), Amber
	case g.line.status == "online":
		return g.text("online", nil), Go
	case g.line.status == "offline":
		return g.text("offline", nil), Alert
	}
	return g.text("connecting", nil), Dim
}

func (g *Game) drawExchangeBand(c *Canvas, band Color, title string) {
	c.Band(0, 1, band)
	c.Center(0, title, Amber)
}

// drawNumberPlate draws this line's number in big letters on a brass plate, from row y.
func (g *Game) drawNumberPlate(c *Canvas, y int) {
	number := g.LineNumber()
	width := BigTextWidth(number) + 6
	x := 40 - width/2
	for row := y; row < y+6; row++ {
		c.PutOn(x, row, strings.Repeat(" ", width), Ink, brassPlate)
	}
	c.PutOn(x+1, y, "▪", bakelite, brassPlate)
	c.PutOn(x+width-2, y, "▪", bakelite, brassPlate)
	Big(c, x+3, y+1, number, bakelite)
}

// drawRotaryDial draws the dial turned `rotation` degrees clockwise: a bakelite wheel with the
// digits in its finger holes, the finger stop at four o'clock, and the digit being dialled lit.
func drawRotaryDial(c *Canvas, rotation float64, turning string) {
	fillEllipse(c, dialCenterX, dialCenterY, 10, 5, bakelite)
	fillEllipse(c, dialCenterX, dialCenterY, 3.2, 1.6, dialFace)
	c.Put(int(math.Round(dialCenterX-2.5)), int(math.Floor(dialCenterY-.5)), "MORSE", bakelite)
	for i, digit := range strings.Split("1234567890", "") {
		// clockwise from twelve o'clock: 1 at 60°, the rest 30° apart going back round
		angle := (60 - float64(i)*30 + rotation) * math.Pi / 180
		x := dialCenterX + 7.4*math.Sin(angle)
		y := dialCenterY - 3.7*math.Cos(angle)
		color := Paper
		if digit == turning {
			color = Lamp
		}
		c.Put(int(math.Round(x-.5)), int(math.Round(y-.5)), digit, color)
	}
	stop := 120 * math.Pi / 180
	c.Put(int(math.Round(dialCenterX+9.6*math.Sin(stop)-.5)), int(math.Round(dialCenterY-4.8*math.Cos(stop)-.5)), "▲", brassPlate)
}

// fillEllipse fills an ellipse centred on (cx, cy) in cells, rx columns and ry rows across from
// its middle, drawing its edge in half cells.
func fillEllipse(c *Canvas, cx, cy, rx, ry float64, color Color) {
	inside := func(x, y float64) bool {
		dx, dy := (x-cx)/rx, (y-cy)/ry
		return dx*dx+dy*dy <= 1
	}
	for y := int(cy - ry - 1); y <= int(cy+ry+1); y++ {
		for x := int(cx - rx - 1); x <= int(cx+rx+1); x++ {
			top, bottom := inside(float64(x)+.5, float64(y)+.25), inside(float64(x)+.5, float64(y)+.75)
			switch {
			case top && bottom:
				c.PutOn(x, y, " ", c.Fg, color)
			case top:
				c.PutOn(x, y, "▀", color, c.BackgroundAt(x, y))
			case bottom:
				c.PutOn(x, y, "▄", color, c.BackgroundAt(x, y))
			}
		}
	}
}

// drawLine draws a call in progress: each side's lamp, the letter it's keying and what it has
// keyed, this player on the left.
func (g *Game) drawLine(c *Canvas, now float64) {
	g.drawExchangeBand(c, ListenBand, g.text("on_the_line", map[string]any{"n": g.line.peerNumber, "name": g.line.peerCodename}))
	k := g.keyer
	sides := []struct {
		name   string
		lit    bool
		live   string
		keyed  string
		middle int
	}{
		{g.text("you", nil) + " · " + g.line.codename, k.Sounding() || (k.Down() && now-k.Last < .12), k.Live(now), g.freeText, 20},
		{g.line.peerCodename, g.line.remoteToneOn, g.line.remote.Live(now), g.line.remoteText, 60},
	}
	for _, side := range sides {
		c.Put(side.middle-runeLen(side.name)/2, 2, side.name, Paper)
		lamp := Faint
		if side.lit {
			lamp = Lamp
		}
		fillEllipse(c, float64(side.middle), 5.5, 7, 2.6, lamp)
		pattern := Pretty(side.live)
		c.Put(side.middle-runeLen(pattern)/2, 9, pattern, Lamp)
		last := tail(strings.TrimRight(side.keyed, " "), 5)
		Big(c, side.middle-BigTextWidth(last)/2, 11, last, Amber)
		typed := tail(side.keyed, 36)
		c.Put(side.middle-runeLen(typed)/2, 16, typed, Dim)
	}
	if now < g.msgUntil {
		c.Center(21, g.msg, g.msgColor)
	}
	c.Center(23, g.text("line_help", nil), Faint)
}
