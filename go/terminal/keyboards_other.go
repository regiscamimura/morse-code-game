//go:build !linux

package terminal

// keyboards: /dev/input exists only on Linux; elsewhere releases come from Kitty or not at all.
type keyboards struct{ spaces chan bool }

func openKeyboards() *keyboards { return nil }

func (k *keyboards) close() {}
