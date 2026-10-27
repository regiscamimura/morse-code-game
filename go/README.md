# Morse Code — The Listener, 1912–1944

One game core drives three front ends:

| Front end | Run it | The telegraph key |
|---|---|---|
| Terminal | `go run ./cmd/morse-term` | space bar; real press/release via the Kitty protocol or `/dev/input`, else autorepeat |
| Desktop window | `go run ./cmd/morse` | space bar; keyboard only, like the terminal |
| Android | `android/build.sh`, then install the APK (see Android build) | touch and hold the red key |

The terminal and desktop builds save to `~/.local/share/terminal-cartridges/morse.json`, the
file the old Python version used, so progress carries over.

On a phone held upright, the game opens on its cartridge cover; a tap inserts it. The game
then sits at the top of the screen in a phone layout: the pictures keep the terminal's 80
columns, and the words between them are set 40 columns wide, twice as large. Below the game the
controls change with the screen:

| Screen | Below the game |
|---|---|
| sending, practice, a chapter's new letters | one red key: touch and hold it |
| receiving | the game's own keyboard: digits, letters, `⌫` |
| every screen | a row of buttons for what it offers: `BEGIN`, `PRACTICE`, `ENTER`, `HINT`, `REPEAT`, … |

Back is `ESC`: it leaves a mission or the practice.

## Layout

```
morse/       the game: state machine, keyer, signal timing, cell canvas, sound mixer
  content.json   everything that isn't logic: chapters, words, UI strings (en, pt), sprites, scenes, covers
terminal/    raw terminal input (Kitty keys, /dev/input), truecolour output
gui/         Ebitengine: draws the cell grid, the phone's cover and controls, audio
exchange/    the WebSocket client for the telegraph line (the server is ../exchange/)
cmd/morse, cmd/morse-term   desktop and terminal entry points
cmd/morse-icon              draws the Android launcher icon into android/app/src/main/res
mobile/      Android entry point, bound by ebitenmobile
android/     Gradle project that wraps the bound .aar in an APK
```

## Playing

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

