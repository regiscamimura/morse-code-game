# Morse Code — Station Seven, 1936

A terminal game that teaches Morse code through a spy story. You are the night
operator at a coastal wireless station in 1936, and every message you send or
receive moves the story forward. The game is available in English and
Brazilian Portuguese.

```
./morse.py
```

One Python file. It needs nothing beyond the standard library plus `aplay` for
sound, and it runs on Linux.

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
SENT N • ━   NEED A • ━   ← "Sent" in English, "Enviou" in Portuguese
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
./morse.py --volume .2         # quieter (0 = mute, 1 = loud, default .4)
./morse.py --letter-gap .4     # more time between letters, for beginners
./morse.py --dah-time .25      # a press must be longer to count as a dah
./morse.py --no-evdev          # ignore /dev/input, use the autorepeat fallback
./morse.py --selftest          # check the keying logic and the story text
```

`--selftest` prints `selftest ok` or stops at the first failed assert.

## How the space bar is read

Terminals report when a key is pressed but never when it's released. That
isn't enough to time a dah, so the game has two modes.

**Direct (default).** If you can read `/dev/input` (be in the `input` group),
the game reads the keyboard device itself and gets the real press and release
times. Key remappers such as keyd work too, because their virtual keyboard is
read as well.

```
$ id
... groups=...,992(input),...    ← you have it
```

Direct mode sees the keyboard system-wide, so pressing space in another window
also keys in the game while it runs.

**Autorepeat fallback.** Without device access, a hold is recognised from the
keyboard's autorepeat: one key event means a tap, and a burst of repeats means
a hold. The delay and rate are read from GNOME's settings, or you can set them:

```
./morse.py --repeat-delay .25 --repeat-interval .045
```

This mode is laggier: a dah only registers once the repeats start (about
0.3 s), and the letter gap can't go below about 0.45 s. If the game opens
device access but no space press ever arrives from it, it switches to this mode
on its own.

## Saves

Progress lives in `.save.json` next to the script:

```json
{"hi": 4210, "chapter": 5, "lang": "pt"}
```

`hi` is your best score, `chapter` is the furthest chapter reached (offered as
"continue" on the title screen) and `lang` is the last language used. Delete
the file to start over.

## Troubleshooting

| Symptom | Fix |
|---|---|
| No sound | Check that `aplay` exists (`alsa-utils`); the game stays silent without it |
| Crackling sound | The audio buffer is too small for your system: raise the `.02` in `Audio._stream` |
| Dahs come out as dits | Hold longer, or lower `--dah-time` |
| A letter splits in two | You paused mid-letter: raise `--letter-gap` |
| "MAKE THE TERMINAL AT LEAST 80x24" | Enlarge the window |
