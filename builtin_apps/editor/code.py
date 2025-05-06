import os

import supervisor
from displayio import Group, Palette, TileGrid
import terminalio
from lvfontio import OnDiskFont
from adafruit_display_text.bitmap_label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_editor import editor, picker
from tilepalettemapper import TilePaletteMapper
import json
from adafruit_argv_file import read_argv, write_argv
from adafruit_fruitjam.peripherals import request_display_config

request_display_config(720, 400)
display = supervisor.runtime.display
display.auto_refresh = True

main_group = Group()

display.root_group = main_group

font_palette = Palette(2)
font_palette[0] = 0x000000
font_palette[1] = 0xFFFFFF


font = terminalio.FONT
char_size = font.get_bounding_box()
screen_size = (display.width // char_size[0], display.height // char_size[1])
print(screen_size)

terminal_area = TileGrid(bitmap=font.bitmap, pixel_shader=font_palette, width=screen_size[0], height=screen_size[1],
                         tile_width=char_size[0], tile_height=char_size[1])

main_group.append(terminal_area)

terminal = terminalio.Terminal(terminal_area, font)

visible_cursor = Label(terminalio.FONT, text="",
                       color=0x000000, background_color=0xeeeeee, padding_left=1)
visible_cursor.hidden = False
visible_cursor.anchor_point = (0, 0)
visible_cursor.anchored_position = (0, 0)
main_group.append(visible_cursor)

file = None
args = read_argv(__file__)
if args is not None and len(args) > 0:
    file = args[0]
else:
    file = picker.pick_file(terminal)

editor.edit(file, terminal, visible_cursor)
