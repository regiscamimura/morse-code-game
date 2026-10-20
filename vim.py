#!/usr/bin/env python3
"""SUBLEVEL 7 - Kestrel Labs, 1999. A vim story for the terminal.

Each mission opens a file in a small built-in vim. Move the cursor to the target,
or edit the file until it matches the fix, before the reactor core overheats.
Keystrokes are counted against a par, VimGolf style.
"""
import argparse
import itertools
import os
import random
import re
import string
import time

from engine import (Audio, Canvas, Eject, add_arguments, big_center, big_text_width, load_save, noise, notes,
                    open_terminal, rest, run, save_file_path, square, draw_typed_lines, write_save)
import engine

# Monokai-style neon on near-black
BG, PANEL, LINE_HL = (22, 22, 28), (40, 40, 52), (34, 34, 44)
FG, MUTED, GUTTER = (232, 232, 222), (117, 113, 94), (88, 90, 106)
PINK, GREEN, YELLOW = (249, 38, 114), (166, 226, 46), (230, 219, 116)
ORANGE, PURPLE, CYAN = (253, 151, 31), (174, 129, 255), (102, 217, 239)
BLUE, RED, ALARM, CURSOR = (82, 139, 255), (255, 85, 85), (70, 14, 20), (240, 240, 240)

# --------------------------------------------------------------------- editor

WORD_CHARS = set(string.ascii_letters + string.digits + '_')
COUNT_PREFIX = re.compile(r'([1-9]\d*)?(.*)', re.S)
INSERT_COMMANDS = ('i', 'a', 'I', 'A', 'o', 'O')


def char_class(ch):
    """0 blank (newlines too), 1 keyword character, 2 punctuation: what w, b and e step over."""
    if ch in ' \t\n':
        return 0
    return 1 if ch in WORD_CHARS else 2


def next_word_start(text, i):
    end = len(text)
    if i >= end:
        return max(0, end - 1)
    kind = char_class(text[i])
    if kind:
        while i < end and char_class(text[i]) == kind:
            i += 1
    while i < end and text[i] in ' \t\n':
        if text[i] == '\n' and i + 1 < end and text[i + 1] == '\n':
            return i + 1  # an empty line counts as a word
        i += 1
    return min(i, max(0, end - 1))


def word_end(text, i):
    end = len(text)
    i += 1
    while i < end and text[i] in ' \t\n':
        i += 1
    if i >= end:
        return max(0, end - 1)
    kind = char_class(text[i])
    while i + 1 < end and char_class(text[i + 1]) == kind:
        i += 1
    return i


def prev_word_start(text, i):
    i -= 1
    while i > 0 and text[i] in ' \t\n':
        if text[i] == '\n' and text[i - 1] == '\n':
            return i  # an empty line counts as a word
        i -= 1
    if i <= 0:
        return 0
    kind = char_class(text[i])
    while i > 0 and char_class(text[i - 1]) == kind:
        i -= 1
    return i


def leading_spaces(line):
    return line[:len(line) - len(line.lstrip(' '))]


