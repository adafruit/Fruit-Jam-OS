# SPDX-FileCopyrightText: 2025 Tim Cocks for Adafruit Industries
#
# SPDX-License-Identifier: MIT
import gc

import displayio
import supervisor
from displayio import OnDiskBitmap, TileGrid, Group
import adafruit_imageload
import time
import math

display = supervisor.runtime.display
display.auto_refresh = False


def make_alternate_platte(input_palette, target_color):
    new_palette = displayio.Palette(len(input_palette))

    for i in range(len(input_palette)):
        new_palette[i] = input_palette[i] & target_color
    new_palette.make_transparent(0)
    return new_palette


class OvershootAnimator:
    """
    A non-blocking animator that moves an element to a target with overshoot effect.

    Instead of blocking with sleep(), this class provides a tick() method that
    should be called repeatedly by an external loop (e.g., game loop, UI event loop).
    """

    def __init__(self, element):
        """
        Initialize the animator with an element to animate.

        Parameters:
        - element: An object with x and y properties that will be animated
        """
        self.element = element
        self.pos_animating = False
        self.start_time = 0
        self.start_x = 0
        self.start_y = 0
        self.target_x = 0
        self.target_y = 0
        self.overshoot_x = 0
        self.overshoot_y = 0
        self.duration = 0
        self.overshoot_pixels = 0
        self.eased_value = None

        self.cur_sprite_index = None
        self.last_sprite_frame_time = -1
        self.sprite_anim_start_time = -1
        self.sprite_anim_from_index = None
        self.sprite_anim_to_index = None
        self.sprite_anim_delay = None

    def animate_to(self, target_x, target_y, duration=1.0, overshoot_pixels=20,
                   start_sprite_anim_at=None, sprite_delay=1 / 60,
                   sprite_from_index=None, sprite_to_index=None, eased_value=None):

        """
        Start a new animation to the specified target.

        Parameters:
        - target_x, target_y: The final target coordinates
        - duration: Total animation time in seconds
        - overshoot_pixels: How many pixels to overshoot beyond the target
                            (use 0 for no overshoot)
        """
        _now = time.monotonic()

        # Record starting position and time
        self.start_x = self.element.x
        self.start_y = self.element.y
        self.start_time = _now
        if start_sprite_anim_at is not None:
            self.sprite_anim_start_time = _now + start_sprite_anim_at
            self.sprite_anim_to_index = sprite_to_index
            self.sprite_anim_from_index = sprite_from_index
            self.cur_sprite_index = self.sprite_anim_from_index
            self.sprite_anim_delay = sprite_delay

        # Store target position and parameters
        self.target_x = target_x
        self.target_y = target_y
        self.duration = duration
        self.overshoot_pixels = overshoot_pixels

        # Calculate distance to target
        dx = target_x - self.start_x
        dy = target_y - self.start_y

        # Calculate the direction vector (normalized)
        distance = math.sqrt(dx * dx + dy * dy)
        if distance <= 0:
            # Already at target
            return False

        dir_x = dx / distance
        dir_y = dy / distance

        # Calculate overshoot position
        self.overshoot_x = target_x + dir_x * overshoot_pixels
        self.overshoot_y = target_y + dir_y * overshoot_pixels

        self.eased_value = eased_value

        # Start the animation
        self.pos_animating = True
        return True

    def sprite_anim_tick(self, cur_time):
        if cur_time >= self.last_sprite_frame_time + self.sprite_anim_delay:
            # print(f"cur idx: {self.cur_sprite_index}")
            self.element[0] = self.cur_sprite_index

            self.last_sprite_frame_time = cur_time
            # display.refresh()
            self.cur_sprite_index += 1
            # print(f"cur idx: {self.cur_sprite_index} > {self.sprite_anim_to_index}")
            if self.cur_sprite_index > self.sprite_anim_to_index:
                # print("returning false from sprite_anim_tick")
                self.cur_sprite_index = None
                self.sprite_anim_from_index = None
                self.sprite_anim_to_index = None
                self.sprite_anim_delay = None
                self.last_sprite_frame_time = -1
                self.sprite_anim_start_time = -1
                return False

        return True

    def tick(self):
        """
        Update the animation based on the current time.

        This method should be called repeatedly until it returns False.

        Returns:
        - True if the animation is still in progress
        - False if the animation has completed
        """
        still_sprite_animating = False
        _now = time.monotonic()
        if self.cur_sprite_index is not None:
            if _now >= self.sprite_anim_start_time:

                still_sprite_animating = self.sprite_anim_tick(_now)
                # print("sprite_still_animating", still_sprite_animating)
                if not still_sprite_animating:
                    return False
        else:
            if not self.pos_animating:
                # print("returning false cur_sprite_index was None and pos_animating False")
                return False

        # Calculate elapsed time and progress
        elapsed = _now - self.start_time
        progress = elapsed / self.duration

        # Check if animation is complete
        if progress >= 1.0:
            # Ensure we end exactly at the target
            if self.element.x != self.target_x or self.element.y != self.target_y:
                self.element.x = self.target_x
                self.element.y = self.target_y
                # display.refresh()
            self.pos_animating = False
            if still_sprite_animating:
                return True
            else:
                return False

        # Calculate the current position based on progress
        if self.overshoot_pixels > 0:
            # Two-phase animation with overshoot
            if progress < 0.7:  # Move smoothly toward overshoot position
                # Use a single smooth curve to the overshoot point
                eased = progress / 0.7  # Linear acceleration toward overshoot
                # Apply slight ease-in to make it accelerate through the target point
                eased = eased ** 1.2
                current_x = self.start_x + (self.overshoot_x - self.start_x) * eased
                current_y = self.start_y + (self.overshoot_y - self.start_y) * eased
            else:  # Return from overshoot to target
                sub_progress = (progress - 0.7) / 0.3
                # Decelerate toward final target
                eased = 1 - (1 - sub_progress) ** 2  # ease-out quad
                current_x = self.overshoot_x + (self.target_x - self.overshoot_x) * eased
                current_y = self.overshoot_y + (self.target_y - self.overshoot_y) * eased
        else:
            # Simple ease-out when no overshoot is desired
            if self.eased_value is None:
                eased = 1 - (1 - progress) ** 4
            else:
                eased = progress / self.eased_value
            current_x = self.start_x + (self.target_x - self.start_x) * eased
            current_y = self.start_y + (self.target_y - self.start_y) * eased

        # Update element position
        self.element.x = int(current_x)
        self.element.y = int(current_y)
        # print(f"cur: {self.element.x}, {self.element.y}")
        # display.refresh(target_frames_per_second=30)

        return True

    def is_animating(self):
        """Check if an animation is currently in progress."""
        return self.pos_animating

    def cancel(self):
        """Cancel the current animation."""
        self.pos_animating = False


