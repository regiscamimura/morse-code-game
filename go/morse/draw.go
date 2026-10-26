package morse

import (
	"fmt"
	"hash/fnv"
	"math"
	"math/rand/v2"
	"slices"
	"strings"
)

// 1930s poster palette: navy night, brass, cream, teal for receiving,
// oxblood for sending and danger, signal green for success, warm lamp yellow.
var (
	Ink        = Color{10, 12, 22}
	Night      = Color{16, 26, 56}
	Earth      = Color{44, 34, 26}
	Sea        = Color{14, 44, 64}
	Fog        = Color{54, 62, 74}
	Faint      = Color{62, 70, 88}
	Dim        = Color{130, 138, 152}
	Amber      = Color{218, 166, 60}
	Paper      = Color{234, 224, 198}
	Alert      = Color{210, 66, 52}
	Teal       = Color{72, 178, 172}
	Go         = Color{118, 192, 96}
	Lamp       = Color{252, 208, 88}
	Flame      = Color{236, 124, 40}
	Ember      = Color{72, 20, 14}
	Band       = Color{22, 32, 60}
	SendBand   = Color{110, 32, 30}
	ListenBand = Color{18, 72, 78}
)

// sceneColors are the colours content.json's scenes may name for sky and ground.
var sceneColors = map[string]Color{"NIGHT": Night, "EARTH": Earth, "SEA": Sea, "FOG": Fog}

// spritePalette maps sprite pixels to colours.
var spritePalette = map[byte]Color{'K': Ink, 'D': Faint, 'S': Dim, 'A': Amber, 'O': Flame,
	'W': Paper, 'Y': Lamp, 'R': Alert, 'T': Teal, 'E': Ember, 'N': Night, 'G': Go,
	'B': Color{110, 66, 34}, 'V': Color{34, 62, 42}, 'L': Color{184, 190, 200}, 'M': Color{36, 40, 52}}

// Draw renders the current screen on a width x height canvas (80x24 or larger).
func (g *Game) Draw(width, height int, now float64) *Canvas {
	c := NewCanvas(width, height, Paper, Ink)
	if width < 80 || height < 24 {
		c.OX, c.OY = 0, 0
		c.Put(0, 0, g.text("size", nil), Amber)
		return c
	}
	switch g.state {
	case "lang":
		g.drawLang(c, now)
	case "codename":
		g.drawCodename(c, now)
	case "switchboard", "calling", "ringing":
		g.drawSwitchboard(c, now)
	case "line":
		g.drawLine(c, now)
	case "title":
		g.drawTitle(c, now)
	case "cover":
		g.drawChapterCover(c, now)
	case "chapter":
		g.drawChapter(c, now)
	case "brief":
		g.drawBrief(c, now)
	case "play":
		g.drawPlay(c, now)
	case "win":
		g.drawResult(c, now, true)
	case "lose":
		g.drawResult(c, now, false)
	case "free":
		g.drawFree(c, now)
	case "game_over":
		g.drawGameOver(c, now)
	case "ending":
		g.drawEnding(c, now)
	}
	return c
}

// blinkOn is true for half of each 1.33 s blink.
func blinkOn(now float64) bool { return int(now*1.5)%2 == 1 }

func (g *Game) drawTypedLines(c *Canvas, y int, lines []string, now float64, color Color) bool {
	g.typedAll = DrawTypedLines(c, y, lines, now-g.stateStart, color)
	return g.typedAll
}

func (g *Game) withWord(text string) string {
	return format(text, map[string]any{"word": g.word})
}

