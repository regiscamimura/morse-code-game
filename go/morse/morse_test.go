package morse

import (
	"fmt"
	"slices"
	"strings"
	"testing"
)

func autorepeatKeyer() *Keyer {
	return NewKeyer(Config{Releases: false, LetterGap: .8, RepeatDelay: .25, RepeatInterval: .045})
}

// hold is the press times a held key produces: the press, then autorepeats.
func hold(t, dur float64) []float64 {
	times := []float64{t}
	for i := 0; i <= int((dur-.25)/.045); i++ {
		times = append(times, t+.25+float64(i)*.045)
	}
	return times
}

func TestAutorepeatKeyer(t *testing.T) {
	cases := []struct {
		presses []float64
		want    string
	}{
		{[]float64{0}, "."},
		{hold(0, .6), "-"},
		{[]float64{0, .2, .4}, "..."},
		{append([]float64{0}, hold(.3, .7)...), ".-"},
		{append(hold(0, .5), .8), "-."},
		{append(hold(0, .5), hold(.8, .5)...), "--"},
	}
	for _, c := range cases {
		k := autorepeatKeyer()
		for _, p := range c.presses {
			k.Press(p)
		}
		if got := k.Tick(c.presses[len(c.presses)-1] + 2); got != c.want {
			t.Errorf("presses %v: got %q, want %q", c.presses, got, c.want)
		}
	}
}

func TestReleaseKeyer(t *testing.T) {
	k := NewKeyer(Config{Releases: true, DahTime: .2, LetterGap: .8})
	for _, press := range [][2]float64{{0, .08}, {.3, .7}, {.9, .95}} {
		k.Press(press[0])
		k.Release(press[1])
	}
	if got := k.Tick(1.0); got != "" {
		t.Errorf("letter finished before the gap: %q", got)
	}
	if got := k.Tick(2); got != ".-." {
		t.Errorf("got %q, want .-.", got)
	}
}

