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
TAB_SIZE = 4  # Number of spaces to represent a tab


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
        row, visual_col = cursor.row, cursor.col
        actual_col = self._visual_to_actual_col(row, visual_col)

        try:
            current = self.lines.pop(row)
        except IndexError:
            current = ""

        new = current[:actual_col] + string + current[actual_col:]
        self.lines.insert(row, new)

    def split(self, cursor):
        row, visual_col = cursor.row, cursor.col
        actual_col = self._visual_to_actual_col(row, visual_col)

        current = self.lines.pop(row)
        self.lines.insert(row, current[:actual_col])
        self.lines.insert(row + 1, current[actual_col:])

    def delete(self, cursor):
        row, visual_col = cursor.row, cursor.col
        actual_col = self._visual_to_actual_col(row, visual_col)

        if (row, actual_col) < (self.bottom, len(self[row])):
            current = self.lines.pop(row)
            if actual_col < len(current):
                new = current[:actual_col] + current[actual_col + 1:]
                self.lines.insert(row, new)
            else:
                nextline = self.lines.pop(row)
                new = current + nextline
                self.lines.insert(row, new)

    def _visual_to_actual_col(self, row, visual_col):
        """Convert a visual column position to the actual buffer position"""
        if row >= len(self.lines):
            return 0

        line = self.lines[row]
        actual_col = 0
        current_visual_col = 0

        while current_visual_col < visual_col and actual_col < len(line):
            if line[actual_col] == '\t':
                current_visual_col += TAB_SIZE
            else:
                current_visual_col += 1

            if current_visual_col <= visual_col:
                actual_col += 1

        return actual_col

    def actual_to_visual_col(self, row, actual_col):
        """Convert an actual buffer position to visual column position"""
        if row >= len(self.lines) or actual_col > len(self.lines[row]):
            return actual_col

        line = self.lines[row]
        visual_col = 0

        for i in range(actual_col):
            if i < len(line) and line[i] == '\t':
                visual_col += TAB_SIZE
            else:
                visual_col += 1

        return visual_col

    def get_visual_length(self, row):
        """Get the visual length of a line, accounting for tabs"""
        if row >= len(self.lines):
            return 0

        line = self.lines[row]
        return sum(TAB_SIZE if c == '\t' else 1 for c in line)


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
        visual_length = buffer.get_visual_length(self.row)
        self._col = min(self._col_hint, visual_length)

    def up(self, buffer):
        if self.row > 0:
            self.row -= 1
            self._clamp_col(buffer)

    def down(self, buffer):
        if self.row < len(buffer) - 1:
            self.row += 1
            self._clamp_col(buffer)

    def left(self, buffer):
        if self.col > 0:
            # Check if cursor is at the end of a tab
            actual_col = buffer._visual_to_actual_col(self.row, self.col)
            if actual_col > 0 and buffer[self.row][actual_col - 1] == '\t':
                # If we're at a tab character, move visual position back by TAB_SIZE
                self.col = buffer.actual_to_visual_col(self.row, actual_col - 1)
            else:
                self.col -= 1
        elif self.row > 0:
            self.row -= 1
            self.col = buffer.get_visual_length(self.row)

    def right(self, buffer):
        visual_length = buffer.get_visual_length(self.row)
        if self.col < visual_length:
            # Check if we're on a tab character
            actual_col = buffer._visual_to_actual_col(self.row, self.col)
            if actual_col < len(buffer[self.row]) and buffer[self.row][actual_col] == '\t':
                # If we're on a tab character, move visual position forward by TAB_SIZE
                self.col = buffer.actual_to_visual_col(self.row, actual_col + 1)
            else:
                self.col += 1
        elif self.row < len(buffer) - 1:
            self.row += 1
            self.col = 0

    def end(self, buffer):
        self.col = buffer.get_visual_length(self.row)


class Window:
    def __init__(self, n_rows, n_cols, row=0, col=0):
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.row = row
        self.col = col

    @property
    def bottom(self):
        return self.row + self.n_rows - 1

    def up(self, cursor):
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


def home(window, buffer, cursor):
    cursor.col = 0
    window.horizontal_scroll(cursor)


def end(window, buffer, cursor):
    cursor.end(buffer)
    window.horizontal_scroll(cursor)


def is_at_tab(buffer, row, col):
    """Check if a visual position corresponds to a tab character"""
    if row >= len(buffer.lines):
        return False

    actual_col = buffer._visual_to_actual_col(row, col)
    if actual_col >= len(buffer.lines[row]):
        return False

    return buffer.lines[row][actual_col] == '\t'