// drawKey: the key lamp, what's been keyed so far, its letter, and the letter lock-in bar.
func (g *Game) drawKey(c *Canvas, x, y int, now float64) {
	k := g.keyer
	lit := k.Sounding() || (k.Down() && now-k.Last < .12)
	label := g.text("key", nil)
	if lit {
		c.PutOn(x, y, label, Ink, Lamp)
	} else {
		c.PutOn(x, y, label, Dim, Faint)
	}
	x += runeLen(label) + 2
	live := k.Live(now)
	c.Put(x, y, Pretty(live), Lamp)
	if live != "" {
		letter, ok := Decode[live]
		if !ok {
			letter = "?"
		}
		color := Paper
		if k.Down() {
			color = Dim
		}
		c.Put(x+16, y, "= "+letter, color)
	}
	if k.Pattern != "" && !k.Down() {
		n := min(5, int((now-k.Last)/k.LetterGap*5))
		c.Put(x+21, y, strings.Repeat("▮", n)+strings.Repeat("▯", 5-n), Teal)
	}
}

func (g *Game) drawHud(c *Canvas) {
	c.Band(0, 1, Band)
	c.Put(1, 0, g.text("score", map[string]any{"score": g.score}), Amber)
	c.Put(22, 0, g.text("chapter_hud", map[string]any{"n": g.chapter, "total": len(g.chapters())}), Amber)
	c.Put(44, 0, strings.Repeat("♥ ", g.lives), Alert)
	best := g.text("best", map[string]any{"best": max(g.hi, g.score)})
	c.Put(79-runeLen(best), 0, best, Dim)
}

// headerBand is the header's colour and its title, which says whether the player sends or receives.
func (g *Game) headerBand() (Color, string) {
	if g.mode != "encode" {
		return ListenBand, g.text("receive", nil) + g.beat.Title
	}
	return SendBand, g.text("send", nil) + g.beat.Title
}

// task is what the player must do with the beat's messages.
func (g *Game) task() string {
	if g.beat.Task != "" {
		return g.beat.Task
	}
	return g.text("task_"+g.mode, nil)
}

func (g *Game) drawHeader(c *Canvas, line2 string) {
	band, title := g.headerBand()
	c.Band(1, 2, band)
	c.Put(1, 1, title, Paper)
	n, total := g.messageNumber()
	message := g.text("message", map[string]any{"n": n, "total": total})
	c.Put(79-runeLen(message), 1, message, Amber)
	c.Put(1, 2, line2, Teal)
}

// seeded is a random source that gives the same numbers every frame for the same seed.
func seeded(seed string) *rand.Rand {
	h := fnv.New64a()
	h.Write([]byte(seed))
	return rand.New(rand.NewPCG(h.Sum64(), 0))
}

// sceneEnding: for drawScene, how a finished mission ended, with seconds since.
type sceneEnding struct {
	won bool // or lost, and the target burns
	t   float64
}

// drawFire sets the w x h cells at (x, y) burning: flames along the top, smoke rising from
// the bottom, t seconds after it caught.
func drawFire(c *Canvas, x, y, w, h int, t, now float64) {
	for i := range 14 {
		r := seeded(fmt.Sprint(i))
		rise := math.Mod(t*1.2+r.Float64()*5, 5)
		if row := y + h - 1 - int(rise); row >= 3 {
			color := Faint
			if rise < 2.5 {
				color = Dim
			}
			c.Put(x+r.IntN(w), row, []string{"░", "▒"}[i%2], color)
		}
	}
	for col := x; col < x+w; col++ {
		if (col*7+int(now*3))%4 == 0 {
			color := Alert
			if (col+int(now*2))%2 == 1 {
				color = Amber
			}
			c.Put(col, y, "▲", color)
		}
	}
}

