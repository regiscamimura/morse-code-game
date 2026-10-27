package morse

import (
	"fmt"
	"math/rand/v2"
	"slices"
	"strings"
)

// Config holds the player's timing settings. RepeatDelay and RepeatInterval only matter
// without Releases, where holds are recognised from the keyboard's autorepeat.
type Config struct {
	Releases       bool
	DahTime        float64 // with releases: a press this long or longer is a dah, seconds
	LetterGap      float64 // silence that ends a letter, seconds
	RepeatDelay    float64
	RepeatInterval float64
	SavePath       string           // "" plays without saving
	Wire           Wire             // the telephone exchange, for the telegraph line; nil plays alone
	OpenURL        func(url string) // opens a web page in a browser; nil where the front end can't
}

// PrivacyURL is the privacy policy Google Play requires a link to from inside the game.
const PrivacyURL = "https://regiscamimura.com/sos-morse/privacy"

func DefaultConfig() Config {
	return Config{Releases: true, DahTime: .2, LetterGap: .3, RepeatDelay: .5, RepeatInterval: .033}
}

// continueHolds is how long a screen stays before ENTER moves on from it, seconds.
var continueHolds = map[string]float64{"volume": 1, "cover": 1, "win": 1, "lose": 1, "game_over": 1.5, "ending": 1.5}

// drillTimes is how often each new letter must be keyed before a chapter's messages begin.
const drillTimes = 3

// Keys the game understands besides typed letters.
const (
	KeyEnter     = "\n"
	KeyTab       = "\t"
	KeyEscape    = "ESC"
	KeyBackspace = "\x7f"
)

// Game is MORSE CODE's state machine. A front end feeds it SpaceDown/SpaceUp (the telegraph
// key), Key (everything typed) and Tick once a frame, then shows Draw. Times are seconds on
// any monotonic clock.
type Game struct {
	Quit bool // the player asked to leave

	cfg   Config
	mixer *Mixer
	keyer *Keyer

	state        string
	stateStart   float64
	typedAll     bool // the current screen's typed-out lines are fully shown
	lang         string
	hi           int
	savedChapter int
	// volumeClosing: the volume screen shows the epilogue of the volume just finished, rather
	// than the prologue of the one the chapter opens
	volumeClosing bool

	score, lives, combo, chapter, beatNo int
	newHi                                bool
	beat                                 Beat
	mode, word, freeText                 string
	newLetters, banner                   string
	bonus                                int
	drill                                []int // times each of newLetters was keyed on the chapter screen

	messages  []string // the beat's messages; word is messages[msgNo]
	msgNo     int
	msgsDone  int      // messages finished in this chapter
	moverFrom float64  // where the scene's mover stood when this message began, 0 to 1
	lastWords []string // what the last receiving beat received, for an echo

	pos         int  // letters of the word done
	hint        bool // show the pattern of the letter to send
	timeTotal   float64
	timeEnd     float64
	nextBeat    float64 // next heartbeat sound in the last stretch
	progressEnd float64
	on          []Element // the received word's tones
	signalStart float64
	tapeLetters string // letters the receiving tape still shows
	lampLetters string // letters that still light the lamp

	msg      string
	msgColor Color
	msgUntil float64

	line telegraphLine // playing with another person (line.go)
}

func NewGame(cfg Config, mixer *Mixer, now float64) *Game {
	saved := LoadSave(cfg.SavePath)
	g := &Game{cfg: cfg, mixer: mixer, hi: saved.Hi, savedChapter: max(1, saved.Chapter), lang: "en", chapter: 1, mode: "encode"}
	if slices.Contains(Langs, saved.Lang) {
		g.lang = saved.Lang
	}
	g.line.codename, g.line.secret, g.line.number = saved.Codename, saved.LineSecret, saved.LineNumber
	g.setState("lang", now)
	return g
}

// ---- what front ends need to lay out their controls

func (g *Game) State() string     { return g.state }
func (g *Game) Mode() string      { return g.mode }
func (g *Game) Lang() string      { return g.lang }
func (g *Game) SavedChapter() int { return g.savedChapter }

