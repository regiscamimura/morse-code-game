package terminal

import (
	"encoding/binary"
	"math/big"
	"os"
	"strings"
	"syscall"
	"unsafe"
)

const (
	evKey    = 1
	keySpace = 57
)

// keyboards reads the space bar straight from every input device that has one, including
// virtual keyboards (keyd, kanata...) that grab the physical ones and re-emit their keys.
type keyboards struct {
	devices []*os.File
	spaces  chan bool // true for space down, false for up
}

// openKeyboards returns nil when no device with a space key can be read (usually: the user
// isn't in the input group).
func openKeyboards() *keyboards {
	listing, err := os.ReadFile("/proc/bus/input/devices")
	if err != nil {
		return nil
	}
	k := &keyboards{spaces: make(chan bool, 64)}
	for _, block := range strings.Split(string(listing), "\n\n") {
		var handlers, keys string
		for _, line := range strings.Split(block, "\n") {
			if rest, ok := strings.CutPrefix(line, "H: Handlers="); ok {
				handlers = rest
			} else if rest, ok := strings.CutPrefix(line, "B: KEY="); ok {
				keys = rest
			}
		}
		event := ""
		for _, h := range strings.Fields(handlers) {
			if strings.HasPrefix(h, "event") {
				event = h
				break
			}
		}
		if event == "" || !hasSpaceKey(keys) {
			continue
		}
		if f, err := os.Open("/dev/input/" + event); err == nil {
			k.devices = append(k.devices, f)
			go k.readSpaces(f)
		}
	}
	if len(k.devices) == 0 {
		return nil
	}
	return k
}

// hasSpaceKey reads a KEY= capability bitmap: 64-bit hex words, most significant first.
func hasSpaceKey(bitmap string) bool {
	words := strings.Fields(bitmap)
	if len(words) == 0 {
		return false
	}
	var padded strings.Builder
	for _, w := range words {
		padded.WriteString(strings.Repeat("0", 16-len(w)) + w)
	}
	n, ok := new(big.Int).SetString(padded.String(), 16)
	return ok && n.Bit(keySpace) == 1
}

// inputEventSize is sizeof(struct input_event): a timeval, then type, code and value.
var inputEventSize = int(unsafe.Sizeof(syscall.Timeval{})) + 8

func (k *keyboards) readSpaces(f *os.File) {
	buf := make([]byte, inputEventSize*64)
	tv := inputEventSize - 8
	for {
		n, err := f.Read(buf)
		if err != nil {
			return
		}
		for off := 0; off+inputEventSize <= n; off += inputEventSize {
			ev := buf[off+tv:]
			kind, code := binary.NativeEndian.Uint16(ev), binary.NativeEndian.Uint16(ev[2:])
			value := int32(binary.NativeEndian.Uint32(ev[4:]))
			if kind == evKey && code == keySpace && (value == 0 || value == 1) { // 2 is autorepeat
				k.spaces <- value == 1
			}
		}
	}
}

func (k *keyboards) close() {
	for _, f := range k.devices {
		f.Close()
	}
}
