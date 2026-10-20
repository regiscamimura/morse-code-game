"""Shared engine for the terminal cartridges: input, sound and drawing.

Input: the space bar's real press and release come from the Windows console, the
Kitty keyboard protocol (Ghostty, Kitty, WezTerm, iTerm2...) or /dev/input on
Linux. Elsewhere only presses are known (UnixTerminal.reports_release is False).
Sound: PortAudio (sounddevice) where available, else aplay on Linux, else silence.
Drawing: a Canvas of coloured cells, a 5x7 pixel font and half-block sprites.
"""
import itertools
import json
import os
import random
import re
import select
import struct
import subprocess
import sys
import threading
import time
import unicodedata

WINDOWS = sys.platform == 'win32'
if WINDOWS:
    import ctypes
    from ctypes import wintypes
else:
    import fcntl
    import termios
    import tty

_FONT = """
A .###. #...# #...# ##### #...# #...# #...#
B ####. #...# #...# ####. #...# #...# ####.
C .###. #...# #.... #.... #.... #...# .###.
D ####. #...# #...# #...# #...# #...# ####.
E ##### #.... #.... ####. #.... #.... #####
F ##### #.... #.... ####. #.... #.... #....
G .###. #...# #.... #.### #...# #...# .####
H #...# #...# #...# ##### #...# #...# #...#
I .###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.
J ..### ...#. ...#. ...#. ...#. #..#. .##..
K #...# #..#. #.#.. ##... #.#.. #..#. #...#
L #.... #.... #.... #.... #.... #.... #####
M #...# ##.## #.#.# #.#.# #...# #...# #...#
N #...# #...# ##..# #.#.# #..## #...# #...#
O .###. #...# #...# #...# #...# #...# .###.
P ####. #...# #...# ####. #.... #.... #....
Q .###. #...# #...# #...# #.#.# #..#. .##.#
R ####. #...# #...# ####. #.#.. #..#. #...#
S .#### #.... #.... .###. ....# ....# ####.
T ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
U #...# #...# #...# #...# #...# #...# .###.
V #...# #...# #...# #...# #...# .#.#. ..#..
W #...# #...# #...# #.#.# #.#.# #.#.# .#.#.
X #...# #...# .#.#. ..#.. .#.#. #...# #...#
Y #...# #...# .#.#. ..#.. ..#.. ..#.. ..#..
Z ##### ....# ...#. ..#.. .#... #.... #####
0 .###. #...# #..## #.#.# ##..# #...# .###.
1 ..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.
2 .###. #...# ....# ...#. ..#.. .#... #####
3 ##### ...#. ..#.. ...#. ....# #...# .###.
4 ...#. ..##. .#.#. #..#. ##### ...#. ...#.
5 ##### #.... ####. ....# ....# #...# .###.
6 ..##. .#... #.... ####. #...# #...# .###.
7 ##### ....# ...#. ..#.. .#... .#... .#...
8 .###. #...# #...# .###. #...# #...# .###.
9 .###. #...# #...# .#### ....# ...#. .##..
! ..#.. ..#.. ..#.. ..#.. ..#.. ..... ..#..
? .###. #...# ....# ...#. ..#.. ..... ..#..
_ ..... ..... ..... ..... ..... ..... #####
"""
FONT = {line[0]: line[2:].split() for line in _FONT.strip().splitlines()}


# --------------------------------------------------------------------- input devices

KEY_SPACE, EV_KEY, INPUT_EVENT = 57, 1, struct.Struct('llHHi')


def open_keyboards():
    """Non-blocking fds for every input device that has a space key.

    Includes virtual keyboards (keyd, kanata...), which grab the physical ones
    and re-emit every key from a device with no /dev/input/by-path entry.
    """
    fds = []
    try:
        with open('/proc/bus/input/devices') as f:
            blocks = f.read().split('\n\n')
    except OSError:
        return fds
    for block in blocks:
        handlers = next((ln for ln in block.splitlines() if ln.startswith('H: Handlers=')), '')
        keys = next((ln for ln in block.splitlines() if ln.startswith('B: KEY=')), '')
        events = [h for h in handlers.split('=', 1)[-1].split() if h.startswith('event')]
        bitmap = keys.split('=', 1)[-1].split()
        if not events or not bitmap:
            continue
        # KEY= is a list of 64-bit hex words, most significant first
        if not int(''.join(w.zfill(16) for w in bitmap), 16) >> KEY_SPACE & 1:
            continue
        try:
            fds.append(os.open(f'/dev/input/{events[0]}', os.O_RDONLY | os.O_NONBLOCK))
        except OSError:
            pass
    return fds


