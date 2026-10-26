package morse

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
)

// Save is the progress kept between runs, in the same file the old Python version wrote,
// so a save from it carries over.
type Save struct {
	Hi      int    `json:"hi"`
	Chapter int    `json:"chapter"`
	Lang    string `json:"lang"`
	// the telegraph line: what others see, the key to this game's number, and the number
	Codename   string `json:"codename,omitempty"`
	LineSecret string `json:"line_secret,omitempty"`
	LineNumber int    `json:"line_number,omitempty"`
}

// DefaultSavePath is where the terminal and desktop builds keep progress.
func DefaultSavePath() string {
	var dir string
	switch runtime.GOOS {
	case "windows":
		dir = os.Getenv("APPDATA")
	case "darwin":
		home, _ := os.UserHomeDir()
		dir = filepath.Join(home, "Library", "Application Support")
	default:
		dir = os.Getenv("XDG_DATA_HOME")
		if dir == "" {
			home, _ := os.UserHomeDir()
			dir = filepath.Join(home, ".local", "share")
		}
	}
	return filepath.Join(dir, "terminal-cartridges", "morse.json")
}

// LoadSave reads the save at path; a missing or broken file is a fresh start.
func LoadSave(path string) Save {
	var s Save
	if data, err := os.ReadFile(path); err == nil {
		_ = json.Unmarshal(data, &s)
	}
	return s
}

// WriteSave stores s at path; failing to save never stops the game.
func WriteSave(path string, s Save) {
	if path == "" {
		return
	}
	data, _ := json.Marshal(s)
	if os.MkdirAll(filepath.Dir(path), 0o755) == nil {
		_ = os.WriteFile(path, data, 0o644)
	}
}
