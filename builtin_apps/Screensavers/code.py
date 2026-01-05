# SPDX-FileCopyrightText: 2025 Tim Cocks for Adafruit Industries
# SPDX-FileCopyrightText: 2026 Cooper Dalrymple (@relic-se)
# SPDX-License-Identifier: MIT

import atexit
import displayio
import os
import supervisor
import sys
import terminalio

from adafruit_anchored_tilegrid import AnchoredTileGrid
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.bitmap_label import Label
from adafruit_fruitjam.peripherals import request_display_config, VALID_DISPLAY_SIZES
import adafruit_imageload
import adafruit_pathlib as pathlib
from adafruit_usb_host_mouse import find_and_init_boot_mouse

from launcher_config import LauncherConfig

launcher_config = LauncherConfig()

def get_screensaver_modules() -> list:
    screensavers = []

    for name in os.listdir():
        if not name.startswith(".") and name.endswith("_screensaver.py"):
            screensavers.append(os.getcwd() + "/" + name[:-len(".py")])

    for dir in ("/screensavers/", "/sd/screensavers/"):
        if pathlib.Path(dir).exists():
            for name in os.listdir(dir):
                if not name.startswith("."):
                    screensavers.append(dir + (name[:-len(".py")] if name.endswith(".py") else name))
    
    return screensavers

def get_screensaver_title(module_name: str) -> str:
    # get last segment of module
    title = module_name.split("/")[-1]

    # remove unneeded prepend/append
    if title.endswith("_screensaver"):
        title = title[:-len("_screensaver")]
    elif title.startswith("Fruit_Jam_Screensaver_"):
        title = title[len("Fruit_Jam_Screensaver_"):]
    elif title.startswith("Fruit_Jam_"):
        title = title[len("Fruit_Jam_"):]
    
    # add spaces
    title = title.replace("_", " ")

    # capitalize words
    title = " ".join(map(lambda x: x[0].upper() + x[1:], title.split(" ")))
    return title

screensaver_modules = get_screensaver_modules()
if not screensaver_modules:
    raise ValueError("No screensavers found!")
print("Available Screensaver Modules:")
for module_name in screensaver_modules:
    print(module_name)

try:
    screensaver_index = screensaver_modules.index(launcher_config.screensaver_module)
except ValueError:
    screensaver_index = 0

if (width_config := os.getenv("CIRCUITPY_DISPLAY_WIDTH")) is not None:
    if width_config not in [x[0] for x in VALID_DISPLAY_SIZES]:
        raise ValueError(f"Invalid display size. Must be one of: {VALID_DISPLAY_SIZES}")
    for display_size in VALID_DISPLAY_SIZES:
        if display_size[0] == width_config:
            break
else:
    display_size = (720, 400)
request_display_config(*display_size)
display = supervisor.runtime.display
display.auto_refresh = False

main_group = displayio.Group()
display.root_group = main_group

bg_bmp = displayio.Bitmap(display.width, display.height, 1)
bg_palette = displayio.Palette(1)
bg_palette[0] = launcher_config.palette_bg
bg_tg = displayio.TileGrid(bitmap=bg_bmp, pixel_shader=bg_palette)
main_group.append(bg_tg)

screensaver_group = displayio.Group()
main_group.append(screensaver_group)

help_label = Label(terminalio.FONT, text="[Arrow]: Change [Enter]: Select [Escape] Exit",
                   color=launcher_config.palette_fg)
help_label.anchor_point = (0.0, 1.0)
help_label.anchored_position = (2, display.height - 2)
main_group.append(help_label)

SCALE = int(display.width > 360) + 1
scaled_group = displayio.Group(scale=SCALE)
main_group.append(scaled_group)

title_label = Label(terminalio.FONT, text="",
                    color=launcher_config.palette_fg,
                    outline_color=launcher_config.palette_bg, outline_size=1)
