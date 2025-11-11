import os
import random
import adafruit_imageload
import supervisor
from displayio import TileGrid, Group, OnDiskBitmap, Bitmap, Palette
from launcher_config import LauncherConfig




fish_sprite_choices = [
    (0, 1),
    (2, 3),
    (4, 5),
    (6, 7),
    (8, 9),
    (10, 11),
    (12, 13),
    (14, 15),
    (16, 17),
    (18, 19),
    (20, 21),
    (22, 23),
    (24, 25),
    (26, 27),
]


class Bubble(TileGrid):
    cooldown = 0

    def __init__(self, spritesheet, pixel_shader):
        super().__init__(spritesheet, pixel_shader=pixel_shader,
                         width=1, height=1,tile_width=30, tile_height=30)


class Fish(TileGrid):
    tile_indexes = (0, 1)
    direction = -2

    animate_cooldown = 4
    max_animate_cooldown = 4

    def __init__(self, spritesheet, spritesheet_pixelshader):
        super().__init__(spritesheet, pixel_shader=spritesheet_pixelshader, width=1, height=1,
                         tile_width=68, tile_height=68)

    def advance_animation(self):
        if self[0] not in self.tile_indexes:
            self[0] = random.choice(self.tile_indexes)
        self.animate_cooldown -= 1
        if self.animate_cooldown <= 0:
            self.animate_cooldown = self.max_animate_cooldown
            self[0] = self.tile_indexes[0] if self[0] == self.tile_indexes[1] else self.tile_indexes[1]

class FishScreenSaver(Group):
    display_size = (640, 480)

    fish_count = 7
    bubble_count = 2
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

        self.sprite_sheet_bmp, self.sprite_sheet_palette = adafruit_imageload.load("fish_sprites.bmp")
        self.sprite_sheet_palette.make_transparent(0)

        self.bubble_bmp, self.bubble_pixel_shader = adafruit_imageload.load("bubble_sprites.bmp")
        self.bubble_pixel_shader.make_transparent(0)

        self.all_fish = []
        self.all_bubbles = []

        self.ground_odb = OnDiskBitmap("ground.bmp")
        self.ground_tg = TileGrid(bitmap=self.ground_odb, pixel_shader=self.ground_odb.pixel_shader)
        self.ground_tg.y = self.display_size[1] - self.ground_tg.tile_height
        self.append(self.ground_tg)

        self.plant_odb = OnDiskBitmap("seaweed.bmp")
        self.plant_odb.pixel_shader.make_transparent(0)
        self.plant_tg = TileGrid(bitmap=self.plant_odb, pixel_shader=self.plant_odb.pixel_shader)
        self.plant_tg.y = random.randint(self.display_size[1] - self.plant_tg.tile_height - 20,
                                         self.display_size[1] - self.plant_tg.tile_height)
        self.plant_tg.x = random.randint(0, self.display_size[0] - self.plant_tg.tile_width)

        for i in range(self.fish_count):
            new_fish = Fish(self.sprite_sheet_bmp, self.sprite_sheet_palette)
            new_fish.x = random.randint(0, self.display_size[0] - new_fish.tile_width)
            new_fish.y = random.randint(0, self.display_size[1] - new_fish.tile_height - self.plant_tg.tile_height)
            new_fish.tile_indexes = random.choice(fish_sprite_choices)

            if random.randint(0, 1) == 1:
                new_fish.flip_x = True
                new_fish.direction = -2
            else:
                new_fish.direction = 2
            self.all_fish.append(new_fish)
            self.append(new_fish)

        for i in range(self.bubble_count):
            new_bubble = Bubble(self.bubble_bmp, self.bubble_pixel_shader)
            new_bubble.x = random.randint(0, self.display_size[0] - new_bubble.tile_width)
            new_bubble.y = self.display_size[1] - new_bubble.tile_height
            new_bubble.hidden = True
            new_bubble.cooldown = i * 10

            if i % 2 == 0:
                self.append(new_bubble)
            else:
                self.insert(2, new_bubble)
            self.all_bubbles.append(new_bubble)

        self.insert(5, self.plant_tg)

    def tick(self):
        for fish in self.all_fish:
            fish.x += fish.direction
            if random.randint(0, 3) == 1:
                if fish.y < 6:
                    fish.y += 2
                elif fish.y >= self.display_size[1] - fish.tile_height - 34:
                    fish.y -= 2
                else:
                    fish.y += random.choice((2, -2))

            if fish.x < (0 - fish.tile_width):
                fish.x = self.display_size[0]
                fish.tile_indexes = random.choice(fish_sprite_choices)
                fish.y = random.randint(6, self.display_size[1] - fish.tile_height - 34)
            elif fish.x > self.display_size[0]:
                fish.x = 0 - fish.tile_width
                fish.tile_indexes = random.choice(fish_sprite_choices)
                fish.y = random.randint(6, self.display_size[1] - fish.tile_height - 34)

            fish.advance_animation()

        for bubble in self.all_bubbles:
            if bubble.cooldown > 0:
                bubble.cooldown -= 1

                if bubble.cooldown == 0:
                    bubble.hidden = False
                continue

            bubble.y -= 2
            if bubble.y % 8 == 0:
                bubble[0] = 1 if bubble[0] == 0 else 0

            if bubble.y < 0 - bubble.tile_height - 30:
                bubble.y = self.display_size[1] - bubble.tile_height
                bubble.x = random.randint(0, self.display_size[0] - bubble.tile_width)
                bubble.hidden = True
                bubble.cooldown = random.randint(30, 140)

        return True
