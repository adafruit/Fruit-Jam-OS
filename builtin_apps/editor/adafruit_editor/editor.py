# SPDX-FileCopyrightText: 2020 Wasim Lorgat
# SPDX-FileCopyrightText: 2023 Jeff Epler for Adafruit Industries
# SPDX-FileCopyrightText: 2024 Tim Cocks for Adafruit Industries
#
# SPDX-License-Identifier: MIT

import gc
import os

import microcontroller
import supervisor
import usb_cdc
from . import dang as curses
from . import util
from adafruit_pathlib import Path
import time
import json
from argv_file_helper import argv_filename

# pylint: disable=redefined-builtin

# def print(message):
#     usb_cdc.data.write(f"{message}\r\n".encode("utf-8"))

INPUT_DISPLAY_REFRESH_COOLDOWN = 0.3  # s
SHOW_MEMFREE = False


class MaybeDisableReload:
    def __enter__(self):
        try:
            from supervisor import runtime  # pylint: disable=import-outside-toplevel
        except ImportError:
            return

        self._old_autoreload = (  # pylint: disable=attribute-defined-outside-init
            runtime.autoreload
        )
        runtime.autoreload = False

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            from supervisor import runtime  # pylint: disable=import-outside-toplevel
        except ImportError:
            return

        runtime.autoreload = self._old_autoreload


def os_exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError:
        return False


def gc_mem_free_hint():
    if not SHOW_MEMFREE:
        return ""
    if hasattr(gc, "mem_free"):
        gc.collect()
        return f" | free: {gc.mem_free()}"
    return ""


class Buffer:
    def __init__(self, lines):
        self.lines = lines

    def __len__(self):
        return len(self.lines)

    def __getitem__(self, index):
        return self.lines[index]

    @property
    def bottom(self):
        return len(self) - 1

    def insert(self, cursor, string):
        row, col = cursor.row, cursor.col
        # print(f"len: {len(self.lines)}")
        # print(f"row: {row}")
        try:
            current = self.lines.pop(row)
        except IndexError:
            current = ""
        new = current[:col] + string + current[col:]
        self.lines.insert(row, new)

    def split(self, cursor):
        row, col = cursor.row, cursor.col
        current = self.lines.pop(row)
        self.lines.insert(row, current[:col])
        self.lines.insert(row + 1, current[col:])

    def delete(self, cursor):
        row, col = cursor.row, cursor.col
        if (row, col) < (self.bottom, len(self[row])):
            current = self.lines.pop(row)
            if col < len(current):
                new = current[:col] + current[col + 1:]
                self.lines.insert(row, new)
            else:
                nextline = self.lines.pop(row)
                new = current + nextline
                self.lines.insert(row, new)


def clamp(x, lower, upper):
    if x < lower:
        return lower
    if x > upper:
        return upper
    return x


def _count_leading_characters(text, char):
    count = 0
    for c in text:
        if c == char:
            count += 1
        else:
            break
    return count


class Cursor:
    def __init__(self, row=0, col=0, col_hint=None):
        self.row = row
        self._col = col
        self._col_hint = col if col_hint is None else col_hint

    @property
    def col(self):
        return self._col

    @col.setter
    def col(self, col):
        self._col = col
        self._col_hint = col

    def _clamp_col(self, buffer):
        self._col = min(self._col_hint, len(buffer[self.row]))

    def up(self, buffer):  # pylint: disable=invalid-name
        if self.row > 0:
            self.row -= 1
            self._clamp_col(buffer)
            # print(f"cursor pos: {self.row}, {self.col}")

    def down(self, buffer):
        if self.row < len(buffer) - 1:
            self.row += 1
            self._clamp_col(buffer)
            # print(f"cursor pos: {self.row}, {self.col}")

    def left(self, buffer):
        if self.col > 0:
            self.col -= 1
            # print(f"cursor pos: {self.row}, {self.col}")
        elif self.row > 0:
            self.row -= 1
            self.col = len(buffer[self.row])
            # print(f"cursor pos: {self.row}, {self.col}")

    def right(self, buffer):
        # print(f"len: {len(buffer)}")
        if len(buffer) > 0 and self.col < len(buffer[self.row]):
            self.col += 1
            # print(f"cursor pos: {self.row}, {self.col}")
        elif self.row < len(buffer) - 1:
            self.row += 1
            self.col = 0
            # print(f"cursor pos: {self.row}, {self.col}")

    def end(self, buffer):
        self.col = len(buffer[self.row])
        # print(f"cursor pos: {self.row}, {self.col}")