// DrillDone: every new letter of the chapter has been keyed drillTimes.
func (g *Game) DrillDone() bool {
	return !slices.ContainsFunc(g.drill, func(n int) bool { return n < drillTimes })
}

// Keying: the telegraph key is live (sending, practising, or trying a chapter's new letters).
func (g *Game) Keying() bool {
	return g.state == "free" || g.state == "chapter" || g.state == "line" || (g.state == "play" && g.mode == "encode")
}

// Receiving: the player is typing the letters of a received word.
func (g *Game) Receiving() bool { return g.state == "play" && g.mode == "decode" }

// Typing: the player types letters or digits: a received word, a codename, a number to dial.
func (g *Game) Typing() bool {
	return g.Receiving() || g.state == "codename" || g.state == "switchboard"
}

// LineAvailable: the game can reach the telephone exchange, so the title offers the line.
func (g *Game) LineAvailable() bool { return g.cfg.Wire != nil }

func (g *Game) chapters() []Chapter { return content.Chapters[g.lang] }

func (g *Game) currentChapter() Chapter { return g.chapters()[g.chapter-1] }

func (g *Game) volumes() []Volume { return content.Volumes[g.lang] }

// volumeOf is the volume holding a chapter, numbered from 1, and the chapter's number in it.
//
//	volumeOf(5) == 2, 1 when the first volume has four chapters
func (g *Game) volumeOf(chapter int) (volume, nth int) {
	for i, v := range g.volumes() {
		if chapter <= v.Chapters {
			return i + 1, chapter
		}
		chapter -= v.Chapters
	}
	return len(g.volumes()), chapter
}

// chapterNumbers fills a label's {v}, {n} and {total}: the chapter's volume, its number in
// that volume and the volume's chapter count.
func (g *Game) chapterNumbers(chapter int) map[string]any {
	v, n := g.volumeOf(chapter)
	return map[string]any{"v": v, "n": n, "total": g.volumes()[v-1].Chapters}
}

// chapterLine is the chapter's number in its volume and its title: "CHAPTER 2 · THE RESCUE".
func (g *Game) chapterLine() string {
	values := g.chapterNumbers(g.chapter)
	values["title"] = g.currentChapter().Title
	return g.text("brief_line", values)
}

// shownVolume is what the volume screen shows: the volume's number, title, a line under it
// (its years, or that this is what came after) and the lines typed out below.
func (g *Game) shownVolume() (n int, title, subtitle string, lines []string) {
	n, _ = g.volumeOf(g.chapter)
	if g.volumeClosing {
		v := g.volumes()[n-2]
		return n - 1, v.Title, g.text("volume_after", nil), v.Epilogue
	}
	v := g.volumes()[n-1]
	return n, v.Title, v.Years, v.Prologue
}

// WaitsForEnter is true on the screens that only wait for ENTER, which a tap on the phone's
// game also gives.
func (g *Game) WaitsForEnter() bool {
	return slices.Contains([]string{"volume", "cover", "brief", "win", "lose", "game_over", "ending"}, g.state)
}

// readyToContinue: the screen has stayed its continueHolds, so ENTER moves on and says so.
func (g *Game) readyToContinue(now float64) bool {
	return now-g.stateStart > continueHolds[g.state]
}

func (g *Game) text(key string, values map[string]any) string {
	return format(content.UI[g.lang][key], values)
}

func (g *Game) storeProgress() {
	WriteSave(g.cfg.SavePath, Save{Hi: g.hi, Chapter: g.savedChapter, Lang: g.lang,
		Codename: g.line.codename, LineSecret: g.line.secret, LineNumber: g.line.number})
}

// ---- state changes

func (g *Game) setState(state string, now float64) {
	g.state, g.stateStart, g.typedAll = state, now, false
	g.keyer = NewKeyer(g.cfg)
	g.mixer.SetKey(false)
	g.mixer.SetRemoteKey(false)
}

