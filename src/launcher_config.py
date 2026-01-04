# SPDX-FileCopyrightText: 2025 Cooper Dalrymple (@relic-se)
# SPDX-License-Identifier: MIT
import json
import sys
import adafruit_pathlib as pathlib

class LauncherConfig:

    def __init__(self):
        self._data = {}
        for directory in ("/", "/sd/", "/saves/"):
            launcher_config_path = directory + "launcher.conf.json"
            if pathlib.Path(launcher_config_path).exists():
                with open(launcher_config_path, "r") as f:
                    self._data = self._data | json.load(f)
        for key in ("palette", "audio", "screensaver"):
            if key not in self._data:
                self._data[key] = {}

    @property
    def data(self) -> dict:
        return self._data

    @data.setter
    def data(self, value: dict) -> None:
        self._data = value

    @property
    def use_mouse(self) -> bool:
        return "use_mouse" not in self._data or self._data["use_mouse"]
    @use_mouse.setter
    def use_mouse(self, value: bool) -> None:
        self._data["use_mouse"] = value

    @property
    def favorites(self) -> list:
        return list(self._data["favorites"]) if "favorites" in self._data else []

    @favorites.setter
    def favorites(self, value: list) -> None:
        self._data["favorites"] = value

    @property
    def palette_bg(self) -> int:
        return int(self._data["palette"].get("bg", "0x222222"), 0)

    @palette_bg.setter
    def palette_bg(self, value: int) -> None:
        self._data["palette"]["bg"] = "0x{:06x}".format(value)

    @property
    def palette_fg(self) -> int:
        return int(self._data["palette"].get("fg", "0xffffff"), 0)

    @palette_fg.setter
    def palette_fg(self, value: int) -> None:
        self._data["palette"]["fg"] = "0x{:06x}".format(value)

    @property
    def palette_arrow(self) -> int:
        return int(self._data["palette"].get("arrow", "0x004abe"), 0)

    @palette_arrow.setter
    def palette_arrow(self, value: int) -> None:
        self._data["palette"]["arrow"] = "0x{:06x}".format(value)

    @property
    def palette_accent(self) -> int:
        return int(self._data["palette"].get("accent", "0x008800"), 0)

    @palette_accent.setter
    def palette_accent(self, value: int) -> None:
        self._data["palette"]["accent"] = "0x{:06x}".format(value)

    @property
    def audio_output(self) -> str:
        return self._data["audio"].get("output", "headphone")

    @audio_output.setter
    def audio_output(self, value: str) -> None:
        self._data["audio"]["output"] = value

    @property
    def audio_output_speaker(self) -> bool:
        return self.audio_output == "speaker"

    @property
    def audio_output_headphones(self) -> bool:
        return not self.audio_output_speaker

    @property
    def audio_volume(self) -> float:
        return min(max(float(self._data["audio"].get("volume", 0.35)), 0.0), 1.0)

    @audio_volume.setter
    def audio_volume(self, value: float) -> None:
        self._data["audio"]["volume"] = min(max(value, 0.0), 1.0)

    @property
    def audio_volume_override_danger(self) -> float:
        return float(self._data["audio"].get("volume_override_danger", 0.75))

    @audio_volume_override_danger.setter
    def audio_volume_override_danger(self, value: float) -> None:
        self._data["audio"]["volume_override_danger"] = min(max(value, 0.0), 1.0)

    @property
    def boot_animation(self) -> str:
        value = self._data["boot_animation"] if "boot_animation" in self._data else ""
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
                    dir += "/"
                paths.append(dir + value)
        for path in paths:
            if pathlib.Path(path).exists():
                return True
        return False

    @property
    def screensaver_module(self) -> str:
        return str(self._data["screensaver"].get("module", ""))
    
    @screensaver_module.setter
    def screensaver_module(self, value: str) -> None:
        if self._valid_module(value):
            self._data["screensaver"]["module"] = value

    @property
    def screensaver_class(self) -> str:
        return str(self._data["screensaver"].get("class", ""))
    
    @screensaver_class.setter
    def screensaver_class(self, value: str) -> None:
        self._data["screensaver"]["class"] = value

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
        if "timeout" in self._data["screensaver"]:
            return self._data["screensaver"].get("timeout", 30)
        else:  # compatibility with previous option
            return self._data.get("screensaver.timeout", 30)
    
    @screensaver_timeout.setter
    def screensaver_timeout(self, value: int) -> None:
        self._data["screensaver"]["timeout"] = value
    
    @property
    def screensaver_background_color(self) -> str:
        if "background_color" in self._data["screensaver"]:
            return self._data["screensaver"].get("background_color", "0x000000")
        else:  # compatibility with previous option
            return self._data.get("screensaver.background_color", "0x000000")
    
    @screensaver_background_color.setter
    def screensaver_background_color(self, value: str|int) -> None:
        if isinstance(value, int):
            value = "0x{:06x}".format(value)
        self._data["screensaver"]["background_color"] = value

    def save(self) -> None:
        with open("/saves/launcher.conf.json", "w") as f:
            json.dump(self._data, f)

    def __str__(self) -> str:
        return str(self._data)