// drawScene draws the mover p of the way toward its target. ended is nil while playing.
func (g *Game) drawScene(c *Canvas, now float64, key string, p float64, ended *sceneEnding) {
	scene := content.Scenes[key]
	sky, ground := sceneColors[scene.Sky], sceneColors[scene.Ground]
	lost := ended != nil && !ended.won
	if lost {
		c.Band(3, 11, Ember)
	} else {
		c.Band(3, 11, sky)
	}
	c.Band(11, 13, ground)
	rnd := seeded(key)
	for range 16 {
		x, y, phase := rnd.IntN(80), 3+rnd.IntN(6), rnd.Float64()
		color := Faint
		if math.Mod(now*.3+phase, 1) > .2 {
			color = Paper
		}
		c.Put(x, y, "·", color)
	}
	if scene.Sky == "FOG" {
		for i := range 10 {
			x := int(rnd.Float64()*80+now*.8) % 80
			c.Put(x, 4+i%6, strings.Repeat("░", 4+rnd.IntN(8)), Dim)
		}
	}
	target, mover := content.Sprites[scene.Target], content.Sprites[scene.Mover]
	tw, th := len(target[0]), (len(target)+1)/2
	mw, mh := len(mover[0]), (len(mover)+1)/2
	tx, ty := 76-tw, 11-th
	if slices.Contains(content.Flyers, scene.Target) {
		ty = 4
	}
	mx := 2 + int(p*float64(tx-mw-3))
	my := 11 - mh
	if slices.Contains(content.Flyers, scene.Mover) {
		my = 4
	}
	Sprite(c, tx, ty, target, spritePalette, false, nil)
	if lost {
		drawFire(c, tx, ty, tw, th, ended.t, now)
	}
	switch {
	case ended == nil || !ended.won:
		Sprite(c, mx, my, mover, spritePalette, int(now*4)%2 == 1, nil)
	case ended.t < 1.5:
		faded := Faint
		Sprite(c, mx, my, mover, spritePalette, false, &faded)
	}
}

func (g *Game) drawTitle(c *Canvas, now float64) {
	g.drawScene(c, now, "wireless", math.Mod(now/120, 1), nil)
	BigCenter(c, 14, g.text("title_big", nil), Amber)
	c.Center(19, g.text("subtitle", nil), Teal)
	c.Center(20, g.text("tap_hold", map[string]any{"dot": Dot, "dah": Dah}), Paper)
	menu := g.text("menu_begin", nil)
	if g.savedChapter > 1 {
		menu += "   " + g.text("menu_continue", map[string]any{"n": g.savedChapter})
	}
	c.Center(22, menu, Amber)
	c.Center(23, g.text("menu_rest", nil), Amber)
	if g.LineAvailable() {
		c.Center(21, g.text("menu_line", nil), Teal)
	}
	if g.hi > 0 {
		c.Center(1, g.text("best", map[string]any{"best": g.hi}), Faint)
	}
}

// coverYearRow is where a chapter cover's year starts, under the picture and the chapter's number.
const coverYearRow = coverHeight/2 + 1

// drawChapterCover: the chapter's cover picture, then its number, its year big and its title.
func (g *Game) drawChapterCover(c *Canvas, now float64) {
	chapter := g.currentChapter()
	drawChapterCoverArt(c, content.Covers[chapter.Cover], now)
	c.Center(coverHeight/2, g.text("chapter_label", map[string]any{"n": g.chapter}), Dim)
	BigCenter(c, coverYearRow, chapter.Year, Amber)
	c.Center(coverYearRow+4, chapter.Title, Paper)
	if g.readyToContinue(now) && blinkOn(now) {
		c.Center(23, g.text("continue", nil), Amber)
	}
}

