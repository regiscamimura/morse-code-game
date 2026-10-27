package morse

import (
	"fmt"
	"strings"
)

// A phone held upright is too narrow for 80 columns of readable text. DrawPhone keeps the
// pictures (scenes, big letters) at 80 columns, cut from Draw, and sets the words between
// them in fewer, larger columns. The phone's buttons stand in for the key hints, so those
// lines are left out.

// DrawPhone renders the current screen as strips to stack top to bottom, each as wide as the
// screen: rows of the 80-column picture, and runs of text `columns` wide.
func (g *Game) DrawPhone(columns int, now float64) []*Canvas {
	picture := g.Draw(80, 24, now)
	p := &page{columns: columns}
	elapsed := now - g.stateStart
	switch g.state {
	case "lang":
		p.picture(picture, 3, 18)
		p.blank()
		for i := range languageNames {
			p.center(g.languageOption(i))
		}
		p.blank()
		p.center(showIf(blinkOn(now), "[ENTER] OK"), Amber)
		p.blank()
		p.center(g.text("privacy", nil), Dim)
		p.center(strings.TrimPrefix(PrivacyURL, "https://"), Dim)
	case "title":
		p.center(showIf(g.hi > 0, g.text("best", map[string]any{"best": g.hi})), Faint)
		p.picture(picture, 3, 18)
		p.center(g.text("subtitle", nil), Teal)
	case "volume":
		_, title, subtitle, lines := g.shownVolume()
		p.blanks(2)
		p.picture(picture, 3, 7)
		p.blank()
		p.wrapped(title, Paper)
		p.center(subtitle, Dim)
		p.blank()
		g.typedAll = p.typed(paragraphs(lines, columns-2), elapsed, Paper)
		p.blank()
		p.center(showIf(g.typedAll && g.readyToContinue(now) && blinkOn(now), g.text("continue", nil)), Amber)
	case "cover": // set out like a book's cover: chapter, picture, year, title
		p.blanks(3)
		p.center(g.text("chapter_label", g.chapterNumbers(g.chapter)), Dim)
		p.blank()
		p.picture(picture, 0, coverHeight/2)
		p.blank()
		p.picture(picture, coverYearRow, coverYearRow+4)
		p.blanks(2)
		p.wrapped(g.currentChapter().Title, Paper)
		p.blank()
		p.wrapped(g.currentChapter().Place, Teal)
		p.wrapped(g.currentChapter().Era, Dim)
		p.blank()
		p.center(showIf(g.readyToContinue(now) && blinkOn(now), g.text("continue", nil)), Amber)
	case "chapter":
		g.drawPhoneHud(p)
		p.center(g.text("chapter_label", g.chapterNumbers(g.chapter)), Dim)
		p.wrapped(g.currentChapter().Title, Dim)
		p.blank()
		p.wrapped(g.lettersLabel(), Teal)
		p.picture(picture, 6, 13)
		p.wrapped(g.drillLine())
		p.blank()
		c, y := p.row(Ink)
		try := g.text("try_them", nil)
		c.Put(1, y, try+tail(g.freeText, columns-2-runeLen(try)), Dim)
		c, y = p.row(Ink)
		g.drawKey(c, 1, y, now)
		p.blank()
		p.center(showIf(g.DrillDone() && blinkOn(now), g.text("enter_begin", nil)), Amber)
	case "brief":
		g.drawPhoneHud(p)
		g.drawPhoneHeader(p)
		p.wrapped(g.chapterLine(), Teal)
		p.picture(picture, 3, 13)
		p.blank()
		var lines []string
		for _, line := range g.beat.Brief {
			lines = append(lines, g.withWord(line))
		}
		g.typedAll = p.typed(append(lines, "", g.task()), elapsed, Paper)
		p.blank()
		p.center(showIf(g.typedAll && g.mode == "encode", g.text("code_word", map[string]any{"word": g.word})), Amber)
		p.center(showIf(g.typedAll && blinkOn(now), g.text("ready", nil)), Amber)
	case "play":
		g.drawPhoneHud(p)
		g.drawPhoneHeader(p)
		p.wrapped(g.task(), Teal)
		lines, _, keyRow := g.messageLayout()
		p.picture(picture, 3, keyRow)
		if len(lines) > 1 { // no room under two lines for the hint: it sits over the key
			p.center(g.hintPattern(), Teal)
		} else {
			p.blank()
		}
		c, y := p.row(Ink)
		if g.mode == "encode" {
			g.drawKey(c, 1, y, now)
		} else {
			g.drawLampAndTape(c, 1, y, columns-runeLen(g.text("lamp", nil))-4, now)
		}
		p.center(showIf(now < g.msgUntil, g.msg), g.msgColor)
	case "win", "lose":
		g.drawPhoneHud(p)
		g.drawPhoneHeader(p)
		p.picture(picture, 3, 18)
		verdict, outcome, outcomeColor := g.resultLines(g.state == "win")
		p.wrapped(g.wordInCode(), Teal)
		p.wrapped(verdict, Paper)
		p.center(outcome, outcomeColor)
		p.blank()
		p.center(showIf(g.readyToContinue(now) && blinkOn(now), g.text("continue", nil)), Amber)
	case "free":
		c, y := p.row(Band)
		c.Center(y, g.text("practice", nil), Amber)
		g.drawPhoneCodeChart(p)
		p.picture(picture, 12, 16)
		p.center(tail(g.freeText, columns-4), Dim)
		c, y = p.row(Ink)
		g.drawKey(c, 1, y, now)
	case "game_over":
		p.picture(picture, 5, 9)
		p.blank()
		p.wrapped(g.text("over_line", nil), Dim)
		p.blank()
		p.center(g.text("final_score", map[string]any{"score": g.score}), Amber)
		p.center(showIf(g.newHi, g.text("new_best", nil)), Paper)
		p.blank()
		p.wrapped(g.text("over_continue", g.chapterNumbers(g.chapter)), Dim)
		p.blank()
		p.center(showIf(g.readyToContinue(now) && blinkOn(now), "[ENTER]"), Paper)
	case "codename":
		c, y := p.row(Band)
		c.Center(y, g.text("exchange", nil), Amber)
		p.blank()
		p.wrapped(g.text("choose_codename", nil), Paper)
		p.wrapped(g.text("codename_hint", nil), Dim)
		p.picture(picture, 7, 13)
	case "switchboard", "calling", "ringing":
		c, y := p.row(Band)
		c.Center(y, g.text("exchange", nil), Amber)
		p.picture(picture, 2, 8)
		p.wrapped(g.text("codename_is", map[string]any{"name": g.line.codename}), Paper)
		p.wrapped(g.lineStatusText())
		p.picture(picture, 11, 22)
		p.wrapped(showIf(now < g.msgUntil, g.msg), g.msgColor)
	case "line":
		c, y := p.row(ListenBand)
		c.Center(y, g.text("on_the_line", map[string]any{"n": g.line.peerNumber, "name": g.line.peerCodename}), Amber)
		p.picture(picture, 2, 15)
		for _, side := range []struct{ name, keyed string }{
			{g.text("you", nil), g.freeText}, {g.line.peerCodename, g.line.remoteText},
		} {
			c, y := p.row(Ink)
			c.Put(1, y, side.name+":", Paper)
			c.Put(runeLen(side.name)+3, y, tail(side.keyed, columns-runeLen(side.name)-4), Dim)
		}
		p.center(showIf(now < g.msgUntil, g.msg), g.msgColor)
	case "ending":
		p.picture(picture, 3, 18)
		p.blank()
		g.typedAll = p.typed(content.Ending[g.lang], elapsed, Dim)
		p.blank()
		p.center(showIf(g.typedAll, g.finalScoreLine()), Amber)
	}
	return p.strips
}

