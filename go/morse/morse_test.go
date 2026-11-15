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
					if LettersToKey(w) == "" || !fitsTheScreen(w) {
						t.Errorf("%s chapter %d: message %q has no letter to key, or is too long to show", lang, n, w)
					}
					if !onlyUses(w, Unlocked(n)) { // whole words only: no letter goes by unkeyed
						t.Errorf("%s chapter %d: message %q has letters not learned yet", lang, n, w)
					}
				}
				if w := b.Words; b.Blind && b.Mode == "decode" && (len(w) < 3 || strings.Contains(w[0], " ") || !strings.Contains(w[len(w)-1], " ")) {
					t.Errorf("%s chapter %d: blind stages %q don't go from single words to a sentence", lang, n, w)
				}
				if b.Echo && (i == 0 || ch.Beats[i-1].Mode != "decode") {
					t.Errorf("%s chapter %d: beat %d echoes a beat that received nothing", lang, n, i+1)
				}
				if _, ok := content.Scenes[b.Scene]; !ok {
					t.Errorf("%s chapter %d: no scene %q", lang, n, b.Scene)
				}
				random := len(b.Words) == 0 && !b.Echo && !b.Groups
				if random && !slices.ContainsFunc(content.Words[lang], func(w string) bool {
					return onlyUses(w, Unlocked(n)) && len(LettersToKey(w)) <= LongestWord(n, b.Mode)
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
		pages := content.Afterword[lang]
		if len(pages) == 0 || len(pages) != len(content.Afterword["en"]) {
			t.Errorf("%s: %d afterword pages, English has %d", lang, len(pages), len(content.Afterword["en"]))
		}
		for _, page := range pages {
			lines = append(lines, page.Title)
			if len(paragraphs(page.Lines, 76)) > 21 {
				t.Errorf("%s: afterword page %q passes 21 lines", lang, page.Title)
			}
		}
		chaptersInVolumes := 0
		for i, v := range content.Volumes[lang] {
			chaptersInVolumes += v.Chapters
			last := i == len(content.Volumes[lang])-1
			if v.Chapters != content.Volumes["en"][i].Chapters || len(v.Prologue) == 0 || (len(v.Epilogue) == 0) != last {
				t.Errorf("%s volume %d: chapters differ from English, or the prologue or epilogue is missing", lang, i+1)
			}
			for _, page := range slices.Concat(v.Prologue, v.Epilogue) {
				// the lines go between the band under the picture and the continue line, row 23
				if _, ok := content.Covers[page.Art]; !ok || len(paragraphs(page.Lines, 76)) > 23-(storyBandRow+2) {
					t.Errorf("%s volume %d: a page has no picture %q, or too many lines: %q", lang, i+1, page.Art, page.Lines)
				}
			}
			g := NewGame(DefaultConfig(), NewMixer(0), 0)
			g.lang, g.chapter = lang, chaptersInVolumes-v.Chapters+1 // the volume's first chapter
			for _, closing := range []bool{false, !last} {
				if closing {
					g.chapter, g.volumeClosing = chaptersInVolumes+1, true // the next volume's first, opening on this epilogue
				}
				// centred under the picture, the band must leave room for the page count at the right
				if name, when, _ := g.shownVolume(); runeLen(name+" · "+when) > 66 {
					t.Errorf("%s volume %d: the band %q is too long", lang, i+1, name+" · "+when)
				}
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
		if len(art.Sky) == 0 || len(art.Ground) == 0 {
			t.Errorf("cover %s: no sky or ground colours", name)
			continue
		}
		if brightness(Faint)-brightness(art.shade()) < 35 {
			t.Errorf("cover %s: Faint text barely shows on its shade %v", name, art.shade())
		}
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
	for pages := 0; g.State() == "volume" && pages < 20; pages++ {
		step(KeyEnter) // finish typing the prologue's page, or turn it
	}
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
				now = keyWord(g, LettersToKey(g.word), now)
				continue
			}
			for _, ch := range LettersToKey(g.word) {
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
	if g.State() != "volume" || g.chapter != 2 { // chapter 2 opens volume 2, on its prologue
		t.Fatalf("after chapter 1: %s, chapter %d", g.State(), g.chapter)
	}
	if g.score == 0 {
		t.Error("no score after three wins")
	}
}

// blindPlay starts the blind message AT TEN, to send or receive at time 1.
// gamePlaying is a game at its first message, message, of beat in chapter.
func gamePlaying(chapter int, beat Beat, message string) *Game {
	g := NewGame(DefaultConfig(), NewMixer(0), 0)
	g.startGame(chapter, 0)
	g.beat, g.mode = beat, beat.Mode
	g.messages, g.msgNo = []string{message}, 0
	g.startPlay(1)
	return g
}

func blindPlay(mode string) *Game { return gamePlaying(1, Beat{Mode: mode, Blind: true}, "AT TEN") }

// TestBlindMessageIsAllOrNothing: no verdict on a letter, no clock, and one wrong letter loses
// the whole message, receiving or sending.
func TestBlindMessageIsAllOrNothing(t *testing.T) {
	typeAll := func(g *Game, letters string) {
		for _, ch := range letters {
			g.Key(string(ch), 2)
		}
	}
	g := blindPlay("decode")
	typeAll(g, "attex")
	g.Key(KeyBackspace, 2)
	typeAll(g, "n")
	g.Key(KeyEnter, 2) // too soon: the signal is still playing
	g.Tick(1e6)        // long past any clock
	if g.State() != "play" || g.typed != "ATTEN" || g.score != 0 {
		t.Fatalf("before ENTER: %s, typed %q, score %d", g.State(), g.typed, g.score)
	}
	g.Key(KeyEnter, 1e6)
	if g.State() != "win" {
		t.Errorf("all letters right: %s", g.State())
	}
	g = blindPlay("decode")
	typeAll(g, "attem")
	g.Key(KeyEnter, 1e6)
	if g.State() != "lose" || g.lives != 2 {
		t.Errorf("one letter wrong: %s, %d lives", g.State(), g.lives)
	}
	g = blindPlay("encode")
	keyWord(g, "AT TEN", 2)
	if g.State() != "win" {
		t.Errorf("sent right: %s", g.State())
	}
	g = blindPlay("encode")
	keyWord(g, "AT TEM", 2)
	if g.State() != "lose" {
		t.Errorf("sent one letter wrong: %s", g.State())
	}
}

// TestOnlySpacesGoBy: whole words only, so receiving or sending "AT TEN" takes every letter;
// just the space passes on its own.
func TestOnlySpacesGoBy(t *testing.T) {
	g := gamePlaying(1, Beat{Mode: "decode"}, "AT TEN")
	for _, ch := range "atte" {
		g.Key(string(ch), 2)
	}
	if g.State() != "play" {
		t.Errorf("a letter short: %s", g.State())
	}
	g.Key("n", 2)
	if g.State() != "win" || g.lives != 3 {
		t.Errorf("after A, T, T, E, N: %s, %d lives", g.State(), g.lives)
	}
	g = gamePlaying(1, Beat{Mode: "encode", Blind: true}, "AT TEN")
	keyWord(g, "ATTEN", 2)
	if g.State() != "win" {
		t.Errorf("blind, sent A, T, T, E, N: %s", g.State())
	}
}

// TestBlindRepeatsStopAtThree: TAB plays a blind message to receive again, three times at most.
func TestBlindRepeatsStopAtThree(t *testing.T) {
	g := blindPlay("decode")
	var lastStart float64
	for i := 1; i <= blindRepeatLimit+1; i++ {
		g.Key(KeyTab, float64(i*10))
		if want := max(0, blindRepeatLimit-i); g.BlindRepeatsLeft() != want {
			t.Errorf("after %d repeats: %d left, want %d", i, g.BlindRepeatsLeft(), want)
		}
		if i == blindRepeatLimit {
			lastStart = g.signalStart
		}
	}
	if g.signalStart != lastStart {
		t.Errorf("a TAB past the limit replayed the message: it starts at %v", g.signalStart)
	}
}

// TestSpeedKeysAreNeverDigits: a typed 2 is a digit, even before digits are learned; SHIFT 2
// and the ▶▶ button pick the speed.
func TestSpeedKeysAreNeverDigits(t *testing.T) {
	for _, c := range []struct {
		chapter   int
		key       string
		wantSpeed int
	}{{1, "2", 0}, {chapterTeaching('2'), "2", 0}, {1, "@", 1}, {chapterTeaching('2'), speedKeys[2], 2}} {
		g := gamePlaying(c.chapter, Beat{Mode: "decode"}, "AGE 2")
		g.Key(c.key, 2)
		if g.speed != c.wantSpeed {
			t.Errorf("chapter %d, key %q: speed %d, want %d", c.chapter, c.key, g.speed, c.wantSpeed)
		}
	}
}

// TestPracticeKeepsEveryLetterAfterTheEnd: finishing the game sends the saved chapter back to
// 1, but practice still plays every letter and digit.
func TestPracticeKeepsEveryLetterAfterTheEnd(t *testing.T) {
	g := NewGame(DefaultConfig(), NewMixer(0), 0)
	if g.practiceLetters() != "ETAN" {
		t.Errorf("a new game practises %q", g.practiceLetters())
	}
	g.finish(0)
	if g.savedChapter != 1 || g.practiceLetters() != Unlocked(len(content.Levels)) {
		t.Errorf("after the end: chapter %d, practising %q", g.savedChapter, g.practiceLetters())
	}
}

// TestEveryVolumeEndsBlind: each volume's last chapter has a blind message to receive and one to
// send, and its last message is blind. The first volume is one chapter, the first four letters:
// too soon for no clues.
func TestEveryVolumeEndsBlind(t *testing.T) {
	for _, lang := range Langs {
		chapter := content.Volumes[lang][0].Chapters
		for _, v := range content.Volumes[lang][1:] {
			chapter += v.Chapters
			beats := content.Chapters[lang][chapter-1].Beats
			blind := func(mode string) bool {
				return slices.ContainsFunc(beats, func(b Beat) bool { return b.Blind && b.Mode == mode })
			}
			if !blind("decode") || !blind("encode") || !beats[len(beats)-1].Blind {
				t.Errorf("%s %s doesn't end blind", lang, v.Title)
			}
		}
	}
}

// TestBlindReceivingIsSlowAtAnySpeed: more time between letters than any other beat, and the ▶
// buttons left on from an earlier beat change neither the signal nor the time allowed.
func TestBlindReceivingIsSlowAtAnySpeed(t *testing.T) {
	g := blindPlay("decode")
	timeAtFirstSpeed := g.timeForMessage(0)
	g.speed = len(Speeds) - 1
	if got := g.timeForMessage(0); got != timeAtFirstSpeed {
		t.Errorf("time allowed at the top speed: %v, at the first: %v", got, timeAtFirstSpeed)
	}
	betweenAandT := g.on[2].Start - g.on[1].End
	if betweenAandT <= content.Pace.LetterGap[0] {
		t.Errorf("%vs between letters isn't more than the slowest other beat's %vs", betweenAandT, content.Pace.LetterGap[0])
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
				for _, state := range []string{"volume", "cover", "chapter", "brief", "play", "win", "lose", "free", "listen", "game_over", "ending", "afterword", "lang", "title",
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

// TestDoubleTapDoesNotTurnAPageUnread: ENTER shows a page's lines at once, and only after the
// page's hold does ENTER turn it.
func TestDoubleTapDoesNotTurnAPageUnread(t *testing.T) {
	g := NewGame(DefaultConfig(), NewMixer(0), 0)
	g.chapter = content.Volumes[g.lang][0].Chapters + 1 // volume 2: a prologue of more than one page
	g.openVolume(false, 0)
	press := func(now float64) { // as the app does: a key, then a frame drawn
		g.Key(KeyEnter, now)
		g.Draw(80, 24, now)
	}
	press(.5) // shows the lines
	press(.6) // too soon: the page holds
	if g.page != 0 {
		t.Fatalf("a double tap turned the page to %d", g.page)
	}
	press(.6 + continueHolds["volume"] + .1)
	if g.page != 1 {
		t.Fatalf("after the hold, still on page %d", g.page)
	}
}

// TestEpilogueLeadsToTheNextPrologue wins volume 1's last chapter, pages through its
// epilogue, and lands on the first page of volume 2's prologue.
func TestEpilogueLeadsToTheNextPrologue(t *testing.T) {
	g := NewGame(DefaultConfig(), NewMixer(0), 0)
	g.chapter = content.Volumes["en"][0].Chapters
	g.beatNo = len(g.currentChapter().Beats) - 1
	g.setState("win", 0)
	now := 1.0
	g.afterResult(now)
	for page := range content.Volumes["en"][0].Epilogue {
		if g.State() != "volume" || !g.volumeClosing || g.page != page {
			t.Fatalf("epilogue page %d: state %s, closing %v, page %d", page, g.State(), g.volumeClosing, g.page)
		}
		for range 2 { // as a player does: ENTER shows the page's lines, and after its hold turns it
			now += 2
			g.Key(KeyEnter, now)
			g.Draw(80, 24, now)
		}
	}
	if name, _, _ := g.shownVolume(); g.State() != "volume" || g.volumeClosing || g.page != 0 || !strings.HasPrefix(name, "VOLUME 2 ") {
		t.Fatalf("after the epilogue: state %s, closing %v, page %d of %q", g.State(), g.volumeClosing, g.page, name)
	}
}