def get_tab_visual_positions(buffer, row, col):
    """Get all visual positions that belong to a tab at the current position"""
    if not is_at_tab(buffer, row, col):
        return []

    actual_col = buffer._visual_to_actual_col(row, col)
    visual_start = buffer.actual_to_visual_col(row, actual_col)

    return list(range(visual_start, visual_start + TAB_SIZE))


def is_within_tab_range(buffer, row, col):
    """Check if a visual position is within any tab's visual range"""
    if row >= len(buffer.lines):
        return False

    line = buffer.lines[row]
    for i, char in enumerate(line):
        if char == '\t':
            visual_start = buffer.actual_to_visual_col(row, i)
            visual_end = visual_start + TAB_SIZE
            if visual_start <= col < visual_end:
                return True
    return False


def only_spaces_before(buffer, cursor):
    """Check if there are only spaces before the cursor"""
    actual_col = buffer._visual_to_actual_col(cursor.row, cursor.col)
    for i in range(actual_col):
        if buffer.lines[cursor.row][i] != " ":
            return False
    return True


def editor(stdscr, filename, mouse=None, terminal_tilegrid=None):
    if os_exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            buffer = Buffer(f.read().splitlines())
    else:
        buffer = Buffer([""])

    if os.getcwd() != "/apps/editor" and os.getcwd() != "/":
        absolute_filepath = os.getcwd() + "/" + filename
    else:
        absolute_filepath = filename

    user_message = None
    user_message_shown_time = -1

    clicked_tile_coords = [None, None]

    window = Window(curses.LINES - 1, curses.COLS - 1)
    cursor = Cursor()

    # Initialize cursor highlighting
    highlight_cursor_position(terminal_tilegrid, buffer, cursor)
    old_cursor_pos = (cursor.col, cursor.row)

    stdscr.erase()

    img = [None] * curses.LINES

    def setline(row, line):
        if img[row] == line:
            return
        img[row] = line
        # Calculate displayed length for padding
        visual_length = sum(TAB_SIZE if c == '\t' else 1 for c in line)
        padding = window.n_cols - visual_length
        if padding > 0:
            line += " " * padding
        stdscr.addstr(row, 0, line)

    while True:
        lastrow = 0
        for row, line in enumerate(buffer[window.row: window.row + window.n_rows]):
            lastrow = row

            if row == cursor.row - window.row and window.col > 0:
                line = "«" + line[window.col + 1:]

            # Calculate visual length for line truncation
            visual_length = sum(TAB_SIZE if c == '\t' else 1 for c in line)
            if visual_length > window.n_cols:
                # Find the position to truncate based on visual length
                actual_col = 0
                current_visual_col = 0
                while current_visual_col < window.n_cols - 1 and actual_col < len(line):
                    if line[actual_col] == '\t':
                        current_visual_col += TAB_SIZE
                    else:
                        current_visual_col += 1
                    actual_col += 1

                if actual_col < len(line):
                    line = line[:actual_col] + "»"

            setline(row, line)

        for row in range(lastrow + 1, window.n_rows):
            setline(row, "~~ EOF ~~")
        row = curses.LINES - 1

        if user_message is None:
            if (not absolute_filepath.startswith("/saves/") and
                    not absolute_filepath.startswith("/sd/") and
                    util.readonly()):

                line = f"{absolute_filepath:12} (mnt RO ^W) | ^R run | ^O Open | ^C: quit{gc_mem_free_hint()}"
            else:
                line = f"{absolute_filepath:12} (mnt RW ^W) | ^R run | ^O Open  | ^S save | ^X: save & exit | ^C: exit no save{gc_mem_free_hint()}"
        else:
            line = user_message
            if user_message_shown_time + 3.0 < time.monotonic():
                user_message = None
        setline(row, line)

        stdscr.move(*window.translate(cursor))

        k = stdscr.getkey()
        if k is not None:
            if len(k) == 1 and " " <= k <= "~":
                buffer.insert(cursor, k)
                right(window, buffer, cursor)
            elif k == "\t":
                buffer.insert(cursor, k)
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
            elif k == "KEY_HOME":
                home(window, buffer, cursor)
            elif k == "KEY_END":
                end(window, buffer, cursor)
            elif k == "KEY_DOWN":
                cursor.down(buffer)
                window.down(buffer, cursor)
                window.horizontal_scroll(cursor)
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
            elif k == "KEY_LEFT":
                left(window, buffer, cursor)
            elif k == "\n":
                # Get leading whitespace from the current line
                current_line = buffer.lines[cursor.row]
                leading_spaces = _count_leading_characters(current_line, " ")
                leading_tabs = _count_leading_characters(current_line, "\t")

                # Split the line at the cursor
                buffer.split(cursor)

                # Move to the beginning of the next line
                cursor.row += 1
                cursor.col = 0

                # Insert indentation in the correct order (first tabs, then spaces)
                for i in range(leading_tabs):
                    buffer.insert(cursor, "\t")
                    right(window, buffer, cursor)

                for i in range(leading_spaces):
                    buffer.insert(cursor, " ")
                    right(window, buffer, cursor)

                # Update window scrolling
                window.down(buffer, cursor)
                window.horizontal_scroll(cursor)

            elif k in ("KEY_DELETE", "\x04"):
                if cursor.row < len(buffer.lines) - 1 or \
                        cursor.col < buffer.get_visual_length(cursor.row):
                    buffer.delete(cursor)
            elif k in ("KEY_BACKSPACE", "\x7f", "\x08"):
                if (cursor.row, cursor.col) > (0, 0):
                    if cursor.col > 0 and only_spaces_before(buffer, cursor):
                        # Handle backspace with spaces
                        for i in range(min(TAB_SIZE, cursor.col)):
                            left(window, buffer, cursor)
                            buffer.delete(cursor)
                    else:
                        # Check if cursor is within a tab's visual space
                        if is_within_tab_range(buffer, cursor.row, cursor.col - 1):
                            actual_col = buffer._visual_to_actual_col(cursor.row, cursor.col - 1)
                            # Set cursor to the beginning of the tab
                            cursor.col = buffer.actual_to_visual_col(cursor.row, actual_col)

                        left(window, buffer, cursor)
                        buffer.delete(cursor)
            else:
                print(f"unhandled k: {k}")

        if mouse is not None:
            pressed_btns = mouse.update()
            if pressed_btns is not None and "left" in pressed_btns:
                clicked_tile_coords[0] = mouse.x // 6
                clicked_tile_coords[1] = mouse.y // 12

                if clicked_tile_coords[1] < len(buffer.lines):
                    visual_length = buffer.get_visual_length(clicked_tile_coords[1])
                    if clicked_tile_coords[0] > visual_length:
                        clicked_tile_coords[0] = visual_length

                cursor.row = clicked_tile_coords[1]
                cursor.col = clicked_tile_coords[0]

        # Update cursor highlighting if position changed
        if old_cursor_pos != (cursor.col, cursor.row):
            # Clear old cursor position
            clear_cursor_highlight(terminal_tilegrid, buffer, old_cursor_pos[1], old_cursor_pos[0])

            # Highlight new cursor position
            highlight_cursor_position(terminal_tilegrid, buffer, cursor)

            old_cursor_pos = (cursor.col, cursor.row)