// UseReleaseKeys switches between timing real presses and guessing holds from autorepeat.
func (g *Game) UseReleaseKeys(releases bool) {
	g.cfg.Releases = releases
	g.keyer = NewKeyer(g.cfg)
}

func (g *Game) Releases() bool { return g.cfg.Releases }

func (g *Game) toTitle(now float64) {
	if g.cfg.Wire != nil {
		g.cfg.Wire.Close()
	}
	g.mixer.StopSignal()
	g.setState("title", now)
}

func (g *Game) startGame(chapter int, now float64) {
	g.score, g.lives, g.combo, g.chapter, g.lastWords = 0, 3, 0, chapter, nil
	g.openChapter(now)
}

func (g *Game) openChapter(now float64) {
	if g.chapter > len(g.chapters()) {
		g.finish(now)
		return
	}
	g.savedChapter = max(g.savedChapter, g.chapter)
	g.storeProgress()
	g.beatNo, g.msgsDone, g.freeText = 0, 0, ""
	g.newLetters = FocusLetters(g.chapter)
	g.drill = make([]int, len(g.newLetters))
	if _, nth := g.volumeOf(g.chapter); nth == 1 {
		g.volumeClosing = false
		g.setState("volume", now)
		return
	}
	g.setState("cover", now)
}

// leaveCover goes on to the chapter's new letters, or straight to its first message when it
// teaches none.
func (g *Game) leaveCover(now float64) {
	if content.Levels[g.chapter-1] == "" {
		g.startBeat(now)
		return
	}
	g.setState("chapter", now)
	g.playNewLetters(1)
}

// countDrill counts a letter keyed on the chapter screen toward its drill, with a chime when
// that letter is done.
func (g *Game) countDrill(letter string) {
	i := strings.Index(g.newLetters, letter)
	if letter == "" || i < 0 || g.drill[i] >= drillTimes {
		return
	}
	g.drill[i]++
	if g.drill[i] == drillTimes {
		g.mixer.Play(Notes([]float64{784, 1047}, .08, .1), FX, false)
	}
}

// playSelect is the "tchu-liiim" of a choice made on the title screens.
func (g *Game) playSelect() {
	g.mixer.Play(Concat(Square(1175, .05, .06), Chime(1760, .55, .08)), FX, true)
}

func (g *Game) playNewLetters(delay float64) {
	s := Rest(delay)
	for _, ch := range g.newLetters {
		on, _ := Schedule(string(ch), 15, 1)
		s = Concat(s, Signal(on), Rest(.8))
	}
	g.mixer.Play(s, Sig, true)
}

// startBeat picks the beat's messages and opens its briefing.
func (g *Game) startBeat(now float64) {
	g.beat = g.currentChapter().Beats[g.beatNo]
	g.mode = g.beat.Mode
	g.messages, g.msgNo, g.moverFrom = g.beatMessages(g.beat), 0, 0
	g.openBeat(now)
}

// beatMessages: the beat's own words, or what the previous beat received, or Count picked
// at random without repeats.
func (g *Game) beatMessages(b Beat) []string {
	switch {
	case len(b.Words) > 0:
		return b.Words
	case b.Echo && len(g.lastWords) > 0:
		return g.lastWords
	}
	pick := func() string {
		if b.Groups {
			return PickGroup(g.chapter)
		}
		return PickWord(g.chapter, g.lang, b.Mode)
	}
	messages := make([]string, max(1, b.Count))
	for i := range messages {
		messages[i] = pick()
		for tries := 0; tries < 5 && slices.Contains(messages[:i], messages[i]); tries++ {
			messages[i] = pick()
		}
	}
	return messages
}

// openBeat shows the briefing for the beat's current message; a lost message comes back here.
func (g *Game) openBeat(now float64) {
	g.word = g.messages[g.msgNo]
	g.mixer.StopSignal()
	g.setState("brief", now)
}

// messageNumber is which message of the chapter this is, and how many it has.
func (g *Game) messageNumber() (n, total int) {
	prev := 0
	for _, b := range g.currentChapter().Beats {
		count := max(1, len(b.Words), b.Count)
		if b.Echo {
			count = prev
		}
		total, prev = total+count, count
	}
	return min(g.msgsDone+1, total), total
}