title_label.anchor_point = (0.5, 0.0)
title_label.anchored_position = (display.width // (2 * SCALE), 2)
scaled_group.append(title_label)

left_bmp, left_palette = adafruit_imageload.load("/launcher_assets/arrow_left.bmp")
left_palette.make_transparent(0)
left_palette[2] = launcher_config.palette_arrow
left_tg = AnchoredTileGrid(bitmap=left_bmp, pixel_shader=left_palette)
left_tg.anchor_point = (0, 0.5)
left_tg.anchored_position = (0, (display.height // (2 * SCALE)) - 2)
scaled_group.append(left_tg)

right_bmp, right_palette = adafruit_imageload.load("/launcher_assets/arrow_right.bmp")
right_palette.make_transparent(0)
right_palette[2] = launcher_config.palette_arrow
right_tg = AnchoredTileGrid(bitmap=right_bmp, pixel_shader=right_palette)
right_tg.anchor_point = (1.0, 0.5)
right_tg.anchored_position = ((display.width // SCALE), (display.height // (2 * SCALE)) - 2)
scaled_group.append(right_tg)

font = bitmap_font.load_font("/fonts/terminal.lvfontbin")

if launcher_config.can_save():
    save_icon_label = Label(font, text="💾", color=launcher_config.palette_arrow)
    save_icon_label.anchor_point = (1.0, 0.0)
    save_icon_label.anchored_position = (display.width // SCALE, 0)
    scaled_group.append(save_icon_label)
else:
    save_icon_label = None

mouse = None
last_left_button_state = False
previous_mouse_location = (0, 0)
if launcher_config.use_mouse:
    mouse = find_and_init_boot_mouse()
    if mouse:
        mouse.scale = SCALE

        exit_icon_label = Label(font, text="🔙", color=launcher_config.palette_arrow)
        exit_icon_label.anchor_point = (0.0, 0.0)
        exit_icon_label.anchored_position = (0, 0)
        scaled_group.append(exit_icon_label)

        mouse_tg = mouse.tilegrid
        mouse_tg.x = display.width // (2 * SCALE)
        mouse_tg.y = display.height // (2 * SCALE)
        scaled_group.append(mouse_tg)

def atexit_callback():
    if mouse and mouse.was_attached and not mouse.device.is_kernel_driver_active(0):
        mouse.device.attach_kernel_driver(0)
atexit.register(atexit_callback)

screensaver = None
def change(index: int = None) -> None:
    global screensaver, screensaver_index, display, SCALE

    # remove existing screensaver
    if screensaver is not None:
        screensaver_group.remove(screensaver)
        del screensaver
    
    # update index
    if index is not None:
        screensaver_index = index % len(screensaver_modules)
    screensaver_module = screensaver_modules[screensaver_index]
    print(f"Selected Index: {screensaver_index}")
    print(f"Selected Module: {screensaver_module}")

    # get screensaver object
    screensaver = launcher_config.get_screensaver(screensaver_module)
    if screensaver is None:
        raise ValueError(f"ScreenSaver class not found in {screensaver_module}")
    
    # update title label
    title_label.text = get_screensaver_title(screensaver_module)

    # update icon state
    if save_icon_label:
        save_icon_label.color = launcher_config.palette_fg if screensaver_module == launcher_config.screensaver_module else launcher_config.palette_arrow
    
    # assign display size if necessary
    if hasattr(screensaver, "display_size"):
        request_display_config(*screensaver.display_size)
        display = supervisor.runtime.display
        if display.root_group != main_group:
            display.root_group = main_group
        
        # update scale
        SCALE = int(display.width > 360) + 1
        scaled_group.scale = SCALE

        # reset positions
        help_label.anchored_position = (2, display.height - 2)
        title_label.anchored_position = (display.width // (2 * SCALE), 2)
        left_tg.anchored_position = (0, (display.height // (2 * SCALE)) - 2)
        right_tg.anchored_position = ((display.width // SCALE), (display.height // (2 * SCALE)) - 2)
        if save_icon_label:
            save_icon_label.anchored_position = (display.width // SCALE, 0)
        if mouse:
            mouse.scale = SCALE

    # display screensaver
    if screensaver not in screensaver_group:
        screensaver_group.append(screensaver)
    display.refresh()

def next() -> None:
    change(screensaver_index + 1)

def previous() -> None:
    change(screensaver_index - 1)

def save() -> None:
    if (screensaver_module := screensaver_modules[screensaver_index]) != launcher_config.screensaver_module:
        print("Saving launcher config to /saves/launcher.config.json")
        launcher_config.screensaver_module = screensaver_module
        launcher_config.screensaver_class = ""
        if launcher_config.save() and save_icon_label:
            save_icon_label.color = launcher_config.palette_fg
            display.refresh()
        else:
            print("Write operation failed")

# display initial screensaver
change()

def handle_key_press(key):
    if key in ("\x1b[A", "\x1b[D"):  # up or left
        previous()
    elif key in ("\x1b[B", "\x1b[C"):  # down or right
        next()
    elif key in "\n":  # enter
        save()
    elif key == "\x1b":  # escape
        raise KeyboardInterrupt()

def label_contains(label: Label, mouse_pos: tuple[int, int]) -> bool:
    label_x, label_y, label_width, label_height = [x * label.scale for x in label.bounding_box]
    label_x += label.x
    label_y += label.y
    return 0 <= mouse_pos[0] - label_x <= label_width and 0 <= mouse_pos[1] - label_y <= label_height
    
# flush keyboard input
while supervisor.runtime.serial_bytes_available:
    sys.stdin.read()

try:
    while True:
        needs_refresh = screensaver.tick()

        available = supervisor.runtime.serial_bytes_available
        if available:
            c = sys.stdin.read(available)
            handle_key_press(c)

        if mouse:
            buttons = mouse.update()

            if (mouse.x, mouse.y) != previous_mouse_location:
                previous_mouse_location = (mouse.x, mouse.y)
                needs_refresh = True

            current_left_button_state = buttons is not None and "left" in buttons
            if current_left_button_state != last_left_button_state and current_left_button_state:
                if right_tg.contains((mouse_tg.x, mouse_tg.y, 0)):
                    next()
                elif left_tg.contains((mouse_tg.x, mouse_tg.y, 0)):
                    previous()
                elif save_icon_label and label_contains(save_icon_label, (mouse_tg.x, mouse_tg.y)):
                    save()
                elif label_contains(exit_icon_label, (mouse_tg.x, mouse_tg.y)):
                    break
            last_left_button_state = current_left_button_state
        
        if needs_refresh:
            display.refresh()

except KeyboardInterrupt:
    pass

finally:
    supervisor.reload()
