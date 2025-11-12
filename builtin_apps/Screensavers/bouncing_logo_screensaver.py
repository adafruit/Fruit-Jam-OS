import os
import random
import time

from displayio import Group, OnDiskBitmap, TileGrid, Bitmap, Palette

import adafruit_imageload


class ScreenSaver(Group):
    def __init__(self, display_size):
        super().__init__()
        self.display_size = display_size
        self.init_graphics(display_size)

    def init_graphics(self, display_size):
        raise NotImplementedError("Subclasses must implement init_graphics()")

    def tick(self):
        raise NotImplementedError("Subclasses must implement tick()")


class BouncingLogoScreenSaver(Group):
    display_size = (640, 480)
    direction: list = [3, 3]
    logo_tg: TileGrid = None
    last_move_time = 0
    move_cooldown = 0.05  # seconds
    colors = [0xffffff, 0xff0000, 0xffff00, 0x00ffff, 0xff00ff, 0x0000ff, 0x00ff00]
    color_index = 0

    def __init__(self):
        super().__init__()
        self.init_graphics()

    def init_graphics(self):
        bg_bmp = Bitmap(self.display_size[0] // 20, self.display_size[1] // 20, 1)
        bg_palette = Palette(1)
        bg_palette[0] = 0x000000
        bg_tg = TileGrid(bitmap=bg_bmp, pixel_shader=bg_palette)

        bg_group = Group(scale=20)
        bg_group.append(bg_tg)
        self.append(bg_group)

        os.chdir("/".join(__file__.split("/")[:-1]))

        logo_bmp, logo_bmp_pixelshader = adafruit_imageload.load("fruit_jam_logo.bmp")
        self.logo_tg = TileGrid(bitmap=logo_bmp, pixel_shader=logo_bmp_pixelshader)
        self.logo_tg.x = random.randint(20, self.display_size[0] - self.logo_tg.tile_width - 20)
        self.append(self.logo_tg)

    def change_color(self):
        self.color_index += 1
        if self.color_index >= len(self.colors):
            self.color_index = 0
        self.logo_tg.pixel_shader[1] = self.colors[self.color_index]

    def tick(self):

        now = time.monotonic()
        if now - self.last_move_time > self.move_cooldown:
            self.last_move_time = now
            # move one step in direction
            self.logo_tg.x += self.direction[0]
            self.logo_tg.y += self.direction[1]

            # bounce left wall
            if self.logo_tg.x <= 0:
                self.direction[0] = 3
                self.change_color()

            # bounce right wall
            if self.logo_tg.x + self.logo_tg.tile_width >= self.display_size[0]:
                self.direction[0] = -3
                self.change_color()

            # bounce top wall
            if self.logo_tg.y <= 0:
                self.direction[1] = 3
                self.change_color()

            # bounce bottom wall
            if self.logo_tg.y + self.logo_tg.tile_height >= self.display_size[1]:
                self.direction[1] = -3
                self.change_color()

            return True
        else:
            print("waiting")
        return False
