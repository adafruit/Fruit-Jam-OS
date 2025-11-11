import os
import random
import adafruit_imageload
import supervisor
from displayio import TileGrid, Group, Bitmap, Palette
from launcher_config import LauncherConfig


class Toaster(TileGrid):
    def __init__(self, spritesheet, spritesheet_pixelshader):
        super().__init__(spritesheet, pixel_shader=spritesheet_pixelshader, width=1, height=1,
                         tile_width=64, tile_height=64)

    def advance_animation(self):
        if self[0] <= 3:
            self[0] += 1
        else:
            self[0] = 1


class FlyingToasterScreenSaver(Group):
    display_size = (640, 480)

    toaster_count = 6
    toast_count = 4
    
    def __init__(self):
        super().__init__()
        self.init_graphics()
    
    def init_graphics(self):

        config = LauncherConfig()
        if "screensaver.background_color" in config.data:
            bg_color_str = config.data["screensaver.background_color"]
        else:
            bg_color_str = "0x000000"

        if bg_color_str != "transparent":
            self.background_bmp = Bitmap(self.display_size[0] // 20, self.display_size[1] // 20, 1)
            self.background_palette = Palette(1)
            self.background_palette[0] = int(bg_color_str, 0)
            self.background_tg = TileGrid(bitmap=self.background_bmp, pixel_shader=self.background_palette)
            self.background_group = Group(scale=20)
            self.background_group.append(self.background_tg)
            self.append(self.background_group)

        os.chdir("/".join(__file__.split("/")[:-1]))

        self.sprite_sheet_bmp, self.sprite_sheet_palette = adafruit_imageload.load("toaster_spritesheet.bmp")
        self.sprite_sheet_palette.make_transparent(0)
        self.toasters = []
        self.toasts = []

        for i in range(self.toaster_count):
            new_toaster = Toaster(self.sprite_sheet_bmp, self.sprite_sheet_palette)
            new_toaster.x = random.randint(0, self.display_size[0] - new_toaster.tile_width)
            new_toaster.y = random.randint(0, self.display_size[0] - new_toaster.tile_width)
            new_toaster[0] = random.randint(1, 4)
            self.toasters.append(new_toaster)
            self.append(new_toaster)

        for i in range(self.toast_count):
            new_toast = TileGrid(bitmap=self.sprite_sheet_bmp, 
                                 pixel_shader=self.sprite_sheet_palette, height=1, width=1,
                                 tile_width=64, tile_height=64, default_tile=5)
            new_toast.x = random.randint(0, self.display_size[0] - new_toast.tile_width)
            new_toast.y = random.randint(0, self.display_size[0] - new_toast.tile_width)
            self.toasts.append(new_toast)
            self.append(new_toast)
    
    def tick(self):
        for toaster in self.toasters:
            toaster.x -= 2
            toaster.y += 2

            if toaster.x < (0 - toaster.tile_width):
                toaster.x = self.display_size[0]
            if toaster.y > self.display_size[1]:
                toaster.y = -64
                toaster.x += random.randint(0, 63)
            toaster.advance_animation()

        for toast in self.toasts:
            toast.x -= 2
            toast.y += 2

            if toast.x < (0 - toast.tile_width):
                toast.x = self.display_size[0]
                toast.y -= random.randint(0, 63)
            if toast.y > self.display_size[1]:
                toast.y = -64
                toast.x += random.randint(0, 63)

        return True