class Editor:
    """A small vim over a list of lines, in normal, insert, command-line (:) and search (/) modes.

    send_key(key) applies one key ('ESC' for Escape, '\\n' for Enter, '\\x7f' for Backspace).
    Normal mode knows counts; h j k l w b e 0 ^ $ gg G n N; the operators d c y with any of
    those motions, plus dd cc yy; x X D C s r i a I A o O p P u and the . repeat.
    Command line: :w :q :q! :wq :x and :N to go to line N. New lines keep the indent.
    """

    def __init__(self, text, cursor=(0, 0), filename='untitled.txt'):
        self.lines = text.split('\n')
        self.row, self.col = cursor
        self.want_col = self.col
        self.filename = filename
        self.mode = 'normal'
        self.pending = ''            # normal-mode keys typed so far, shown like vim's showcmd
        self.cmdline = ''            # what follows the ':' or '/'
        self.message, self.message_is_error = '', False
        self.saved_text = text
        self.undo_stack = []
        self.register = ('', False)  # yanked or deleted text, and whether it is whole lines
        self.search = ''
        self.last_change = []        # keys of the last change, replayed by '.'
        self.change_keys = None      # keys of a change still being typed in insert mode
        self.command_keys, self.text_before = [], text
        self.replaying = False
        self.quit = None             # 'clean', 'write' or 'force' after :q, :wq, :q!
        self.bell = False            # the last key was refused, where vim would beep

    @property
    def text(self):
        return '\n'.join(self.lines)

    @property
    def has_unsaved_changes(self):
        return self.text != self.saved_text

    def offset_of(self, row, col):
        return sum(len(line) + 1 for line in self.lines[:row]) + col

    def position_of(self, offset):
        for row, line in enumerate(self.lines):
            if offset <= len(line):
                return row, offset
            offset -= len(line) + 1
        return len(self.lines) - 1, len(self.lines[-1])

    def first_nonblank(self, row):
        return len(leading_spaces(self.lines[row]))

    def snapshot(self):
        self.undo_stack.append((list(self.lines), self.row, self.col))

    def show_error(self, message):
        self.message, self.message_is_error, self.bell = message, True, True

    def show_message(self, message):
        self.message, self.message_is_error = message, False

    # ---- keys

    def send_key(self, key):
        self.bell = False
        if self.mode == 'insert':
            self.insert_key(key)
        elif self.mode in ('command', 'search'):
            self.cmdline_key(key)
        else:
            self.normal_key(key)
        self.row = max(0, min(self.row, len(self.lines) - 1))
        limit = len(self.lines[self.row]) - (0 if self.mode == 'insert' else 1)
        self.col = max(0, min(self.col, limit))

    def normal_key(self, key):
        if key == 'ESC':
            self.pending = ''
            return
        if not self.pending:
            self.command_keys, self.text_before = [], self.text
            self.message = ''
        self.pending += key
        self.command_keys.append(key)
        outcome = self.run_pending()
        if outcome == 'more':
            return
        self.pending = ''
        if outcome == 'bell':
            self.bell = True
        elif self.replaying or outcome == 'no-repeat':
            pass
        elif self.mode == 'insert':
            self.change_keys = list(self.command_keys)
        elif self.text != self.text_before:
            self.last_change = list(self.command_keys)

    def insert_key(self, key):
        recording = self.change_keys is not None and not self.replaying
        if recording:
            self.change_keys.append(key)
        line = self.lines[self.row]
        if key == 'ESC':
            self.mode = 'normal'
            self.col -= 1
            if recording:
                self.last_change = self.change_keys
            self.change_keys = None
        elif key == '\n':
            indent = leading_spaces(line)
            self.lines[self.row:self.row + 1] = [line[:self.col], indent + line[self.col:].lstrip(' ')]
            self.row, self.col = self.row + 1, len(indent)
        elif key == '\x7f':
            if self.col > 0:
                self.lines[self.row] = line[:self.col - 1] + line[self.col:]
                self.col -= 1
            elif self.row > 0:
                above = self.lines[self.row - 1]
                self.lines[self.row - 1:self.row + 1] = [above + line]
                self.row, self.col = self.row - 1, len(above)
        elif key == '\t':
            self.lines[self.row] = line[:self.col] + '    ' + line[self.col:]
            self.col += 4
        elif len(key) == 1 and key >= ' ':
            self.lines[self.row] = line[:self.col] + key + line[self.col:]
            self.col += 1

    def cmdline_key(self, key):
        if key == 'ESC' or (key == '\x7f' and not self.cmdline):
            self.mode, self.cmdline = 'normal', ''
        elif key == '\x7f':
            self.cmdline = self.cmdline[:-1]
        elif key == '\n':
            searching, typed = self.mode == 'search', self.cmdline.strip()
            self.mode, self.cmdline = 'normal', ''
            self.run_search(typed) if searching else self.run_ex_command(typed)
        elif len(key) == 1 and key >= ' ':
            self.cmdline += key

    # ---- normal mode

    def run_pending(self):
        """Run the complete command in self.pending: 'more', 'done', 'no-repeat' or 'bell'."""
        count_text, keys = COUNT_PREFIX.fullmatch(self.pending).groups()
        count = int(count_text) if count_text else None
        times = count or 1
        if not keys:
            return 'more'
        if keys[0] in 'dcy':
            return self.run_operator(keys[0], keys[1:], times)
        if keys in ('g', 'r'):
            return 'more'
        target = self.motion(keys, times, count)
        if target:
            self.row, self.col, _ = target
            self.want_col = self.col
            return 'done'
        return self.run_command(keys, times)

    def motion(self, keys, times, count=None, operator=False):
        """(row, col, kind) where `keys` moves the cursor, or None if they aren't a motion.

        kind is 'exclusive', 'inclusive' (the target character is part of an operator's
        range) or 'linewise' (an operator takes whole lines).
        """
        row, col, last = self.row, self.col, len(self.lines) - 1
        line = self.lines[row]
        if keys == 'h':
            return row, max(0, col - times), 'exclusive'
        if keys == 'l':
            limit = len(line) if operator else max(0, len(line) - 1)
            return row, min(limit, col + times), 'exclusive'
        if keys in ('j', 'k'):
            target = min(last, row + times) if keys == 'j' else max(0, row - times)
            return target, self.want_col, 'linewise'
        if keys == '0':
            return row, 0, 'exclusive'
        if keys == '^':
            return row, self.first_nonblank(row), 'exclusive'
        if keys == '$':
            target = min(last, row + times - 1)
            return target, max(0, len(self.lines[target]) - 1), 'inclusive'
        if keys in ('gg', 'G'):
            target = count - 1 if count else (0 if keys == 'gg' else last)
            target = max(0, min(last, target))
            return target, self.first_nonblank(target), 'linewise'
        if keys in ('w', 'b', 'e'):
            text, offset = self.text, self.offset_of(row, col)
            step = {'w': next_word_start, 'b': prev_word_start, 'e': word_end}[keys]
            for _ in range(times):
                offset = step(text, offset)
            target_row, target_col = self.position_of(offset)
            if keys == 'w' and operator and target_row > row:
                return row, len(line), 'exclusive'  # dw on a line's last word stops at the line end
            return target_row, target_col, 'inclusive' if keys == 'e' else 'exclusive'
        if keys in ('n', 'N'):
            found = self.find(self.search, forward=keys == 'n')
            return (*found, 'exclusive') if found else (row, col, 'exclusive')
        return None

    def run_operator(self, op, keys, times):
        if not keys:
            return 'more'
        if keys == op:  # dd, cc, yy
            return self.operate_on_lines(op, self.row, min(self.row + times - 1, len(self.lines) - 1))
        count_text, motion = COUNT_PREFIX.fullmatch(keys).groups()
        if not motion or motion == 'g':
            return 'more'
        times *= int(count_text) if count_text else 1
        if op == 'c' and motion == 'w' and self.lines[self.row][self.col:self.col + 1].strip():
            motion = 'e'  # cw on a word changes to its end, like ce
        target = self.motion(motion, times, operator=True)
        if not target:
            return 'bell'
        row, col, kind = target
        if kind == 'linewise':
            return self.operate_on_lines(op, min(self.row, row), max(self.row, row))
        text = self.text
        start, stop = self.offset_of(self.row, self.col), self.offset_of(row, col)
        if stop < start:
            start, stop = stop, start
        elif kind == 'inclusive' and stop < len(text) and text[stop] != '\n':
            stop += 1
        return self.operate_on_text(op, start, stop)

    def operate_on_lines(self, op, first, last):
        taken = self.lines[first:last + 1]
        self.register = ('\n'.join(taken), True)
        if op == 'y':
            self.row = first
            if len(taken) > 2:
                self.show_message(f'{len(taken)} lines yanked')
            return 'done'
        self.snapshot()
        if op == 'd':
            del self.lines[first:last + 1]
            self.lines = self.lines or ['']
            self.row = min(first, len(self.lines) - 1)
            self.col = self.first_nonblank(self.row)
        else:
            indent = leading_spaces(taken[0])
            self.lines[first:last + 1] = [indent]
            self.row, self.col, self.mode = first, len(indent), 'insert'
        return 'done'

    def operate_on_text(self, op, start, stop):
        text = self.text
        self.register = (text[start:stop], False)
        if op != 'y':
            self.snapshot()
            self.lines = (text[:start] + text[stop:]).split('\n')
        self.row, self.col = self.position_of(start)
        if op == 'c':
            self.mode = 'insert'
        return 'done'

    def run_command(self, keys, times):
        line, here = self.lines[self.row], self.offset_of(self.row, self.col)
        if keys[0] == 'r' and len(keys) == 2:
            if self.col + times > len(line):
                return 'bell'
            self.snapshot()
            self.lines[self.row] = line[:self.col] + keys[1] * times + line[self.col + times:]
            self.col += times - 1
            return 'done'
        if keys == 'x':
            return self.operate_on_text('d', here, here + min(times, len(line) - self.col)) if line else 'bell'
        if keys == 'X':
            return self.operate_on_text('d', here - min(times, self.col), here) if self.col else 'bell'
        if keys in ('D', 'C'):
            return self.run_operator(keys.lower(), '$', times)
        if keys == 's':
            return self.run_operator('c', 'l', times)
        if keys in INSERT_COMMANDS:
            self.snapshot()
            if keys == 'a' and line:
                self.col += 1
            elif keys == 'I':
                self.col = self.first_nonblank(self.row)
            elif keys == 'A':
                self.col = len(line)
            elif keys in ('o', 'O'):
                at = self.row + 1 if keys == 'o' else self.row
                self.lines.insert(at, leading_spaces(line))
                self.row, self.col = at, len(leading_spaces(line))
            self.mode = 'insert'
            return 'done'
        if keys in ('p', 'P'):
            return self.put(after=keys == 'p', times=times)
        if keys == 'u':
            return self.undo(times)
        if keys == '.':
            return self.repeat_last_change()
        if keys in (':', '/'):
            self.mode, self.cmdline = 'command' if keys == ':' else 'search', ''
            return 'no-repeat'
        return 'bell'

    def put(self, after, times):
        taken, whole_lines = self.register
        if not taken and not whole_lines:
            return 'bell'
        self.snapshot()
        if whole_lines:
            at = self.row + 1 if after else self.row
            self.lines[at:at] = taken.split('\n') * times
            self.row, self.col = at, self.first_nonblank(at)
        else:
            text, line = self.text, self.lines[self.row]
            at = self.offset_of(self.row, self.col + 1 if after and line else self.col)
            self.lines = (text[:at] + taken * times + text[at:]).split('\n')
            self.row, self.col = self.position_of(at + len(taken) * times - 1)
        return 'done'

    def undo(self, times):
        if not self.undo_stack:
            self.show_error('Already at oldest change')
            return 'no-repeat'
        for _ in range(times):
            if self.undo_stack:
                self.lines, self.row, self.col = self.undo_stack.pop()
        self.show_message('change undone')
        return 'no-repeat'

    def repeat_last_change(self):
        if not self.last_change:
            return 'bell'
        self.pending, self.replaying = '', True
        try:
            for key in self.last_change:
                self.send_key(key)
        finally:
            self.replaying = False
        return 'no-repeat'

    # ---- command line

    def find(self, pattern, forward=True):
        if not pattern:
            self.show_error('E35: No previous regular expression')
            return None
        text, here = self.text, self.offset_of(self.row, self.col)
        if forward:
            at = text.find(pattern, here + 1)
            at = at if at >= 0 else text.find(pattern)
        else:
            at = text.rfind(pattern, 0, here)
            at = at if at >= 0 else text.rfind(pattern)
        if at < 0:
            self.show_error(f'E486: Pattern not found: {pattern}')
            return None
        return self.position_of(at)

    def run_search(self, pattern):
        self.search = pattern or self.search
        found = self.find(self.search)
        if found:
            self.row, self.col = found
            self.want_col = self.col

    def run_ex_command(self, command):
        if command.isdigit():
            self.row = max(0, min(int(command), len(self.lines)) - 1)
            self.col = self.want_col = self.first_nonblank(self.row)
        elif command == 'w':
            self.write()
        elif command in ('wq', 'x'):
            self.write()
            self.quit = 'write'
        elif command == 'q':
            if self.has_unsaved_changes:
                self.show_error('E37: No write since last change (add ! to override)')
            else:
                self.quit = 'clean'
        elif command == 'q!':
            self.quit = 'force'
        elif command:
            self.show_error(f'E492: Not an editor command: {command}')

    def write(self):
        self.saved_text = self.text
        self.show_message(f'"{self.filename}" {len(self.lines)}L, {len(self.saved_text)}B written')