// drawPhoneHud: score, chapter and lives on one row.
func (g *Game) drawPhoneHud(p *page) {
	c, y := p.row(Band)
	score := g.text("score", map[string]any{"score": g.score})
	c.Put(1, y, score, Amber)
	// centred, unless the row is too narrow: then two spaces after the score
	chapter := g.text("chapter_hud", g.chapterNumbers(g.chapter))
	c.Put(max((c.W-2*c.OX)/2-runeLen(chapter)/2, 1+runeLen(score)+2), y, chapter, Amber)
	hearts := strings.TrimSpace(strings.Repeat("♥ ", g.lives))
	c.Put(c.W-1-runeLen(hearts), y, hearts, Alert)
}

// drawPhoneHeader: send or receive and the mission's title, then which of the chapter's
// messages it is.
func (g *Game) drawPhoneHeader(p *page) {
	band, title := g.headerBand()
	c, y := p.row(band)
	c.Put(1, y, title, Paper)
	n, total := g.messageNumber()
	count := fmt.Sprintf("%d/%d", n, total)
	c.Put(c.W-1-runeLen(count), y, count, Amber)
}

// drawPhoneCodeChart: every letter and digit with its pattern, in three columns of twelve.
func (g *Game) drawPhoneCodeChart(p *page) {
	c, top := p.row(Ink)
	for range 11 {
		p.row(Ink)
	}
	last := lastLetter(g.freeText)
	for i, ch := range strings.Split(CodeOrder, "") {
		x, y := 1+(i/12)*(p.columns/3), top+i%12
		letterColor, patternColor := Paper, Teal
		if ch == last {
			letterColor, patternColor = Lamp, Lamp
		}
		c.Put(x, y, ch, letterColor)
		c.Put(x+2, y, Pretty(Code[ch]), patternColor)
	}
}

