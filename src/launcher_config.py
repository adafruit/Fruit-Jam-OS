# SPDX-FileCopyrightText: 2025 Cooper Dalrymple (@relic-se)
# SPDX-License-Identifier: MIT
import json
import sys

import adafruit_pathlib as pathlib
import storage

try:
    from io import FileIO
    from typing import Any
except ImportError:
    pass


def _merge(data: dict, changes: dict) -> dict:
    if data is None:
        return changes
    if changes is not None:
        for key, value in changes.items():
            if isinstance(value, dict) and key in data and isinstance(data[key], dict):
                data[key] = _merge(data[key], value)
            else:
                data[key] = value
    return data


def _json_dump_pretty(
    data: dict | list | tuple, stream: FileIO, indent: int = 0, indent_size: int = 4
) -> None:
    stream.write(("{" if isinstance(data, dict) else "[") + "\n")

    first_item = True
    for key, value in data.items() if isinstance(data, dict) else enumerate(data):
        if not first_item:
            stream.write(",\n")
        else:
            first_item = False

        stream.write(" " * ((indent + 1) * indent_size))
        if isinstance(data, dict):
            stream.write(f'"{key}": ')

        if isinstance(value, (dict, list, tuple)):
            _json_dump_pretty(value, stream, indent + 1, indent_size)
        elif isinstance(value, bool):
            stream.write("true" if value else "false")
        elif isinstance(value, int):
            stream.write(str(value))
        else:
            stream.write(f'"{value}"')

    stream.write("\n" + (" " * (indent * indent_size)) + ("}" if isinstance(data, dict) else "]"))