def read_space_events(fd):
    """Yield True for space down, False for space up (autorepeat ignored)."""
    try:
        data = os.read(fd, INPUT_EVENT.size * 64)
    except OSError:
        return
    for off in range(0, len(data) - INPUT_EVENT.size + 1, INPUT_EVENT.size):
        _, _, kind, code, value = INPUT_EVENT.unpack_from(data, off)
        if kind == EV_KEY and code == KEY_SPACE and value in (0, 1):
            yield value == 1


# --------------------------------------------------------------------- audio

RATE, KEY_HZ = 11025, 700


def square(freq, dur, vol=.2):
    phase = 0.0
    for _ in range(int(dur * RATE)):
        phase = (phase + freq / RATE) % 1
        yield vol if phase < .5 else -vol


def slide(f0, f1, dur, vol=.2):
    n, phase = int(dur * RATE), 0.0
    for i in range(n):
        phase = (phase + (f0 + (f1 - f0) * i / n) / RATE) % 1
        yield vol if phase < .5 else -vol


def noise(dur, vol=.3, hold=12):
    """Sample-and-hold noise with a linear fade: the TIA rumble."""
    n, v = int(dur * RATE), 0.0
    for i in range(n):
        if i % hold == 0:
            v = random.uniform(-vol, vol)
        yield v * (1 - i / n)


def rest(dur):
    return itertools.repeat(0.0, int(dur * RATE))


def notes(freqs, dur=.1, vol=.15):
    return itertools.chain(*(square(f, dur, vol) if f else rest(dur) for f in freqs))


