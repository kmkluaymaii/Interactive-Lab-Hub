import time
import board
import threading
import subprocess
import pi_servo_hat

from adafruit_apds9960.apds9960 import APDS9960


# ==========================================
# SERVO SETTINGS
# ==========================================
SERVO_CH = 0

UPRIGHT = 45
BOWING = 90

# Same movement speed for bowing down and returning upright
MOVEMENT_SPEED = 0.005


# ==========================================
# AUDIO SETTINGS
# ==========================================
AUDIO_FILE = "/home/pi/Interactive-Lab-Hub/Lab 4/ittadakimasu.mp3"

# Let the greeting play briefly before bowing
AUDIO_HEAD_START = 0.5

# Pause briefly while bowed before returning upright
BOW_HOLD_TIME = 0.5


# ==========================================
# CHOPSTICK SENSOR SETTINGS
# ==========================================
GONE_DELAY = 0.6
BACK_DELAY = 0.6
SAMPLE_INTERVAL = 0.2

# Thresholds based on your sensor measurements
CHOPSTICK_MIN_PROX = 2
CHOPSTICK_MAX_CLEAR = 3800
BACKGROUND_MAX_PROX = 1


# Initial state: wait until a chopstick is detected
chopstick_present = False
initialized = False

gone_since = None
back_since = None


# ==========================================
# INITIALIZE SERVO
# ==========================================
print("Initializing servo...")

servo = pi_servo_hat.PiServoHat()
servo.restart()

servo.move_servo_position(SERVO_CH, UPRIGHT)
time.sleep(1)


# ==========================================
# INITIALIZE APDS9960 SENSOR
# ==========================================
print("Initializing APDS9960 sensor...")

i2c = board.I2C()
apds = APDS9960(i2c)

apds.enable_proximity = True
apds.enable_color = True


# ==========================================
# CLASSIFY SENSOR READINGS
# ==========================================
def classify(proximity, clear):
    """
    Return:
        'present'   - chopstick detected
        'absent'    - background detected
        'uncertain' - ambiguous reading
    """

    # Strong evidence that the chopstick is present
    if (
        proximity >= CHOPSTICK_MIN_PROX
        and clear <= CHOPSTICK_MAX_CLEAR
    ):
        return "present"

    # Strong evidence that the sensor sees the background
    if proximity <= BACKGROUND_MAX_PROX:
        return "absent"

    # Hand, shirt, or ambiguous measurement
    return "uncertain"


# ==========================================
# SERVO MOVEMENT
# ==========================================
def move_smoothly(start_angle, end_angle, step_delay=MOVEMENT_SPEED):
    """Move the servo smoothly between two angles."""

    step = 1 if end_angle > start_angle else -1

    for angle in range(start_angle, end_angle + step, step):
        servo.move_servo_position(SERVO_CH, angle)
        time.sleep(step_delay)


# ==========================================
# PLAY JAPANESE GREETING
# ==========================================
def play_greeting():
    """Play the Itadakimasu greeting."""

    subprocess.run(
        ["mpg123", "-q", AUDIO_FILE],
        check=True
    )


# ==========================================
# GREETING AND BOW SEQUENCE
# ==========================================
def perform_bow():
    """Play the greeting, bow, and return upright."""

    print("\nChopstick gone! Playing greeting and bowing.")

    # Start the audio in a separate thread
    audio_thread = threading.Thread(target=play_greeting)
    audio_thread.start()

    # Let the greeting begin before bowing
    time.sleep(AUDIO_HEAD_START)

    # Bow down while the greeting continues
    move_smoothly(
        UPRIGHT,
        BOWING,
        step_delay=MOVEMENT_SPEED
    )

    # Wait for the greeting to finish
    audio_thread.join()

    # Hold the bowed position briefly
    time.sleep(BOW_HOLD_TIME)

    # Return upright at the same speed
    move_smoothly(
        BOWING,
        UPRIGHT,
        step_delay=MOVEMENT_SPEED
    )

    print("Bow complete. Waiting for chopstick to return.")


# ==========================================
# MAIN SENSOR LOOP
# ==========================================
print("\nBow-n Appétit is ready!")
print("Waiting for the chopstick to be detected...")
print("Press Ctrl+C to stop.\n")


try:
    while True:

        # Read the sensor
        proximity = apds.proximity
        red, green, blue, clear = apds.color_data

        now = time.monotonic()
        result = classify(proximity, clear)

        # Uncomment to see live sensor readings
        # print(
        #     f"Proximity: {proximity:2} | "
        #     f"R: {red:4} G: {green:4} B: {blue:4} "
        #     f"C: {clear:5} | {result}"
        # )

        # --------------------------------------
        # STARTUP: WAIT FOR FIRST DETECTION
        # --------------------------------------
        if not initialized:

            if result == "present":
                initialized = True
                chopstick_present = True

                gone_since = None
                back_since = None

                print("Chopstick detected!")
                print("Monitoring for chopstick removal...")

            else:
                # Do nothing until the chopstick is detected
                gone_since = None
                back_since = None

            time.sleep(SAMPLE_INTERVAL)
            continue

        # --------------------------------------
        # CHOPSTICK IS ABSENT
        # --------------------------------------
        if result == "absent":

            # Cancel any timer for the chopstick returning
            back_since = None

            if gone_since is None:
                gone_since = now

            elif (
                chopstick_present
                and now - gone_since >= GONE_DELAY
            ):
                # Confirmed that the chopstick is gone
                chopstick_present = False
                gone_since = None

                # Play greeting and bow once
                perform_bow()

        # --------------------------------------
        # CHOPSTICK IS PRESENT
        # --------------------------------------
        elif result == "present":

            # Cancel any timer for the chopstick going away
            gone_since = None

            if back_since is None:
                back_since = now

            elif (
                not chopstick_present
                and now - back_since >= BACK_DELAY
            ):
                # Confirmed that the chopstick has returned
                chopstick_present = True
                back_since = None

                print("\nChopstick back!")
                print("Ready for the next removal.")

        # --------------------------------------
        # UNCERTAIN SENSOR READING
        # --------------------------------------
        else:

            # Require continuous evidence before changing states
            gone_since = None
            back_since = None

        time.sleep(SAMPLE_INTERVAL)


except KeyboardInterrupt:
    print("\nBow-n Appétit stopped.")

except Exception as e:
    print(f"\nAn error occurred: {e}")

finally:
    # Return the servo to the upright position
    servo.move_servo_position(SERVO_CH, UPRIGHT)
    print("Servo returned to upright position.")