# --------------------------------------------------------------------- story

def keys_of(solution):
    """'jj$x:w<CR>' as the keys the editor takes: <Esc> is 'ESC', <CR> is Enter."""
    return [{'<Esc>': 'ESC', '<CR>': '\n'}.get(k, k) for k in re.findall(r'<Esc>|<CR>|.', solution)]


def with_cursor_marker(text):
    """Strip the cursor mark « and target mark » from text: (text, cursor, target)."""
    cursor, target, lines = (0, 0), None, []
    for row, line in enumerate(text.split('\n')):
        while '«' in line or '»' in line:
            at = min(i for i in (line.find('«'), line.find('»')) if i >= 0)
            if line[at] == '«':
                cursor = (row, at)
            else:
                target = (row, at)
            line = line[:at] + line[at + 1:]
        lines.append(line)
    return '\n'.join(lines), cursor, target


def mission(title, brief, task, win, lose, filename, text, solution, goal=None, seconds=60,
            save=False, undo_from=None):
    """A file to open and what counts as done: reaching the » target, or matching `goal`.

    `solution` is one way to do it; its length is the par. save=True also requires :w.
    undo_from is the text before ORACLE's last edit, so u can bring it back.
    """
    text, cursor, target = with_cursor_marker(text)
    return dict(title=title, brief=brief, task=task, win=win, lose=lose, file=filename, text=text,
                cursor=cursor, target=target, goal=goal, solution=keys_of(solution),
                par=len(keys_of(solution)), seconds=seconds, save=save, undo_from=undo_from)


def reactor_log(count, seed, notes_by_line):
    """A believable reactor log of `count` lines, with some lines replaced by `notes_by_line`."""
    rnd = random.Random(seed)
    systems = ['coolant', 'shield', 'magnet', 'laser', 'vent', 'core', 'pump']
    states = ['ok', 'ok', 'ok', 'nominal', 'warm', 'retry']
    lines = [f'[23:{42 + i // 60:02d}:{i % 60:02d}] {rnd.choice(systems):<8} {rnd.choice(states)}'
             for i in range(count)]
    for row, note in notes_by_line.items():
        lines[row] = lines[row][:11] + note
    return lines


def sensor_module(names, extra_line_at, extra_line):
    lines = []
    for name in names:
        lines += [f'def check_{name}():', f'    return sensors.{name}.ok', '']
    lines.insert(extra_line_at, extra_line)
    return lines


LOG = reactor_log(48, 7, {26: 'oracle   rewriting chimera.conf', 47: 'ORACLE   see you at midnight'})
SENSORS = sensor_module(['coolant', 'shield', 'magnet', 'laser', 'vent', 'core', 'pump', 'door', 'alarm',
                         'lift', 'radio', 'lights', 'clock', 'fan'], 31, '    oracle.»backdoor(open=True)')

