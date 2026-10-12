
import time
import board
from adafruit_apds9960.apds9960 import APDS9960

i2c = board.I2C()
apds = APDS9960(i2c)
apds.enable_proximity = True
apds.enable_color = True

GONE_DELAY = 1.0
BACK_DELAY = 3.0
SAMPLE_INTERVAL = 0.2

# Initial thresholds from your measurements
CHOPSTICK_MIN_PROX = 2
CHOPSTICK_MAX_CLEAR = 3800
BACKGROUND_MAX_PROX = 1

chopstick_present = True
gone_since = None
back_since = None

def classify(proximity, clear):
    # Strong evidence that the chopstick is present
    if (
        proximity >= CHOPSTICK_MIN_PROX
        and clear <= CHOPSTICK_MAX_CLEAR
    ):
        return "present"

    # Strong evidence that the sensor sees the background
    if proximity <= BACKGROUND_MAX_PROX:
        return "absent"

    # Shirt, hand, or ambiguous measurement
    return "uncertain"


print("Monitoring chopstick...")

try:
    while True:
        proximity = apds.proximity
        red, green, blue, clear = apds.color_data

        now = time.monotonic()
        result = classify(proximity, clear)

      #  print(f"Proximity:{proximity:2} | "f"R:{red:4} G:{green:4} B:{blue:4} "f"C:{clear:5} | {result}")

        if result == "absent":
            back_since = None

            if gone_since is None:
                gone_since = now

            elif chopstick_present and now - gone_since >= GONE_DELAY:
                print("chopstick gone")
                chopstick_present = False

        elif result == "present":
            gone_since = None

            if back_since is None:
                back_since = now

            elif not chopstick_present and now - back_since >= BACK_DELAY:
                print("chopstick back")
                chopstick_present = True

        else:
            # Do not let uncertain readings trigger a transition.
            # Reset timers so the evidence must be continuous.
            gone_since = None
            back_since = None

        time.sleep(SAMPLE_INTERVAL)

except KeyboardInterrupt:
    print("\nStopped.")