class LauncherConfig:
    def __init__(self):
        self._data = {}
        self._changes = {}
        for directory in ("/sd/", "/", "/saves/"):
            launcher_config_path = directory + "launcher.conf.json"
            if pathlib.Path(launcher_config_path).exists():
                with open(launcher_config_path) as f:
                    try:
                        data = json.load(f)
                    except (AttributeError, ValueError):
                        pass
                    else:
                        self._data = _merge(self._data, data)

    def _set_value(self, name: str, value: Any) -> None:
        self._data[name] = value
        self._changes[name] = value

    def _get_group_value(self, group: str, name: str, default: Any = None) -> Any:
        return self._data[group].get(name, default) if group in self._data else default

    def _set_group_value(self, group: str, name: str, value: Any) -> None:
        if group not in self._data:
            self._data[group] = {}
        if group not in self._changes:
            self._changes[group] = {}
        self._data[group][name] = value
        self._changes[group][name] = value

    @property
    def data(self) -> dict:
        return self._data

    @data.setter
    def data(self, value: dict) -> None:
        self._data = value
        self._changes = {}

    @property
    def use_mouse(self) -> bool:
        return bool(self._data.get("use_mouse", True))

    @use_mouse.setter
    def use_mouse(self, value: bool) -> None:
        self._set_value("use_mouse", value)

    @property
    def use_gamepad(self) -> bool:
        return "use_gamepad" not in self._data or self._data["use_gamepad"]

    @use_gamepad.setter
    def use_gamepad(self, value: bool) -> None:
        self._data["use_gamepad"] = value

    @property
    def favorites(self) -> list:
        return list(self._data.get("favorites", []))

    @favorites.setter
    def favorites(self, value: list) -> None:
        self._set_value("favorites", value)

    @property
    def palette_bg(self) -> int:
        return int(self._get_group_value("palette", "bg", "0x222222"), 0)

    @palette_bg.setter
    def palette_bg(self, value: int) -> None:
        self._set_group_value("palette", "bg", f"0x{value:06x}")

    @property
    def palette_fg(self) -> int:
        return int(self._get_group_value("palette", "fg", "0xffffff"), 0)

    @palette_fg.setter
    def palette_fg(self, value: int) -> None:
        self._set_group_value("palette", "fg", f"0x{value:06x}")

    @property
    def palette_arrow(self) -> int:
        return int(self._get_group_value("palette", "arrow", "0x004abe"), 0)

    @palette_arrow.setter
    def palette_arrow(self, value: int) -> None:
        self._set_group_value("palette", "arrow", f"0x{value:06x}")

    @property
    def palette_accent(self) -> int:
        return int(self._get_group_value("palette", "accent", "0x008800"), 0)

    @palette_accent.setter
    def palette_accent(self, value: int) -> None:
        self._set_group_value("palette", "accent", f"0x{value:06x}")

    @property
    def audio_output(self) -> str:
        return str(self._get_group_value("audio", "output", "headphone"))

    @audio_output.setter
    def audio_output(self, value: str) -> None:
        self._set_group_value("audio", "output", value)

    @property
    def audio_output_speaker(self) -> bool:
        return self.audio_output == "speaker"

    @property
    def audio_output_headphones(self) -> bool:
        return not self.audio_output_speaker

    @property
    def audio_volume(self) -> float:
        return min(max(float(self._get_group_value("audio", "volume", 0.35)), 0.0), 1.0)

    @audio_volume.setter
    def audio_volume(self, value: float) -> None:
        self._set_group_value("audio", "volume", min(max(value, 0.0), 1.0))

    @property
    def audio_volume_override_danger(self) -> float:
        return min(
            max(float(self._get_group_value("audio", "volume_override_danger", 0.75)), 0.0), 1.0
        )

    @audio_volume_override_danger.setter
    def audio_volume_override_danger(self, value: float) -> None:
        self._set_group_value("audio", "volume_override_danger", min(max(value, 0.0), 1.0))

    @property
    def boot_animation(self) -> str:
        value = str(self._data.get("boot_animation", ""))
        if not value.endswith(".py") or not pathlib.Path(value).exists():
            return "/boot_animation.py"
        return value

    @boot_animation.setter
    def boot_animation(self, value: str) -> None:
        if value.endswith(".py") and pathlib.Path(value).exists():
            self._data["boot_animation"] = value

    @staticmethod
    def _valid_module(value: str, relative: bool = False) -> bool:
        paths = []
        if "/" in value:
            if not relative and not value.startswith("/"):
                return False
            paths.append(value)
            if not value.endswith(".py"):
                paths.append(value + ".py")
        else:
            for dir in sys.path:
                if not relative and not dir:
                    continue
                if dir and not dir.endswith("/"):
                    dir += "/"  # noqa: PLW2901, loop var overwritten
                paths.append(dir + value)
        for path in paths:
            if pathlib.Path(path).exists():
                return True
        return False

    @property
    def screensaver_module(self) -> str:
        return str(self._get_group_value("screensaver", "module", ""))

    @screensaver_module.setter
    def screensaver_module(self, value: str) -> None:
        if self._valid_module(value):
            self._set_group_value("screensaver", "module", value)

    @property
    def screensaver_class(self) -> str:
        return str(self._get_group_value("screensaver", "class", ""))

    @screensaver_class.setter
    def screensaver_class(self, value: str) -> None:
        self._set_group_value("screensaver", "class", value)

    def get_screensaver(self, module_name: str = None) -> object:
        class_name = ""
        if not module_name:
            module_name = self.screensaver_module
            class_name = self.screensaver_class
        if not module_name:
            return None

        try:
            m = __import__(module_name)
        except ImportError:
            return None

        if class_name and hasattr(m, class_name):
            return getattr(m, class_name)()
        elif not class_name:
            for member in reversed(dir(m)):
                if member.endswith("ScreenSaver"):
                    return getattr(m, member)()

    @property
    def screensaver_timeout(self) -> int:
        value = self._get_group_value("screensaver", "timeout")
        if value is None:
            value = self._data.get("screensaver.timeout")  # compatibility with previous option
        return int(value) if value is not None else 30

    @screensaver_timeout.setter
    def screensaver_timeout(self, value: int) -> None:
        self._set_group_value("screensaver", "timeout", max(value, 1))

    @property
    def screensaver_background_color(self) -> str:
        value = self._get_group_value("screensaver", "background_color")
        if value is None:
            value = self._data.get(
                "screensaver.background_color"
            )  # compatibility with previous option
        return str(value) if value is not None else "0x000000"

    @screensaver_background_color.setter
    def screensaver_background_color(self, value: str | int) -> None:
        if isinstance(value, int):
            value = f"0x{value:06x}"
        self._set_group_value("screensaver", "background_color", value)

    @staticmethod
    def can_save() -> bool:
        try:
            mount = storage.getmount("/saves")
        except OSError:
            return False
        else:
            return not mount.readonly

    def save(self) -> bool:
        if not self._changes:
            return False

        # read existing config
        data = None
        if pathlib.Path("/saves/launcher.conf.json").exists():
            try:
                with open("/saves/launcher.conf.json") as f:
                    data = json.load(f)
            except (AttributeError, ValueError, OSError):
                pass

        # merge with changes
        data = _merge(data, self._changes)

        # save updated config
        try:
            with open("/saves/launcher.conf.json", "w") as f:
                _json_dump_pretty(data, f)
        except OSError:
            return False
        else:
            return True

    def __str__(self) -> str:
        return str(self._data)