func (g *Game) startPlay(now float64) {
	g.setState("play", now)
	g.word = g.messages[g.msgNo]
	g.pos, g.hint = 0, g.chapter <= 3
	pace, n := content.Pace, float64(letterCount(g.word))
	var budget float64
	if g.mode == "decode" {
		lead := .8
		if g.msgNo > 0 { // straight on from the last message: a breath first
			lead = 1.5
		}
		var length float64
		g.on, length = Schedule(g.word, PaceAtChapter(g.chapter, pace.WPM), PaceAtChapter(g.chapter, pace.Spacing))
		g.tapeLetters, g.lampLetters = LettersStillAided(g.chapter, pace.TapeChapters), LettersStillAided(g.chapter, pace.LampChapters)
		g.replay(now, lead)
		budget = length + lead + n*PaceAtChapter(g.chapter, pace.ReceiveTime)
	} else {
		budget = n * PaceAtChapter(g.chapter, pace.SendTime)
	}
	g.timeTotal = budget + 2
	g.timeEnd = now + g.timeTotal
	g.nextBeat = now
}

func (g *Game) replay(now, lead float64) {
	g.signalStart = now + lead
	g.mixer.Play(Concat(Rest(lead), Signal(g.on)), Sig, true)
}

// progress is how much of the message's time is gone, 0 to 1.
func (g *Game) progress(now float64) float64 {
	return min(1, max(0, 1-(g.timeEnd-now)/g.timeTotal))
}

// sceneProgress is how far the scene's mover has come, given how far into the current message
// it is. It crosses once per beat: each message takes it from where the last one left it to
// the end of this message's share of the way.
func (g *Game) sceneProgress(intoMessage float64) float64 {
	shareEnd := float64(g.msgNo+1) / float64(len(g.messages))
	return g.moverFrom + (shareEnd-g.moverFrom)*intoMessage
}

func (g *Game) say(text string, color Color, now float64) {
	g.msg, g.msgColor, g.msgUntil = text, color, now+2.5
}

func (g *Game) correct(now float64) {
	g.pos++
	g.combo++
	points := 10 * g.chapter * min(g.combo, 8)
	g.score += points
	g.say(fmt.Sprintf("+%d", points), Go, now)
	g.mixer.Play(Square(1047, .04, .08), FX, false)
	for g.pos < len(g.word) && g.word[g.pos] == ' ' {
		g.pos++
	}
	if g.pos < len(g.word) {
		return
	}
	if g.msgNo+1 < len(g.messages) {
		g.nextMessage(now)
	} else {
		g.win(now)
	}
}

// timeBonus is the points for finishing a message with time to spare.
func (g *Game) timeBonus(now float64) int {
	return int(max(0, g.timeEnd-now)*10*float64(g.chapter)) + 100*g.chapter
}

// nextMessage goes straight on to the beat's next message, banking this one's time bonus.
func (g *Game) nextMessage(now float64) {
	bonus := g.timeBonus(now)
	g.score += bonus
	g.moverFrom = g.sceneProgress(g.progress(now))
	g.msgNo++
	g.msgsDone++
	g.mixer.Play(Notes([]float64{659, 784}, .08, .1), FX, false)
	g.startPlay(now)
	g.say(g.text("time_bonus", map[string]any{"bonus": bonus}), Amber, now)
}

func (g *Game) wrong(text string, now float64) {
	g.combo = 0
	g.timeEnd -= g.timeTotal * .1
	g.say(text, Alert, now)
	g.mixer.Play(Square(150, .12, .15), FX, false)
}

func pickOne(options []string) string { return options[rand.IntN(len(options))] }

func (g *Game) win(now float64) {
	g.progressEnd = g.sceneProgress(g.progress(now))
	g.bonus = g.timeBonus(now)
	g.score += g.bonus
	g.banner = pickOne(content.WinBanners[g.lang])
	if g.mode == "decode" {
		g.lastWords = g.messages
	}
	g.mixer.StopSignal()
	g.setState("win", now)
	g.mixer.Play(Notes([]float64{523, 659, 784}, .12, .1), FX, true)
}

