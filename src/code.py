# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
This example uses adafruit_display_text.label to display text using a custom font
loaded by adafruit_bitmap_font
"""
import array
import atexit
import json

import displayio

import supervisor
import sys
import usb
import adafruit_pathlib as pathlib
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.text_box import TextBox
from adafruit_display_text.bitmap_label import Label
from adafruit_displayio_layout.layouts.grid_layout import GridLayout
from adafruit_anchored_tilegrid import AnchoredTileGrid
import adafruit_imageload
import adafruit_usb_host_descriptors
from adafruit_anchored_group import AnchoredGroup

display = supervisor.runtime.display

scale = 1
if display.width > 360:
    scale = 2

font_file = "/fonts/terminal.lvfontbin"
font = bitmap_font.load_font(font_file)
main_group = displayio.Group(scale=scale)
display.root_group = main_group

background_bmp = displayio.Bitmap(display.width, display.height, 1)
bg_palette = displayio.Palette(1)
bg_palette[0] = 0x222222
bg_tg = displayio.TileGrid(bitmap=background_bmp, pixel_shader=bg_palette)
main_group.append(bg_tg)

# load the mouse cursor bitmap
mouse_bmp = displayio.OnDiskBitmap("launcher_assets/mouse_cursor.bmp")

# make the background pink pixels transparent
mouse_bmp.pixel_shader.make_transparent(0)

# create a TileGrid for the mouse, using its bitmap and pixel_shader
mouse_tg = displayio.TileGrid(mouse_bmp, pixel_shader=mouse_bmp.pixel_shader)

# move it to the center of the display
mouse_tg.x = display.width // (2 * scale)
mouse_tg.y = display.height // (2 * scale)
# 046d:c52f


# mouse = usb.core.find(idVendor=0x046d, idProduct=0xc52f)

DIR_IN = 0x80
mouse_interface_index, mouse_endpoint_address = None, None
mouse = None
# scan for connected USB device and loop over any found
print("scanning usb")
for device in usb.core.find(find_all=True):
    # print device info
    print(f"{device.idVendor:04x}:{device.idProduct:04x}")
    print(device.manufacturer, device.product)
    print()
    config_descriptor = adafruit_usb_host_descriptors.get_configuration_descriptor(
        device, 0
    )
    print(config_descriptor)
    #
    # i = 0
    # while i < len(config_descriptor):
    #     descriptor_len = config_descriptor[i]
    #     descriptor_type = config_descriptor[i + 1]
    #     if descriptor_type == adafruit_usb_host_descriptors.DESC_CONFIGURATION:
    #         config_value = config_descriptor[i + 5]
    #         print(f" value {config_value:d}")
    #     elif descriptor_type == adafruit_usb_host_descriptors.DESC_INTERFACE:
    #         interface_number = config_descriptor[i + 2]
    #         interface_class = config_descriptor[i + 5]
    #         interface_subclass = config_descriptor[i + 6]
    #         interface_protocol = config_descriptor[i + 7]
    #         print(f" interface[{interface_number:d}]")
    #         print(
    #             f"  class {interface_class:02x} subclass {interface_subclass:02x}"
    #         )
    #         print(f"protocol: {interface_protocol}")
    #     elif descriptor_type == adafruit_usb_host_descriptors.DESC_ENDPOINT:
    #         endpoint_address = config_descriptor[i + 2]
    #         if endpoint_address & DIR_IN:
    #             print(f"  IN {endpoint_address:02x}")
    #         else:
    #             print(f"  OUT {endpoint_address:02x}")
    #     i += descriptor_len
    # print()
    #
    # # assume the device is the mouse
    # mouse = device
    mouse_interface_index, mouse_endpoint_address = adafruit_usb_host_descriptors.find_boot_mouse_endpoint(device)
    if mouse_interface_index is not None and mouse_endpoint_address is not None:
        mouse = device
        print(f"mouse interface: {mouse_interface_index} endpoint_address: {hex(mouse_endpoint_address)}")

mouse_was_attached = None
if mouse is not None:
    # detach the kernel driver if needed
    if mouse.is_kernel_driver_active(0):
        mouse_was_attached = True
        mouse.detach_kernel_driver(0)
    else:
        mouse_was_attached = False

    # set configuration on the mouse so we can use it
    mouse.set_configuration()

mouse_buf = array.array("b", [0] * 8)
WIDTH = 280
HEIGHT = 182

config = {
    "menu_title": "Launcher Menu",
    "width": 3,
    "height": 2,
    "apps": [
        {
            "title": "🐍Snake🐍",
            "icon": "icon_snake.bmp",
            "file": "code_snake_game.py"
        },
        {
            "title": "Nyan😺Flap",
            "icon": "icon_flappynyan.bmp",
            "file": "code_flappy_nyan.py"
        },
        {
            "title": "Memory🧠",
            "icon": "icon_memory.bmp",
            "file": "code_memory.py"
        },
        {
            "title": "Matrix",
            "icon": "/apps/matrix/icon.bmp",
            "file": "/apps/matrix/code.py"
        },
        {
            "title": "Breakout",
            "icon": "icon_breakout.bmp",
            "file": "code_breakout.py"
        },
        {
            "title": "Paint🖌️",
            "icon": "icon_paint.bmp",
        }

    ]
}

cell_width = WIDTH // config["width"]

default_icon_bmp, default_icon_palette = adafruit_imageload.load("launcher_assets/default_icon.bmp")
default_icon_palette.make_transparent(0)
menu_grid = GridLayout(x=40, y=16, width=WIDTH, height=HEIGHT, grid_size=(config["width"], config["height"]),
                       divider_lines=False)
main_group.append(menu_grid)

menu_title_txt = Label(font, text=config["menu_title"])
menu_title_txt.anchor_point = (0.5, 0.5)
menu_title_txt.anchored_position = (display.width // (2 * scale), 2)
main_group.append(menu_title_txt)

app_titles = []
apps = []
app_path = pathlib.Path("/apps")
i = 0

pages = [{}]

cur_file_index = 0
cur_page = 0
for path in app_path.iterdir():
    print(path)
    cell_group = AnchoredGroup()

    code_file = path / "code.py"
    if not code_file.exists():
        continue

    metadata_file = path / "metadata.json"
    if not metadata_file.exists():
        metadata_file = None
        metadata = None
    if metadata_file is not None:
        with open(metadata_file.absolute(), "r") as f:
            metadata = json.load(f)

    if metadata is not None and "icon" in metadata:
        icon_file = path / metadata["icon"]
    else:
        icon_file = path / "icon.bmp"

    if not icon_file.exists():
        icon_file = None

    if metadata is not None and "title" in metadata:
        title = metadata["title"]
    else:
        title = path.name

    apps.append({
        "title": title,
        "icon": str(icon_file.absolute()) if icon_file is not None else None,
        "file": str(code_file.absolute())
    })
    if apps[-1]["icon"] is None:
        icon_tg = displayio.TileGrid(bitmap=default_icon_bmp, pixel_shader=default_icon_palette)
        cell_group.append(icon_tg)
    else:
        icon_bmp, icon_palette = adafruit_imageload.load(apps[-1]["icon"])
        icon_tg = displayio.TileGrid(bitmap=icon_bmp, pixel_shader=icon_palette)
        cell_group.append(icon_tg)

    icon_tg.x = cell_width // 2 - icon_tg.tile_width // 2
    title_txt = TextBox(font, text=apps[-1]["title"], width=WIDTH // config["width"], height=18,
                        align=TextBox.ALIGN_CENTER)
    cell_group.append(title_txt)
    title_txt.anchor_point = (0, 0)
    title_txt.anchored_position = (0, icon_tg.y + icon_tg.tile_height)
    app_titles.append(title_txt)
    menu_grid.add_content(cell_group, grid_position=(i % config["width"], i // config["width"]), cell_size=(1, 1))
    i += 1

left_bmp, left_palette = adafruit_imageload.load("launcher_assets/arrow_left.bmp")
left_palette.make_transparent(0)
right_bmp, right_palette = adafruit_imageload.load("launcher_assets/arrow_right.bmp")
right_palette.make_transparent(0)

left_tg = AnchoredTileGrid(bitmap=left_bmp, pixel_shader=left_palette)
left_tg.anchor_point = (0, 0.5)
left_tg.anchored_position = (4, (display.height // 2 // scale) - 2)

right_tg = AnchoredTileGrid(bitmap=right_bmp, pixel_shader=right_palette)
right_tg.anchor_point = (1.0, 0.5)
right_tg.anchored_position = ((display.width // scale) - 4, (display.height // 2 // scale) - 2)

main_group.append(left_tg)
main_group.append(right_tg)

if mouse:
    main_group.append(mouse_tg)

selected = 0


def atexit_callback():
    """
    re-attach USB devices to kernel if needed.
    :return:
    """
    print("inside atexit callback")
    if mouse_was_attached and not mouse.is_kernel_driver_active(0):
        mouse.attach_kernel_driver(0)

atexit.register(atexit_callback)

# print(f"apps: {apps}")
while True:
    index = None

    available = supervisor.runtime.serial_bytes_available
    if available:
        c = sys.stdin.read(available)
        print(repr(c))
        app_titles[selected].background_color = None

        if c == "\x1b[A":
            selected = max(0, selected - 1)
        elif c == "\x1b[B":
            selected = min(len(config["apps"]) - 1, selected + 1)
        elif c == "\n":
            index = selected
            print("go!")
        print("selected", selected)
        app_titles[selected].background_color = 0x008800

    if mouse:
        try:
            # attempt to read data from the mouse
            # 10ms timeout, so we don't block long if there
            # is no data
            count = mouse.read(mouse_endpoint_address, mouse_buf, timeout=20)
        except usb.core.USBTimeoutError:
            # skip the rest of the loop if there is no data
            count = 0

        # update the mouse tilegrid x and y coordinates
        # based on the delta values read from the mouse
        if count > 0:
            mouse_tg.x = max(0, min((display.width // scale) - 1, mouse_tg.x + mouse_buf[1]))
            mouse_tg.y = max(0, min((display.height // scale) - 1, mouse_tg.y + mouse_buf[2]))

            if mouse_buf[0] & (1 << 0) != 0:
                clicked_cell = menu_grid.which_cell_contains((mouse_tg.x, mouse_tg.y))
                if clicked_cell is not None:
                    index = clicked_cell[1] * config["width"] + clicked_cell[0]

    if index is not None:
        # print("index", index)
        # print(f"selected: {apps[index]}")
        launch_file = apps[index]["file"]
        supervisor.set_next_code_file(launch_file, sticky_on_reload=True, reload_on_error=True,
                                      working_directory="/".join(launch_file.split("/")[:-1]))

        if mouse and not mouse.is_kernel_driver_active(0):
            mouse.attach_kernel_driver(0)
        supervisor.reload()