class Window:
    def __init__(self, n_rows, n_cols, row=0, col=0):
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.row = row
        self.col = col

    @property
    def bottom(self):
        return self.row + self.n_rows - 1

    def up(self, cursor):  # pylint: disable=invalid-name
        if cursor.row == self.row - 1 and self.row > 0:
            self.row -= 1

    def down(self, buffer, cursor):
        if cursor.row == self.bottom + 1 and self.bottom < len(buffer) - 1:
            self.row += 1

    def horizontal_scroll(self, cursor, left_margin=5, right_margin=2):
        n_pages = cursor.col // (self.n_cols - right_margin)
        self.col = max(n_pages * self.n_cols - right_margin - left_margin, 0)

    def translate(self, cursor):
        return cursor.row - self.row, cursor.col - self.col


def left(window, buffer, cursor):
    cursor.left(buffer)
    window.up(cursor)
    window.horizontal_scroll(cursor)


def right(window, buffer, cursor):
    cursor.right(buffer)
    window.down(buffer, cursor)
    window.horizontal_scroll(cursor)


def home(window, buffer, cursor):  # pylint: disable=unused-argument
    cursor.col = 0
    window.horizontal_scroll(cursor)


def end(window, buffer, cursor):
    cursor.end(buffer)
    window.horizontal_scroll(cursor)