func (g *Game) lose(now float64) {
	g.progressEnd, g.lives, g.combo = 1, g.lives-1, 0
	g.banner = pickOne(content.LoseBanners[g.lang])
	g.mixer.StopSignal()
	g.setState("lose", now)
	g.mixer.Play(Noise(1.4, .25, 40), FX, true)
}

func (g *Game) afterResult(now float64) {
	if g.state == "lose" {
		if g.lives <= 0 {
			g.gameOver(now)
		} else {
			g.openBeat(now)
		}
		return
	}
	g.beatNo++
	g.msgsDone++
	if g.beatNo >= len(g.currentChapter().Beats) {
		g.chapter++
		if _, nth := g.volumeOf(g.chapter); nth == 1 && g.chapter <= len(g.chapters()) {
			g.savedChapter = max(g.savedChapter, g.chapter) // leaving on the epilogue still keeps the chapter won
			g.storeProgress()
			g.volumeClosing = true
			g.setState("volume", now)
			return
		}
		g.openChapter(now)
		return
	}
	g.startBeat(now)
}

func (g *Game) recordScore() {
	g.newHi = g.score > g.hi
	g.hi = max(g.hi, g.score)
	g.storeProgress()
}

func (g *Game) gameOver(now float64) {
	g.recordScore()
	g.setState("game_over", now)
	g.mixer.Play(Slide(300, 80, 1, .12), FX, true)
}

func (g *Game) finish(now float64) {
	g.savedChapter = 1
	g.recordScore()
	g.setState("ending", now)
	g.newLetters = ""
	s, _ := Schedule("S", 12, 1)
	k, _ := Schedule("K", 12, 1)
	for _, e := range k {
		s = append(s, Element{e.Start + .6, e.End + .6, e.Kind, e.Letter})
	}
	g.mixer.Play(Concat(Rest(4), Signal(s)), Sig, true)
}

// ---- input

func (g *Game) SpaceDown(now float64) {
	if !g.Keying() {
		return
	}
	g.keyer.Press(now)
	if !g.keyer.BlipOnPress() {
		g.mixer.SetKey(true)
	} else if !g.keyer.Holding() {
		g.mixer.Blip(.09)
		g.sendBlipDownTheLine(now, .09)
	}
	g.sendToneDownTheLine(now)
}

func (g *Game) SpaceUp(now float64) {
	if g.Keying() {
		g.keyer.Release(now)
		g.mixer.SetKey(g.keyer.Sounding())
		g.sendToneDownTheLine(now)
	}
}

// Key handles a typed key: a character, or one of the Key* constants.
func (g *Game) Key(k string, now float64) {
	s := g.state
	if g.lineKey(k, now) {
		return
	}
	if k == KeyEscape {
		if s == "title" || s == "lang" {
			g.Quit = true
		} else {
			g.toTitle(now)
		}
		return
	}
	if k == " " { // a typed space: only sent when releases are unknown
		g.SpaceDown(now)
		return
	}
	enter := k == KeyEnter || k == "\r"
	if enter && (s == "brief" || s == "ending" || s == "volume") && !g.typedAll {
		g.stateStart -= 100 // skip the typing-out
		return
	}
	switch s {
	case "lang":
		if k == "1" || k == "2" {
			g.lang = Langs[k[0]-'1']
		} else if strings.ToLower(k) == "v" && g.cfg.OpenURL != nil {
			g.cfg.OpenURL(PrivacyURL)
			g.playSelect()
		} else if enter {
			g.storeProgress()
			g.toTitle(now)
			g.playSelect()
		}
	case "title":
		switch key := strings.ToLower(k); {
		case enter:
			g.startGame(1, now)
		case key == "c" && g.savedChapter > 1:
			g.startGame(g.savedChapter, now)
		case key == "f" || key == "p":
			g.setState("free", now)
			g.freeText = ""
		case key == "l":
			g.setState("lang", now)
		case key == "q":
			g.Quit = true
			return
		case key == "w" && g.LineAvailable():
			g.openLine(now)
		default:
			return
		}
		g.playSelect()
	case "volume":
		if enter && g.readyToContinue(now) && g.volumeClosing {
			g.openChapter(now)
		} else if enter && g.readyToContinue(now) {
			g.setState("cover", now)
		}
	case "cover":
		if enter && g.readyToContinue(now) {
			g.leaveCover(now)
		}
	case "chapter":
		if enter && g.DrillDone() {
			g.startBeat(now)
		} else if k == KeyTab {
			g.playNewLetters(0)
		}
	case "brief":
		if enter {
			g.startPlay(now)
		}
	case "win", "lose":
		if enter && g.readyToContinue(now) {
			g.afterResult(now)
		}
	case "game_over", "ending":
		if enter && g.readyToContinue(now) {
			g.toTitle(now)
		}
	case "free":
		if k == KeyBackspace || k == "\x08" {
			r := []rune(g.freeText)
			g.freeText = string(r[:max(0, len(r)-1)])
		}
	case "play":
		g.keyDuringPlay(k, now)
	}
}