# 8172592
# apple_sprites, apple_sprites_palette = adafruit_imageload.load("apple_spritesheet.bmp")

# 8342576

def color_sweep(color, palette, delay=0, start_at_index=1):
    for i in range(start_at_index, len(palette)):
        palette[i] = color
        if delay > 0:
            time.sleep(delay)


apple_sprites, apple_sprites_palette = adafruit_imageload.load("/boot_animation/apple_spritesheet_lined_6_indexed.bmp")
#print(f"free: {gc.mem_free()}")
# apple_sprites_palette.make_transparent(0)
color_sweep(0xffffff, apple_sprites_palette)

f_sprites, f_sprites_palette = adafruit_imageload.load("/boot_animation/f_spritesheet_lined_6_indexed.bmp")
color_sweep(0xffffff, f_sprites_palette)
# f_sprites_palette.make_transparent(0)
r_sprites, r_sprites_palette = adafruit_imageload.load("/boot_animation/r_spritesheet_lined_6_indexed.bmp")
color_sweep(0xffffff, r_sprites_palette)
# r_sprites_palette.make_transparent(0)
u_sprites, u_sprites_palette = adafruit_imageload.load("/boot_animation/u_spritesheet_lined_6_indexed.bmp")
color_sweep(0xffffff, u_sprites_palette)
# u_sprites_palette.make_transparent(0)
i_sprites, i_sprites_palette = adafruit_imageload.load("/boot_animation/i_spritesheet_lined_6_indexed.bmp")
color_sweep(0xffffff, i_sprites_palette)
# i_sprites_palette.make_transparent(0)
t_sprites, t_sprites_palette = adafruit_imageload.load("/boot_animation/t_spritesheet_lined_6_indexed.bmp")
color_sweep(0xffffff, t_sprites_palette)
# t_sprites_palette.make_transparent(0)
j_sprites, j_sprites_palette = adafruit_imageload.load("/boot_animation/j_spritesheet_lined_6_indexed.bmp")
j_sprites_palette.make_transparent(0)
color_sweep(0xffffff, j_sprites_palette, start_at_index=2)
a_sprites, a_sprites_palette = adafruit_imageload.load("/boot_animation/a_spritesheet_lined_6_indexed.bmp")
a_sprites_palette.make_transparent(0)
color_sweep(0xffffff, a_sprites_palette, start_at_index=2)
m_sprites, m_sprites_palette = adafruit_imageload.load("/boot_animation/m_spritesheet_lined_6_indexed.bmp")
m_sprites_palette.make_transparent(0)
color_sweep(0xffffff, m_sprites_palette, start_at_index=2)


