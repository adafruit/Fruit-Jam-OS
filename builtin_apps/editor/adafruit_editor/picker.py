# SPDX-FileCopyrightText: 2023 Jeff Epler for Adafruit Industries
# SPDX-FileCopyrightText: 2024 Tim Cocks for Adafruit Industries
#
# SPDX-License-Identifier: MIT

import os
import time

import usb_cdc
from . import dang as curses
from . import util

# pylint: disable=redefined-builtin

# def print(message):
#     usb_cdc.data.write(f"{message}\r\n".encode("utf-8"))


always = ["code.py", "boot.py", "settings.toml", "boot_out.txt"]
good_extensions = [".py", ".toml", ".txt", ".json"]


def os_exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError:
        return False


def isdir(filename):
    return os.stat(filename)[0] & 0o40_000


def has_good_extension(filename):
    for g in good_extensions:
        if filename.endswith(g):
            return True
    return False


def picker(stdscr, options, notes=(), start_idx=0):
    stdscr.erase()
    visible_files = None
    if len(options) > curses.LINES - 1:
        visible_files = options[:curses.LINES - 1]
    else:
        visible_files = options

    scroll_offset = 0
    need_to_scroll = False

    # del options[curses.LINES - 1:]
    print(f"len opts: {len(options)}")
    print(f"len vis: {len(visible_files)}")

    def _draw_file_list():

        for row, option in enumerate(visible_files):
            if row < len(notes) and (note := notes[row]):
                option = f"{option} {note}"
            try:
                space_count = max(len(visible_files[row + 1]), len(visible_files[row - 1])) - len(option)
                if space_count < 0:
                    space_count = 0
            except IndexError:
                space_count = curses.COLS - len(option)
            stdscr.addstr(row, 3, option + " " * space_count)
        stdscr.addstr(curses.LINES - 1, 0, "Enter: select | ^C: quit | ^N: New")

    _draw_file_list()

    old_idx = None
    idx = start_idx
    while True:

        if need_to_scroll:
            need_to_scroll = False
            _draw_file_list()

        if idx != old_idx:
            if old_idx is not None:
                stdscr.addstr(old_idx, 0, "  ")
            stdscr.addstr(idx, 0, "=>")
            old_idx = idx

        k = stdscr.getkey()

        if k == "KEY_DOWN":
            print(f"{scroll_offset + len(visible_files)} < {len(options)}")
            if scroll_offset + len(visible_files) < len(options):
                if idx == len(visible_files) - 1:
                    need_to_scroll = True
                    scroll_offset += 1
                    visible_files = options[scroll_offset:scroll_offset + curses.LINES - 1]
            idx = min(idx + 1, len(visible_files) - 1)

        elif k == "KEY_UP":
            if scroll_offset > 0:
                if idx == 0:
                    need_to_scroll = True
                    scroll_offset -= 1
                    visible_files = options[scroll_offset:scroll_offset + curses.LINES - 1]
            idx = max(idx - 1, 0)
        elif k == "\n":
            if visible_files[idx] == "../":
                os.chdir("../")
                options, notes = _files_list()
                return picker(stdscr, options, notes)
            elif isdir(visible_files[idx]):
                os.chdir(visible_files[idx])
                options, notes = _files_list()
                return picker(stdscr, options, notes)
            else:
                return visible_files[idx]


        # ctrl-N
        elif k == "\x0E":
            # if not util.readonly():
                new_file_name = new_file(stdscr)
                if new_file_name is not None:
                    return new_file_name
                else:
                    time.sleep(2)
                    stdscr.erase()
                    old_idx = None
                    _draw_file_list()



def terminal_input(stdscr, message):
    stdscr.erase()
    stdscr.addstr(0, 0, message)
    input_str_list = []
    k = stdscr.getkey()
    while k != "\n":
        if len(k) == 1 and " " <= k <= "~":
            input_str_list.append(k)
            stdscr.addstr(0, len(message) + len(input_str_list) - 1, k)
        elif k == "\x08":
            input_str_list.pop(len(input_str_list) - 1)
            stdscr.addstr(0, len(message) + len(input_str_list) - 1, k)
        k = stdscr.getkey()
    # submit after enter pressed
    return "".join(input_str_list)


# pylint: disable=inconsistent-return-statements
def new_file(stdscr):
    stdscr.erase()
    new_file_name = terminal_input(stdscr, "New File Name: ")
    if os_exists(new_file_name):
        stdscr.addstr(1,0, "Error: File Already Exists")
        return
    print(f"new filename: {new_file_name}")
    if not new_file_name.startswith("/saves/") and not new_file_name.startswith("/sd/"):
        if not util.readonly():
            with open(new_file_name, "w") as f:
                f.write("")

            return new_file_name
        else:
            stdscr.addstr(1, 0, "Error: Cannot create file in readonly storage")
    else:
        with open(new_file_name, "w") as f:
            f.write("")
        return new_file_name


def _files_list():
    options = sorted(
        (
            g
            for g in os.listdir(".")
            if not g.startswith(".")
        ),
        key=lambda filename: (not has_good_extension(filename), filename),
    )  # + always[:]

    if os.getcwd() != "/":
        options.insert(0, "../")

    # notes = [None if os_exists(filename) else "(NEW)" for filename in options]
    notes = [None] * len(options)
    return options, notes


def pick_file(terminal):
    os.chdir("/")
    options, notes = _files_list()
    return curses.custom_terminal_wrapper(terminal, picker, options, notes)
