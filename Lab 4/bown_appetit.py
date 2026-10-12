import time
import board
from adafruit_apds9960.apds9960 import APDS9960

i2c = board.I2C()
apds = APDS9960(i2c)
apds.enable_proximity = True

previous_value = apds.proximity
above_one_since = None
back_printed = False

while True:
    current_value = apds.proximity
    print(current_value)

    # Chopstick removed
    if previous_value > 1 and current_value <= 1:
        print("chopstick gone")
        above_one_since = None
        back_printed = False

    # Reading is back above 1
    if current_value > 1:
        if above_one_since is None:
            above_one_since = time.time()

        # Only print once after staying above 1 for 3 seconds
        elif not back_printed and time.time() - above_one_since >= 3:
            print("chopstick back")
            back_printed = True
    else:
        above_one_since = None
        back_printed = False

    previous_value = current_value
    time.sleep(0.2)