def color_sweep_all(color, delay=0.05, refresh_during=True):
    _start = 4

    for i in range(1, len(apple_sprites_palette)):
        apple_sprites_palette[i] = color

        if _start <= i < _start+7:
            f_sprites_palette[i-_start+1] = color
            r_sprites_palette[i-_start+1] = color
            u_sprites_palette[i-_start+1] = color
            i_sprites_palette[i-_start+1] = color
            t_sprites_palette[i-_start+1] = color
        # print(f"i: {i} >= {len(apple_sprites_palette) -7}")
        if i >= len(apple_sprites_palette) - 7:
            _adjusted_idx = i - (len(apple_sprites_palette) - 7) + 2
            # print(f"adj idx: {_adjusted_idx}")
            j_sprites_palette[_adjusted_idx] = color
            a_sprites_palette[_adjusted_idx] = color
            m_sprites_palette[_adjusted_idx] = color

        if i % 6 == 0 and refresh_during:
            display.refresh()
            if delay > 0:
                time.sleep(delay)
    display.refresh()
# apple_sprites = OnDiskBitmap("apple_spritesheet.bmp")
# apple_sprites_palette = apple_sprites.pixel_shader
# apple_sprites_palette.make_transparent(0)
#
# f_sprites = OnDiskBitmap("f_spritesheet.bmp")
# f_sprites_palette = f_sprites.pixel_shader
# f_sprites_palette.make_transparent(0)
# r_sprites = OnDiskBitmap("r_spritesheet.bmp")
# r_sprites_palette = r_sprites.pixel_shader
# r_sprites_palette.make_transparent(0)
# u_sprites = OnDiskBitmap("u_spritesheet.bmp")
# u_sprites_palette = u_sprites.pixel_shader
# u_sprites_palette.make_transparent(0)
# i_sprites = OnDiskBitmap("i_spritesheet.bmp")
# i_sprites_palette = i_sprites.pixel_shader
# i_sprites_palette.make_transparent(0)
# t_sprites = OnDiskBitmap("t_spritesheet.bmp")
# t_sprites_palette = t_sprites.pixel_shader
# t_sprites_palette.make_transparent(0)
# j_sprites = OnDiskBitmap("j_spritesheet.bmp")
# j_sprites_palette = j_sprites.pixel_shader
# j_sprites_palette.make_transparent(0)
# a_sprites = OnDiskBitmap("a_spritesheet.bmp")
# a_sprites_palette = a_sprites.pixel_shader
# a_sprites_palette.make_transparent(0)
# m_sprites = OnDiskBitmap("m_spritesheet.bmp")
# m_sprites_palette = m_sprites.pixel_shader
# m_sprites_palette.make_transparent(0)

default_sprite_delay = 1 / 35

main_group = Group()
main_group.x = display.width // 4
main_group.y = display.height // 4

sliding_group = Group()
main_group.append(sliding_group)

letters_x_start = 83
letters_y_start = display.height