// page stacks up a phone screen: strips of the 80-column picture between runs of text set
// `columns` wide.
type page struct {
	columns int
	strips  []*Canvas
	text    *Canvas // the run of text being written; nil when the last strip is a picture
}

// picture adds rows y0..y1-1 of the 80-column picture.
func (p *page) picture(c *Canvas, y0, y1 int) {
	p.strips = append(p.strips, c.Rows(y0, y1))
	p.text = nil
}

// row adds a text row on bg and returns the canvas holding it and the row's y on it.
func (p *page) row(bg Color) (*Canvas, int) {
	if p.text == nil {
		p.text = &Canvas{W: p.columns, Fg: Paper, Bg: Ink}
		p.strips = append(p.strips, p.text)
	}
	cells := make([]Cell, p.columns)
	for i := range cells {
		cells[i] = Cell{' ', Paper, bg}
	}
	p.text.Cells = append(p.text.Cells, cells)
	p.text.H++
	return p.text, p.text.H - 1
}

func (p *page) blank() { p.row(Ink) }

func (p *page) blanks(n int) {
	for range n {
		p.blank()
	}
}

func (p *page) center(text string, color Color) {
	c, y := p.row(Ink)
	c.Center(y, text, color)
}

// wrapped centres text over as many rows as it takes.
func (p *page) wrapped(text string, color Color) {
	for _, line := range wrap(text, p.columns-2) {
		p.center(line, color)
	}
}

// typed is DrawTypedLines with the lines wrapped to the page: true once all are shown.
func (p *page) typed(lines []string, elapsed float64, color Color) bool {
	var wrapped []string
	for _, line := range lines {
		wrapped = append(wrapped, wrap(line, p.columns-2)...)
	}
	c, top := p.row(Ink)
	for range len(wrapped) - 1 {
		p.row(Ink)
	}
	return DrawTypedLines(c, top, wrapped, elapsed, color)
}

// wrap breaks text between words into lines of at most width runes; "" stays one empty line.
//
//	wrap("THE CREW CALLS YOU CORUJA", 12) == []string{"THE CREW", "CALLS YOU", "CORUJA"}
func wrap(text string, width int) []string {
	var lines []string
	line := ""
	for _, word := range strings.Fields(text) {
		switch {
		case line == "":
			line = word
		case runeLen(line)+1+runeLen(word) <= width:
			line += " " + word
		default:
			lines = append(lines, line)
			line = word
		}
	}
	return append(lines, line)
}

// showIf is text when show is true, else "": a blinking or delayed line keeps its row.
func showIf(show bool, text string) string {
	if show {
		return text
	}
	return ""
}
