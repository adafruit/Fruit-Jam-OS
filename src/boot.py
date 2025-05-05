import os

import supervisor
from argv_file_helper import argv_filename
import json
import storage

supervisor.runtime.autoreload = False

"""
boot.py arguments

  0: storage readonly flag, False means writable to CircuitPython, True means read-only to CircuitPython
  1: next code files
2-N: args to pass to next code file

"""
try:
    arg_file = argv_filename(__file__)
    print(f"arg files: {arg_file}")
    with open(arg_file, "r") as f:
        args = json.load(f)

    print("args file found and loaded")
    os.remove(arg_file)
    print("args file removed")

    readonly = args[0]
    next_code_file = None
    remaining_args = None

    if len(args) >= 1:
        next_code_file = args[1]
    if len(args) >= 2:
        remaining_args = args[2:]

    if remaining_args is not None:
        next_code_argv_filename = argv_filename(next_code_file)
        with open(next_code_argv_filename, "w") as f:
            f.write(json.dumps(remaining_args))
            print("next code args written")

    print(f"setting storage readonly to: {readonly}")
    storage.remount("/", readonly=readonly)

    next_code_file = next_code_file
    supervisor.set_next_code_file(next_code_file)
    print(f"launching: {next_code_file}")
    # os.rename("/saves/.boot_py_argv", "/saves/.not_boot_py_argv")


except OSError:
    print("launching boot animation")
    supervisor.set_next_code_file("boot_animation.py")