- **Volumes:** the chapters are grouped into six stories: Titanic (4
  chapters), Lusitania (2), Room 40 (3), Hindenburg (1), Station X (3) and
  Coruja (4). A volume opens with the history you need ("1914. EUROPE GOES TO
  WAR...") and closes with what came of it ("THE LUSITANIA TOOK 1,198 LIVES.
  128 WERE AMERICAN."). Chapters are numbered within their volume:
  `VOLUME 2 · CHAPTER 1`.
- **Chapters:** each is a historical event. It opens on a cover: a pixel-art
  picture of the event (the Titanic going down by the bow, the Hindenburg in
  flames over the mast), its year, its name, and where and when it happens
  (`LONDON · THE FIRST WORLD WAR`). Only the flames, smoke,
  searchlights and sea move. Then about ten messages in four or five beats.
- **Beats:** each beat is a step of the story. The briefing says who is
  sending and why it matters. The message carries the plot. Winning says what
  your message made happen; losing says what happens without it, before you
  try again:

      SOS SOS          win:  SHE HAS STRUCK A BERG AND IS SINKING. YOU RUN TO THE BRIDGE IN ONE BOOT.
                       lose: YOU SHUT DOWN AND SLEEP, LIKE THE CALIFORNIAN. NO ONE GOES TO THE TITANIC.
- **Messages:** short sentences (`TEA AT TEN`, `SOS SOS`, `THE WAR IS OVER`),
  cipher groups (`TNEAT`), or what the beat before received, passed on. A beat
  may hold several; they follow one another without a screen between. The
  whole message is on screen at once, on one or two lines. Spaces are skipped
  for you: you key or type only the letters.
- **Send missions:** tap out the message before the timer runs out, while
  the threat on screen (a liner, a train, a submarine) moves closer. It
  crosses once per beat, each message taking it a share of the way.
- **Receive missions:** a signal plays and you type the letters you hear.
  A lamp flashes along and the dits and dahs scroll past on a tape. The aids
  come off one letter at a time: a letter stays on the tape for six chapters
  after you learn it and on the lamp for nine, then you only hear it. So in
  chapter 7 only `E T A N` show as `?` on the tape (`━ ━   ?   • ━ •`), and
  new letters always keep both aids. Speed and time per letter change
  gradually from the first chapter to the last (`pace` in `morse/content.json`).
- **Mistakes:** a wrong letter costs time and shows the right pattern:
  `SENT N • ━   NEED A • ━`.
- **Learning order:** new letters arrive in Koch order (`ETAN`, `IM`, `SO`…).
  Each must be keyed three times on the chapter's letter screen before the
  messages begin. Every third chapter brings no new letters: its messages lean
  on the two groups before it. Messages only use letters you've learned
  (`TestContent` checks every fixed one).

| Screen  | Key | Does |
|---------|-----|------|
| title   | `Enter` / `C` | new game / continue from your chapter |
|         | `F` or `P` | free practice, with a full Morse chart |
|         | `L` | language |
| mission | `Tab` | hint (send; costs points) / replay the signal (receive) |

Options: `--letter-gap .4` (more time between letters), `--dah-time .25` (a dah
must be held longer).

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

## Code

Front ends only call the game's `SpaceDown`, `SpaceUp`, `Key`, `Tick` and `Draw`:

```go
g := morse.NewGame(morse.DefaultConfig(), morse.NewMixer(.4), 0)
g.Key(morse.KeyEnter, 0.5) // language screen -> title
g.SpaceDown(1.0)           // key down...
g.SpaceUp(1.3)             // ...held 0.3 s: a dah
g.Tick(2.0)
fmt.Print(g.Draw(80, 24, 2.0).ANSI())
```

## Telegraph line

Two players key to each other. `[W] TELEGRAPH LINE` on the title (the `LINE` button on a phone)
asks once for a codename, then opens the switchboard:

```
┌ TELEGRAPH EXCHANGE ───────────────────┐
│          ▐ MORSE 123 ▌                │   your number, yours for good
│        CODENAME CORUJA                │
│  ON THE EXCHANGE · WAITING FOR CALLS  │
│     (rotary dial)    DIAL A NUMBER    │   type 456, ENTER: the dial turns and clicks
│                          456_         │
└───────────────────────────────────────┘
```

Dialling `456` rings that player's bell. When they answer, each side's key lamp and tone (lower,
560 Hz) reach the other end, with both tapes decoded underneath. ESC hangs up. Calls only ring
at the switchboard.

The exchange is a Cloudflare Worker in [`../exchange/`](../exchange/), live at
`wss://exchange.regiscamimura.com`. What crosses the line is each press and release with the
sender's clock, e.g. `{"type":"key","down":true,"at":12.34}`. The far end replays them a
quarter second late, so network jitter can't turn a dit into a dah. The full list of messages
is at the top of `exchange/src/index.ts`.

```
cd exchange && npm run dev                           # a local exchange on ws://localhost:8787
MORSE_EXCHANGE=ws://localhost:8787 go run ./cmd/morse-term
cd exchange && npm run smoke -- --url wss://exchange.regiscamimura.com   # one test call on the live one
cd exchange && npm run deploy                        # needs `npx wrangler login` once
```

Every smoke call against the live exchange hands out two new numbers for good.

## Tests

```
go test ./...                       # keyers, content checks, playthroughs, a call between two games
MORSE_EXCHANGE=ws://localhost:8787 go test ./exchange   # the client against a running exchange
SCREENSHOTS=/tmp/shots SCREENSHOT_SIZE=1080x2400 xvfb-run go test ./gui -run Screens
                                    # plays through the real phone GUI and saves PNGs
SCREENSHOTS=/tmp/shots SCREENSHOT_SIZE=1080x2400 xvfb-run go test ./gui -run LineScreens
                                    # a call on the telegraph line, through a scripted exchange
```

## Android build

`android/build.sh` needs the Android SDK with an NDK (`ANDROID_HOME`, default `~/Android/Sdk`) and
Gradle (`GRADLE`, else `gradle` on PATH, else `~/Android/gradle-8.11.1`). It runs `ebitenmobile bind` into `app/libs/morse.aar`
and then `gradle clean assembleDebug`. The APK holds only arm64 (every phone since about 2017), stripped and compressed: about 5 MB.

To install, either copy `app/build/outputs/apk/debug/app-debug.apk` to the phone and open it
(allow "install unknown apps" for the app you open it from), or with USB debugging on:

```
~/Android/Sdk/platform-tools/adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

The launcher icon is the cover's cartridge, drawn by `go run ./cmd/morse-icon android/app/src/main/res`.