coordinator = {
    "steps": [
        # Apple fly on
        {
            "type": "animation_step",
            "tilegrid": TileGrid(apple_sprites, pixel_shader=apple_sprites_palette,
                                 tile_width=73, tile_height=107, width=1, height=1),
            "offscreen_loc": (0, -107),
            "onscreen_loc": (0, 21),
            "move_duration": 0.45,
            "overshoot_pixels": 1,
            "eased_value": None,
            "sprite_anim_range": (0, 11),
            "sprite_delay": 1 / 42,
            "start_time": 0.0,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        # F fly on
        {
            "type": "animation_step",
            "tilegrid": TileGrid(f_sprites, pixel_shader=f_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start, letters_y_start),
            "onscreen_loc": (letters_x_start, 67),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 0.45,
            "sprite_anim_start": 0.347,
            "started": False,

        },
        # R fly on
        {
            "type": "animation_step",
            "tilegrid": TileGrid(r_sprites, pixel_shader=r_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + 32 + 3 - 1, letters_y_start),
            "onscreen_loc": (letters_x_start + 32 + 3 - 1, 67),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 0.9,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        # Left slide everything
        {
            "type": "animation_step",
            "tilegrid": sliding_group,
            "offscreen_loc": (100, 0),
            "onscreen_loc": (30, 0),
            "move_duration": 1.75,
            "overshoot_pixels": 0,

            "eased_value": 1,
            "sprite_anim_range": None,
            "sprite_delay": None,
            "start_time": 0.9,
            "sprite_anim_start": None,
            "started": False,
        },
        # U fly on
        {
            "type": "animation_step",
            "tilegrid": TileGrid(u_sprites, pixel_shader=u_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + (32 + 3) * 2 - 2, letters_y_start),
            "onscreen_loc": (letters_x_start + (32 + 3) * 2 - 2, 67),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 1.35,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        # I fly on
        {
            "type": "animation_step",
            "tilegrid": TileGrid(i_sprites, pixel_shader=i_sprites_palette,
                                 tile_width=16, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + (32 + 3) * 3 - 3, letters_y_start),
            "onscreen_loc": (letters_x_start + (32 + 3) * 3 - 3, 67),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 1.8,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        # T fly on
        {
            "type": "animation_step",
            "tilegrid": TileGrid(t_sprites, pixel_shader=t_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + (32 + 3) * 3 + 16 + 3 - 4, letters_y_start),
            "onscreen_loc": (letters_x_start + (32 + 3) * 3 + 16 + 3 - 4, 67),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 2.25,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        # J fly on
        {
            "type": "animation_step",
            "tilegrid": TileGrid(j_sprites, pixel_shader=j_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start, letters_y_start),
            "onscreen_loc": (letters_x_start, 50 + 39),
            "move_duration": 0.45,
            "overshoot_pixels": 4,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 2.7,
            # "sprite_anim_start": 0.347,
            "sprite_anim_start": 0.4,
            "started": False,
        },
        # A fly on
        {
            "type": "animation_step",
            "tilegrid": TileGrid(a_sprites, pixel_shader=a_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + 32 + 3 - 1, letters_y_start),
            "onscreen_loc": (letters_x_start + 32 + 3 - 1, 50 + 39),
            "move_duration": 0.45,
            "overshoot_pixels": 4,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 3.15,
            "sprite_anim_start": 0.4,
            "started": False,
        },
        # M fly on
        {
            "type": "animation_step",
            "tilegrid": TileGrid(m_sprites, pixel_shader=m_sprites_palette,
                                 tile_width=43, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + 32 + 3 + 32 + 2 - 1, letters_y_start),
            "onscreen_loc": (letters_x_start + 32 + 3 + 32 + 2 - 1, 50 + 39),
            "move_duration": 0.45,
            "overshoot_pixels": 4,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 3.6,
            "sprite_anim_start": 0.4,
            "started": False,
        }

    ]
}

for step in coordinator["steps"]:
    if isinstance(step["tilegrid"], TileGrid):
        sliding_group.append(step["tilegrid"])
        step["default_palette"] = step["tilegrid"].pixel_shader
        # step["red_palette"] = make_alternate_platte(step["default_palette"], 0xff0000)
        # step["yellow_palette"] = make_alternate_platte(step["default_palette"], 0xffff00)
        # step["teal_palette"] = make_alternate_platte(step["default_palette"], 0x00ffff)
        # step["pink_palette"] = make_alternate_platte(step["default_palette"], 0xff00ff)
        # step["blue_palette"] = make_alternate_platte(step["default_palette"], 0x0000ff)
        # step["green_palette"] = make_alternate_platte(step["default_palette"], 0x00ff00)
        # step["tilegrid"].pixel_shader = step["red_palette"]
    step["tilegrid"].x = step["offscreen_loc"][0]
    step["tilegrid"].y = step["offscreen_loc"][1]
    step["animator"] = OvershootAnimator(step["tilegrid"])

# F bounce up from J impact
coordinator["steps"].insert(8,
                            {
                                "type": "animation_step",
                                "tilegrid": coordinator["steps"][1]["tilegrid"],
                                "animator": coordinator["steps"][1]["animator"],
                                "offscreen_loc": (letters_x_start, letters_y_start),
                                "onscreen_loc": (letters_x_start, 52),
                                # "move_duration": 0.3,
                                "move_duration": 0.3,
                                "overshoot_pixels": 22,
                                "eased_value": None,
                                "sprite_anim_range": (19, 27),
                                "sprite_delay": 1 / 22,
                                # "start_time": 4.08,
                                # "start_time": 3.047,
                                "start_time": 3.0,
                                # "sprite_anim_start": 0.15,
                                "sprite_anim_start": 0.15,
                                "started": False,
                            },
                            )
# R bounce up from A impact
coordinator["steps"].insert(10,
                            {
                                "type": "animation_step",
                                "tilegrid": coordinator["steps"][2]["tilegrid"],
                                "animator": coordinator["steps"][2]["animator"],
                                "offscreen_loc": (letters_x_start + 32 + 3 - 1, letters_y_start),
                                "onscreen_loc": (letters_x_start + 32 + 3 - 1, 52),
                                "move_duration": 0.3,
                                "overshoot_pixels": 22,
                                "eased_value": None,
                                "sprite_anim_range": (19, 27),
                                "sprite_delay": 1 / 22,
                                # "start_time": 4.78,
                                # "start_time": 3.497,
                                "start_time": 3.45,
                                "sprite_anim_start": 0.15,
                                "started": False,
                            },
                            )
# U bounce up from M impact
coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][4]["tilegrid"],
        "animator": coordinator["steps"][4]["animator"],
        "offscreen_loc": (letters_x_start + (32 + 3) * 2 - 2, letters_y_start),
        "onscreen_loc": (letters_x_start + (32 + 3) * 2 - 2, 52),
        "move_duration": 0.3,
        "overshoot_pixels": 22,
        "eased_value": None,
        "sprite_anim_range": (19, 27),
        "sprite_delay": 1 / 22,
        # "start_time": 5.48,
        # "start_time": 3.947,
        "start_time": 3.9,
        "sprite_anim_start": 0.15,
        "started": False,
    },
)
# I bounce up from M impact
coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][5]["tilegrid"],
        "animator": coordinator["steps"][5]["animator"],
        "offscreen_loc": (letters_x_start + (32 + 3) * 3 - 3, letters_y_start),
        "onscreen_loc": (letters_x_start + (32 + 3) * 3 - 3, 52),
        "move_duration": 0.3,
        "overshoot_pixels": 22,
        "eased_value": None,
        "sprite_anim_range": (19, 27),
        "sprite_delay": 1 / 22,
        # "start_time": 5.58,
        # "start_time": 4.047,
        "start_time": 4.00,
        "sprite_anim_start": 0.15,
        "started": False,
    },
)
# T bounce up from M impact
coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][6]["tilegrid"],
        "animator": coordinator["steps"][6]["animator"],
        "offscreen_loc": (letters_x_start + (32 + 3) * 3 + 16 + 3 - 4,  letters_y_start),
        "onscreen_loc": (letters_x_start + (32 + 3) * 3 + 16 + 3 - 4, 52),
        "move_duration": 0.3,
        "overshoot_pixels": 22,
        "eased_value": None,
        "sprite_anim_range": (19, 27),
        "sprite_delay": 1 / 22,
        # "start_time": 5.68,
        # "start_time": 4.147,
        "start_time": 4.1,
        "sprite_anim_start": 0.15,
        "started": False,
    },
)
# color red
coordinator["steps"].append(
    {
        "start_time": 4.75,
        "type": "change_palette",
        "new_palette": "red_palette",
        "color": 0xff0000,
        "started": False,
    }
)
# color yellow
coordinator["steps"].append(
    {
        "start_time": 5,
        "type": "change_palette",
        "new_palette": "yellow_palette",
        "color": 0xffff00,
        "started": False,
    }
)
# color teal
coordinator["steps"].append(
    {
        "start_time": 5.25,
        "type": "change_palette",
        "new_palette": "teal_palette",
        "color": 0x00ffff,
        "started": False,
    }
)
# color pink
coordinator["steps"].append(
    {
        "start_time": 5.5,
        "type": "change_palette",
        "new_palette": "pink_palette",
        "color": 0xff00ff,
        "started": False,
    }
)
# color blue
coordinator["steps"].append(
    {
        "start_time": 5.75,
        "type": "change_palette",
        "new_palette": "blue_palette",
        "color": 0x0000ff,
        "started": False,
    }
)
# color green
coordinator["steps"].append(
    {
        "start_time": 6.00,
        "type": "change_palette",
        "new_palette": "green_palette",
        "color": 0x00ff00,
        "started": False,
    }
)
# Apple eyes blink
coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][0]["tilegrid"],
        "animator": coordinator["steps"][0]["animator"],
        "offscreen_loc": (0, -107),
        "onscreen_loc": (0, 21),
        "move_duration": 0.01,
        "overshoot_pixels": 0,
        "eased_value": None,
        "sprite_anim_range": (12, 27),
        "sprite_delay": 1 / 32,
        # "start_time": 5.68,
        "start_time": 6.65,
        "sprite_anim_start": 0.0,
        "started": False,
    }
)
# Apple eyes blink again
coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][0]["tilegrid"],
        "animator": coordinator["steps"][0]["animator"],
        "offscreen_loc": (0, -107),
        "onscreen_loc": (0, 21),
        "move_duration": 0.01,
        "overshoot_pixels": 0,
        "eased_value": None,
        "sprite_anim_range": (13, 18),
        "sprite_delay": 1 / 32,
        # "start_time": 5.68,
        "start_time": 8.75,
        "sprite_anim_start": 0.0,
        "started": False,
    }
)

