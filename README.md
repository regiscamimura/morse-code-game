# Terminal Cartridges

Two story games for the terminal. Each one teaches a skill. You start by picking a
cartridge, Atari 2600 style:

| Cartridge | You learn | The story |
|---|---|---|
| **MORSE CODE** | Morse code, sending and receiving | 1936. Night operator at a coastal wireless station, chasing a ring of spies. English or Brazilian Portuguese. |
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
python morse.py         # straight into one game
python vim.py
```

The terminal needs to be at least 80×24. On the picker, `←` `→` (or `h` `l`)
choose, `Enter` inserts the cartridge, `q` quits. Leaving a game's title screen
(`Esc` or `q`) ejects back to the picker.

## Morse Code — Station Seven, 1936

The space bar is your telegraph key.

| You do                    | You send |
|---------------------------|----------|
| tap space                 | dit `•`  |
| hold space (≥ 0.2 s)      | dah `━`  |
| let go for 0.3 s          | the letter is finished |

So **A** (`• ━`) is: tap, hold, let go.

```
KEY  • ━            = A   ▮▮▮▯▯
 │    │               │     └ fills while you're silent; full = letter locked in
 │    │               └ the letter your dits and dahs spell so far
 │    └ what you've keyed so far
 └ lights up while the key is down
```

- **Send missions:** tap out the code word before the timer runs out, while
  the threat on screen (a fuse, an airship, a submarine) moves closer.
- **Receive missions:** a signal plays and you type the letters you hear.
  Until chapter 4 a lamp flashes along and the dits and dahs scroll past.
  From chapter 5 you only hear it.
- **Mistakes:** a wrong letter costs time and shows the right pattern:
  `SENT N • ━   NEED A • ━`.
- **Learning order:** new letters arrive in Koch order (`ETAN`, `IM`, `SO`…),
  each with a practice screen. Code words only use letters you've learned.

| Screen  | Key | Does |
|---------|-----|------|
| title   | `Enter` / `C` | new game / continue from your chapter |
|         | `F` or `P` | free practice, with a full Morse chart |
|         | `L` | language |
| mission | `Tab` | hint (send; costs points) / replay the signal (receive) |

Options: `--letter-gap .4` (more time between letters), `--dah-time .25` (a dah
must be held longer).

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

## Which terminals work best

The Morse game needs to know when you *release* the space bar, and most
terminals only report presses. The game uses the best source it can find:

| Where you run it | Key releases come from | Feel |
|---|---|---|
| Windows (any console) | the Windows console's own key events | exact |
| Ghostty, Kitty, WezTerm, foot, iTerm2 3.5+ | the Kitty keyboard protocol | exact |
| Linux, inside tmux or any terminal | `/dev/input` (needs the `input` group) | exact |
| macOS Terminal.app, others | guessed from keyboard autorepeat | laggier |

With autorepeat, a dah only registers once the key starts repeating (about
0.3 s). The repeat timing is read from GNOME or macOS settings; override it with
`--repeat-delay` and `--repeat-interval`. On Linux `/dev/input` sees the keyboard
system-wide, and `--no-evdev` turns it off.

## Saves

Progress is kept per user, one file per cartridge:

| System  | Folder |
|---------|--------|
| Linux   | `~/.local/share/terminal-cartridges/` |
| macOS   | `~/Library/Application Support/terminal-cartridges/` |
| Windows | `%APPDATA%\terminal-cartridges\` |

```
morse.json   {"hi": 4210, "chapter": 5, "lang": "pt"}
vim.json     {"hi": 1830, "chapter": 3}
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
| `engine.py` | shared: terminal input per OS, sound, drawing, saves, the main loop |
| `morse.py` | the Morse game: keyers, story (EN and PT-BR), screens |
| `vim.py` | the vim game: the built-in editor, missions, screens |

`--selftest` on any of them checks the keyers, the input decoder and the story
text. For the vim game it also replays every mission's solution through the
editor and checks that it actually solves the mission.

## Troubleshooting

| Symptom | Fix |
|---|---|
| No sound on Linux | Install PortAudio (`libportaudio2`) or `alsa-utils` (`aplay`) |
| `Esc` is slow in the vim game inside tmux | tmux waits to see if Esc starts a sequence: `set -sg escape-time 10` in `~/.tmux.conf` |
| Dahs come out as dits | Hold longer, or lower `--dah-time` |
| A Morse letter splits in two | You paused mid-letter: raise `--letter-gap` |
| "MAKE THE TERMINAL AT LEAST 80x24" | Enlarge the window |