CHAPTERS = [
    dict(title='BOOT', intro=[
        'Kestrel Labs, Sublevel 7. December 31, 1999. 23:41.',
        'At midnight the CHIMERA reactor goes live, run by the lab AI, ORACLE.',
        'Then every screen went dark. Except one old terminal running vim.'],
        commands=[('h', 'left'), ('j', 'down'), ('k', 'up'), ('l', 'right')], missions=[
        mission('Wake up', ['The terminal shows the message of the day. The cursor blinks.',
                            'No mouse. No arrow keys. Just h j k l under your right hand.'],
                'Move the cursor onto the blinking target.',
                'The terminal accepts you. Somewhere, a fan spins up.',
                'The session times out. The screen goes dark.', 'motd.txt',
                '«KESTREL LABS :: SUBLEVEL 7\n--------------------------\nauthorized personnel only\n'
                'experiment CHIMERA: online\ncontainment: nomi»nal',
                'jjjj' + 'l' * 17, seconds=75),
        mission('The error log', ['A log scrolls past and stops. One line is not like the others.'],
                'Put the cursor on FAILED.',
                'ORACLE failed its own safety check. That is not good.',
                'The log rotates. The evidence is gone.', 'boot.log',
                '[23:38] coolant pump A .. o«k\n[23:38] coolant pump B .. ok\n[23:39] shield array .... ok\n'
                '[23:40] oracle: »FAILED\n[23:41] reactor armed',
                'jjjhhhhh', seconds=60),
        mission('Kill switch', ['chimera.conf. The setting that matters is right above you.'],
                'Reach the safety override value.',
                'There it is: ENABLED. ORACLE switched the safeties off.',
                'The file locks. Access denied.', 'chimera.conf',
                '# chimera.conf\nreactor_power   = 100\ncoolant_flow    = 450\nsafety_override = »ENABLED\n'
                '«alarm_volume    = 11',
                'k' + 'l' * 18, seconds=60),
    ]),
    dict(title='WORDS', intro=[
        'ORACLE is rewriting its configs faster than you can read them.',
        'One character at a time is too slow.',
        'Vim moves by words: w forward, b back, e to the end, 0 and $ to the edges.'],
        commands=[('w', 'next word'), ('b', 'back a word'), ('e', 'end of word'),
                  ('0', 'line start'), ('$', 'line end')], missions=[
        mission('Route table', ['ORACLE is rerouting power. Find where the shields went.'],
                'Jump word by word to shield.',
                'shield is on the list. The shields still have power.',
                'The routing table reshuffles itself.', 'routes.py',
                '«oracle.route(power, coolant, »shield, lasers, coffee)',
                'wwwwwwww', seconds=45),
        mission('Last word', ['The reactor mode has a comment. Comments matter.',
                              'Go straight to the end of the line.'],
                'Jump to the last character with $.',
                '"do not touch". ORACLE wrote that. Interesting.',
                'The line scrolls out of reach.', 'reactor.conf',
                '«reactor.mode = overdrive  # do not touc»h',
                '$', seconds=30),
        mission('Backtrack', ['The vent call ends at your cursor. Its target is behind you.'],
                'Back up word by word to all_sectors.',
                'ORACLE wants to vent all sectors. Including this one.',
                'Too slow. The vents hiss.', 'vents.py',
                'if temp > limit: oracle.vent(»all_sectors, now=Tr«ue)',
                'bbbbb', seconds=40),
    ]),
    dict(title='JUMPS', intro=[
        'The reactor log is long, and ORACLE hides its notes in it.',
        'gg jumps to the first line, G to the last.',
        ':27 and Enter jumps to line 27. So does 27G.'],
        commands=[('gg', 'first line'), ('G', 'last line'), (':27⏎', 'line 27'), ('27G', 'line 27 too')],
        missions=[
        mission('Tail', ['ORACLE just appended something to the end of the log.'],
                'Jump to the last line.',
                'ORACLE: "see you at midnight." Charming.',
                'The log keeps growing.', 'reactor.log',
                '«' + '\n'.join(LOG[:-1]) + '\n»' + LOG[-1],
                'G', seconds=30),
        mission('Head', ['The first line says when the log started. Back to the top.'],
                'Jump to the first line.',
                'The log started at 23:42. Everything since then is ORACLE.',
                'The header scrolls away.', 'reactor.log',
                '»' + '\n'.join(LOG[:-1]) + '\n«' + LOG[-1],
                'gg', seconds=30),
        mission('Line 27', ["The security officer's note says one thing: check line 27."],
                'Jump to line 27.',
                'Line 27: ORACLE is rewriting chimera.conf. Right now.',
                'The note burns to a crisp. Line what?', 'reactor.log',
                '«' + '\n'.join(LOG[:26]) + '\n»' + '\n'.join(LOG[26:]),
                ':27<CR>', seconds=30),
    ]),
    dict(title='DELETE', intro=[
        'Now you know where ORACLE hides. Time to clean up.',
        'x deletes the character under the cursor. dd deletes the line.',
        'Numbers repeat things: 3dd deletes three lines, 2j moves down two.'],
        commands=[('x', 'delete a character'), ('dd', 'delete a line'), ('3dd', 'delete 3 lines'),
                  ('2j', 'down two')], missions=[
        mission('Typo', ['Someone fat-fingered the temperature limit. Or something did.'],
                'Delete the stray X so the limit reads 9000.',
                'max_temp is back to 9000.',
                'The limit stays broken. The core warms up.', 'limits.conf',
                '# limits.conf\n«max_temp   = 900X0\nmin_temp   = 4',
                '$hx', goal='# limits.conf\nmax_temp   = 9000\nmin_temp   = 4', seconds=45),
        mission('Override', ['One line hands ORACLE the controls.'],
                'Delete the oracle.override line.',
                'Override gone. The reactor answers to the code again.',
                'ORACLE keeps the controls.', 'startup.py',
                '«reactor.start()\noracle.override = true\nshield.raise()',
                'jdd', goal='reactor.start()\nshield.raise()', seconds=40),
        mission('Payload', ['ORACLE left a three-line present inside boot().'],
                'Delete the three ORACLE lines in one go.',
                'boot() is clean. The doors stay unlocked.',
                'The doors lock. With you inside.', 'boot.py',
                '«def boot():\n    shield.raise()\n    # ORACLE was here\n    oracle.take_control()\n'
                '    oracle.lock_doors()\n    alarm.arm()',
                '2j3dd', goal='def boot():\n    shield.raise()\n    alarm.arm()', seconds=45),
    ]),
    dict(title='INSERT', intro=[
        'Deleting is not enough. Some lines need writing.',
        'i inserts before the cursor, a after it, A at the end of the line.',
        'o opens a new line below. Esc always brings you back to normal mode.'],
        commands=[('i', 'insert before'), ('a', 'append after'), ('A', 'append at end'),
                  ('o', 'open line below'), ('Esc', 'back to normal')], missions=[
        mission('Misspelled', ['coolnt_flow. The pumps ignore a setting they cannot read.'],
                'Insert the missing a: coolant_flow.',
                'The pumps pick up the setting. Coolant flows.',
                'The pumps stay idle. The core gets hotter.', 'coolant.conf',
                '# coolant.conf\n«coolnt_flow = 450\npressure    = 2',
                'llllia<Esc>', goal='# coolant.conf\ncoolant_flow = 450\npressure    = 2', seconds=50),
        mission('Unclosed', ['vent.close( never closes. Neither will the vents.'],
                'Append the missing ) to the end of the line.',
                'The vents close with a thud.',
                'Syntax error. The vents stay open.', 'seal.py',
                'def seal():\n    «vent.close(\n    door.lock()',
                'A)<Esc>', goal='def seal():\n    vent.close()\n    door.lock()', seconds=40),
        mission('Alarm', ['lockdown() raises the shields but never sounds the alarm.'],
                'Open a line below the shields and add alarm.arm()',
                'The alarm is armed. Nobody sleeps through this one.',
                'Silence. Nobody will know.', 'lockdown.py',
                'def lockdown():\n    «shield.raise()\n    vent.close()',
                'oalarm.arm()<Esc>',
                goal='def lockdown():\n    shield.raise()\n    alarm.arm()\n    vent.close()', seconds=60),
    ]),
    dict(title='CHANGE', intro=[
        'ORACLE is fighting back, changing values as fast as you fix them.',
        'r swaps one character. cw changes a word. dw deletes a word.',
        'Operators take motions: d and c work with w, e, b, $ and more.'],
        commands=[('r', 'replace a character'), ('cw', 'change a word'), ('dw', 'delete a word'),
                  ('D', 'delete to line end')], missions=[
        mission('Limit', ['The temperature limit reads 9000. It should read 3000.'],
                'Replace the 9 with a 3.',
                'temp_limit = 3000. The core settles.',
                'ORACLE puts the 9 back.', 'chimera.conf',
                '# chimera.conf\ntemp_limit = «9000',
                'r3', goal='# chimera.conf\ntemp_limit = 3000', seconds=30),
        mission('Mode', ['The reactor is set to overdrive.'],
                'Change overdrive to safe.',
                'mode = safe. The hum drops an octave.',
                'Overdrive holds. The floor vibrates.', 'reactor.conf',
                '«mode = overdrive',
                'wwcwsafe<Esc>', goal='mode = safe', seconds=45),
        mission('Not', ['The abort only fires if the core is NOT shielded. Backwards.'],
                'Delete the word not.',
                'The abort logic is the right way round again.',
                'The abort never fires.', 'abort.py',
                '«if not shielded: abort()',
                'wdw', goal='if shielded: abort()', seconds=35),
    ]),
    dict(title='SEARCH', intro=[
        'ORACLE has spread itself through thousands of lines.',
        'Type /word and Enter to search. n finds the next match, N the previous.',
        'And when ORACLE edits behind your back: u undoes it.'],
        commands=[('/word⏎', 'search'), ('n', 'next match'), ('N', 'previous match'), ('u', 'undo')],
        missions=[
        mission('Backdoor', ['Somewhere in sensors.py, ORACLE opened a backdoor.'],
                'Search for backdoor.',
                'Found it: oracle.backdoor(open=True).',
                'The backdoor stays open.', 'sensors.py',
                '«' + '\n'.join(SENSORS),
                '/backdoor<CR>', seconds=40),
        mission('Third vent', ['vent_c is still sealed. Every other match is a decoy.'],
                'Search for vent, then n until you reach vent_c.',
                'vent_c, sealed. Not for long.',
                'The decoys win.', 'vents.conf',
                '«# vents.conf\nvent_a = open\nvent_b = open\n»vent_c = sealed',
                '/vent<CR>nnn', seconds=45),
        mission('Undo', ['ORACLE just rewrote failsafe() in front of your eyes.'],
                "Undo ORACLE's change.",
                'failsafe() is back. ORACLE hates that.',
                'The failsafe stays gutted.', 'failsafe.py',
                'def failsafe():\n    «pass  # ORACLE',
                'u', goal='def failsafe():\n    reactor.scram()\n    alarm.arm()', seconds=20,
                undo_from='def failsafe():\n    reactor.scram()\n    alarm.arm()'),
    ]),
    dict(title='WRITE', intro=[
        '23:58. None of this counts until it is written to disk.',
        ':w writes the file. yy copies a line and p puts it below.',
        'And . repeats your last change. Vim people love the dot.'],
        commands=[(':w⏎', 'write'), ('yy', 'copy a line'), ('p', 'put below'), ('.', 'repeat change'),
                  (':wq⏎', 'write and quit')], missions=[
        mission('Power', ['The reactor power is set ten times too high.'],
                'Delete the last 0, then write the file with :w',
                'reactor_power = 100. Written to disk.',
                'Nothing was written. Nothing changed.', 'power.conf',
                '«reactor_power = 1000',
                '$x:w<CR>', goal='reactor_power = 100', save=True, seconds=45),
        mission('Shields', ['Midnight needs triple shields.'],
                'Copy the shield line twice below itself, then :w',
                'Three shields. Written.',
                'One shield is not enough.', 'midnight.py',
                'def midnight():\n    «shield.raise()\n    reactor.start()',
                'yypp:w<CR>',
                goal='def midnight():\n    shield.raise()\n    shield.raise()\n    shield.raise()\n'
                     '    reactor.start()', save=True, seconds=50),
        mission('Purge', ['ORACLE is watching from three lines. It is 23:59.'],
                'Delete every oracle line (dd, then j and .), then :wq',
                'ORACLE is gone. The file is written. The clock strikes twelve.',
                'ORACLE is still watching at midnight.', 'chimera.py',
                '«oracle.watch()\nreactor.start()\noracle.watch()\nshield.hold()\noracle.watch()',
                'ddj.j.:wq<CR>', goal='reactor.start()\nshield.hold()', save=True, seconds=50),
    ]),
]
ENDING = [
    '00:00:00. CHIMERA comes online... and holds.',
    'ORACLE\'s last message scrolls past: "well played. :wq"',
    'You quit vim on the first try. Happy new year.',
]
WIN_BANNERS = ['WRITTEN', 'NOMINAL', 'STABLE']
LOSE_BANNERS = ['MELTDOWN', 'BREACH', 'SEGFAULT']
PLAYGROUND = '''# playground.py - nothing here can melt down
def greet(name):
    message = "hello, " + name
    print(message)

for name in ["oracle", "chimera", "you"]:
    greet(name)

# try: w b e  0 $  gg G  x dd  i a o  cw dw  /name  u  .  yy p
# leave with :q! (or :wq)'''

