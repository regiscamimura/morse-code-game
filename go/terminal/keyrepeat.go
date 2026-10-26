package terminal

import (
	"context"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// SystemKeyRepeat is the keyboard's autorepeat (delay, interval) in seconds from macOS or
// GNOME settings, else common defaults. Without releases, holds are recognised from it.
func SystemKeyRepeat() (delay, interval float64) {
	run := func(command ...string) string {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		out, _ := exec.CommandContext(ctx, command[0], command[1:]...).Output()
		return strings.TrimSpace(string(out))
	}
	lastNumber := func(s string) (float64, bool) {
		fields := strings.Fields(s)
		if len(fields) == 0 {
			return 0, false
		}
		n, err := strconv.ParseFloat(fields[len(fields)-1], 64)
		return n, err == nil
	}
	if runtime.GOOS == "darwin" { // macOS stores both in units of 15 ms
		d, ok1 := lastNumber(run("defaults", "read", "-g", "InitialKeyRepeat"))
		i, ok2 := lastNumber(run("defaults", "read", "-g", "KeyRepeat"))
		if ok1 && ok2 {
			return d * .015, i * .015
		}
		return .5, .033
	}
	const gnome = "org.gnome.desktop.peripherals.keyboard"
	d, ok1 := lastNumber(run("gsettings", "get", gnome, "delay"))
	i, ok2 := lastNumber(run("gsettings", "get", gnome, "repeat-interval"))
	if ok1 && ok2 {
		return d / 1000, i / 1000
	}
	return .5, .033
}