// drawChapter: the chapter's new letters, each to be keyed drillTimes before the messages begin.
func (g *Game) drawChapter(c *Canvas, now float64) {
	g.drawHud(c)
	c.Center(2, g.text("brief_line", map[string]any{"n": g.chapter, "title": g.currentChapter().Title}), Dim)
	c.Center(5, g.lettersLabel(), Teal)
	columnWidth := 76 / len(g.newLetters)
	last := lastLetter(g.freeText)
	for i, ch := range strings.Split(g.newLetters, "") {
		x := 2 + i*columnWidth + columnWidth/2 - 9
		color := Paper
		if last == ch {
			color = Go
		}
		Big(c, x, 7, ch, color)
		c.Put(x+8, 8, Pretty(Code[ch]), Lamp)
		done, pipColor := g.drill[i], Lamp
		if done >= drillTimes {
			pipColor = Go
		}
		c.Put(x, 12, strings.TrimSpace(strings.Repeat("● ", done)+strings.Repeat("○ ", drillTimes-done)), pipColor)
	}
	line, color := g.drillLine()
	c.Center(15, line, color)
	c.Put(10, 17, g.text("try_them", nil)+tail(g.freeText, 50), Dim)
	g.drawKey(c, 24, 19, now)
	if g.DrillDone() && blinkOn(now) {
		c.Center(22, g.text("enter_begin", nil), Amber)
	}
	c.Center(23, g.text("chapter_help", nil), Faint)
}

// drillLine asks for the new letters to be keyed, until they all have been.
func (g *Game) drillLine() (string, Color) {
	if g.DrillDone() {
		return g.text("drill_done", nil), Go
	}
	return g.text("drill", map[string]any{"n": drillTimes}), Paper
}

// lettersLabel heads the chapter's letters: the first ones, or new ones.
func (g *Game) lettersLabel() string {
	if g.chapter == 1 {
		return g.text("first_letters", nil)
	}
	return g.text("new_letters", nil)
}

func (g *Game) drawBrief(c *Canvas, now float64) {
	g.drawHud(c)
	g.drawHeader(c, g.text("brief_line", map[string]any{"n": g.chapter, "title": g.currentChapter().Title}))
	g.drawScene(c, now, g.beat.Scene, g.sceneProgress(0), nil)
	var lines []string
	for _, line := range g.beat.Brief {
		lines = append(lines, g.withWord(line))
	}
	if g.drawTypedLines(c, 14, append(lines, "", g.task()), now, Paper) {
		if g.mode == "encode" {
			c.Center(19, g.text("code_word", map[string]any{"word": g.word}), Amber)
		}
		if blinkOn(now) {
			c.Center(22, g.text("ready", nil), Amber)
		}
	}
}

func (g *Game) drawPlay(c *Canvas, now float64) {
	g.drawHud(c)
	g.drawHeader(c, g.task())
	g.drawScene(c, now, g.beat.Scene, g.sceneProgress(g.progress(now)), nil)
	left := max(0, g.timeEnd-now)
	frac := left / g.timeTotal
	color := Dim
	if frac <= .3 {
		color = Alert
		if frac <= .15 && int(now*2)%2 == 0 {
			color = Ember
		}
	}
	n := int(frac * 60)
	c.Put(7, 13, strings.Repeat("▬", n), color)
	c.Put(7+n, 13, strings.Repeat("▬", 60-n), Band)
	c.Put(70, 13, fmt.Sprintf("%4.0fs", left), color)
	lines, top, keyRow := g.messageLayout()
	hintX := 0 // under the letter to send next
	i := 0     // the letter of g.word being drawn
	for n, line := range lines {
		x0, y := 40-BigTextWidth(line)/2, top+4*n
		for col, ch := range strings.Split(line, "") {
			done := i < g.pos
			letterColor := Faint
			if done {
				letterColor = Go
			} else if i == g.pos {
				letterColor, hintX = Lamp, x0+col*6+2
			}
			if g.mode != "encode" && !done && ch != " " {
				ch = "_"
			}
			Big(c, x0+col*6, y, ch, letterColor)
			i++
		}
		i++ // the space the line broke at
	}
	var help string
	if g.mode == "encode" {
		hint := g.hintPattern()
		if len(lines) == 1 {
			c.Put(hintX-runeLen(hint)/2, top+4, hint, Teal)
		} else { // no room under two lines: it goes beside the key
			c.Put(2, keyRow, hint, Teal)
		}
		g.drawKey(c, 24, keyRow, now)
		help = g.text("encode_help", nil)
	} else {
		g.drawLampAndTape(c, 2, keyRow, 68, now)
		help = g.text("decode_help", nil)
	}
	if now < g.msgUntil {
		c.Center(keyRow+1, g.msg, g.msgColor)
	}
	if keyRow+1 < 23 || now >= g.msgUntil {
		c.Center(23, help, Faint)
	}
}