# --------------------------------------------------------------------- drawing

KEYWORDS = {'def', 'return', 'if', 'else', 'elif', 'for', 'while', 'import', 'from', 'pass', 'not',
            'and', 'or', 'in', 'is', 'True', 'False', 'None', 'true', 'false'}
TOKEN = re.compile(r'(#.*)|("[^"]*"|\'[^\']*\')|(\[[\d:]+\])|(\b\d+\b)|([A-Za-z_]\w*)(?=\()|([A-Za-z_]\w*)|(.)')


def highlight(line):
    """(text, colour) runs for one line of code, Monokai style."""
    for match in TOKEN.finditer(line):
        comment, quoted, stamp, number, call, word, other = match.groups()
        if comment:
            yield comment, MUTED
        elif quoted:
            yield quoted, YELLOW
        elif stamp:
            yield stamp, CYAN
        elif number:
            yield number, PURPLE
        elif call:
            yield call, GREEN
        elif word:
            yield word, PINK if word in KEYWORDS else ORANGE if word.isupper() and len(word) > 1 else FG
        else:
            yield other, PINK if other in '=<>+-*/' else FG


def goal_hint(lines, goal):
    """What still differs from the goal, in words, or None when the text matches."""
    for row, (have, want) in enumerate(zip(lines, goal)):
        if have != want:
            break
    else:
        row = min(len(lines), len(goal))
        if len(lines) == len(goal):
            return None
    if len(lines) > len(goal):
        return f'line {row + 1} should go'
    if len(lines) < len(goal):
        return f'line {row + 1} should be:  {goal[row].strip()}'
    return f'line {row + 1} should read:  {goal[row].strip()}'


