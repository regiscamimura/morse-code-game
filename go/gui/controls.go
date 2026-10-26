package gui

import (
	"image"
	"image/color"
	"math"
	"slices"
	"strings"

	"github.com/hajimehoshi/ebiten/v2"
	"github.com/hajimehoshi/ebiten/v2/text/v2"
	"github.com/hajimehoshi/ebiten/v2/vector"

	"github.com/regiscamimura/morse-code-game/go/morse"
)

// control is one tappable area of the phone: a button that sends key, or the telegraph key.
type control struct {
	label        string
	key          string
	rect         image.Rectangle
	telegraphKey bool
	action       bool // one of the screen's buttons, not a letter: an amber lamp
}

// action is a button before it's placed: its label in each language and the key it sends.
type action struct {
	en, pt string
	key    string
}

func (a action) label(lang string) string {
	if lang == "pt" {
		return a.pt
	}
	return a.en
}

// The buttons a phone shows below the game, with its keyboard or telegraph key; Back is ESC.
var (
	english        = action{"ENGLISH", "ENGLISH", "1"}
	portuguese     = action{"PORTUGUÊS", "PORTUGUÊS", "2"}
	confirm        = action{"OK", "OK", morse.KeyEnter}
	begin          = action{"BEGIN", "COMEÇAR", morse.KeyEnter}
	resume         = action{"CONTINUE", "CONTINUAR", "c"}
	practice       = action{"PRACTICE", "PRATICAR", "p"}
	language       = action{"LANGUAGE", "IDIOMA", "l"}
	hint           = action{"HINT", "DICA", morse.KeyTab}
	repeat         = action{"REPEAT", "REPETIR", morse.KeyTab}
	hearNew        = action{"HEAR AGAIN", "OUVIR DE NOVO", morse.KeyTab}
	erase          = action{"ERASE", "APAGAR", morse.KeyBackspace}
	enter          = action{"ENTER", "ENTER", morse.KeyEnter}
	telegraphLine  = action{"LINE", "LINHA", "w"}
	callNumber     = action{"CALL", "CHAMAR", morse.KeyEnter}
	changeCodename = action{"CODENAME", "CODINOME", morse.KeyTab}
	answerCall     = action{"ANSWER", "ATENDER", morse.KeyEnter}
	declineCall    = action{"DECLINE", "RECUSAR", morse.KeyEscape}
	hangUp         = action{"HANG UP", "DESLIGAR", morse.KeyEscape}
	clearTapes     = action{"CLEAR", "LIMPAR", morse.KeyBackspace}
)

// keyboardRows are the keyboard's keys while typing (a received word, a codename, a number to
// dial); the last row adds ⌫, and a row of buttons follows.
var keyboardRows = []string{"1234567890", "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"}

// screenActions are the buttons for the game's current screen.
func (a *App) screenActions() []action {
	g := a.game
	switch g.State() {
	case "lang":
		return []action{english, portuguese, confirm}
	case "title":
		actions := []action{begin, practice, language}
		if g.SavedChapter() > 1 {
			actions = []action{begin, resume, practice, language}
		}
		if g.LineAvailable() {
			actions = append(actions, telegraphLine)
		}
		return actions
	case "codename":
		return []action{confirm}
	case "switchboard":
		return []action{callNumber, changeCodename}
	case "calling":
		return []action{hangUp}
	case "ringing":
		return []action{answerCall, declineCall}
	case "line":
		return []action{clearTapes, hangUp}
	}
	switch {
	case g.State() == "chapter" && g.DrillDone():
		return []action{hearNew, enter}
	case g.State() == "chapter":
		return []action{hearNew}
	case g.State() == "free":
		return []action{erase}
	case g.Receiving():
		return []action{repeat}
	case g.State() == "play":
		return []action{hint}
	}
	return []action{enter}
}

// controlsArea is the phone's screen below the game: all of it for the telegraph key or the
// keyboard, else just the bottom, enough for a row of buttons.
func (a *App) controlsArea() image.Rectangle {
	top := a.gameBottom
	if !a.game.Keying() && !a.game.Typing() {
		top = max(top, a.height-a.controlsMinHeight())
	}
	return image.Rect(0, top, a.width, a.height)
}

