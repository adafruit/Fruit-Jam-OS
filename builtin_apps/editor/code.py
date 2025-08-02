import atexit
import os

import supervisor
from displayio import Group, Palette, TileGrid
from adafruit_display_text.bitmap_label import Label
from adafruit_editor import editor, picker
from tilepalettemapper import TilePaletteMapper
from adafruit_argv_file import read_argv, write_argv
from adafruit_fruitjam.peripherals import request_display_config
from adafruit_usb_host_mouse import find_and_init_boot_mouse
import terminalio
import usb

print(f"cwd in editor/code.py: {os.getcwd()}")

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

highlight_palette = Palette(3)
highlight_palette[0] = 0x000000
highlight_palette[1] = 0xFFFFFF
highlight_palette[2] = 0xC9C9C9


tpm = TilePaletteMapper(highlight_palette, 2)
terminal_area = TileGrid(bitmap=font.bitmap, width=screen_size[0], height=screen_size[1],
                         tile_width=char_size[0], tile_height=char_size[1], pixel_shader=tpm)

for x in range(screen_size[0]):
    tpm[x,screen_size[1]-1] = [2,0]

main_group.append(terminal_area)

terminal = terminalio.Terminal(terminal_area, font)

# visible_cursor = Label(terminalio.FONT, text="",
#                        color=0x000000, background_color=0xeeeeee, padding_left=1)
# visible_cursor.hidden = False
# visible_cursor.anchor_point = (0, 0)
# visible_cursor.anchored_position = (0, 0)
# main_group.append(visible_cursor)

file = None
args = read_argv(__file__)
if args is not None and len(args) > 0:
    file = args[0]
else:
    file = picker.pick_file(terminal)

usb_device_count = 0
for dev in usb.core.find(find_all=True):
    usb_device_count += 1

mouse = None
if usb_device_count > 1:
    mouse = find_and_init_boot_mouse()

if mouse is not None:
    mouse.x = display.width - 6
    main_group.append(mouse.tilegrid)


def atexit_callback():
    """
    re-attach USB devices to kernel if needed.
    :return:
    """
    print("inside atexit callback")
    if mouse is not None:
        mouse.release()

atexit.register(atexit_callback)
editor.edit(file, terminal, mouse, terminal_area)