def editor(stdscr, filename, visible_cursor):  # pylint: disable=too-many-branches,too-many-statements

    def _only_spaces_before(cursor):
        i = cursor.col - 1
        while i >= 0:
            print(f"i: {i} chr: '{buffer.lines[cursor.row][i]}'")
            if buffer.lines[cursor.row][i] != " ":
                return False
            i -= 1
        return True
    if os_exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            buffer = Buffer(f.read().splitlines())
    else:
        buffer = Buffer([""])

    absolute_filepath = os.getcwd() + "/" + filename

    user_message = None

    window = Window(curses.LINES - 1, curses.COLS - 1)
    cursor = Cursor()
    try:
        visible_cursor.text = buffer[0][0]
    except IndexError:
        visible_cursor.text = " "

    stdscr.erase()

    img = [None] * curses.LINES

    def setline(row, line):
        if img[row] == line:
            return
        img[row] = line
        line += " " * (window.n_cols - len(line))
        stdscr.addstr(row, 0, line)

    while True:
        lastrow = 0
        for row, line in enumerate(buffer[window.row: window.row + window.n_rows]):
            lastrow = row
            if row == cursor.row - window.row and window.col > 0:
                line = "«" + line[window.col + 1:]
            if len(line) > window.n_cols:
                line = line[: window.n_cols - 1] + "»"
            setline(row, line)
        for row in range(lastrow + 1, window.n_rows):
            setline(row, "~~ EOF ~~")
        row = curses.LINES - 1

        if user_message is None:
            if (not absolute_filepath.startswith("/saves/") and
                    not absolute_filepath.startswith("/sd/") and
                    util.readonly()):

                line = f"{filename:12} (mnt RO ^W) | ^R run | ^P exit & picker | ^C: quit{gc_mem_free_hint()}"
            else:
                line = f"{filename:12} (mnt RW ^W) | ^R run | ^S save | ^X: save & exit | ^P exit & picker | ^C: exit no save{gc_mem_free_hint()}"
        else:
            line = user_message
            user_message = None
        setline(row, line)

        stdscr.move(*window.translate(cursor))
        old_cursor_pos = (cursor.col, cursor.row)
        # display.refresh(minimum_frames_per_second=20)
        k = stdscr.getkey()
        # print(repr(k))
        if len(k) == 1 and " " <= k <= "~":
            buffer.insert(cursor, k)
            for _ in k:
                right(window, buffer, cursor)
        elif k == "\x18":  # ctrl-x
            if not util.readonly():
                with open(filename, "w", encoding="utf-8") as f:
                    for row in buffer:
                        f.write(f"{row}\n")
                return
            else:
                print("Unable to Save due to readonly mode! File Contents:")
                print("---- begin file contents ----")
                for row in buffer:
                    print(row)
                print("---- end file contents ----")
        elif k == "\x13":  # Ctrl-S
            if (absolute_filepath.startswith("/saves/") or
                    absolute_filepath.startswith("/sd/") or
                    util.readonly()):

                with open(filename, "w", encoding="utf-8") as f:
                    for row in buffer:
                        f.write(f"{row}\n")
                    user_message = "Saved"
            else:
                user_message = "Unable to Save due to readonly mode!"
        elif k == "\x11":  # Ctrl-Q
            print("ctrl-Q")
            for row in buffer:
                print(row)
        elif k == "\x17":  # Ctrl-W
            boot_args_file = argv_filename("/boot.py")
            with open(boot_args_file, "w") as f:
                f.write(json.dumps([not util.readonly(), "/apps/editor/code.py", Path(filename).absolute()]))
            microcontroller.reset()
        elif k == "\x12":  # Ctrl-R
            print(f"Run: {filename}")

            launcher_code_args_file = argv_filename("/code.py")
            with open(launcher_code_args_file, "w") as f:
                f.write(json.dumps(["/apps/editor/code.py", Path(filename).absolute()]))

            supervisor.set_next_code_file(filename, sticky_on_reload=False, reload_on_error=True,
                                          working_directory=Path(filename).parent.absolute())
            supervisor.reload()
        elif k == "\x10":  # Ctrl-P
            supervisor.set_next_code_file("/apps/editor/code.py", sticky_on_reload=False, reload_on_error=True,
                                          working_directory="/apps/editor")
            supervisor.reload()
        elif k == "KEY_HOME":
            home(window, buffer, cursor)
        elif k == "KEY_END":
            end(window, buffer, cursor)
        elif k == "KEY_LEFT":
            left(window, buffer, cursor)
        elif k == "KEY_DOWN":

            cursor.down(buffer)
            window.down(buffer, cursor)
            window.horizontal_scroll(cursor)
            print(f"scroll pos: {window.row}")
        elif k == "KEY_PGDN":
            for _ in range(window.n_rows):
                cursor.down(buffer)
                window.down(buffer, cursor)
                window.horizontal_scroll(cursor)
        elif k == "KEY_UP":
            cursor.up(buffer)
            window.up(cursor)
            window.horizontal_scroll(cursor)
        elif k == "KEY_PGUP":
            for _ in range(window.n_rows):
                cursor.up(buffer)
                window.up(cursor)
                window.horizontal_scroll(cursor)
        elif k == "KEY_RIGHT":
            right(window, buffer, cursor)
        elif k == "\n":
            leading_spaces = _count_leading_characters(buffer.lines[cursor.row], " ")
            buffer.split(cursor)
            right(window, buffer, cursor)
            for i in range(leading_spaces):
                buffer.insert(cursor, " ")
                right(window, buffer, cursor)
        elif k in ("KEY_DELETE", "\x04"):
            print("delete")
            if cursor.row < len(buffer.lines) - 1 or \
                    cursor.col < len(buffer.lines[cursor.row]):
                buffer.delete(cursor)
                try:
                    visible_cursor.text = buffer.lines[cursor.row][cursor.col]
                except IndexError:
                    visible_cursor.text = " "

        elif k in ("KEY_BACKSPACE", "\x7f", "\x08"):
            print(f"backspace {bytes(k, 'utf-8')}")
            if (cursor.row, cursor.col) > (0, 0):
                if cursor.col > 0 and buffer.lines[cursor.row][cursor.col-1] == " " and _only_spaces_before(cursor):
                    for i in range(4):
                        left(window, buffer, cursor)
                        buffer.delete(cursor)
                else:
                    left(window, buffer, cursor)
                    buffer.delete(cursor)

        else:
            print(f"unhandled k: {k}")
            print(f"unhandled K: {ord(k)}")
            print(f"unhandled k: {bytes(k, 'utf-8')}")
        # print("updating visible cursor")
        # print(f"anchored pos: {((cursor.col * 6) - 1, (cursor.row * 12) + 20)}")
        if old_cursor_pos != (cursor.col, cursor.row):

            # terminal_tilegrid.pixel_shader[old_cursor_pos[0], old_cursor_pos[1]] = [0,1]
            # terminal_tilegrid.pixel_shader[cursor.col, cursor.row] = [1,0]

            # visible_cursor.anchored_position = ((cursor.col * 6) - 1, (cursor.row * 12) + 20)
            visible_cursor.anchored_position = ((cursor.col * 6), ((cursor.row - window.row) * 12))

            try:
                visible_cursor.text = buffer.lines[cursor.row][cursor.col]
            except IndexError:
                visible_cursor.text = " "


def edit(filename, terminal=None, visible_cursor=None):
    with MaybeDisableReload():
        if terminal is None:
            return curses.wrapper(editor, filename)
        else:
            return curses.custom_terminal_wrapper(terminal, editor, filename, visible_cursor)