display.root_group = main_group

# hrule = displayio.Bitmap(200, 1, 1)
# hrule_palette = displayio.Palette(1)
# hrule_palette[0] = 0xff0000
# hrule_tg = TileGrid(bitmap=hrule, pixel_shader=hrule_palette)
# main_group.append(hrule_tg)
# hrule_tg.y = 59
# hrule_tg.x = 40

start_time = time.monotonic()

while True:

    now = time.monotonic()
    still_going = True

    for i, step in enumerate(coordinator["steps"]):
        if now - start_time >= step["start_time"]:
            if not step["started"]:
                step["started"] = True
                if step["type"] == "animation_step":
                    if step["sprite_anim_range"] is not None:
                        step["animator"].animate_to(
                            *step["onscreen_loc"],
                            duration=step["move_duration"], overshoot_pixels=step["overshoot_pixels"],
                            start_sprite_anim_at=step["sprite_anim_start"],
                            sprite_from_index=step["sprite_anim_range"][0],
                            sprite_to_index=step["sprite_anim_range"][1],
                            sprite_delay=step["sprite_delay"], eased_value=step["eased_value"],
                        )
                    else:
                        step["animator"].animate_to(
                            *step["onscreen_loc"],
                            duration=step["move_duration"], overshoot_pixels=step["overshoot_pixels"],
                            eased_value=step["eased_value"]
                        )
                elif step["type"] == "change_palette":
                    color_sweep_all(step["color"], delay=0)

            if "animator" in step:
                if i == len(coordinator["steps"]) - 1:
                    still_going = step["animator"].tick()
                else:
                    step["animator"].tick()
            else:
                if i == len(coordinator["steps"]) - 1:
                    still_going = False

    display.refresh()

    if not still_going:
        for step in coordinator["steps"]:
            if step["type"] == "animation_step":
                step["tilegrid"].x = step["offscreen_loc"][0]
                step["tilegrid"].y = step["offscreen_loc"][1]

            step["started"] = False

        # reset the apple to no eyes sprite
        coordinator["steps"][0]["tilegrid"][0] = 0

        time.sleep(2)
        color_sweep_all(0xffffff, delay=0, refresh_during=False)
        display.refresh()
        start_time = time.monotonic()
