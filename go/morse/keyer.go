package morse

// Keyer turns space-key events into dit/dah patterns.
//
// With Releases (touch, a GUI window, Kitty-protocol terminals, /dev/input), a press held
// DahTime or longer is a dah. Without them only presses arrive: one press alone is a tap
// (dit); a tap followed ~repeat-delay later by a burst of autorepeats ~repeat-interval
// apart is a hold (dah); two presses with no burst after them were two quick taps.
type Keyer struct {
	Releases               bool
	DahTime                float64
	LetterGap              float64
	Pattern                string    // dits and dahs of the letter being keyed, as '.' and '-'
	Last                   float64   // time of the last press (or release, with Releases)
	ev                     []float64 // presses not yet judged
	firstRepeat, repeatGap float64
}

func NewKeyer(cfg Config) *Keyer {
	k := &Keyer{Releases: cfg.Releases, DahTime: cfg.DahTime, LetterGap: cfg.LetterGap}
	if !cfg.Releases {
		k.firstRepeat = cfg.RepeatDelay + .08
		k.repeatGap = cfg.RepeatInterval*2 + .05
		k.LetterGap = max(cfg.LetterGap, k.firstRepeat+.1)
	}
	return k
}

// Down reports a press that hasn't been judged or released yet.
func (k *Keyer) Down() bool { return len(k.ev) > 0 }

// BlipOnPress: without releases the tone can't start for real until the hold is proven.
func (k *Keyer) BlipOnPress() bool { return !k.Releases }

func (k *Keyer) settle(now float64) {
	for len(k.ev) > 0 {
		gap := now - k.ev[len(k.ev)-1]
		switch {
		case len(k.ev) == 1:
			if gap <= k.firstRepeat {
				return
			}
			k.Pattern += "."
			k.ev = k.ev[:0]
		case len(k.ev) == 2:
			if gap <= k.repeatGap {
				return
			}
			k.Pattern += "."
			k.ev = k.ev[1:] // first was a tap; judge the second as its own press
		default:
			if gap <= k.repeatGap {
				return
			}
			k.Pattern += "-"
			k.ev = k.ev[:0]
		}
	}
}

func (k *Keyer) Press(t float64) {
	if k.Releases {
		if len(k.ev) == 0 {
			k.ev, k.Last = []float64{t}, t
		}
		return
	}
	k.settle(t)
	k.ev = append(k.ev, t)
	k.Last = t
}

func (k *Keyer) Release(t float64) {
	if !k.Releases || len(k.ev) == 0 {
		return
	}
	if t-k.ev[0] >= k.DahTime {
		k.Pattern += "-"
	} else {
		k.Pattern += "."
	}
	k.ev, k.Last = nil, t
}

// Holding: without releases, a press followed by an autorepeat burst.
func (k *Keyer) Holding() bool { return !k.Releases && len(k.ev) >= 3 }

func (k *Keyer) Sounding() bool {
	if k.Releases {
		return len(k.ev) > 0
	}
	return k.Holding()
}

// Live is the pattern so far, including the element still being keyed.
func (k *Keyer) Live(now float64) string {
	if len(k.ev) == 0 {
		return k.Pattern
	}
	if k.Releases {
		if now-k.ev[0] >= k.DahTime {
			return k.Pattern + "-"
		}
		return k.Pattern + "."
	}
	if k.Holding() {
		return k.Pattern + "-"
	}
	return k.Pattern + "."
}

// Tick returns a finished letter pattern once the letter gap has passed, else "".
func (k *Keyer) Tick(now float64) string {
	if !k.Releases {
		k.settle(now)
	}
	if len(k.ev) == 0 && k.Pattern != "" && now-k.Last > k.LetterGap {
		p := k.Pattern
		k.Pattern = ""
		return p
	}
	return ""
}