def highlight_cursor_position(terminal_tilegrid, buffer, cursor):
    """Highlight the cursor position, handling tabs properly"""
    if terminal_tilegrid is None:
        return

    if is_at_tab(buffer, cursor.row, cursor.col):
        # If at a tab, highlight all positions that represent the tab
        tab_positions = get_tab_visual_positions(buffer, cursor.row, cursor.col)
        for pos in tab_positions:
            terminal_tilegrid.pixel_shader[pos, cursor.row] = [1, 0]
    else:
        # Otherwise just highlight the current position
        terminal_tilegrid.pixel_shader[cursor.col, cursor.row] = [1, 0]


def clear_cursor_highlight(terminal_tilegrid, buffer, row, col):
    """Clear cursor highlighting, handling tabs properly"""
    if terminal_tilegrid is None:
        return

    if is_at_tab(buffer, row, col):
        # If at a tab, clear all positions that represent the tab
        tab_positions = get_tab_visual_positions(buffer, row, col)
        for pos in tab_positions:
            terminal_tilegrid.pixel_shader[pos, row] = [0, 1]
    else:
        # Otherwise just clear the current position
        terminal_tilegrid.pixel_shader[col, row] = [0, 1]


def edit(filename, terminal=None, mouse=None, terminal_tilegrid=None):
    with MaybeDisableReload():
        if terminal is None:
            return curses.wrapper(editor, filename)
        else:
            return curses.custom_terminal_wrapper(terminal, editor, filename, mouse, terminal_tilegrid)