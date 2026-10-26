package morse

import (
	"encoding/binary"
	"math"
	"math/rand/v2"
	"sync"
)

// Rate is the synthesis rate; OutRate is what's sent to the sound card, each sample played 4 times.
const (
	Rate    = 11025
	OutRate = Rate * 4
	KeyHz   = 700
	// RemoteHz is the other player's tone on the telegraph line.
	RemoteHz = 560
)

// Sound is mono samples at Rate, in -1..1.
type Sound []float32

func Square(freq, dur, vol float64) Sound {
	s, phase := make(Sound, int(dur*Rate)), 0.0
	for i := range s {
		phase = math.Mod(phase+freq/Rate, 1)
		s[i] = float32(vol)
		if phase >= .5 {
			s[i] = float32(-vol)
		}
	}
	return s
}

func Slide(f0, f1, dur, vol float64) Sound {
	n, phase := int(dur*Rate), 0.0
	s := make(Sound, n)
	for i := range s {
		phase = math.Mod(phase+(f0+(f1-f0)*float64(i)/float64(n))/Rate, 1)
		s[i] = float32(vol)
		if phase >= .5 {
			s[i] = float32(-vol)
		}
	}
	return s
}

// Noise is sample-and-hold noise with a linear fade: the TIA rumble.
func Noise(dur, vol float64, hold int) Sound {
	n, v := int(dur*Rate), 0.0
	s := make(Sound, n)
	for i := range s {
		if i%hold == 0 {
			v = (rand.Float64()*2 - 1) * vol
		}
		s[i] = float32(v * (1 - float64(i)/float64(n)))
	}
	return s
}

// Chime is a square tone that rings out, fading away over dur seconds.
func Chime(freq, dur, vol float64) Sound {
	s := Square(freq, dur, vol)
	for i := range s {
		s[i] *= float32(math.Exp(-4 * float64(i) / float64(len(s))))
	}
	return s
}

func Rest(dur float64) Sound { return make(Sound, max(0, int(dur*Rate))) }

// Notes plays each frequency for dur; 0 is a rest.
func Notes(freqs []float64, dur, vol float64) Sound {
	var s Sound
	for _, f := range freqs {
		if f == 0 {
			s = append(s, Rest(dur)...)
		} else {
			s = append(s, Square(f, dur, vol)...)
		}
	}
	return s
}

func Concat(sounds ...Sound) Sound {
	var s Sound
	for _, part := range sounds {
		s = append(s, part...)
	}
	return s
}

type Channel int

const (
	FX Channel = iota
	Sig
)

type queued struct {
	sound Sound
	pos   int
}

// Mixer plays two queued channels (FX, Sig) plus the player's sidetone.
// The game calls it from its loop; the sound card's thread reads it through Stream.
type Mixer struct {
	Volume      float64
	mu          sync.Mutex
	queues      [2][]queued
	keyOn       bool
	blip        int
	phase       float64
	remoteOn    bool // the other player's key, on the telegraph line
	remotePhase float64
}

func NewMixer(volume float64) *Mixer { return &Mixer{Volume: volume} }

func (m *Mixer) Play(s Sound, ch Channel, cut bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if cut {
		m.queues[ch] = nil
	}
	m.queues[ch] = append(m.queues[ch], queued{sound: s})
}

func (m *Mixer) StopSignal() {
	m.mu.Lock()
	m.queues[Sig] = nil
	m.mu.Unlock()
}

// SetKey turns the sidetone on or off.
func (m *Mixer) SetKey(on bool) {
	m.mu.Lock()
	m.keyOn = on
	m.mu.Unlock()
}

// SetRemoteKey turns the other player's tone on or off: lower than the sidetone, so the two
// are told apart.
func (m *Mixer) SetRemoteKey(on bool) {
	m.mu.Lock()
	m.remoteOn = on
	m.mu.Unlock()
}

// Blip sounds the sidetone for a moment: a press whose length isn't known yet.
func (m *Mixer) Blip(seconds float64) {
	m.mu.Lock()
	m.blip = int(seconds * Rate)
	m.mu.Unlock()
}

func (m *Mixer) next(ch Channel) float64 {
	q := m.queues[ch]
	for len(q) > 0 {
		if q[0].pos < len(q[0].sound) {
			q[0].pos++
			return float64(q[0].sound[q[0].pos-1])
		}
		q = q[1:]
		m.queues[ch] = q
	}
	return 0
}

// sample is the next mixed sample at Rate; the caller holds mu.
func (m *Mixer) sample() float32 {
	v := m.next(FX) + m.next(Sig)
	if m.keyOn || m.blip > 0 {
		m.blip--
		m.phase = math.Mod(m.phase+float64(KeyHz)/Rate, 1)
		if m.phase < .5 {
			v += .25
		} else {
			v -= .25
		}
	}
	if m.remoteOn {
		m.remotePhase = math.Mod(m.remotePhase+float64(RemoteHz)/Rate, 1)
		if m.remotePhase < .5 {
			v += .25
		} else {
			v -= .25
		}
	}
	// the terminal version's 8-bit output scaled v by 100/128 and clipped
	return float32(max(-1, min(1, v*m.Volume*100/128)))
}

// Stream returns an io.Reader of float32 little-endian samples at OutRate
// with `channels` interleaved copies of the mix.
func (m *Mixer) Stream(channels int) *Stream { return &Stream{m: m, channels: channels} }

type Stream struct {
	m        *Mixer
	channels int
	sub      int
	current  float32
}

func (s *Stream) Read(p []byte) (int, error) {
	frame := 4 * s.channels
	frames := len(p) / frame
	s.m.mu.Lock()
	for f := 0; f < frames; f++ {
		if s.sub == 0 {
			s.current = s.m.sample()
		}
		s.sub = (s.sub + 1) % (OutRate / Rate)
		bits := math.Float32bits(s.current)
		for c := 0; c < s.channels; c++ {
			binary.LittleEndian.PutUint32(p[f*frame+c*4:], bits)
		}
	}
	s.m.mu.Unlock()
	return frames * frame, nil
}