// layoutControls lays out the phone's controls below the game: a row of the screen's buttons
// at the bottom, and above it the red telegraph key while keying, or a keyboard while
// receiving. Every row is as wide as the screen.
func (a *App) layoutControls() []control {
	below := a.controlsArea()
	gap := max(3, below.Dx()/100)
	area := below.Inset(gap * 3)
	// a key's height: a fifth of the room under a keyboard, a quarter under the telegraph key,
	// all of it for buttons alone; never taller than a 10-key row's keys are wide, times 1.6
	keyHeight := area.Dy()
	switch {
	case a.game.Typing():
		keyHeight = (area.Dy() - gap*4) / 5
	case a.game.Keying():
		keyHeight = area.Dy() / 4
	}
	keyHeight = min(keyHeight, area.Dx()/10*8/5)
	lang := a.game.Lang()

	var controls []control
	buttons := image.Rect(area.Min.X, area.Max.Y-keyHeight, area.Max.X, area.Max.Y)
	for i, r := range splitRow(buttons, gap, slices.Repeat([]int{1}, len(a.screenActions()))) {
		b := a.screenActions()[i]
		controls = append(controls, control{label: b.label(lang), key: b.key, action: true, rect: r})
	}
	above := image.Rect(area.Min.X, area.Min.Y, area.Max.X, buttons.Min.Y-gap*3)

	if a.game.Keying() {
		side := min(above.Dx(), above.Dy(), a.width*45/100)
		center := image.Pt((above.Min.X+above.Max.X)/2, (above.Min.Y+above.Max.Y)/2)
		square := image.Rect(center.X-side/2, center.Y-side/2, center.X+side/2, center.Y+side/2)
		return append(controls, control{rect: square, telegraphKey: true})
	}
	if !a.game.Typing() {
		return controls
	}

	y := above.Max.Y - len(keyboardRows)*(keyHeight+gap) + gap
	for i, row := range keyboardRows {
		labels, keys, widths := strings.Split(row, ""), strings.Split(strings.ToLower(row), ""), slices.Repeat([]int{2}, len(row))
		if i == len(keyboardRows)-1 {
			labels, keys, widths = append(labels, "⌫"), append(keys, morse.KeyBackspace), append(widths, 3)
		}
		for j, r := range splitRow(image.Rect(area.Min.X, y, area.Max.X, y+keyHeight), gap, widths) {
			controls = append(controls, control{label: labels[j], key: keys[j], rect: r})
		}
		y += keyHeight + gap
	}
	return controls
}

// splitRow divides row into keys separated by gap, each as wide as its share of weights.
func splitRow(row image.Rectangle, gap int, weights []int) []image.Rectangle {
	total := 0
	for _, w := range weights {
		total += w
	}
	space := row.Dx() - gap*(len(weights)-1)
	rects, x, used := make([]image.Rectangle, len(weights)), row.Min.X, 0
	for i, w := range weights {
		used += w
		right := row.Min.X + space*used/total + gap*i
		rects[i] = image.Rect(x, row.Min.Y, right, row.Max.Y)
		x = right + gap
	}
	return rects
}

// The controls look like a submarine's panel: lamps of tinted glass on dark riveted steel,
// glowing when pressed, and a flat red telegraph key.
var (
	steel       = color.NRGBA{20, 25, 31, 255}
	steelSeam   = color.NRGBA{34, 41, 50, 255}
	rivet       = color.NRGBA{52, 61, 72, 255}
	sonarGreen  = color.NRGBA{80, 235, 170, 255}
	lampAmber   = color.NRGBA{255, 178, 64, 255}
	keyRed      = color.NRGBA{178, 34, 34, 255}
	keyRedLit   = color.NRGBA{236, 62, 48, 255}
	keyRedShade = color.NRGBA{120, 22, 22, 255}
)

// panelPainter keeps the steel and the unlit glass keys drawn on an image of its own, redrawn
// only when the controls change: they're too slow to draw every frame, or every key press,
// on a phone. The key held down is lit on top of it each frame.
type panelPainter struct {
	image    *ebiten.Image
	controls []control
}

func (a *App) drawControls(screen *ebiten.Image) {
	below := a.controlsArea()
	p := &a.panel
	if p.image == nil || p.image.Bounds() != screen.Bounds() {
		if p.image != nil {
			p.image.Deallocate()
		}
		p.image, p.controls = ebiten.NewImage(screen.Bounds().Dx(), screen.Bounds().Dy()), nil
	}
	if p.controls == nil || !slices.Equal(p.controls, a.controls) {
		p.controls = a.controls
		p.image.Clear()
		drawSteelPanel(p.image, below)
		for _, c := range a.controls {
			if !c.telegraphKey {
				drawGlassKey(p.image, c, controlTint(c), false)
			}
		}
	}
	op := &ebiten.DrawImageOptions{}
	op.GeoM.Translate(float64(below.Min.X), float64(below.Min.Y))
	screen.DrawImage(p.image.SubImage(below).(*ebiten.Image), op)
	for _, c := range a.controls {
		switch {
		case c.telegraphKey:
			drawTelegraphKey(screen, c.rect, a.keyPointer != noPointer)
		case c.rect == a.heldButton:
			drawGlassKey(screen, c, controlTint(c), true)
		}
	}
}

// controlTint: amber for the screen's buttons, green for the keyboard's letters.
func controlTint(c control) color.NRGBA {
	if c.action {
		return lampAmber
	}
	return sonarGreen
}