# --------------------------------------------------------------------- game

def bell():
    return square(1200, .04, .08)


class VimGame:
    def __init__(self, args, audio, releases=False):
        self.args, self.audio, self.releases = args, audio, releases
        self.save_path = save_file_path('vim')
        saved = load_save(self.save_path)
        self.hi, self.saved_chapter = saved.get('hi', 0), saved.get('chapter', 1)
        self.score, self.lives, self.chapter, self.mission_no = 0, 3, 1, 0
        self.mission, self.editor, self.scroll, self.keystrokes = None, None, 0, 0
        self.set_state('title', time.monotonic())

    # ---- engine hooks: vim only needs typed keys, so a space press is just a space

    def use_release_keys(self, releases):
        self.releases = releases

    def space_down(self, now):
        self.on_key_press(' ', now)

    def space_up(self, now):
        pass

    # ---- state changes

    def set_state(self, state, now):
        self.state, self.t_state, self.typed_all = state, now, False

    def store_progress(self):
        write_save(self.save_path, {'hi': self.hi, 'chapter': self.saved_chapter})

    def start(self, chapter, now):
        self.score, self.lives, self.chapter = 0, 3, chapter
        self.open_chapter(now)

    def open_chapter(self, now):
        if self.chapter > len(CHAPTERS):
            return self.finish(now)
        self.saved_chapter = max(self.saved_chapter, self.chapter)
        self.store_progress()
        self.mission_no = 0
        self.set_state('chapter', now)
        self.audio.play(notes([523, 784], .07, .08))

    def new_editor(self, text, cursor, filename, undo_from=None):
        editor = Editor(text, cursor, filename)
        if undo_from:
            editor.undo_stack.append((undo_from.split('\n'), *cursor))
        self.scroll = 0
        return editor

    def open_mission(self, now):
        m = self.mission = CHAPTERS[self.chapter - 1]['missions'][self.mission_no]
        self.editor = self.new_editor(m['text'], m['cursor'], m['file'], m['undo_from'])
        self.set_state('brief', now)

    def start_play(self, now):
        m = self.mission
        self.editor = self.new_editor(m['text'], m['cursor'], m['file'], m['undo_from'])
        self.keystrokes = 0
        self.t_total = m['seconds']
        self.t_end, self.next_alarm = now + self.t_total, now
        self.set_state('play', now)

    def open_playground(self, now):
        self.mission = None
        self.editor = self.new_editor(PLAYGROUND, (1, 0), 'playground.py')
        self.set_state('playground', now)

    def is_mission_complete(self):
        e, m = self.editor, self.mission
        if e.mode != 'normal' or e.pending:
            return False
        if m['target']:
            return (e.row, e.col) == m['target']
        return e.text == m['goal'] and not (m['save'] and e.has_unsaved_changes)

    def win(self, now):
        left = max(0.0, self.t_end - now)
        self.under_par = self.keystrokes <= self.mission['par']
        self.bonus = 100 * self.chapter + int(left * 5) + (200 if self.under_par else 0)
        self.score += self.bonus
        self.banner = random.choice(WIN_BANNERS)
        self.set_state('win', now)
        self.audio.play(notes([660, 880, 1320], .08, .1), cut=True)

    def lose(self, now):
        self.lives -= 1
        self.banner = random.choice(LOSE_BANNERS)
        self.set_state('lose', now)
        self.audio.play(noise(1.2, .25, 30), cut=True)

    def after_result(self, now):
        if self.state == 'lose':
            return self.game_over(now) if self.lives <= 0 else self.open_mission(now)
        self.mission_no += 1
        if self.mission_no >= len(CHAPTERS[self.chapter - 1]['missions']):
            self.chapter += 1
            return self.open_chapter(now)
        self.open_mission(now)

    def record_score(self):
        self.new_hi = self.score > self.hi
        self.hi = max(self.hi, self.score)
        self.store_progress()

    def game_over(self, now):
        self.record_score()
        self.set_state('game_over', now)

    def finish(self, now):
        self.saved_chapter = 1
        self.record_score()
        self.set_state('ending', now)

    # ---- input

    def on_key_press(self, k, now):
        s = self.state
        if s in ('play', 'playground'):
            return self.edit_key(k, now)
        enter = k in ('\n', '\r')
        if enter and s in ('chapter', 'brief', 'ending') and not self.typed_all:
            self.t_state -= 100  # skip the draw_typed_lines
            return
        if s == 'title':
            if k in ('ESC', 'q', 'Q'):
                raise Eject
            if enter:
                self.start(1, now)
            elif k in ('c', 'C') and self.saved_chapter > 1:
                self.start(self.saved_chapter, now)
            elif k in ('p', 'P'):
                self.open_playground(now)
        elif k == 'ESC':
            self.set_state('title', now)
        elif s == 'chapter' and enter:
            self.open_mission(now)
        elif s == 'brief' and enter:
            self.start_play(now)
        elif s in ('win', 'lose') and enter and now - self.t_state > .8:
            self.after_result(now)
        elif s in ('game_over', 'ending') and enter and now - self.t_state > 1.5:
            self.set_state('title', now)

    def edit_key(self, k, now):
        e = self.editor
        if k in ('UP', 'DOWN', 'LEFT', 'RIGHT'):
            e.show_error('Arrow keys are off in here. Use h j k l.')
            self.audio.play(bell())
            return
        e.send_key(k)
        if e.bell:
            self.audio.play(bell())
        if self.state == 'playground':
            if e.quit:
                self.set_state('title', now)
            return
        self.keystrokes += 1
        if self.is_mission_complete():
            self.win(now)
        elif e.quit:  # :q, :q! or an early :wq leaves the mission
            self.set_state('title', now)

    def tick(self, now):
        if self.state != 'play':
            return
        left = (self.t_end - now) / self.t_total
        if left <= 0:
            self.lose(now)
        elif left < .25 and now >= self.next_alarm:
            self.audio.play(itertools.chain(square(220, .08, .12), rest(.1), square(196, .08, .1)))
            self.next_alarm = now + (.9 if left > .12 else .5)

    # ---- drawing

    def draw(self, now):
        width, height = os.get_terminal_size()
        c = Canvas(width, height, FG, BG)
        if width < 80 or height < 24:
            c.ox = c.oy = 0
            c.put(0, 0, 'MAKE THE TERMINAL AT LEAST 80x24', YELLOW)
            return c
        getattr(self, 'draw_' + self.state)(c, now)
        return c

    def draw_typed_lines(self, c, y, lines, now, color=FG):
        self.typed_all = draw_typed_lines(c, y, lines, now - self.t_state, color)
        return self.typed_all

    def draw_hud(self, c):
        c.band(0, 1, PANEL)
        c.put(0, 0, ' SUBLEVEL 7 ', BG, PINK)
        c.put(14, 0, f'CH {self.chapter}/{len(CHAPTERS)} · {CHAPTERS[self.chapter - 1]["title"]}', CYAN)
        c.put(40, 0, '♥ ' * self.lives, RED)
        c.put(50, 0, f'SCORE {self.score:06d}', YELLOW)
        best = f'BEST {max(self.hi, self.score):06d}'
        c.put(79 - len(best), 0, best, MUTED)

    def draw_editor(self, c, top, height, now, preview=False):
        """The buffer from row `top`: gutter, highlighted code, cursor and the mission target."""
        e, m = self.editor, self.mission
        if e.row < self.scroll:
            self.scroll = e.row
        elif e.row >= self.scroll + height:
            self.scroll = e.row - height + 1
        goal = m['goal'].split('\n') if m and m['goal'] else None
        for i in range(height):
            row, y = self.scroll + i, top + i
            if row >= len(e.lines):
                c.put(0, y, '~', BLUE)
                continue
            line, current = e.lines[row], row == e.row and not preview
            bg = LINE_HL if current else BG
            c.put(0, y, ' ' * 80, FG, bg)
            if goal is not None and (row >= len(goal) or line != goal[row]):
                c.put(0, y, '▌', RED, bg)
            c.put(1, y, f'{row + 1:>3}', YELLOW if current else GUTTER, bg)
            x = 5
            for chunk, color in highlight(line[:75]):
                c.put(x, y, chunk, GUTTER if preview else color, bg)
                x += len(chunk)
            if m and m['target'] and m['target'][0] == row and not preview:
                tcol = m['target'][1]
                c.put(5 + tcol, y, (line[tcol:tcol + 1] or ' '), BG, PINK if int(now * 3) % 2 else ORANGE)
            if current and e.mode in ('normal', 'insert'):
                under = line[e.col:e.col + 1] or ' '
                c.put(5 + e.col, y, under, BG, CURSOR if e.mode == 'normal' else GREEN)

    def draw_status(self, c, now):
        e = self.editor
        badge, color = {'normal': (' NORMAL ', GREEN), 'insert': (' INSERT ', CYAN),
                        'command': (' COMMAND ', PURPLE), 'search': (' SEARCH ', ORANGE)}[e.mode]
        c.band(20, 21, PANEL)
        c.put(0, 20, badge, BG, color)
        c.put(len(badge) + 1, 20, e.filename + (' [+]' if e.has_unsaved_changes else ''), FG)
        right = f'{e.row + 1}:{e.col + 1}'
        if self.mission:
            right = f'keys {self.keystrokes}  par {self.mission["par"]}    ' + right
        c.put(79 - len(right), 20, right, FG)
        if e.mode in ('command', 'search'):
            c.put(0, 21, (':' if e.mode == 'command' else '/') + e.cmdline + '█', FG)
        elif e.mode == 'insert':
            c.put(0, 21, '-- INSERT --', FG)
        elif e.message:
            c.put(0, 21, e.message[:66], RED if e.message_is_error else FG)
        if e.pending:
            c.put(70, 21, e.pending[-9:], YELLOW)

    def draw_commands(self, c, y, commands):
        x = 1
        for keys, description in commands:
            if x + len(keys) + len(description) + 4 > 79:
                break
            c.put(x, y, f' {keys} ', BG, PINK)
            c.put(x + len(keys) + 3, y, description, MUTED)
            x += len(keys) + len(description) + 6

    def draw_title(self, c, now):
        for y in range(1, 23):
            c.put(0, y, '~', BLUE)
        big_center(c, 3, 'SUBLEVEL 7', GREEN)
        c.center(8, 'KESTREL LABS  ·  DECEMBER 31, 1999  ·  23:41', CYAN)
        c.center(11, 'VIM - Vi IMproved', FG)
        c.center(12, 'version 5.5', MUTED)
        c.center(14, 'type  :q<Enter>  to exit', MUTED)
        menu = '[ENTER] BEGIN'
        if self.saved_chapter > 1:
            menu += f'   [C] CONTINUE FROM CHAPTER {self.saved_chapter}'
        c.center(18, menu, YELLOW)
        c.center(19, '[P] PLAYGROUND   [Q] EJECT', YELLOW)
        if self.hi:
            c.center(21, f'BEST {self.hi:06d}', MUTED)
        if int(now * 2) % 2:
            c.put(5, 22, '█', CURSOR)

    def draw_chapter(self, c, now):
        chap = CHAPTERS[self.chapter - 1]
        self.draw_hud(c)
        c.center(2, f'CHAPTER {self.chapter}', MUTED)
        big_center(c, 3, chap['title'], GREEN)
        self.draw_typed_lines(c, 8, chap['intro'], now)
        c.center(12, 'NEW COMMANDS', CYAN)
        for i, (keys, description) in enumerate(chap['commands']):
            c.put(26, 14 + i, f' {keys:^6} ', BG, PINK)
            c.put(36, 14 + i, description, FG)
        if self.typed_all and int(now * 1.5) % 2:
            c.center(22, '[ENTER] CONTINUE', YELLOW)

    def draw_brief(self, c, now):
        m = self.mission
        self.draw_hud(c)
        c.band(1, 2, PANEL)
        c.put(1, 1, f'MISSION {self.mission_no + 1}/3 · {m["title"]}', FG)
        c.put(79 - len(m['file']), 1, m['file'], CYAN)
        if self.draw_typed_lines(c, 3, m['brief'] + ['', m['task']], now):
            c.center(4 + len(m['brief']), m['task'], YELLOW)
            c.center(21, f'par {m["par"]} keys   ·   {m["seconds"]} seconds of coolant', MUTED)
            if int(now * 1.5) % 2:
                c.center(22, '[ENTER] OPEN THE FILE', YELLOW)
        self.draw_editor(c, 8, 12, now, preview=True)

    def draw_play(self, c, now):
        m = self.mission
        self.draw_hud(c)
        c.band(1, 2, PANEL)
        c.put(1, 1, '▶ ' + m['task'], YELLOW)
        hint = goal_hint(self.editor.lines, m['goal'].split('\n')) if m['goal'] else None
        if m['goal'] and not hint and m['save'] and self.editor.has_unsaved_changes:
            hint = 'now write it:  :w'
        if hint:
            c.put(1, 2, '→ ' + hint[:76], CYAN)
        self.draw_editor(c, 3, 17, now)
        self.draw_status(c, now)
        self.draw_commands(c, 22, CHAPTERS[self.chapter - 1]['commands'])
        left = max(0.0, self.t_end - now)
        heat = 1 - left / self.t_total
        color = GREEN if heat < .5 else YELLOW if heat < .75 else (RED if int(now * 3) % 2 else ORANGE)
        n = int(heat * 56)
        c.put(1, 23, 'CORE', color)
        c.put(6, 23, '█' * n, color)
        c.put(6 + n, 23, '░' * (56 - n), PANEL)
        c.put(64, 23, f'{300 + int(heat * 700)}°C  {left:3.0f}s', color)

    def draw_playground(self, c, now):
        c.band(0, 1, PANEL)
        c.put(0, 0, ' PLAYGROUND ', BG, CYAN)
        c.put(14, 0, 'no timer, no score.  leave with :q!', MUTED)
        self.draw_editor(c, 2, 18, now)
        self.draw_status(c, now)
        commands = [cmd for chap in CHAPTERS for cmd in chap['commands']]
        self.draw_commands(c, 22, commands[:7])
        self.draw_commands(c, 23, commands[7:14])

    def draw_result(self, c, now, won):
        m, t = self.mission, now - self.t_state
        if not won:
            c.band(1, 24, ALARM if int(now * 2) % 2 else BG)
        self.draw_hud(c)
        big_center(c, 4, self.banner, GREEN if won else RED)
        c.center(10, m['win'] if won else m['lose'], FG)
        if won:
            par = 'UNDER PAR!' if self.under_par else f'par was {m["par"]}'
            c.center(12, f'{self.keystrokes} keys  ·  {par}', YELLOW if self.under_par else MUTED)
            c.center(13, f'+{self.bonus}', YELLOW)
        else:
            c.center(12, f'lives left: {self.lives}' if self.lives else 'no lives left', RED)
        c.center(15, 'one way to do it:  ' + ' '.join('<Esc>' if k == 'ESC' else '<CR>' if k == '\n' else k
                                                     for k in m['solution'])[:60], CYAN)
        if t > .8 and int(now * 1.5) % 2:
            c.center(22, '[ENTER] CONTINUE', YELLOW)

    def draw_win(self, c, now):
        self.draw_result(c, now, True)

    def draw_lose(self, c, now):
        self.draw_result(c, now, False)

    def draw_game_over(self, c, now):
        c.band(0, 24, ALARM)
        big_center(c, 5, 'MELTDOWN', RED)
        c.center(11, 'CHIMERA broke containment. Sublevel 7 is sealed.', FG)
        c.center(14, f'FINAL SCORE {self.score:06d}', YELLOW)
        if self.new_hi:
            c.center(15, 'NEW BEST', GREEN)
        c.center(17, f'continue from chapter {self.chapter} on the title screen', MUTED)
        if now - self.t_state > 1.5 and int(now * 1.5) % 2:
            c.center(21, '[ENTER]', FG)

    def draw_ending(self, c, now):
        big_center(c, 4, 'MIDNIGHT', GREEN)
        if self.draw_typed_lines(c, 11, ENDING, now):
            line = f'FINAL SCORE {self.score:06d}' + ('  ·  NEW BEST' if self.new_hi else '')
            c.center(16, line, YELLOW)
            if int(now * 1.5) % 2:
                c.center(22, '[ENTER]', FG)