func (g *Game) keyDuringPlay(k string, now float64) {
	if k == KeyTab {
		if g.mode == "decode" {
			g.replay(now, .3)
		} else if !g.hint {
			cost := 25 * g.chapter
			g.hint, g.score = true, max(0, g.score-cost)
			g.say(g.text("hints_on", map[string]any{"cost": cost}), Amber, now)
		}
		return
	}
	ch := strings.ToUpper(k)
	if _, isLetter := Code[ch]; g.mode != "decode" || !isLetter {
		return
	}
	if ch == string(g.word[g.pos]) {
		g.correct(now)
	} else {
		g.wrong(g.text("incorrect", map[string]any{"ch": ch, "pattern": Pretty(Code[ch])}), now)
	}
}

// ---- time

// typeKeyedLetters adds to text the letter the keyer just finished, if any, and a space once
// the key has been idle a while after a word; text keeps its last 60 runes. It also returns
// the letter, or "" when none was finished.
func typeKeyedLetters(k *Keyer, text string, letterGap, now float64) (string, string) {
	var letter string
	if pattern := k.Tick(now); pattern != "" {
		var ok bool
		if letter, ok = Decode[pattern]; !ok {
			letter = "?"
		}
		text = tail(text+letter, 60)
	}
	idle := !k.Down() && k.Pattern == ""
	if idle && text != "" && !strings.HasSuffix(text, " ") && now-k.Last > letterGap*2.5 {
		text += " "
	}
	return text, letter
}

func (g *Game) Tick(now float64) {
	switch g.state {
	case "free", "chapter":
		var letter string
		g.freeText, letter = typeKeyedLetters(g.keyer, g.freeText, g.cfg.LetterGap, now)
		if g.state == "chapter" {
			g.countDrill(letter)
		}
	case "codename", "switchboard", "calling", "ringing", "line":
		g.tickLine(now)
	case "play":
		if g.mode == "encode" {
			if pattern := g.keyer.Tick(now); pattern != "" {
				need := string(g.word[g.pos])
				if got := Decode[pattern]; got == need {
					g.correct(now)
				} else {
					if got == "" {
						got = "??"
					}
					g.wrong(g.text("sent_need", map[string]any{"got": got, "sent": Pretty(pattern),
						"need": need, "needed": Pretty(Code[need])}), now)
				}
			}
		}
		if g.state == "play" {
			left := (g.timeEnd - now) / g.timeTotal
			if now >= g.timeEnd {
				g.lose(now)
			} else if left < .3 && now >= g.nextBeat {
				// heartbeat in the last stretch: the only timer sound
				g.mixer.Play(Concat(Square(55, .05, .2), Rest(.12), Square(50, .05, .15)), FX, false)
				g.nextBeat = now + 1
				if left <= .15 {
					g.nextBeat = now + .6
				}
			}
		}
	}
	g.mixer.SetKey(g.Keying() && g.keyer.Sounding())
}