// drawTelegraphKey draws the telegraph key as a flat red square with a darker lower edge,
// brighter and pushed down by that edge while held.
func drawTelegraphKey(screen *ebiten.Image, r image.Rectangle, held bool) {
	x, y, w, h := float32(r.Min.X), float32(r.Min.Y), float32(r.Dx()), float32(r.Dy())
	edge := max(4, h/24)
	if held {
		vector.FillRect(screen, x, y+edge, w, h-edge, keyRedLit, false)
		return
	}
	vector.FillRect(screen, x, y+h-edge, w, edge, keyRedShade, false)
	vector.FillRect(screen, x, y, w, h-edge, keyRed, false)
}

// drawSteelPanel fills the area below the game with steel plate, a seam along its top and a
// rivet in each corner.
func drawSteelPanel(screen *ebiten.Image, r image.Rectangle) {
	x, y, w, h := float32(r.Min.X), float32(r.Min.Y), float32(r.Dx()), float32(r.Dy())
	vector.FillRect(screen, x, y, w, h, steel, false)
	seam := max(2, w/300)
	vector.FillRect(screen, x, y, w, seam, steelSeam, false)
	inset, size := w/60, max(3, w/180)
	for _, corner := range [][2]float32{{x + inset, y + inset}, {x + w - inset, y + inset}, {x + inset, y + h - inset}, {x + w - inset, y + h - inset}} {
		vector.FillCircle(screen, corner[0], corner[1], size, rivet, true)
	}
}

// withAlpha is tint at the given opacity, 0 to 1.
func withAlpha(tint color.NRGBA, opacity float64) color.NRGBA {
	tint.A = uint8(255 * opacity)
	return tint
}

// roundedRect is r with corners rounded by radius, grown by grow on every side.
func roundedRect(r image.Rectangle, radius, grow float32) *vector.Path {
	x0, y0 := float32(r.Min.X)-grow, float32(r.Min.Y)-grow
	x1, y1 := float32(r.Max.X)+grow, float32(r.Max.Y)+grow
	radius += grow
	var p vector.Path
	p.MoveTo(x0+radius, y0)
	p.LineTo(x1-radius, y0)
	p.QuadTo(x1, y0, x1, y0+radius)
	p.LineTo(x1, y1-radius)
	p.QuadTo(x1, y1, x1-radius, y1)
	p.LineTo(x0+radius, y1)
	p.QuadTo(x0, y1, x0, y1-radius)
	p.LineTo(x0, y0+radius)
	p.QuadTo(x0, y0, x0+radius, y0)
	p.Close()
	return &p
}

func fillPath(screen *ebiten.Image, p *vector.Path, c color.Color) {
	op := &vector.DrawPathOptions{AntiAlias: true}
	op.ColorScale.ScaleWithColor(c)
	vector.FillPath(screen, p, nil, op)
}

func strokePath(screen *ebiten.Image, p *vector.Path, width float32, c color.Color) {
	op := &vector.DrawPathOptions{AntiAlias: true}
	op.ColorScale.ScaleWithColor(c)
	vector.StrokePath(screen, p, &vector.StrokeOptions{Width: width}, op)
}

// drawGlassKey draws a key as a lamp of tinted glass: dim with a glowing rim and legend, and
// lit up with a halo while held.
func drawGlassKey(screen *ebiten.Image, c control, tint color.NRGBA, lit bool) {
	r := c.rect
	radius := min(float32(min(r.Dx(), r.Dy()))*.16, 40)
	rim := min(max(2, float32(r.Dy())/28), 7)
	body, legend := withAlpha(tint, .16), color.Color(tint)
	if lit {
		for i := 4; i >= 1; i-- {
			fillPath(screen, roundedRect(r, radius, float32(i)*rim*1.5), withAlpha(tint, .07))
		}
		body, legend = withAlpha(tint, .8), color.NRGBA{255, 255, 255, 255}
	}
	fillPath(screen, roundedRect(r, radius, 0), body)
	glare := image.Rect(r.Min.X, r.Min.Y, r.Max.X, r.Min.Y+r.Dy()*2/5).Inset(int(rim * 2))
	fillPath(screen, roundedRect(glare, radius*.6, 0), color.NRGBA{255, 255, 255, 14})
	strokePath(screen, roundedRect(r, radius, 0), rim, withAlpha(tint, .75))
	size := math.Min(float64(r.Dy())*.45, float64(r.Dx())/(float64(len([]rune(c.label)))*.6+.6))
	drawLabel(screen, c.label, size, r, legend)
}

func drawLabel(screen *ebiten.Image, label string, size float64, r image.Rectangle, ink color.Color) {
	op := &text.DrawOptions{}
	op.PrimaryAlign, op.SecondaryAlign = text.AlignCenter, text.AlignCenter
	op.GeoM.Translate(float64(r.Min.X+r.Max.X)/2, float64(r.Min.Y+r.Max.Y)/2)
	op.ColorScale.ScaleWithColor(ink)
	text.Draw(screen, label, &text.GoTextFace{Source: monoFont, Size: size}, op)
}
