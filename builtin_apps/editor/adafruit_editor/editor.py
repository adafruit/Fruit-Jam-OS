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
from adafruit_argv_file import argv_filename

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


def editor(stdscr, filename, mouse=None, terminal_tilegrid=None):  # pylint: disable=too-many-branches,too-many-statements

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
    print(f"cwd: {os.getcwd()} | {os.getcwd() == "/apps/editor"}")
    if os.getcwd() != "/apps/editor" and os.getcwd() != "/":
        absolute_filepath = os.getcwd() + "/" + filename
    else:
        absolute_filepath = filename

    user_message = None
    user_message_shown_time = -1
    user_prompt = None
    user_response = ""
    last_find = ""
    find_command = False
    goto_command = False

    clicked_tile_coords = [None, None]

    window = Window(curses.LINES - 1, curses.COLS - 1)
    cursor = Cursor()
    terminal_tilegrid.pixel_shader[cursor.col,cursor.row] = [1, 0]
    old_cursor_pos = (cursor.col, cursor.row)
    old_window_pos = (window.col, window.row)
    # try:
    #     visible_cursor.text = buffer[0][0]
    # except IndexError:
    #     visible_cursor.text = " "

    stdscr.erase()

    img = [None] * curses.LINES

    def setline(row, line):
        if img[row] == line:
            return
        img[row] = line
        line += " " * (window.n_cols - len(line))
        stdscr.addstr(row, 0, line)

    print(f"cwd: {os.getcwd()} | abs path: {absolute_filepath} | filename: {filename}")
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

        if user_message is None and user_prompt is None:
            if (not absolute_filepath.startswith("/saves/") and
                    not absolute_filepath.startswith("/sd/") and
                    util.readonly()):

                line = f"{absolute_filepath:12} (mnt RO ^W) | ^R Run | ^O Open | ^F Find | ^G GoTo | ^C quit {gc_mem_free_hint()}"
            else:
                line = f"{absolute_filepath:12} (mnt RW ^W) | ^R Run | ^O Open | ^F Find | ^G GoTo | ^S Save | ^X save & eXit | ^C quit {gc_mem_free_hint()}"
            line = line + " " * (window.n_cols - len(line))
            line = line[:window.n_cols-len(f'{cursor.row+1},{cursor.col+1}')] + f"{cursor.row+1},{cursor.col+1}"

        elif user_message is not None:
            line = user_message
            if user_message_shown_time + 3.0 < time.monotonic():
                user_message = None
        elif user_prompt is not None:
            line = f'{user_prompt} {user_response}'
        setline(row, line)

        stdscr.move(*window.translate(cursor))

        # display.refresh(minimum_frames_per_second=20)
        k = stdscr.getkey()
        if k is not None:
            # print(repr(k))
            if user_prompt is not None:
                if len(k) == 1 and " " <= k <= "~":
                    user_response += k
                elif k == "\n":
                    user_prompt = None

                    if find_command:
                        found = False
                        if user_response == "":
                            user_response = last_find
                        if user_response:
                            last_find = user_response
                            if buffer[cursor.row][min(cursor.col+1,len(buffer[cursor.row])-1):].find(user_response) != -1:
                                found = True
                                user_message = f"Found '{user_response}' in line {cursor.row+1}"
                                cursor.col += buffer[cursor.row][cursor.col:].find(user_response) - 1
                                right(window, buffer, cursor)
                            else:
                                for r, line in enumerate(buffer[cursor.row+1:]):
                                    if line.find(user_response) != -1:
                                        found = True
                                        user_message = f"Found '{user_response}' in line {r + cursor.row + 2}"
                                        cursor.row = clamp(r + cursor.row + 1, 0, len(buffer) - 1)
                                        window.row = clamp(cursor.row - window.n_rows // 2, 0, len(buffer) - window.n_rows)
                                        cursor.col = line.find(user_response) - 1
                                        right(window, buffer, cursor)
                                        break

                        if not found:
                            user_message = f"'{user_response}' not found"
                        user_message_shown_time = time.monotonic()

                        user_response = ""
                        find_command = False

                    elif goto_command:
                        if user_response.isdigit():
                            cursor.row = clamp(int(user_response) - 1, 0, len(buffer) - 1)
                            window.row = clamp(cursor.row - window.n_rows // 2, 0, len(buffer) - window.n_rows)
                            cursor.col = 0
                            window.horizontal_scroll(cursor)

                        user_response = ""
                        goto_command = False

                elif k == "\x7f" or k == "\x08":  # backspace
                    user_response = user_response[:-1]
                elif k == "\x1b":  # escape
                    user_prompt = None
                    user_response = ""
                else:
                    print(f"unhandled k: {k}")
                    print(f"unhandled K: {ord(k)}")
                    print(f"unhandled k: {bytes(k, 'utf-8')}")

            elif len(k) == 1 and " " <= k <= "~":
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
                print(absolute_filepath)
                print(f"starts with saves: {absolute_filepath.startswith("/saves/")}")
                print(f"stars saves: {absolute_filepath.startswith("/saves/")}")
                print(f"stars sd: {absolute_filepath.startswith("/sd/")}")
                print(f"readonly: {util.readonly()}")
                if (absolute_filepath.startswith("/saves/") or
                        absolute_filepath.startswith("/sd/") or
                        not util.readonly()):

                    with open(absolute_filepath, "w", encoding="utf-8") as f:
                        for row in buffer:
                            f.write(f"{row}\n")
                        user_message = "Saved"
                        user_message_shown_time = time.monotonic()
                else:
                    user_message = "Unable to Save due to readonly mode!"
                    user_message_shown_time = time.monotonic()
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
            elif k == "\x0f":  # Ctrl-O

                supervisor.set_next_code_file("/apps/editor/code.py", sticky_on_reload=False, reload_on_error=True,
                                              working_directory="/apps/editor")
                supervisor.reload()
            elif k == "\x06":  # Ctrl-F
                find_command = True
                if last_find == "":
                    user_prompt = "Find:"
                else:
                    user_prompt = f"Find: [{last_find}]"
            elif k == "\x07":  # Ctrl-G
                goto_command = True
                user_prompt = "Goto line:"

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
                    # try:
                    #     visible_cursor.text = buffer.lines[cursor.row][cursor.col]
                    # except IndexError:
                    #     visible_cursor.text = " "

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


        if mouse is not None:
            pressed_btns = mouse.update()
            if pressed_btns is not None and "left" in pressed_btns:
                clicked_tile_coords[0] = mouse.x // 6
                clicked_tile_coords[1] = mouse.y // 12

                if clicked_tile_coords[0] > len(buffer.lines[clicked_tile_coords[1]+window.row]):
                    clicked_tile_coords[0] = len(buffer.lines[clicked_tile_coords[1]+window.row])
                cursor.row = clicked_tile_coords[1] + window.row
                cursor.col = clicked_tile_coords[0] + window.col

        # print("updating visible cursor")
        # print(f"anchored pos: {((cursor.col * 6) - 1, (cursor.row * 12) + 20)}")

        if (old_cursor_pos[0] - old_window_pos[0] != cursor.col - window.col or
                old_cursor_pos[1] - old_window_pos[1] != cursor.row - window.row):
            # print(f"old cursor: {old_cursor_pos}, new: {(cursor.col, cursor.row)}")
            # print(f"window (row,col): {window.row}, {window.col}")
            terminal_tilegrid.pixel_shader[old_cursor_pos[0] - old_window_pos[0], old_cursor_pos[1] - old_window_pos[1]] = [0,1]
            terminal_tilegrid.pixel_shader[cursor.col - window.col, cursor.row - window.row] = [1,0]
            # print(f"old: {terminal_tilegrid.pixel_shader[old_cursor_pos[0], old_cursor_pos[1]]} new: {terminal_tilegrid.pixel_shader[cursor.col, cursor.row]}")

            # visible_cursor.anchored_position = ((cursor.col * 6) - 1, (cursor.row * 12) + 20)

            # visible_cursor.anchored_position = ((cursor.col * 6), ((cursor.row - window.row) * 12))
            #
            # try:
            #     visible_cursor.text = buffer.lines[cursor.row][cursor.col]
            # except IndexError:
            #     visible_cursor.text = " "


        old_cursor_pos = (cursor.col, cursor.row)
        old_window_pos = (window.col, window.row)

def edit(filename, terminal=None, mouse=None, terminal_tilegrid=None):
    with MaybeDisableReload():
        if terminal is None:
            return curses.wrapper(editor, filename)
        else:
            return curses.custom_terminal_wrapper(terminal, editor, filename, mouse, terminal_tilegrid)