class Audio:
    """Two queued channels (fx, sig) plus the player's sidetone.

    Played through PortAudio (the sounddevice package) where it's available,
    else streamed to aplay on Linux, else the game is silent.
    """

    OUT_RATE = RATE * 4  # sound cards rarely accept 11025 Hz; each sample is played 4 times

    def __init__(self, volume):
        self.volume = volume
        self.lock = threading.Lock()
        self.queues = {'fx': [], 'sig': []}
        self.key_on, self.blip, self.phase = False, 0, 0.0
        self.proc = None
        self.stream = self._open_portaudio()
        if self.stream or WINDOWS:
            return
        try:
            self.proc = subprocess.Popen(
                ['aplay', '-q', '-t', 'raw', '-f', 'U8', '-r', str(RATE), '-c', '1',
                 '--buffer-time=30000', '--period-time=7500'],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                env={**os.environ, 'PIPEWIRE_LATENCY': f'128/{RATE}'})
        except OSError:
            return  # no aplay either: play silently
        threading.Thread(target=self._stream_to_aplay, daemon=True).start()

    def _open_portaudio(self):
        try:
            import sounddevice
        except (ImportError, OSError):  # not installed, or no PortAudio library on this system
            return None
        try:
            stream = sounddevice.RawOutputStream(samplerate=self.OUT_RATE, channels=1, dtype='uint8',
                                                 latency='low', callback=self._fill_portaudio)
            stream.start()
            return stream
        except sounddevice.PortAudioError:
            return None

    def _fill_portaudio(self, outdata, frames, time_info, status):
        samples = self._render_audio(-(-frames // 4))
        out = bytearray(len(samples) * 4)
        for i in range(4):
            out[i::4] = samples
        outdata[:] = bytes(out[:frames])

    def play(self, gen, channel='fx', cut=False):
        with self.lock:
            if cut:
                self.queues[channel].clear()
            self.queues[channel].append(gen)

    def stop_signal_playback(self):
        with self.lock:
            self.queues['sig'].clear()

    def _next_sample(self, queue):
        while queue:
            v = next(queue[0], None)
            if v is not None:
                return v
            queue.pop(0)
        return 0.0

    def _render_audio(self, sample_count):
        """The next `sample_count` 8-bit samples at RATE: both channels plus the sidetone."""
        buf = bytearray(sample_count)
        with self.lock:
            for i in range(sample_count):
                v = self._next_sample(self.queues['fx']) + self._next_sample(self.queues['sig'])
                if self.key_on or self.blip > 0:
                    self.blip -= 1
                    self.phase = (self.phase + KEY_HZ / RATE) % 1
                    v += .25 if self.phase < .5 else -.25
                buf[i] = max(0, min(255, int(128 + v * 100 * self.volume)))
        return buf

    def _stream_to_aplay(self):
        # A pipe holds ~6 s of 11 kHz U8 audio; writing freely queues the sidetone
        # behind all of it. Only top up when less than LEAD is waiting in the pipe.
        fd, lead = self.proc.stdin.fileno(), int(.02 * RATE)
        while True:
            try:
                queued = struct.unpack('i', fcntl.ioctl(fd, termios.FIONREAD, b'\0\0\0\0'))[0]
            except OSError:
                return
            if queued > lead:
                time.sleep(.003)
                continue
            try:
                os.write(fd, self._render_audio(64))
            except OSError:
                return

    def close(self):
        if self.stream:
            self.stream.close()
        if self.proc:
            self.proc.kill()


# --------------------------------------------------------------------- terminal

SETUP_SCREEN = '\x1b[?1049h\x1b[?25l\x1b[?7l'
RESTORE_SCREEN = '\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l'
# Kitty keyboard protocol flags: 1 disambiguate + 2 report press/release + 8 every key as a code
KITTY_PUSH, KITTY_POP = '\x1b[>11u', '\x1b[<u'
KITTY_KEY = re.compile(r'\x1b\[(\d+)(?::\d*)*(?:;(\d*)(?::(\d+))?)?(?:;[\d:]*)?u')
INPUT_TOKEN = re.compile(r'\x1b\[[0-9:;?<=>]*[ -/]*[@-~]|\x1bO.|\x1b|.', re.S)
KITTY_NAMED = {13: '\n', 9: '\t', 127: '\x7f', 8: '\x7f', 27: 'ESC'}
KITTY_PRESS, KITTY_REPEAT, KITTY_RELEASE, KITTY_CTRL = 1, 2, 3, 4
ARROW_KEY = re.compile(r'\x1b[\[O](?:1;\d*(?::(\d+))?)?([ABCD])')
ARROW_NAMES = {'A': 'UP', 'B': 'DOWN', 'C': 'RIGHT', 'D': 'LEFT'}


class UnixTerminal:
    """cbreak tty. Space releases come from the Kitty keyboard protocol when the
    terminal speaks it, else from /dev/input on Linux, else they're unknown.

    read() returns events: ('space', True/False) for a real press/release, or
    ('key', k) for anything typed (k == ' ' only when releases are unknown).
    """

    def __init__(self, use_devices):
        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        self.kitty = self._terminal_reports_releases()
        if self.kitty:
            self.write(KITTY_PUSH)
        on_linux = sys.platform.startswith('linux')
        self.devices = open_keyboards() if use_devices and on_linux and not self.kitty else []
        self.device_seen = False
        self.write(SETUP_SCREEN)

    @property
    def reports_release(self):
        return self.kitty or bool(self.devices)

    def write(self, text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def _terminal_reports_releases(self):
        # Ask for the Kitty keyboard flags, then for the device attributes every
        # terminal answers. A flags reply arriving first means the protocol works.
        self.write('\x1b[?u\x1b[c')
        reply, deadline = '', time.monotonic() + .5
        while not re.search(r'\x1b\[\?[\d;]*c', reply) and time.monotonic() < deadline:
            if select.select([self.fd], [], [], .05)[0]:
                reply += os.read(self.fd, 256).decode(errors='ignore')
        return bool(re.search(r'\x1b\[\?\d+u', reply))

    def read(self, timeout):
        events = []
        ready = select.select([self.fd] + self.devices, [], [], timeout)[0]
        for device in self.devices:
            if device in ready:
                for down in read_space_events(device):
                    self.device_seen = True
                    events.append(('space', down))
        if self.fd in ready:
            for token in INPUT_TOKEN.findall(os.read(self.fd, 256).decode(errors='ignore')):
                events += self._decode_token(token)
        return events

    def _decode_token(self, token):
        match = KITTY_KEY.fullmatch(token)
        if match:
            code, mods, kind = int(match[1]), int(match[2] or 1) - 1, int(match[3] or KITTY_PRESS)
            if code == 32:
                return [] if kind == KITTY_REPEAT else [('space', kind == KITTY_PRESS)]
            if kind == KITTY_RELEASE:
                return []
            if mods & KITTY_CTRL and code == ord('c'):
                raise KeyboardInterrupt
            if mods & KITTY_CTRL and ord('a') <= code <= ord('z'):
                return [('key', chr(code & 0x1F))]
            if code in KITTY_NAMED:
                return [('key', KITTY_NAMED[code])]
            return [('key', chr(code))] if 32 < code < 0xE000 else []  # skip modifier-only keys
        if token == '\x1b':
            return [('key', 'ESC')]
        arrow = ARROW_KEY.fullmatch(token)
        if arrow:
            return [] if arrow[1] and int(arrow[1]) == KITTY_RELEASE else [('key', ARROW_NAMES[arrow[2]])]
        if token.startswith('\x1b'):
            return []
        if token == ' ' and self.devices:
            if self.device_seen:
                return []  # the devices already reported this press
            # the terminal saw a space the devices didn't: they aren't this keyboard
            for device in self.devices:
                os.close(device)
            self.devices = []
        return [('key', token)]

    def restore(self):
        if self.kitty:
            self.write(KITTY_POP)
        self.write(RESTORE_SCREEN)
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
        for device in self.devices:
            os.close(device)


if WINDOWS:
    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [('bKeyDown', wintypes.BOOL), ('wRepeatCount', wintypes.WORD),
                    ('wVirtualKeyCode', wintypes.WORD), ('wVirtualScanCode', wintypes.WORD),
                    ('uChar', wintypes.WCHAR), ('dwControlKeyState', wintypes.DWORD)]

    class INPUT_RECORD(ctypes.Structure):
        # the real Event is a union; the key record is its largest member
        _fields_ = [('EventType', wintypes.WORD), ('Event', KEY_EVENT_RECORD)]


class WindowsConsole:
    """Windows console input records carry real key-down and key-up events.

    read() returns the same events as UnixTerminal.read().
    """

    reports_release = True
    KEY_EVENT, VK_SPACE, VK_ESCAPE, VK_C, CTRL_PRESSED = 1, 0x20, 0x1B, 0x43, 0x0C
    VK_ARROWS = {0x25: 'LEFT', 0x26: 'UP', 0x27: 'RIGHT', 0x28: 'DOWN'}
    INPUT_RAW = 0x0080  # extended flags only: no line input, echo, quick-edit or Ctrl+C handling
    OUTPUT_ANSI = 0x0001 | 0x0004  # processed output + virtual terminal sequences

    def __init__(self):
        self.kernel = ctypes.windll.kernel32
        self.kernel.GetStdHandle.restype = wintypes.HANDLE
        self.stdin, self.stdout = self.kernel.GetStdHandle(-10), self.kernel.GetStdHandle(-11)
        self.saved_in, self.saved_out = wintypes.DWORD(), wintypes.DWORD()
        self.kernel.GetConsoleMode(self.stdin, ctypes.byref(self.saved_in))
        self.kernel.GetConsoleMode(self.stdout, ctypes.byref(self.saved_out))
        self.kernel.SetConsoleMode(self.stdin, self.INPUT_RAW)
        self.kernel.SetConsoleMode(self.stdout, self.saved_out.value | self.OUTPUT_ANSI)
        self.kernel.SetConsoleOutputCP(65001)
        sys.stdout.reconfigure(encoding='utf-8')
        self.space_down = False
        self.write(SETUP_SCREEN)

    def write(self, text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def read(self, timeout):
        events = []
        if self.kernel.WaitForSingleObject(self.stdin, int(timeout * 1000)) != 0:
            return events
        count = wintypes.DWORD()
        self.kernel.GetNumberOfConsoleInputEvents(self.stdin, ctypes.byref(count))
        if not count.value:
            return events
        records = (INPUT_RECORD * count.value)()
        self.kernel.ReadConsoleInputW(self.stdin, records, count.value, ctypes.byref(count))
        for record in records[:count.value]:
            if record.EventType != self.KEY_EVENT:
                continue
            key = record.Event
            if key.wVirtualKeyCode == self.VK_SPACE:
                if bool(key.bKeyDown) != self.space_down:  # held keys repeat their key-down
                    self.space_down = bool(key.bKeyDown)
                    events.append(('space', self.space_down))
            elif not key.bKeyDown:
                continue
            elif key.wVirtualKeyCode == self.VK_ESCAPE:
                events.append(('key', 'ESC'))
            elif key.wVirtualKeyCode in self.VK_ARROWS:
                events.append(('key', self.VK_ARROWS[key.wVirtualKeyCode]))
            elif key.wVirtualKeyCode == self.VK_C and key.dwControlKeyState & self.CTRL_PRESSED:
                raise KeyboardInterrupt
            elif key.uChar not in ('', '\x00'):  # keys that type nothing carry NUL
                events.append(('key', {'\r': '\n', '\x08': '\x7f'}.get(key.uChar, key.uChar)))
        return events

    def restore(self):
        self.write(RESTORE_SCREEN)
        self.kernel.SetConsoleMode(self.stdin, self.saved_in.value)
        self.kernel.SetConsoleMode(self.stdout, self.saved_out.value)


# --------------------------------------------------------------------- drawing

class Canvas:
    """Full-terminal cell grid; drawing coordinates are an 80x24 area centred in it."""

    def __init__(self, width, height, fg, bg):
        self.W, self.H, self.fg, self.bg = width, height, fg, bg
        self.ox, self.oy = (width - 80) // 2, (height - 24) // 2
        self.cells = [[(' ', fg, bg)] * width for _ in range(height)]

    def _cell_index(self, x, y):
        X, Y = x + self.ox, y + self.oy
        return (X, Y) if 0 <= X < self.W and 0 <= Y < self.H else None

    def put(self, x, y, text, fg=None, bg=None):
        fg = fg or self.fg
        for i, ch in enumerate(text):
            p = self._cell_index(x + i, y)
            if p:
                X, Y = p
                self.cells[Y][X] = (ch, fg, bg or self.cells[Y][X][2])

    def background_at(self, x, y):
        p = self._cell_index(x, y)
        return self.cells[p[1]][p[0]][2] if p else self.bg

    def band(self, y0, y1, bg):
        for y in range(y0, y1):
            Y = y + self.oy
            if 0 <= Y < self.H:
                self.cells[Y] = [(' ', self.fg, bg)] * self.W

    def center(self, y, text, fg=None, bg=None):
        self.put(40 - len(text) // 2, y, text, fg, bg)

    def render(self):
        out, last = [], None
        for Y, row in enumerate(self.cells):
            out.append(f'\x1b[{Y + 1};1H')
            for ch, fg, bg in row:
                if (fg, bg) != last:
                    out.append('\x1b[38;2;%d;%d;%d;48;2;%d;%d;%dm' % (fg + bg))
                    last = (fg, bg)
                out.append(ch)
        return ''.join(out)


def big_text_width(text):
    return len(text) * 6 - 1


def big(c, x, y, text, color):
    """5x7 pixel font, 4 cells tall."""
    for n, ch in enumerate(text):
        glyph = FONT.get(ch) or FONT.get(unicodedata.normalize('NFD', ch)[0])
        if not glyph:
            continue
        rows = glyph + ['.....']
        for r in range(0, 8, 2):
            for i in range(5):
                a, b = rows[r][i] == '#', rows[r + 1][i] == '#'
                X, Y = x + n * 6 + i, y + r // 2
                if a:
                    c.put(X, Y, '▀', color, color if b else c.background_at(X, Y))
                elif b:
                    c.put(X, Y, '▄', color)


def big_center(c, y, text, color):
    big(c, 40 - big_text_width(text) // 2, y, text, color)


def draw_typed_lines(c, y, lines, elapsed, color):
    """Centre `lines` from row y, revealed 40 characters a second; True once all are shown."""
    budget = int(elapsed * 40)
    for i, line in enumerate(lines):
        c.center(y + i, line[:max(0, budget)].ljust(len(line)), color)
        budget -= len(line) + 8  # a short pause between lines
    return budget >= 0


def sprite(c, x, y, rows, palette, flicker=False, faded=None):
    """Pixel art packed two rows per cell with half blocks; '.' is transparent.

    flicker swaps the O and Y pixels (flames); faded draws every pixel in that colour.
    """
    if len(rows) % 2:
        rows = rows + ['.' * len(rows[0])]

    def blend_pixel_over(p, under):
        if p == '.':
            return under
        if faded:
            return faded
        if flicker and p in 'OY':
            p = 'Y' if p == 'O' else 'O'
        return palette[p]

    for r in range(0, len(rows), 2):
        for i, (a, b) in enumerate(zip(rows[r], rows[r + 1])):
            if a == '.' and b == '.':
                continue
            under = c.background_at(x + i, y + r // 2)
            c.put(x + i, y + r // 2, '▀', blend_pixel_over(a, under), blend_pixel_over(b, under))


# --------------------------------------------------------------------- saves

def user_data_dir():
    """Where per-user files go: a one-file build unpacks itself into a temporary folder."""
    if WINDOWS:
        return os.environ.get('APPDATA') or os.path.expanduser('~')
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Application Support')
    return os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')


def save_file_path(game):
    return os.path.join(user_data_dir(), 'terminal-cartridges', f'{game}.json')


def load_save(path, *older_paths):
    """The saved dict at `path`, else at the first of `older_paths` that has one, else {}."""
    for candidate in (path, *older_paths):
        try:
            with open(candidate) as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def write_save(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f)
    except OSError:
        pass


def read_system_key_repeat():
    """(delay, interval) in seconds from macOS or GNOME settings, else common defaults."""
    def run(*command):
        return subprocess.run(command, capture_output=True, text=True, timeout=1).stdout

    try:
        if sys.platform == 'darwin':  # macOS stores both in units of 15 ms
            return (int(run('defaults', 'read', '-g', 'InitialKeyRepeat')) * .015,
                    int(run('defaults', 'read', '-g', 'KeyRepeat')) * .015)
        gnome = 'org.gnome.desktop.peripherals.keyboard'
        return (int(run('gsettings', 'get', gnome, 'delay').split()[-1]) / 1000,
                int(run('gsettings', 'get', gnome, 'repeat-interval').split()[-1]) / 1000)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return .5, .033


# --------------------------------------------------------------------- loop

class Eject(Exception):
    """Raised by a game to leave it: back to the cartridge picker, or quit when run alone."""


def open_terminal(args):
    return WindowsConsole() if WINDOWS else UnixTerminal(use_devices=not args.no_evdev)


def add_arguments(parser):
    parser.add_argument('--volume', type=float, default=.4, help='0 (mute) to 1')
    parser.add_argument('--no-evdev', action='store_true',
                        help="Linux: don't read /dev/input when the terminal can't report releases")
    parser.add_argument('--selftest', action='store_true')


def run(app, terminal):
    """Feed terminal input to `app` and draw it ~30 times a second until it ejects.

    `app` provides: releases, use_release_keys(bool), space_down(now), space_up(now),
    on_key_press(k, now), tick(now) and draw(now) -> Canvas.
    """
    try:
        last = ''
        while True:
            events = terminal.read(1 / 30)
            now = time.monotonic()
            if terminal.reports_release != app.releases:  # /dev/input turned out not to be ours
                app.use_release_keys(terminal.reports_release)
            for kind, value in events:
                if kind == 'space':
                    app.space_down(now) if value else app.space_up(now)
                else:
                    app.on_key_press(value, now)
            app.tick(now)
            frame = app.draw(now).render()
            if frame != last:
                terminal.write(frame)
                last = frame
    except (KeyboardInterrupt, SystemExit, Eject):
        pass
    finally:
        terminal.restore()


def selftest():
    kitty = UnixTerminal.__new__(UnixTerminal)
    kitty.devices = []
    assert kitty._decode_token('\x1b[32u') == [('space', True)]
    assert kitty._decode_token('\x1b[32;1:3u') == [('space', False)]
    assert kitty._decode_token('\x1b[32;1:2u') == []
    assert kitty._decode_token('\x1b[97;2u') == [('key', 'a')]
    assert kitty._decode_token('\x1b[103;5u') == [('key', '\x07')]
    assert kitty._decode_token('\x1b[13u') == [('key', '\n')]
    assert kitty._decode_token('\x1b[57441;2u') == []
    assert kitty._decode_token('\x1b[D') == [('key', 'LEFT')]
    assert kitty._decode_token('\x1b[1;1:3C') == []
    assert INPUT_TOKEN.findall('a\x1b[32;1:3ub') == ['a', '\x1b[32;1:3u', 'b']
    assert all(len(g) == 7 and all(len(r) == 5 for r in g) for g in FONT.values())