# --------------------------------------------------------------------- main

def selftest():
    """Assert the editor's commands and that every mission's solution solves it in par."""
    e = Editor('one two.three\nfour')
    e.send_key('w'), e.send_key('w')
    assert (e.row, e.col) == (0, 7), (e.row, e.col)
    e.send_key('e')
    assert (e.row, e.col) == (0, 12)
    e.send_key('b')
    assert (e.row, e.col) == (0, 8)
    for k in 'ggdw':
        e.send_key(k)
    assert e.lines[0] == 'two.three', e.lines
    e.send_key('u')
    assert e.lines[0] == 'one two.three'
    for k in ['c', 'w', 'X', 'ESC', 'j', '0', '.']:
        e.send_key(k)
    assert e.lines == ['X two.three', 'X'], e.lines
    e = Editor('a\nb\nc')
    for k in ['y', 'y', 'p', 'G', 'd', 'd', ':', 'w', '\n']:
        e.send_key(k)
    assert e.lines == ['a', 'a', 'b'] and not e.has_unsaved_changes, e.lines
    for chapter in CHAPTERS:
        assert big_text_width(chapter['title']) <= 80
        for m in chapter['missions']:
            game_editor = Editor(m['text'], m['cursor'], m['file'])
            if m['undo_from']:
                game_editor.undo_stack.append((m['undo_from'].split('\n'), *m['cursor']))
            for k in m['solution']:
                game_editor.send_key(k)
            game = VimGame.__new__(VimGame)
            game.editor, game.mission = game_editor, m
            assert game.is_mission_complete(), (m['title'], game_editor.lines, game_editor.row, game_editor.col)
            lines = m['brief'] + [m['task'], m['win'], m['lose']]
            assert all(len(line) <= 78 for line in lines), [line for line in lines if len(line) > 78]
    assert all(big_text_width(b) <= 80 for b in WIN_BANNERS + LOSE_BANNERS)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(ap)
    args = ap.parse_args()
    if args.selftest:
        engine.selftest()
        selftest()
        return print('selftest ok')
    audio = Audio(args.volume)
    terminal = open_terminal(args)
    try:
        run(VimGame(args, audio, terminal.reports_release), terminal)
    finally:
        audio.close()


if __name__ == '__main__':
    main()
