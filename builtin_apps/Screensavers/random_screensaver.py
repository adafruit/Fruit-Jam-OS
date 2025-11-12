import os
import random
import displayio
from launcher_config import LauncherConfig


class RandomScreenSaver(displayio.Group):
    """ Launches a random screen saver
    The screen saver selection is only done after an OS restart (soft or hard)

    A new random selection will be made after launching an app. Simply moving
    the mouse or entering a key will interrupt the current screen saver but not
    select a new one at the next timeout.

    launcher.conf.json 'RandomScreenSaver' Parameters:
        ScreenSaverDirectory - The folder containing the Screen Saver apps
            Default: /apps/Screensavers

    """

    def __init__(self):
        super().__init__()

        randScnSaverClass = None
        self.randScnSaver = None
        self.display_size = (None, None)

        launcher_config = LauncherConfig()

        if launcher_config.data.get("RandomScreenSaver") is not None:
            scnSaverDir = launcher_config.data["RandomScreenSaver"].get("ScreenSaverDirectory", None)
            if type(scnSaverDir) == str:
                if scnSaverDir[-1:] != '/':
                    scnSaverDir += '/'
            else:
                scnSaverDir = "/apps/Screensavers/"
        else:
            scnSaverDir = "/apps/Screensavers/"

        files = []
        try:
            files = [f for f in os.listdir(scnSaverDir) if
                     f[-3:].upper() == ".PY" and f.upper() not in ['CODE.PY', 'RANDOM_SCREENSAVER.PY']]
        except OSError:
            pass

        print(f'Screen Saver Directory: {scnSaverDir}')

        randclass = []
        randScnSaverPkg = None
        while len(randclass) != 1 and len(files) > 0:
            _indx = random.randrange(len(files))
            randScnSaverPkg = __import__(scnSaverDir + files[_indx][:-3])
            filename = files.pop(_indx)

            randclass = [c for c in reversed(dir(randScnSaverPkg)) if
                         c[-11:].upper() == "SCREENSAVER" and c.upper() != "SCREENSAVER"]

        if randScnSaverPkg is not None and len(randclass) == 1:
            print(f'Selected screen saver: {filename}')
            randScnSaverClass = getattr(randScnSaverPkg, randclass[0])
            self.randScnSaver = randScnSaverClass()
            self.append(self.randScnSaver)
            self.display_size = self.randScnSaver.display_size

    def tick(self):
        if self.randScnSaver is not None:
            return self.randScnSaver.tick()

        return False