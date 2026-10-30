package morse

import (
	"math/rand/v2"
	"slices"
	"strings"
)

var Code = map[string]string{
	"A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....",
	"I": "..", "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.",
	"Q": "--.-", "R": ".-.", "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
	"Y": "-.--", "Z": "--..", "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
	"5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
}

// CodeOrder is the reference chart's order: letters, then digits.
const CodeOrder = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

var Decode = func() map[string]string {
	d := map[string]string{}
	for ch, pattern := range Code {
		d[pattern] = ch
	}
	return d
}()

const (
	Dot = "•"
	Dah = "━"
)

// Pretty draws a pattern for people: Pretty(".-") == "• ━".
func Pretty(pattern string) string {
	parts := make([]string, len(pattern))
	for i, e := range pattern {
		parts[i] = Dot
		if e == '-' {
			parts[i] = Dah
		}
	}
	return strings.Join(parts, " ")
}

// Unlocked is every letter learned by the given chapter.
func Unlocked(chapter int) string {
	return strings.Join(content.Levels[:min(chapter, len(content.Levels))], "")
}

// FocusLetters are the letters a chapter drills: its new ones, or for a chapter without new
// ones the two groups before it.
func FocusLetters(chapter int) string {
	if content.Levels[chapter-1] != "" {
		return content.Levels[chapter-1]
	}
	var groups []string
	for _, g := range content.Levels[:chapter] {
		if g != "" {
			groups = append(groups, g)
		}
	}
	return strings.Join(groups[max(0, len(groups)-2):], "")
}

// LongestWord is the most letters a random message may have, spaces aside: it grows a letter
// every three chapters, from 6 when receiving and 5 when sending, up to 10.
func LongestWord(chapter int, mode string) int {
	if mode == "decode" {
		return min(10, 6+(chapter-1)/3)
	}
	return min(10, 5+(chapter-1)/3)
}

// letterCount is the letters in a message, leaving out the spaces between its words.
func letterCount(message string) int { return len(strings.ReplaceAll(message, " ", "")) }

// PaceAtChapter is a pace setting at this chapter: its first value at chapter 1, its last at the
// final chapter, in a straight line between.
//
//	PaceAtChapter(1, content.Pace.SendTime) == 8; PaceAtChapter(17, content.Pace.SendTime) == 3.5
func PaceAtChapter(chapter int, setting [2]float64) float64 {
	first, last := setting[0], setting[1]
	return first + (last-first)*float64(chapter-1)/float64(len(content.Levels)-1)
}

// chapterTeaching is the chapter that teaches a letter.
func chapterTeaching(letter rune) int {
	for n, group := range content.Levels {
		if strings.ContainsRune(group, letter) {
			return n + 1
		}
	}
	return 0
}

// LettersStillAided is the known letters still shown by an aid kept for chaptersKept chapters after
// they're learned: newer letters keep it, older ones are left to the ear.
func LettersStillAided(chapter, chaptersKept int) string {
	var letters []rune
	for _, ch := range Unlocked(chapter) {
		if chapter-chapterTeaching(ch) < chaptersKept {
			letters = append(letters, ch)
		}
	}
	return string(letters)
}

// onlyUses: every letter of a message is one of letters; spaces between words don't count.
func onlyUses(word, letters string) bool {
	for _, ch := range word {
		if ch != ' ' && !strings.ContainsRune(letters, ch) {
			return false
		}
	}
	return true
}

// PickWord: a word or short sentence made only of known letters, usually one with a letter
// the chapter drills.
func PickWord(chapter int, lang, mode string) string {
	known, focus := Unlocked(chapter), FocusLetters(chapter)
	var pool, fresh []string
	for _, w := range content.Words[lang] {
		if onlyUses(w, known) && letterCount(w) <= LongestWord(chapter, mode) {
			pool = append(pool, w)
			if strings.ContainsAny(w, focus) {
				fresh = append(fresh, w)
			}
		}
	}
	if len(fresh) > 0 && rand.Float64() < .7 {
		return fresh[rand.IntN(len(fresh))]
	}
	if len(pool) > 0 {
		return pool[rand.IntN(len(pool))]
	}
	letters := []rune(known)
	slices.Sort(letters)
	word := make([]rune, 3)
	for i := range word {
		word[i] = letters[rand.IntN(len(letters))]
	}
	return string(word)
}

// PickGroup is a cipher group: four or five known letters, half of them ones the chapter drills.
//
//	PickGroup(1) might be "TNEA" or "ANTTE"
func PickGroup(chapter int) string {
	known, focus := Unlocked(chapter), FocusLetters(chapter)
	group := make([]byte, 4+rand.IntN(2))
	for i := range group {
		from := known
		if rand.IntN(2) == 0 {
			from = focus
		}
		group[i] = from[rand.IntN(len(from))]
	}
	return string(group)
}

// ---------------------------------------------------------------- signal

const SignalHz = 600

// Element is one tone of a sent word.
type Element struct {
	Start, End float64
	Kind       byte // '.' or '-'
	Letter     int  // index into the word
}

// Schedule times a message: the on-intervals of its tones and its total length, in seconds.
// A space between words stretches the 3-dot gap after a letter to 7 dots (both widened by
// farnsworth).
func Schedule(word string, wpm, farnsworth float64) ([]Element, float64) {
	dot, t := 1.2/wpm, 0.0
	var on []Element
	for li, ch := range []rune(word) {
		if ch == ' ' {
			t += dot * 4 * farnsworth
			continue
		}
		for _, e := range []byte(Code[string(ch)]) {
			d := dot
			if e == '-' {
				d = 3 * dot
			}
			on = append(on, Element{t, t + d, e, li})
			t += d + dot
		}
		t += dot * (3*farnsworth - 1)
	}
	return on, t
}

// FarnsworthFor is the factor that stretches the gap between letters at wpm to letterGap
// seconds; never below 1, the standard 3-dot gap.
//
//	FarnsworthFor(2.2, 11) == 2.2/(3*1.2/11) ≈ 6.7
func FarnsworthFor(letterGap, wpm float64) float64 {
	return max(1, letterGap/(3*1.2/wpm))
}

func Signal(on []Element) Sound {
	var s Sound
	prev := 0.0
	for _, e := range on {
		s = append(s, Rest(e.Start-prev)...)
		s = append(s, Square(SignalHz, e.End-e.Start, .22)...)
		prev = e.End
	}
	return s
}
