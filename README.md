# Morse Code — Station Seven, 1936

A terminal game that teaches Morse code through a spy story. You are the night
operator at a coastal wireless station in 1936, and every message you send or
receive moves the story forward. Available in English and Brazilian Portuguese.

## Get it

Download the file for your system from the
[Releases page](https://github.com/regiscamimura/morse-code-game/releases) and
run it in a terminal. Nothing else to install.

| System  | File                       | Run it                                       |
|---------|----------------------------|----------------------------------------------|
| Windows | `morse-windows-x64.exe`    | double-click, or `.\morse-windows-x64.exe`   |
| macOS   | `morse-macos-arm64`        | `chmod +x morse-macos-arm64 && ./morse-macos-arm64` |
| Linux   | `morse-linux-x64`          | `chmod +x morse-linux-x64 && ./morse-linux-x64` |

macOS blocks downloaded programs that aren't signed. Clear the flag once:

```
xattr -d com.apple.quarantine morse-macos-arm64
```

Or run it from source with Python 3.10+ (`sounddevice` is optional, for sound
outside Linux):

```
pip install sounddevice
python morse.py
```

The terminal needs to be at least 80×24.

## How you play

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

Each chapter has three missions of two kinds:

- **Send:** a code word is shown and you tap it out before the timer runs out.
  The threat on screen (a fuse, an airship, a submarine) moves closer as
  time passes.
- **Receive:** a signal plays and you type the letters you hear on the
  keyboard. Until chapter 4 a lamp flashes along with the sound and the dits
  and dahs scroll past as text. From chapter 5 you only hear it.

A wrong letter costs time and shows the correct pattern, so the mistake turns
into a lesson:

```
SENT N • ━   NEED A • ━
```

Each chapter teaches new letters in Koch order (`ETAN`, then `IM`, `SO`, `RK`
and so on) and opens with a practice screen where you hear and try them. Code
words only use letters you've already learned.

## Keys

| Screen    | Key                     | Does                                  |
|-----------|-------------------------|---------------------------------------|
| everywhere| `Esc`                   | back to the title screen (quits from there) |
| title     | `Enter` / `C`           | new game / continue from your chapter |
|           | `F` or `P`              | free practice, with a full Morse chart |
|           | `L`                     | change language                       |
| mission   | `Tab`                   | hint (send; costs points) / replay the signal (receive) |
| stories   | `Enter`                 | skip the typewriter text              |

## Options

```
morse --volume .2         # quieter (0 = mute, 1 = loud, default .4)
morse --letter-gap .4     # more time between letters, for beginners
morse --dah-time .25      # a press must be longer to count as a dah
morse --selftest          # check the keying logic and the story text
```

## Which terminals work best

Timing a dah needs to know when you *release* the space bar, and most terminals
only report presses. The game uses the best source it finds:

| Where you run it | Key releases come from | Feel |
|---|---|---|
| Windows (any console) | the Windows console's own key events | exact |
| Ghostty, Kitty, WezTerm, foot, iTerm2 3.5+ | the Kitty keyboard protocol | exact |
| Linux, inside tmux or any terminal | `/dev/input` (needs the `input` group) | exact |
| macOS Terminal.app, others | guessed from keyboard autorepeat | laggier |

In the autorepeat case a dah only registers once the key starts repeating
(about 0.3 s), and the gap between letters can't go below about 0.45 s. The
repeat timing is read from GNOME or macOS settings; override it with
`--repeat-delay` and `--repeat-interval`.

On Linux, `/dev/input` sees the keyboard system-wide: while the game runs,
pressing space in another window also keys in the game. `--no-evdev` turns
that source off. Key remappers such as keyd work, because their virtual
keyboard is read too.

## Saves

Progress is kept per user:

| System  | File |
|---------|------|
| Linux   | `~/.local/share/morse-code/save.json` |
| macOS   | `~/Library/Application Support/morse-code/save.json` |
| Windows | `%APPDATA%\morse-code\save.json` |

```json
{"hi": 4210, "chapter": 5, "lang": "pt"}
```

`hi` is your best score, `chapter` is the furthest chapter reached (offered as
"continue" on the title screen) and `lang` is the last language used. Delete
the file to start over.

## Building the executables

`.github/workflows/build.yml` builds all three with PyInstaller on GitHub's
Linux, macOS and Windows machines (PyInstaller can't build for another OS).

- **Actions tab → build → Run workflow:** builds and attaches the files to
  the run.
- **Push a tag** such as `v1.0`: builds and publishes them as a release.

```
git tag v1.0 && git push origin v1.0
```

To build one locally for your own system:

```
pip install pyinstaller sounddevice
pyinstaller --onefile --name morse morse.py     # → dist/morse
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| No sound on Linux | Install PortAudio (`libportaudio2`) or `alsa-utils` (`aplay`); without either the game is silent |
| Crackling sound | The audio buffer is too small for your system: raise the `.02` in `Audio._stream_to_aplay` |
| Dahs come out as dits | Hold longer, or lower `--dah-time` |
| A letter splits in two | You paused mid-letter: raise `--letter-gap` |
| "MAKE THE TERMINAL AT LEAST 80x24" | Enlarge the window |
