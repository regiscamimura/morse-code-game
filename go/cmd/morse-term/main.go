// Command morse-term is MORSE CODE in the terminal: tap space for a dit, hold it for a dah.
//
// A press of --dah-time or longer is a dah when the terminal reports key releases (see
// package terminal). Otherwise a hold is recognised from the keyboard's autorepeat burst;
// tune --repeat-delay / --repeat-interval then.
package main

import (
	"flag"
	"fmt"
	"os"
	"runtime"
	"time"

	"github.com/ebitengine/oto/v3"

	"github.com/regiscamimura/morse-code-game/go/exchange"
	"github.com/regiscamimura/morse-code-game/go/morse"
	"github.com/regiscamimura/morse-code-game/go/terminal"
)

func main() {
	delay, interval := terminal.SystemKeyRepeat()
	cfg := morse.DefaultConfig()
	volume := flag.Float64("volume", .4, "0 (mute) to 1")
	noEvdev := flag.Bool("no-evdev", false, "Linux: don't read /dev/input when the terminal can't report releases")
	flag.Float64Var(&cfg.RepeatDelay, "repeat-delay", delay, "keyboard autorepeat delay, seconds")
	flag.Float64Var(&cfg.RepeatInterval, "repeat-interval", interval, "autorepeat interval, seconds")
	flag.Float64Var(&cfg.LetterGap, "letter-gap", cfg.LetterGap, "silence that ends a letter, seconds")
	flag.Float64Var(&cfg.DahTime, "dah-time", cfg.DahTime, "with key releases reported: press at least this long for a dah, seconds")
	flag.Parse()

	mixer := morse.NewMixer(*volume)
	player := startSound(mixer)
	defer runtime.KeepAlive(player) // oto closes a player the garbage collector finds unreferenced
	t, err := terminal.Open(!*noEvdev)
	if err != nil {
		fmt.Fprintln(os.Stderr, "morse needs a terminal:", err)
		os.Exit(1)
	}
	defer t.Restore()
	cfg.Releases = t.ReportsRelease()
	cfg.SavePath = morse.DefaultSavePath()
	cfg.Wire = exchange.New(exchange.Address())
	play(morse.NewGame(cfg, mixer, 0), t)
}

// startSound plays the mixer on the default sound card, or leaves the game silent and says why.
// The caller must keep the player referenced for as long as the sound should play.
func startSound(mixer *morse.Mixer) *oto.Player {
	ctx, ready, err := oto.NewContext(&oto.NewContextOptions{
		SampleRate: morse.OutRate, ChannelCount: 1, Format: oto.FormatFloat32LE,
		BufferSize: 20 * time.Millisecond,
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "morse: no sound:", err)
		return nil
	}
	<-ready
	player := ctx.NewPlayer(mixer.Stream(1))
	// short buffer: the sidetone must start the moment the key goes down
	player.SetBufferSize(morse.OutRate * 4 * 30 / 1000)
	player.Play()
	return player
}

// play feeds terminal input to the game and redraws ~30 times a second until it quits.
func play(g *morse.Game, t *terminal.Terminal) {
	start := time.Now()
	last := ""
	for !g.Quit {
		events := t.Read(time.Second / 30)
		now := time.Since(start).Seconds()
		if t.ReportsRelease() != g.Releases() { // /dev/input turned out not to be ours
			g.UseReleaseKeys(t.ReportsRelease())
		}
		for _, e := range events {
			switch {
			case e.Key == terminal.KeyInterrupt:
				return
			case e.Space && e.Down:
				g.SpaceDown(now)
			case e.Space:
				g.SpaceUp(now)
			default:
				g.Key(e.Key, now)
			}
		}
		g.Tick(now)
		width, height := t.Size()
		if frame := g.Draw(width, height, now).ANSI(); frame != last {
			t.Write(frame)
			last = frame
		}
	}
}
