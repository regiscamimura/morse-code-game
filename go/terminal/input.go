package terminal

import (
	"regexp"
	"strconv"
)

// Event is one thing the player did: the space bar going down or up (when the terminal or
// /dev/input reports releases), or a typed key. Key is a character or a morse.Key* name;
// it's " " only when releases are unknown.
type Event struct {
	Space bool // Down is meaningful
	Down  bool
	Key   string
}

const (
	setupScreen   = "\x1b[?1049h\x1b[?25l\x1b[?7l"
	restoreScreen = "\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l"
	// Kitty keyboard protocol flags: 1 disambiguate + 2 report press/release + 8 every key as a code
	kittyPush = "\x1b[>11u"
	kittyPop  = "\x1b[<u"
)

const (
	kittyPress   = 1
	kittyRepeat  = 2
	kittyRelease = 3
	kittyCtrl    = 4
)

var (
	kittyKey   = regexp.MustCompile(`^\x1b\[(\d+)(?::\d*)*(?:;(\d*)(?::(\d+))?)?(?:;[\d:]*)?u$`)
	inputToken = regexp.MustCompile(`(?s)\x1b\[[0-9:;?<=>]*[ -/]*[@-~]|\x1bO.|\x1b|.`)
	arrowKey   = regexp.MustCompile(`^\x1b[\[O](?:1;\d*(?::(\d+))?)?([ABCD])$`)
	kittyNamed = map[int]string{13: "\n", 9: "\t", 127: "\x7f", 8: "\x7f", 27: "ESC"}
	arrowNames = map[string]string{"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}
)

// KeyInterrupt is Ctrl+C (or the input closing): quit.
const KeyInterrupt = "INTERRUPT"

// tokens splits terminal input into escape sequences and single characters.
//
//	tokens("a\x1b[32;1:3ub") == []string{"a", "\x1b[32;1:3u", "b"}
func tokens(input string) []string { return inputToken.FindAllString(input, -1) }

// decodeToken turns one token into events. Space presses and releases come from Kitty
// sequences; autorepeats and the release of every other key are dropped.
func decodeToken(token string) []Event {
	if m := kittyKey.FindStringSubmatch(token); m != nil {
		code, _ := strconv.Atoi(m[1])
		mods, kind := 0, kittyPress
		if m[2] != "" {
			mods, _ = strconv.Atoi(m[2])
			mods--
		}
		if m[3] != "" {
			kind, _ = strconv.Atoi(m[3])
		}
		switch {
		case code == 32:
			if kind == kittyRepeat {
				return nil
			}
			return []Event{{Space: true, Down: kind == kittyPress}}
		case kind == kittyRelease:
			return nil
		case mods&kittyCtrl != 0 && code == 'c':
			return []Event{{Key: KeyInterrupt}}
		case mods&kittyCtrl != 0 && code >= 'a' && code <= 'z':
			return []Event{{Key: string(rune(code & 0x1F))}}
		}
		if name, ok := kittyNamed[code]; ok {
			return []Event{{Key: name}}
		}
		if code > 32 && code < 0xE000 { // skip modifier-only keys
			return []Event{{Key: string(rune(code))}}
		}
		return nil
	}
	if token == "\x1b" {
		return []Event{{Key: "ESC"}}
	}
	if m := arrowKey.FindStringSubmatch(token); m != nil {
		if m[1] != "" {
			if kind, _ := strconv.Atoi(m[1]); kind == kittyRelease {
				return nil
			}
		}
		return []Event{{Key: arrowNames[m[2]]}}
	}
	if token[0] == '\x1b' {
		return nil
	}
	if token == "\x03" {
		return []Event{{Key: KeyInterrupt}}
	}
	if token == "\r" {
		token = "\n"
	}
	return []Event{{Key: token}}
}
