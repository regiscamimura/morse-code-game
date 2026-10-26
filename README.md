# Terminal Cartridges

Story games that each teach a skill. You start by inserting a cartridge, Atari 2600 style:

| Cartridge | You learn | The story |
|---|---|---|
| **MORSE CODE** | Morse code, sending and receiving | 1912–1944. One wireless operator's life: the Titanic's SOS, Room 40, the Hindenburg, Bletchley's listeners, a last transmission in occupied France. English or Brazilian Portuguese. Written in Go for the terminal, a desktop window and Android: see [`go/`](go/README.md). |
| **VIM** | vim, from `hjkl` to `.` and `:wq` | December 31, 1999. A lab AI is rewriting the reactor's code, and the only working terminal runs vim. |

## Get it

Download the file for your system from the
[Releases page](https://github.com/regiscamimura/morse-code-game/releases) and
run it in a terminal. Nothing else to install.

| System  | File                            | Run it |
|---------|---------------------------------|--------|
| Windows | `cartridges-windows-x64.exe`    | double-click, or `.\cartridges-windows-x64.exe` |
| macOS   | `cartridges-macos-arm64`        | `chmod +x cartridges-macos-arm64 && ./cartridges-macos-arm64` |
| Linux   | `cartridges-linux-x64`          | `chmod +x cartridges-linux-x64 && ./cartridges-linux-x64` |

macOS blocks downloaded programs that aren't signed. Clear the flag once:

```
xattr -d com.apple.quarantine cartridges-macos-arm64
```

Or run from source with Python 3.10+ (`sounddevice` is optional, for sound
outside Linux):

```
pip install sounddevice
python play.py          # the cartridge picker
python vim.py           # straight into the game
```

The terminal needs to be at least 80×24. On the picker `Enter` inserts the
cartridge and `q` quits. Leaving a game's title screen
(`Esc` or `q`) ejects back to the picker.

## Vim — Sublevel 7, 1999

Each mission opens a file in a small built-in vim. You either move the cursor
onto the blinking target or edit the file until it matches the fix, before the
reactor core overheats. Your keystrokes are counted against a par, VimGolf style,
and finishing under par earns a bonus.

```
▶ Delete the oracle.override line.
→ line 2 should go                     ← what still differs from the fix
▌ 2 oracle.override = true             ← red bar: this line isn't right yet
 NORMAL  startup.py [+]        keys 2  par 3    2:1
```

Eight chapters, each adding commands:

| Chapter | Commands |
|---|---|
| BOOT | `h` `j` `k` `l` |
| WORDS | `w` `b` `e` `0` `$` |
| JUMPS | `gg` `G` `:27` `27G` |
| DELETE | `x` `dd` counts like `3dd` `2j` |
| INSERT | `i` `a` `A` `o` `Esc` |
| CHANGE | `r` `cw` `dw` `D` |
| SEARCH | `/word` `n` `N` `u` |
| WRITE | `:w` `yy` `p` `.` `:wq` |

The built-in vim also understands operators with any motion (`d3w`, `c$`, `ye`),
`X` `s` `C` `I` `O` `P`, and `:q`/`:q!`. Arrow keys are switched off on purpose.
Inside a mission `Esc` belongs to vim, so leave with `:q!`. The title screen also
has a **playground** (`P`) with no timer.

## Saves

Progress is kept per user, one file per cartridge:

| System  | Folder |
|---------|--------|
| Linux   | `~/.local/share/terminal-cartridges/` |
| macOS   | `~/Library/Application Support/terminal-cartridges/` |
| Windows | `%APPDATA%\terminal-cartridges\` |

```
vim.json     {"hi": 1830, "chapter": 3}
morse.json   {"hi": 4210, "chapter": 5, "lang": "pt"}    ← the Go terminal and desktop builds
```

`hi` is your best score and `chapter` the furthest chapter reached (offered as
"continue"). Delete a file to start that game over.

## Building the executables

`.github/workflows/build.yml` builds all three on GitHub's Linux, macOS and
Windows machines (PyInstaller can't build for another OS). It runs
`python play.py --selftest` first.

- **Actions tab → build → Run workflow:** builds and attaches the files to the run.
- **Push a tag** such as `v1.1`: builds and publishes them as a release.

```
git tag v1.1 && git push origin v1.1
```

To build one locally:

```
pip install pyinstaller sounddevice
pyinstaller --onefile --name cartridges play.py     # → dist/cartridges
```

## Project layout

| File | What's in it |
|---|---|
| `play.py` | the cartridge picker; the bundle's entry point |
| `engine.py` | terminal input per OS, sound, drawing, saves, the main loop |
| `go/` | the Morse game, in Go |
| `exchange/` | the Morse game's telephone exchange: a Cloudflare Worker that connects two players |
| `vim.py` | the vim game: the built-in editor, missions, screens |

`--selftest` on any of them checks the keyers, the input decoder and the story
text. For the vim game it also replays every mission's solution through the
editor and checks that it actually solves the mission.

## Troubleshooting

| Symptom | Fix |
|---|---|
| No sound on Linux | Install PortAudio (`libportaudio2`) or `alsa-utils` (`aplay`) |
| `Esc` is slow in the vim game inside tmux | tmux waits to see if Esc starts a sequence: `set -sg escape-time 10` in `~/.tmux.conf` |
| "MAKE THE TERMINAL AT LEAST 80x24" | Enlarge the window |
