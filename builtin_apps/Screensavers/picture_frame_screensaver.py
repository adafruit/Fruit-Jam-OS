import os
import gc
import random
import gifio
import displayio
import adafruit_ticks
import adafruit_imageload
import bitmaptools
from launcher_config import LauncherConfig


class PictFrameScreenSaver(displayio.Group):
    """ Displays images (.jpg, .bmp, .png, .rle, .gif) as a screen saver

    launcher.conf.json 'PictFrame' Parameters:
        DisplaySeconds - The number of seconds to display an image before displaying the next
            Default: 15 seconds
        PictureDirectory - The folder containing the images to be displayed
            Default: First folder with image files found in this list: /, /sd/PictFrame/, /sd/
        Shuffle - Whether the images are displayed in the order found or randomly shuffled
            Default: false

    example:
    {
        "screensaver": {
            "module": "/apps/Screensavers/picture_frame_screensaver",
            "class": "PictFrameScreenSaver",
        }
        "PictFrame": {
            "DisplaySeconds": 25,
            "Shuffle": true,
            "PictureDirectory": "/sd/PictFrame",
        }
    }

    """

    display_size = (320, 240)

    def __init__(self):
        super().__init__()
        self.init_graphics()

    def __del__(self):
        if self.facecc:
            self.facecc = None
        if self.bitframe:
            self.bitframe.deinit()
            self.bitframe = None
        if self.odg:
            self.odg.deinit()
            self.odg = None
        gc.collect()

    def init_graphics(self):
        launcher_config = LauncherConfig()

        if launcher_config.data.get("PictFrame") is not None:
            self.dispseconds = launcher_config.data["PictFrame"].get("DisplaySeconds", 15)

            _shuffle = launcher_config.data["PictFrame"].get("Shuffle", False)
            if type(_shuffle) == str:
                self.shuffle = (_shuffle[0].upper() == "T")
            elif type(_shuffle) == int:
                self.shuffle = not (_shuffle == 0)
            elif type(_shuffle) != bool:
                self.shuffle == False
            else:
                self.shuffle = _shuffle

            _pictDir = launcher_config.data["PictFrame"].get("PictureDirectory", None)
            if type(_pictDir) == str:
                if _pictDir[-1:] != '/':
                    _pictDir += '/'
                _pictDir = [_pictDir]
            else:
                _pictDir = ["/", "/sd/PictFrame/", "/sd/"]
        else:
            self.dispseconds = 15
            self.shuffle = False
            _pictDir = ["/", "/sd/PictFrame/", "/sd/"]

        self.files = []
        for self.pictDir in _pictDir:
            try:
                self.files = [f for f in os.listdir(self.pictDir) if
                              f[-4:].upper() in [".BMP", ".PNG", ".JPG", ".RLE", ".GIF"]]
            except OSError:
                pass

            if len(self.files) != 0:
                break
        print(f'Picture Directory: {self.pictDir}')

        self.shuffle_indx = [i for i in range(len(self.files))]
        self.fileindx = -1
        self.odg = None
        self.bitframe = None
        self.facecc = None
        self.scalefactor = None

        self.stop = adafruit_ticks.ticks_ms()
        self.stop_frame = None
        self.displaying = False

    def tick(self):

        if adafruit_ticks.ticks_less(self.stop, adafruit_ticks.ticks_ms()):
            self.stop = adafruit_ticks.ticks_add(adafruit_ticks.ticks_ms(), int(self.dispseconds * 1000))
            if len(self.files) == 0:
                print(f"\n\n\nNo images found in the root folder or on the SD card (/sd).\n\n\n\n")
                return False

            if self.shuffle:
                if len(self.shuffle_indx) == 0:
                    self.shuffle_indx = [i for i in range(len(self.files))]

                _shuffle_indx = random.randrange(len(self.shuffle_indx))
                self.fileindx = self.shuffle_indx[_shuffle_indx]
                self.shuffle_indx.pop(_shuffle_indx)
            else:
                self.fileindx = (self.fileindx + 1) % len(self.files)

            if self.displaying:
                self.pop()
                if self.facecc:
                    self.facecc = None
                if self.bitframe:
                    self.bitframe.deinit()
                    self.bitframe = None
                if self.odg:
                    self.odg.deinit()
                    self.odg = None
                gc.collect()
            self.displaying = False
            return False

        if len(self.files) == 0:
            return False

        fname = self.files[self.fileindx]

        if fname[-4:].upper() in [".BMP", ".PNG", ".JPG", ".RLE"]:
            if self.displaying:
                return False

            try:
                # Force garbage collection before loading new image
                gc.collect()

                # Load the image
                try:
                    bitmap, palette = adafruit_imageload.load( \
                        self.pictDir + fname, bitmap=displayio.Bitmap, palette=displayio.Palette)
                except RuntimeError as e:
                    print(f"Skipping {fname} - {e}")
                    gc.collect()
                    self.stop = adafruit_ticks.ticks_ms()  # Force next image
                    return False

                # Calculate scale factor while considering memory constraints
                self.scalefactor = min(
                    self.display_size[0] / bitmap.width,
                    self.display_size[1] / bitmap.height
                )

                # Round down scale factor to prevent memory issues
                if self.scalefactor > 1:
                    self.scalefactor = int(self.scalefactor)
                print(f"{fname} self.scalefactor: {self.scalefactor}")

                # Create scaled bitmap
                self.bitframe = displayio.Bitmap(self.display_size[0], self.display_size[1], 2 ** bitmap.bits_per_value)
                bitmaptools.rotozoom(self.bitframe, bitmap, scale=self.scalefactor)
                self.facecc = displayio.TileGrid(self.bitframe, pixel_shader=palette)
                pwidth = self.bitframe.width
                pheight = self.bitframe.height

                # Clean up original bitmap
                bitmap.deinit()
                bitmap = None
                gc.collect()

            except MemoryError:
                print(f"Skipping {fname} - insufficient memory")
                gc.collect()
                self.stop = adafruit_ticks.ticks_ms()  # Force next image
                return False

            if pwidth < self.display_size[0]:
                self.facecc.x = (self.display_size[0] - pwidth) // 2
            if pheight < self.display_size[1]:
                self.facecc.y = (self.display_size[1] - pheight) // 2
            self.append(self.facecc)
            self.displaying = True

            return True

        elif fname[-4:].upper() in [".GIF"]:

            if not self.displaying:
                try:
                    # Force garbage collection before loading new GIF
                    gc.collect()

                    self.odg = gifio.OnDiskGif(self.pictDir + fname)

                    if os.getenv('PYDOS_DISPLAYIO_COLORSPACE', "").upper() == 'BGR565_SWAPPED':
                        colorspace = displayio.Colorspace.BGR565_SWAPPED
                    else:
                        colorspace = displayio.Colorspace.RGB565_SWAPPED

                    # Calculate scale factor while considering memory constraints
                    self.scalefactor = min(
                        self.display_size[0] / self.odg.width,
                        self.display_size[1] / self.odg.height
                    )

                    if self.scalefactor > 1:
                        self.scalefactor = int(self.scalefactor)
                    print(f"{fname} self.scalefactor: {self.scalefactor}")

                    if self.scalefactor != 1:
                        # Create scaled bitmap with optimized dimensions
                        self.bitframe = displayio.Bitmap(self.display_size[0], self.display_size[1],
                                                         2 ** self.odg.bitmap.bits_per_value)
                        bitmaptools.rotozoom(self.bitframe, self.odg.bitmap, scale=self.scalefactor)
                        self.facecc = displayio.TileGrid(self.bitframe, \
                                                         pixel_shader=displayio.ColorConverter(
                                                             input_colorspace=colorspace))
                        pwidth = self.bitframe.width
                        pheight = self.bitframe.height
                    else:
                        self.facecc = displayio.TileGrid(self.odg.bitmap, \
                                                         pixel_shader=displayio.ColorConverter(
                                                             input_colorspace=colorspace))
                        pwidth = self.odg.bitmap.width
                        pheight = self.odg.bitmap.height

                    gc.collect()  # Clean up any temporary objects

                except MemoryError:
                    print(f"Skipping {fname} - insufficient memory")
                    if self.odg:
                        self.odg.deinit()
                        self.odg = None
                    gc.collect()
                    self.stop = adafruit_ticks.ticks_ms()  # Force next image
                    return False

                if pwidth < self.display_size[0]:
                    self.facecc.x = (self.display_size[0] - pwidth) // 2
                if pheight < self.display_size[1]:
                    self.facecc.y = (self.display_size[1] - pheight) // 2
                self.append(self.facecc)
                self.displaying = True
                self.stop_frame = None

                return True

            if self.stop_frame is None or \
                    adafruit_ticks.ticks_less(self.stop_frame, adafruit_ticks.ticks_ms()):
                try:
                    next_delay = self.odg.next_frame()
                    self.stop_frame = adafruit_ticks.ticks_add(adafruit_ticks.ticks_ms(), int(next_delay * 1000))

                    if next_delay > 0:
                        if self.scalefactor != 1:
                            gc.collect()  # Clean up before frame update
                            bitmaptools.rotozoom(self.bitframe, self.odg.bitmap, scale=self.scalefactor)

                    return True

                except MemoryError:
                    print(f"Memory error during GIF animation - skipping to next image")
                    if self.odg:
                        self.odg.deinit()
                        self.odg = None
                    gc.collect()
                    self.stop = adafruit_ticks.ticks_ms()  # Force next image
                    return False

            return False
