# SPDX-FileCopyrightText: 2025 Tim Cocks for Adafruit Industries
# SPDX-License-Identifier: MIT

import adafruit_pathlib as pathlib
import storage
import supervisor
from adafruit_argv_file import read_argv, write_argv

supervisor.runtime.autoreload = False

"""
boot.py arguments

  0: storage readonly flag, False means writable to CircuitPython,
     True means read-only to CircuitPython
  1: next code files
2-N: args to pass to next code file

"""


args = read_argv(__file__)
if args is not None and len(args) > 0:
    readonly = args[0]
    next_code_file = None
    remaining_args = None

    if len(args) >= 1:
        next_code_file = args[1]
    if len(args) >= 2:
        remaining_args = args[2:]

    if remaining_args is not None:
        write_argv(next_code_file, remaining_args)

    # print(f"setting storage readonly to: {readonly}")
    storage.remount("/", readonly=readonly)

    supervisor.set_next_code_file(
        next_code_file,
        sticky_on_reload=False,
        reload_on_error=True,
        working_directory="/".join(next_code_file.split("/")[:-1]),
    )

elif supervisor.runtime.display is None:
    supervisor.set_next_code_file("code.py")
else:
    from launcher_config import LauncherConfig

    supervisor.set_next_code_file(LauncherConfig().boot_animation)