// bigLineLetters is the most big letters, spaces included, that fit in the screen's 78
// columns: they stand 6 apart and the last is 5 wide.
const bigLineLetters = (78 + 1) / 6

// messageLayout is the message wrapped to fit across the screen in big letters (one line, or
// two), the row its first line starts on, and the row for the key or the lamp under it.
func (g *Game) messageLayout() (lines []string, top, keyRow int) {
	lines = wrap(g.word, bigLineLetters)
	if len(lines) == 1 {
		return lines, 15, 20
	}
	return lines, 14, 22
}

// hintPattern is the pattern of the letter to send next, while hints are on.
func (g *Game) hintPattern() string {
	if g.mode != "encode" || !g.hint || g.pos >= len(g.word) {
		return ""
	}
	return Pretty(Code[string(g.word[g.pos])])
}

// drawLampAndTape draws the lamp at (x, y), lit with each tone, and after it the last tapeWidth
// columns of the tape of what's been sent so far. Letters past their aids show as '?' on the
// tape and leave the lamp dark.
func (g *Game) drawLampAndTape(c *Canvas, x, y, tapeWidth int, now float64) {
	t := now - g.signalStart
	letterOf := func(e Element) rune { return rune(g.word[e.Letter]) }
	lit := slices.ContainsFunc(g.on, func(e Element) bool {
		return e.Start <= t && t < e.End && strings.ContainsRune(g.lampLetters, letterOf(e))
	})
	lamp := g.text("lamp", nil)
	if lit {
		c.PutOn(x, y, lamp, Ink, Lamp)
	} else {
		c.PutOn(x, y, lamp, Dim, Faint)
	}
	var tape []string
	for i, e := range g.on {
		if e.Start > t {
			continue
		}
		newLetter := i == 0 || g.on[i-1].Letter != e.Letter
		if newLetter && i > 0 && e.Letter-g.on[i-1].Letter > 1 { // a space between words
			tape = append(tape, "/")
		}
		switch {
		case !strings.ContainsRune(g.tapeLetters, letterOf(e)):
			if newLetter {
				tape = append(tape, "?")
			}
		case newLetter:
			tape = append(tape, Pretty(string(e.Kind)))
		default:
			tape[len(tape)-1] += " " + Pretty(string(e.Kind))
		}
	}
	c.Put(x+runeLen(lamp)+2, y, tail(strings.Join(tape, "   "), tapeWidth), Teal)
}

func (g *Game) drawResult(c *Canvas, now float64, won bool) {
	t := now - g.stateStart
	g.drawHud(c)
	g.drawHeader(c, g.task())
	g.drawScene(c, now, g.beat.Scene, g.progressEnd, &sceneEnding{won: won, t: t})
	verdict, outcome, outcomeColor := g.resultLines(won)
	bannerColor := Alert
	if won {
		bannerColor = Go
	}
	BigCenter(c, 14, g.banner, bannerColor)
	c.Center(19, g.wordInCode(), Teal)
	c.Center(20, verdict, Paper)
	c.Center(21, outcome, outcomeColor)
	if g.readyToContinue(now) && blinkOn(now) {
		c.Center(23, g.text("continue", nil), Amber)
	}
}

// resultLines are what a mission's end says: the story's verdict, then the time bonus won or
// the lives left, and that line's colour.
func (g *Game) resultLines(won bool) (verdict, outcome string, outcomeColor Color) {
	lose := g.withWord(g.beat.Lose)
	if lose == "" {
		lose = g.text("lose_line", nil)
	}
	switch {
	case won:
		return g.withWord(g.beat.Win), g.text("time_bonus", map[string]any{"bonus": g.bonus}), Amber
	case g.lives > 0:
		return lose, g.text("lives_left", map[string]any{"n": g.lives}), Alert
	}
	return lose, g.text("no_lives", nil), Alert
}

