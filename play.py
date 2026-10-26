#!/usr/bin/env python3
"""TERMINAL CARTRIDGES - insert the cartridge: VIM (Sublevel 7, 1999). MORSE CODE now lives in go/.

Enter or space inserts the cartridge, q quits.
Each game's own quit (Esc or q on its title screen) ejects back here.
"""
import argparse
import os

from engine import (Audio, Canvas, Eject, add_arguments, big_center, noise, notes, open_terminal, run,
                    slide, sprite)
import engine
import vim

# Atari 2600 NTSC-ish palette
BLACK, PLASTIC, RIDGE, LABEL = (0, 0, 0), (30, 30, 32), (58, 58, 62), (12, 12, 12)
WHITE, GREY, RED, ORANGE = (236, 236, 236), (142, 142, 142), (200, 72, 72), (227, 128, 44)
YELLOW, GREEN, CYAN, BLUE = (252, 224, 112), (92, 186, 92), (84, 184, 204), (45, 50, 184)
PURPLE, PINK, BRASS = (120, 92, 214), (228, 111, 192), (214, 164, 62)
WOOD_LIGHT, WOOD_DARK, SLOT = (150, 92, 40), (84, 46, 18), (8, 8, 8)
RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, PURPLE]
PALETTE = {'K': (16, 16, 16), 'W': WHITE, 'S': GREY, 'R': RED, 'O': ORANGE, 'Y': YELLOW, 'G': GREEN,
       'C': CYAN, 'B': BLUE, 'P': PINK, 'N': (110, 62, 24), 'A': BRASS}

TERMINAL = ['..SSSSSSSSSSSSSSSS..', '..SKKKKKKKKKKKKKKS..', '..SKGGGG.PPPKKKKKS..',
            '..SKKKCCCCCC.YYYKS..', '..SKGGG.WKKKKKKKKS..', '..SKKKKKKKKKKKKKKS..',
            '..SSSSSSSSSSSSSSSS..', '.......SSSSSS.......', '.....SSSSSSSSSS.....',
            '....................']

CARTRIDGES = [
    dict(title='VIM', subtitle='SUBLEVEL 7', stripes=[GREEN, CYAN, PINK], art=TERMINAL,
         start=lambda args, audio, releases: vim.VimGame(args, audio, releases)),
]
CART_W, CART_H, CART_X = 26, 15, (27,)
INSERT_SECONDS, POWER_ON_SECONDS = .7, 1.2


def draw_cartridge(c, x, y, cart, selected):
    """One cartridge: ridged black plastic grip on top, picture label below."""
    for row in range(CART_H):
        c.put(x, y + row, ' ' * CART_W, WHITE, PLASTIC)
    for row in range(3):
        c.put(x + 1, y + row, '▀' * (CART_W - 2), RIDGE, PLASTIC)
    label_x, width = x + 2, CART_W - 4
    for row in range(4, 13):
        c.put(label_x, y + row, ' ' * width, WHITE, LABEL)
    first, second, third = cart['stripes']
    c.put(label_x, y + 4, cart['title'].center(width), BLACK, first)
    c.put(label_x, y + 5, '▀' * width, second, third)
    sprite(c, x + 3, y + 6, cart['art'], PALETTE)
    c.put(label_x, y + 11, cart['subtitle'].center(width), GREY, LABEL)
    c.put(label_x, y + 12, '▀' * width, third, second)
    if selected:
        c.put(x - 2, y + 7, '▶', YELLOW)
        c.put(x + CART_W + 1, y + 7, '◀', YELLOW)


def draw_console(c):
    """The woodgrain console top the cartridges slide into."""
    c.band(20, 21, BLACK)
    for x in CART_X:
        c.put(x - 1, 20, ' ' * (CART_W + 2), WHITE, SLOT)
    for y, (light, dark) in zip((21, 22), ((WOOD_LIGHT, WOOD_DARK), (WOOD_DARK, WOOD_LIGHT))):
        c.band(y, y + 1, dark)
        c.put(0, y, ''.join('▀' if (i * 7 + y) % 5 else '▄' for i in range(80)), light, dark)
    c.band(23, 24, BLACK)


class Launcher:
    """The cartridge picker; once a cartridge is in, every hook goes to its game."""

    def __init__(self, args, audio, releases):
        self.args, self.audio, self.releases = args, audio, releases
        self.choice, self.game, self.inserted_at = 0, None, None

    def use_release_keys(self, releases):
        self.releases = releases
        if self.game:
            self.game.use_release_keys(releases)

    def space_down(self, now):
        self.game.space_down(now) if self.game else self.on_key_press(' ', now)

    def space_up(self, now):
        if self.game:
            self.game.space_up(now)

    def on_key_press(self, k, now):
        if self.game:
            try:
                self.game.on_key_press(k, now)
            except Eject:
                self.eject()
            return
        if self.inserted_at is not None:
            return
        if k in ('\n', '\r', ' '):
            self.inserted_at = now
            self.audio.play(slide(300, 80, .35, .15))
            self.audio.play(noise(.12, .2, 8))
        elif k in ('ESC', 'q', 'Q'):
            raise Eject

    def eject(self):
        self.game, self.inserted_at = None, None
        self.audio.stop_signal_playback()
        self.audio.key_on = False

    def tick(self, now):
        if self.game:
            return self.game.tick(now)
        if self.inserted_at is not None and now - self.inserted_at > POWER_ON_SECONDS:
            self.game = CARTRIDGES[self.choice]['start'](self.args, self.audio, self.releases)
            self.audio.play(notes([262, 392, 523], .06, .1))

    def draw(self, now):
        if self.game:
            return self.game.draw(now)
        width, height = os.get_terminal_size()
        c = Canvas(width, height, WHITE, BLACK)
        if width < 80 or height < 24:
            c.ox = c.oy = 0
            c.put(0, 0, 'MAKE THE TERMINAL AT LEAST 80x24', YELLOW)
            return c
        inserting = self.inserted_at is not None
        t = now - self.inserted_at if inserting else 0
        if inserting and t > INSERT_SECONDS:  # power on: the screen flickers through the colours
            c.band(0, 24, RAINBOW[int(t * 20) % len(RAINBOW)] if t < INSERT_SECONDS + .25 else BLACK)
            return c
        for y in (0, 5):
            for i, color in enumerate(RAINBOW):
                c.put(i * 12 - 2, y, '▀' * 12, color)
        big_center(c, 1, 'SELECT GAME', YELLOW)
        for i, cart in enumerate(CARTRIDGES):
            selected = i == self.choice
            y = 6 - selected
            if selected and inserting:
                y += int(min(1, t / INSERT_SECONDS) * 13)
            draw_cartridge(c, CART_X[i], y, cart, selected and not inserting)
        draw_console(c)
        if int(now * 1.5) % 2 or inserting:
            c.center(23, 'ENTER INSERT     Q QUIT', GREY)
        return c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(ap)
    args = ap.parse_args()
    if args.selftest:
        engine.selftest()
        vim.selftest()
        return print('selftest ok')
    audio = Audio(args.volume)
    terminal = open_terminal(args)
    try:
        run(Launcher(args, audio, terminal.reports_release), terminal)
    finally:
        audio.close()


if __name__ == '__main__':
    main()
