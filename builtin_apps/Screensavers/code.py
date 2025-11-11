import supervisor
from adafruit_fruitjam.peripherals import request_display_config

m = __import__("apps/Screensavers/flying_toasters_screensaver")
cls = getattr(m, "FlyingToasterScreenSaver")

# m = __import__("apps/Screensavers/fish_screensaver")
# cls = getattr(m, "FishScreenSaver")

# m = __import__("apps/Screensavers/bouncing_logo_screensaver")
# cls = getattr(m, "BouncingLogoScreensaver")

screensaver = cls()
request_display_config(screensaver.display_size[0], screensaver.display_size[1])
display = supervisor.runtime.display
display.root_group = screensaver

display.auto_refresh = False
while True:
    needs_refresh = screensaver.tick()
    if needs_refresh:
        display.refresh()