func TestFormat(t *testing.T) {
	got := format("SCORE {score:06d} {word} {missing}", map[string]any{"score": 42, "word": "SOS"})
	if want := "SCORE 000042 SOS {missing}"; got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestContent(t *testing.T) {
	if Decode[".-"] != "A" {
		t.Error("decode table")
	}
	for _, ch := range CodeOrder {
		if _, ok := Font[ch]; !ok {
			t.Errorf("no glyph for %c", ch)
		}
	}
	for name, rows := range content.Sprites {
		for _, row := range rows {
			if len(row) != len(rows[0]) || strings.ContainsFunc(row, func(r rune) bool {
				_, ok := spritePalette[byte(r)]
				return r != '.' && !ok
			}) {
				t.Errorf("sprite %s has a bad row %q", name, row)
			}
		}
	}
	for _, lang := range Langs {
		chapters := content.Chapters[lang]
		if len(chapters) != len(content.Levels) {
			t.Errorf("%s: %d chapters for %d levels", lang, len(chapters), len(content.Levels))
		}
		for key := range content.UI["en"] {
			if _, ok := content.UI[lang][key]; !ok {
				t.Errorf("%s: no UI string %q", lang, key)
			}
		}
		for _, w := range content.Words[lang] {
			if !onlyUses(w, CodeOrder) || !fitsTheScreen(w) {
				t.Errorf("%s: word %q can't be sent or is too long to show", lang, w)
			}
		}
		var lines []string
		lines = append(lines, content.Ending[lang]...)
		for n, ch := range chapters {
			n++
			lines = append(lines, ch.Title, ch.Place+" · "+ch.Era)
			if ch.Place == "" || ch.Era == "" || len(ch.Beats) == 0 || BigTextWidth(ch.Year) > 80 {
				t.Errorf("%s chapter %d: %d beats, year %q", lang, n, len(ch.Beats), ch.Year)
			}
			if _, ok := content.Covers[ch.Cover]; !ok {
				t.Errorf("%s chapter %d: no cover %q", lang, n, ch.Cover)
			}
			for i, b := range ch.Beats {
				for _, w := range b.Words {
					if !onlyUses(w, Unlocked(n)) || !fitsTheScreen(w) {
						t.Errorf("%s chapter %d: message %q uses locked letters or is too long to show", lang, n, w)
					}
				}
				if b.Echo && (i == 0 || ch.Beats[i-1].Mode != "decode") {
					t.Errorf("%s chapter %d: beat %d echoes a beat that received nothing", lang, n, i+1)
				}
				if _, ok := content.Scenes[b.Scene]; !ok {
					t.Errorf("%s chapter %d: no scene %q", lang, n, b.Scene)
				}
				random := len(b.Words) == 0 && !b.Echo && !b.Groups
				if random && !slices.ContainsFunc(content.Words[lang], func(w string) bool {
					return onlyUses(w, Unlocked(n)) && letterCount(w) <= LongestWord(n, b.Mode)
				}) {
					t.Errorf("%s chapter %d: no word fits a %s mission", lang, n, b.Mode)
				}
				long := map[string]any{"word": "WWWWWWWW"}
				for _, line := range b.Brief {
					lines = append(lines, format(line, long))
				}
				lines = append(lines, b.Title, b.Task)
				if len(b.Brief) > 3 || len(wrap(format(b.Win, long), 78)) > 2 || len(wrap(format(b.Lose, long), 78)) > 2 {
					t.Errorf("%s chapter %d: beat %d's briefing passes 3 lines, or its win or loss 2", lang, n, i+1)
				}
			}
		}
		chaptersInVolumes := 0
		for i, v := range content.Volumes[lang] {
			chaptersInVolumes += v.Chapters
			last := i == len(content.Volumes[lang])-1
			if v.Chapters != content.Volumes["en"][i].Chapters || len(paragraphs(v.Prologue, 76)) > 10 ||
				len(paragraphs(v.Epilogue, 76)) > 10 || (len(v.Epilogue) == 0) != last {
				t.Errorf("%s volume %d: chapters differ from English, a prologue or epilogue passes 10 lines, or the epilogue is missing", lang, i+1)
			}
			lines = append(lines, v.Title, v.Years)
		}
		if chaptersInVolumes != len(chapters) {
			t.Errorf("%s: volumes hold %d chapters of %d", lang, chaptersInVolumes, len(chapters))
		}
		for _, banner := range append(content.WinBanners[lang], content.LoseBanners[lang]...) {
			if BigTextWidth(banner) > 80 {
				t.Errorf("%s: banner %q too wide", lang, banner)
			}
		}
		for _, line := range lines {
			if runeLen(line) > 78 {
				t.Errorf("%s: line longer than 78: %q", lang, line)
			}
		}
	}
	for name, art := range content.Covers {
		for _, l := range art.Layers {
			if _, ok := content.Sprites[l.Sprite]; l.Sprite != "" && !ok {
				t.Errorf("cover %s: no sprite %q", name, l.Sprite)
			}
		}
	}
	for name, scene := range content.Scenes {
		for _, color := range []string{scene.Sky, scene.Ground} {
			if _, ok := sceneColors[color]; !ok {
				t.Errorf("scene %s: unknown colour %s", name, color)
			}
		}
	}
}

// fitsTheScreen: the message shows whole in big letters, in at most two lines.
func fitsTheScreen(message string) bool {
	lines := wrap(message, bigLineLetters)
	return len(lines) <= 2 && !slices.ContainsFunc(lines, func(line string) bool { return BigTextWidth(line) > 78 })
}

// keyWord sends a word on the key from time t and returns when the last letter locked in.
func keyWord(g *Game, word string, t float64) float64 {
	for _, ch := range word {
		for _, e := range Code[string(ch)] {
			g.SpaceDown(t)
			g.Tick(t)
			if e == '-' {
				t += .3
			} else {
				t += .08
			}
			g.SpaceUp(t)
			g.Tick(t)
			t += .1
			g.Tick(t)
		}
		t += .5
		g.Tick(t)
	}
	return t
}

func screenText(c *Canvas) string {
	var b strings.Builder
	for _, row := range c.Cells {
		for _, cell := range row {
			b.WriteRune(cell.Ch)
		}
		b.WriteByte('\n')
	}
	return b.String()
}

// TestPlaythrough plays chapter 1 from the language screen: the cover, the letter drill, then
// every beat's messages sent or received, with a deliberately wrong letter, drawing every
// screen on the way.
func TestPlaythrough(t *testing.T) {
	g := NewGame(DefaultConfig(), NewMixer(0), 0)
	now := 0.0
	step := func(k string) {
		now += 2
		g.Key(k, now)
		g.Tick(now)
		g.Draw(80, 24, now)
	}
	step(KeyEnter) // language
	if g.State() != "title" {
		t.Fatalf("after language: %s", g.State())
	}
	step(KeyEnter) // begin
	if g.State() != "volume" {
		t.Fatalf("after begin: %s", g.State())
	}
	step(KeyEnter) // finish typing the prologue
	step(KeyEnter) // the volume
	if g.State() != "cover" {
		t.Fatalf("after the volume: %s", g.State())
	}
	step(KeyEnter) // the cover
	step(KeyEnter) // too soon: the drill isn't done
	if g.State() != "chapter" {
		t.Fatalf("before the drill: %s", g.State())
	}
	now = keyWord(g, strings.Repeat(g.newLetters, drillTimes), now)
	if !g.DrillDone() {
		t.Fatalf("drill after keying each letter %d times: %v", drillTimes, g.drill)
	}
	step(KeyEnter) // first briefing
	wrongOnce := true
	for beat := 0; g.chapter == 1; beat++ {
		if g.State() != "brief" {
			t.Fatalf("beat %d: expected brief, got %s", beat, g.State())
		}
		step(KeyEnter) // finish typing
		step(KeyEnter) // play
		for g.State() == "play" {
			if !g.Receiving() {
				now = keyWord(g, g.word, now)
				continue
			}
			for _, ch := range strings.ReplaceAll(g.word, " ", "") {
				if wrongOnce {
					step("Q") // wrong on purpose: Q isn't in any chapter-1 message
					wrongOnce = false
				}
				step(strings.ToLower(string(ch)))
			}
		}
		if g.State() != "win" {
			t.Fatalf("beat %d (%s %q): expected win, got %s at letter %d\n%s",
				beat, g.mode, g.word, g.State(), g.pos, screenText(g.Draw(80, 24, now)))
		}
		g.Draw(80, 24, now)
		step(KeyEnter)
	}
	if g.State() != "cover" || g.chapter != 2 {
		t.Fatalf("after chapter 1: %s, chapter %d", g.State(), g.chapter)
	}
	if g.score == 0 {
		t.Error("no score after three wins")
	}
}

// TestEveryScreenDraws draws each state in both languages, at every chapter's settings.
func TestEveryScreenDraws(t *testing.T) {
	for _, lang := range Langs {
		for chapter := 1; chapter <= len(content.Levels); chapter++ {
			g := NewGame(DefaultConfig(), NewMixer(0), 0)
			g.lang = lang
			g.startGame(chapter, 0)
			for beat := range g.chapters()[chapter-1].Beats {
				g.beatNo = beat
				g.startBeat(1)
				g.startPlay(2)
				g.line.remote = NewKeyer(DefaultConfig())
				for _, state := range []string{"volume", "cover", "chapter", "brief", "play", "win", "lose", "free", "game_over", "ending", "lang", "title",
					"codename", "switchboard", "calling", "ringing", "line"} {
					g.state = state
					g.progressEnd, g.banner = .5, "OK"
					screen := screenText(g.Draw(80, 24, 50))
					if !strings.ContainsFunc(screen, func(r rune) bool { return r != ' ' && r != '\n' }) {
						t.Errorf("%s chapter %d: %s screen is empty", lang, chapter, state)
					}
					if len(g.DrawPhone(48, 50)) == 0 {
						t.Errorf("%s chapter %d: %s phone screen is empty", lang, chapter, state)
					}
				}
			}
		}
	}
}

func TestWrap(t *testing.T) {
	got := wrap("THE CREW  CALLS YOU CORUJA", 12)
	if want := []string{"THE CREW", "CALLS YOU", "CORUJA"}; !slices.Equal(got, want) {
		t.Errorf("wrap = %q, want %q", got, want)
	}
	if got := wrap("", 12); !slices.Equal(got, []string{""}) {
		t.Errorf("wrap of nothing = %q, want one empty line", got)
	}
}

func ExamplePretty() {
	fmt.Println(Pretty(Code["K"]))
	// Output: ━ • ━
}

// TestAidsFadeLetterByLetter: through chapter 6 every letter has the tape; from 7 on the oldest
// letters lose it first, and the newest letters always keep both aids.
func TestAidsFadeLetterByLetter(t *testing.T) {
	pace := content.Pace
	for chapter := 1; chapter <= len(content.Levels); chapter++ {
		tape, lamp := LettersStillAided(chapter, pace.TapeChapters), LettersStillAided(chapter, pace.LampChapters)
		if chapter <= pace.TapeChapters && tape != Unlocked(chapter) {
			t.Errorf("chapter %d: tape only for %q", chapter, tape)
		}
		if !strings.Contains(tape, FocusLetters(chapter)[:1]) || !strings.Contains(lamp, tape) {
			t.Errorf("chapter %d: tape %q, lamp %q, newest %q", chapter, tape, lamp, FocusLetters(chapter))
		}
	}
	if got := LettersStillAided(7, pace.TapeChapters); got != "IMSORKDU" {
		t.Errorf("chapter 7 tape: %q", got)
	}
	if PaceAtChapter(1, pace.WPM) != pace.WPM[0] || PaceAtChapter(len(content.Levels), pace.WPM) != pace.WPM[1] {
		t.Error("pace doesn't run from its first value to its last")
	}
}