// wordInCode is the message and its letters' patterns, with / between words:
// "AT TEN  =  • ━   ━   /   ━   •   ━ •". A message too long for that is shown alone.
func (g *Game) wordInCode() string {
	var patterns []string
	for _, ch := range strings.Split(g.word, "") {
		if ch == " " {
			patterns = append(patterns, "/")
		} else {
			patterns = append(patterns, Pretty(Code[ch]))
		}
	}
	if line := g.word + "  =  " + strings.Join(patterns, "   "); runeLen(line) <= 78 {
		return line
	}
	return g.word
}

func (g *Game) drawFree(c *Canvas, now float64) {
	c.Band(0, 1, Band)
	c.Center(0, g.text("practice", nil), Amber)
	last := lastLetter(g.freeText)
	for i, ch := range strings.Split(CodeOrder, "") {
		x, y := 3+(i/9)*19, 2+i%9
		letterColor, patternColor := Paper, Teal
		if ch == last {
			letterColor, patternColor = Lamp, Lamp
		}
		c.Put(x, y, ch, letterColor)
		c.Put(x+2, y, Pretty(Code[ch]), patternColor)
	}
	BigCenter(c, 12, tail(g.freeText, 12), Amber)
	c.Center(17, tail(g.freeText, 70), Dim)
	g.drawKey(c, 24, 19, now)
	c.Center(23, g.text("free_help", nil), Faint)
}

func (g *Game) drawGameOver(c *Canvas, now float64) {
	BigCenter(c, 5, g.text("over_big", nil), Alert)
	c.Center(11, g.text("over_line", nil), Dim)
	c.Center(14, g.text("final_score", map[string]any{"score": g.score}), Amber)
	if g.newHi {
		c.Center(15, g.text("new_best", nil), Paper)
	}
	c.Center(17, g.text("over_continue", map[string]any{"n": g.chapter}), Dim)
	if g.readyToContinue(now) && blinkOn(now) {
		c.Center(21, "[ENTER]", Paper)
	}
}

func (g *Game) drawEnding(c *Canvas, now float64) {
	g.drawScene(c, now, "wireless", 1, &sceneEnding{won: true, t: 9})
	BigCenter(c, 14, g.text("end_big", nil), Amber)
	if g.drawTypedLines(c, 19, content.Ending[g.lang], now, Dim) {
		c.Center(23, g.finalScoreLine(), Amber)
	}
}

func (g *Game) finalScoreLine() string {
	line := g.text("final_score", map[string]any{"score": g.score})
	if g.newHi {
		line += "  ·  " + g.text("new_best", nil)
	}
	return line
}

var languageNames = []struct{ lang, name string }{{"en", "ENGLISH (EN-US)"}, {"pt", "PORTUGUÊS (PT-BR)"}}

// languageOption is a line of the language menu, marked when it's the one chosen.
func (g *Game) languageOption(i int) (string, Color) {
	if languageNames[i].lang == g.lang {
		return fmt.Sprintf("▸ [%d] %s", i+1, languageNames[i].name), Lamp
	}
	return fmt.Sprintf("  [%d] %s", i+1, languageNames[i].name), Dim
}

func (g *Game) drawLang(c *Canvas, now float64) {
	g.drawScene(c, now, "wireless", math.Mod(now/120, 1), nil)
	BigCenter(c, 14, "MORSE", Amber)
	for i := range languageNames {
		option, color := g.languageOption(i)
		c.Center(19+i, option, color)
	}
	if blinkOn(now) {
		c.Center(22, "[ENTER] OK", Amber)
	}
}
