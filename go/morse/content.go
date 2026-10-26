package morse

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
)

// content.json holds everything that isn't game logic: the Koch letter order, word lists,
// chapters, UI strings in both languages, sprite art and scene layouts.
//
//go:embed content.json
var contentJSON []byte

type Beat struct {
	Mode  string   `json:"mode"` // "encode" (you send) or "decode" (you receive)
	Title string   `json:"title"`
	Brief []string `json:"brief"`
	Task  string   `json:"task"` // "" gives the mode's usual task
	Win   string   `json:"win"`
	Lose  string   `json:"lose"` // "" gives the usual line
	Scene string   `json:"scene"`
	// The messages, sent or received one after another: Words in order, else the ones the
	// previous beat received (Echo), else Count picked at random, as cipher groups if Groups.
	Words  []string `json:"words"`
	Echo   bool     `json:"echo"`
	Count  int      `json:"count"`
	Groups bool     `json:"groups"`
}

// Chapter is a historical event. It opens on a cover: the Cover picture, the year and the title.
type Chapter struct {
	Title string `json:"title"`
	Year  string `json:"year"`
	Cover string `json:"cover"` // a key of Content.Covers
	Beats []Beat `json:"beats"`
}

// Scene: the mover creeping toward the target is the mission timer. Sky and ground name palette colours.
type Scene struct {
	Mover  string `json:"mover"`
	Target string `json:"target"`
	Sky    string `json:"sky"`
	Ground string `json:"ground"`
}

// Pace sets how difficulty grows. Each pair is the value at the first chapter and at the
// last, with a straight line between.
type Pace struct {
	WPM         [2]float64 `json:"wpm"`          // speed of received words
	Spacing     [2]float64 `json:"spacing"`      // extra space between their letters (Farnsworth factor)
	ReceiveTime [2]float64 `json:"receive_time"` // seconds allowed per letter to receive
	SendTime    [2]float64 `json:"send_time"`    // seconds allowed per letter to send
	// A letter is shown on the receiving tape for TapeChapters chapters after it's learned,
	// and lights the lamp for LampChapters; after that it's heard only.
	TapeChapters int `json:"tape_chapters"`
	LampChapters int `json:"lamp_chapters"`
}

type Content struct {
	// Levels is the Koch-style unlock order: chapter N adds Levels[N-1]. "" adds none: that
	// chapter's messages drill the two groups learned just before it.
	Levels      []string                     `json:"levels"`
	Pace        Pace                         `json:"pace"`
	Words       map[string][]string          `json:"words"`
	Chapters    map[string][]Chapter         `json:"chapters"`
	Ending      map[string][]string          `json:"ending"`
	WinBanners  map[string][]string          `json:"win_banners"`
	LoseBanners map[string][]string          `json:"lose_banners"`
	UI          map[string]map[string]string `json:"ui"`
	Sprites     map[string][]string          `json:"sprites"`
	Flyers      []string                     `json:"flyers"` // movers that cross the sky instead of the ground
	Scenes      map[string]Scene             `json:"scenes"`
	Covers      map[string]CoverArt          `json:"covers"`
}

var Langs = []string{"en", "pt"}

var content = func() Content {
	var c Content
	if err := json.Unmarshal(contentJSON, &c); err != nil {
		panic(err)
	}
	return c
}()

var placeholder = regexp.MustCompile(`\{(\w+)(?::0(\d+)d)?\}`)

// format fills Python-style placeholders: "{word}" and zero-padded "{score:06d}".
//
//	format("SCORE {score:06d}", map[string]any{"score": 42}) == "SCORE 000042"
func format(s string, values map[string]any) string {
	return placeholder.ReplaceAllStringFunc(s, func(m string) string {
		parts := placeholder.FindStringSubmatch(m)
		v, ok := values[parts[1]]
		if !ok {
			return m
		}
		if parts[2] != "" {
			width, _ := strconv.Atoi(parts[2])
			return fmt.Sprintf("%0*d", width, v)
		}
		return fmt.Sprint(v)
	})
}
