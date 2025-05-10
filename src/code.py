# SPDX-FileCopyrightText: 2025 Tim Cocks for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
Fruit Jam OS Launcher
"""
import array
import atexit
import json
import math
import os

import displayio

import supervisor
import sys

import terminalio

import adafruit_pathlib as pathlib
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.text_box import TextBox
from adafruit_display_text.bitmap_label import Label

from adafruit_displayio_layout.layouts.grid_layout import GridLayout
from adafruit_anchored_tilegrid import AnchoredTileGrid
import adafruit_imageload

from adafruit_usb_host_mouse import find_and_init_boot_mouse
from adafruit_anchored_group import AnchoredGroup
from adafruit_fruitjam.peripherals import request_display_config
from adafruit_argv_file import read_argv, write_argv

"""
desktop launcher code.py arguments

  0: next code files
1-N: args to pass to next code file

"""

args = read_argv(__file__)
if args is not None and len(args) > 0:
    next_code_file = None
    remaining_args = None
    if len(args) > 0:
        next_code_file = args[0]
    if len(args) > 1:
        remaining_args = args[1:]

    if remaining_args is not None:
        write_argv(next_code_file, remaining_args)

    next_code_file = next_code_file
    supervisor.set_next_code_file(next_code_file, sticky_on_reload=False, reload_on_error=True,
                                  working_directory="/".join(next_code_file.split("/")[:-1]))
    print(f"launching: {next_code_file}")
    supervisor.reload()

request_display_config(720, 400)
display = supervisor.runtime.display

scale = 1
if display.width > 360:
    scale = 2

font_file = "/fonts/terminal.lvfontbin"
font = bitmap_font.load_font(font_file)
scaled_group = displayio.Group(scale=scale)

main_group = displayio.Group()
main_group.append(scaled_group)

display.root_group = main_group

background_bmp = displayio.Bitmap(display.width, display.height, 1)
bg_palette = displayio.Palette(1)
bg_palette[0] = 0x222222
bg_tg = displayio.TileGrid(bitmap=background_bmp, pixel_shader=bg_palette)
scaled_group.append(bg_tg)

mouse = find_and_init_boot_mouse()

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
scaled_group.append(menu_grid)

menu_title_txt = Label(font, text="Fruit Jam OS")
menu_title_txt.anchor_point = (0.5, 0.5)
menu_title_txt.anchored_position = (display.width // (2 * scale), 2)
scaled_group.append(menu_title_txt)

app_titles = []
apps = []
app_path = pathlib.Path("/apps")
i = 0

pages = [{}]

cur_file_index = 0

for path in app_path.iterdir():
    print(path)

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

    i += 1


def reuse_cell(grid_coords):
    try:
        cell_group = menu_grid.get_content(grid_coords)
        return cell_group
    except KeyError:
        return None


def _create_cell_group(app):
    cell_group = AnchoredGroup()

    if app["icon"] is None:
        icon_tg = displayio.TileGrid(bitmap=default_icon_bmp, pixel_shader=default_icon_palette)
        cell_group.append(icon_tg)
    else:
        icon_bmp, icon_palette = adafruit_imageload.load(app["icon"])
        icon_tg = displayio.TileGrid(bitmap=icon_bmp, pixel_shader=icon_palette)
        cell_group.append(icon_tg)

    icon_tg.x = cell_width // 2 - icon_tg.tile_width // 2
    title_txt = TextBox(font, text=app["title"], width=WIDTH // config["width"], height=18,
                        align=TextBox.ALIGN_CENTER)
    cell_group.append(title_txt)
    title_txt.anchor_point = (0, 0)
    title_txt.anchored_position = (0, icon_tg.y + icon_tg.tile_height)
    return cell_group


def _reuse_cell_group(app, cell_group):
    _unhide_cell_group(cell_group)
    if app["icon"] is None:
        icon_tg = cell_group[0]
        icon_tg.bitmap = default_icon_bmp
        icon_tg.pixel_shader = default_icon_palette
    else:
        icon_bmp, icon_palette = adafruit_imageload.load(app["icon"])
        icon_tg = cell_group[0]
        icon_tg.bitmap = icon_bmp
        icon_tg.pixel_shader = icon_palette

    icon_tg.x = cell_width // 2 - icon_tg.tile_width // 2
    # title_txt = TextBox(font, text=app["title"], width=WIDTH // config["width"], height=18,
    #                     align=TextBox.ALIGN_CENTER)
    # cell_group.append(title_txt)
    title_txt = cell_group[1]
    title_txt.text = app["title"]
    # title_txt.anchor_point = (0, 0)
    # title_txt.anchored_position = (0, icon_tg.y + icon_tg.tile_height)


def _hide_cell_group(cell_group):
    # hide the tilegrid
    cell_group[0].hidden = True
    # set the title to blank space
    cell_group[1].text = "      "


def _unhide_cell_group(cell_group):
    # show tilegrid
    cell_group[0].hidden = False


def display_page(page_index):
    for grid_index in range(6):
        grid_pos = (grid_index % config["width"], grid_index // config["width"])
        try:
            cur_app = apps[grid_index + (page_index * 6)]
        except IndexError:
            try:
                cell_group = menu_grid.get_content(grid_pos)
                _hide_cell_group(cell_group)
            except KeyError:
                pass

            # skip to the next for loop iteration
            continue

        try:
            cell_group = menu_grid.get_content(grid_pos)
            _reuse_cell_group(cur_app, cell_group)
        except KeyError:
            cell_group = _create_cell_group(cur_app)
            menu_grid.add_content(cell_group, grid_position=grid_pos, cell_size=(1, 1))

        # app_titles.append(title_txt)
        print(f"{grid_index} | {grid_index % config["width"], grid_index // config["width"]}")


cur_page = 0
display_page(cur_page)

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
original_arrow_btn_color = left_palette[2]

scaled_group.append(left_tg)
scaled_group.append(right_tg)

if len(apps) <= 6:
    right_tg.hidden = True
    left_tg.hidden = True

if mouse is not None:
    mouse.scale = 2
    mouse.x = display.width - 6
    scaled_group.append(mouse.tilegrid)


help_txt = Label(terminalio.FONT, text="[Arrow]: Move\n[E]:     Edit\n[Enter]:  Run")
# help_txt = TextBox(terminalio.FONT, width=88, height=30, align=TextBox.ALIGN_RIGHT, background_color=0x008800, text="[E]: Edit\n[Enter]:  Run")
help_txt.anchor_point = (0, 0)

help_txt.anchored_position = (2, 2)
# help_txt.anchored_position = (display.width - 89, 1)

print(help_txt.bounding_box)
main_group.append(help_txt)


def atexit_callback():
    """
    re-attach USB devices to kernel if needed.
    :return:
    """
    print("inside atexit callback")
    if mouse is not None:
        mouse.release()


atexit.register(atexit_callback)

selected = None


def change_selected(new_selected):
    global selected
    # tuple means an item in the grid is selected
    if isinstance(selected, tuple):
        menu_grid.get_content(selected)[1].background_color = None

    # TileGrid means arrow is selected
    elif isinstance(selected, AnchoredTileGrid):
        selected.pixel_shader[2] = original_arrow_btn_color

    # tuple means an item in the grid is selected
    if isinstance(new_selected, tuple):
        menu_grid.get_content(new_selected)[1].background_color = 0x008800
    # TileGrid means arrow is selected
    elif isinstance(new_selected, AnchoredTileGrid):
        new_selected.pixel_shader[2] = 0x008800
    selected = new_selected


change_selected((0, 0))


def handle_key_press(key):
    global index, editor_index, cur_page
    # print(key)
    # up key
    if key == "\x1b[A":
        if isinstance(selected, tuple):
            change_selected((selected[0], (selected[1] - 1) % 2))
        elif selected is left_tg:
            change_selected((0, 0))
        elif selected is right_tg:
            change_selected((2, 0))


    # down key
    elif key == "\x1b[B":
        if isinstance(selected, tuple):
            change_selected((selected[0], (selected[1] + 1) % 2))
        elif selected is left_tg:
            change_selected((0, 1))
        elif selected is right_tg:
            change_selected((2, 1))
        # selected = min(len(config["apps"]) - 1, selected + 1)

    # left key
    elif key == "\x1b[D":
        if isinstance(selected, tuple):
            if selected[0] >= 1:
                change_selected((selected[0] - 1, selected[1]))
            elif not left_tg.hidden:
                change_selected(left_tg)
            else:
                change_selected(((selected[0] - 1) % 3, selected[1]))
        elif selected is left_tg:
            change_selected(right_tg)
        elif selected is right_tg:
            change_selected((2, 0))

    # right key
    elif key == "\x1b[C":
        if isinstance(selected, tuple):
            if selected[0] <= 1:
                change_selected((selected[0] + 1, selected[1]))
            elif not right_tg.hidden:
                change_selected(right_tg)
            else:
                change_selected(((selected[0] + 1) % 3, selected[1]))
        elif selected is left_tg:
            change_selected((0, 0))
        elif selected is right_tg:
            change_selected(left_tg)

    elif key == "\n":
        if isinstance(selected, tuple):
            index = (selected[1] * 3 + selected[0]) + (cur_page * 6)
            if index >= len(apps):
                index = None
            print("go!")
        elif selected is left_tg:
            if cur_page > 0:
                cur_page -= 1
                display_page(cur_page)

        elif selected is right_tg:
            if cur_page < math.ceil(len(apps) / 6) - 1:
                cur_page += 1
                display_page(cur_page)

    elif key == "e":
        if isinstance(selected, tuple):
            editor_index = (selected[1] * 3 + selected[0]) + (cur_page * 6)
            if editor_index >= len(apps):
                editor_index = None

            print("go!")
    else:
        print(f"unhandled key: {repr(key)}")


print(f"apps: {apps}")
# print(mouse_interface_index, mouse_endpoint_address)
while True:
    index = None
    editor_index = None

    available = supervisor.runtime.serial_bytes_available
    if available:
        c = sys.stdin.read(available)
        print(repr(c))
        # app_titles[selected].background_color = None

        handle_key_press(c)
        print("selected", selected)
        # app_titles[selected].background_color = 0x008800

    if mouse:
        pressed_btns = mouse.update()

        if pressed_btns is not None and "left" in pressed_btns:
            print("left click")
            clicked_cell = menu_grid.which_cell_contains((mouse.x, mouse.y))
            if clicked_cell is not None:
                index = clicked_cell[1] * config["width"] + clicked_cell[0]

            clicked_coords = (mouse.x, mouse.y, 0)
            if left_tg.contains(clicked_coords):
                if cur_page > 0:
                    cur_page -= 1
                    display_page(cur_page)
            elif right_tg.contains(clicked_coords):
                if cur_page < math.ceil(len(apps) / 6) - 1:
                    cur_page += 1
                    display_page(cur_page)

    if index is not None:
        print("index", index)
        print(f"selected: {apps[index]}")
        launch_file = apps[index]["file"]
        supervisor.set_next_code_file(launch_file, sticky_on_reload=False, reload_on_error=True,
                                      working_directory="/".join(launch_file.split("/")[:-1]))
        supervisor.reload()
    if editor_index is not None:
        print("editor_index", editor_index)
        print(f"editor selected: {apps[editor_index]}")
        edit_file = apps[editor_index]["file"]

        editor_launch_file = "apps/editor/code.py"
        write_argv(editor_launch_file, [apps[editor_index]["file"]])
        # with open(argv_filename(launch_file), "w") as f:
        #     f.write(json.dumps([apps[editor_index]["file"]]))

        supervisor.set_next_code_file(editor_launch_file, sticky_on_reload=False, reload_on_error=True,
                                      working_directory="/".join(editor_launch_file.split("/")[:-1]))
        supervisor.reload()
