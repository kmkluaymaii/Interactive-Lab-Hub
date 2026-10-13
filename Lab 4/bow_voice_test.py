import pi_servo_hat
import subprocess
import time
import threading

# =========================
# Servo Settings
# =========================
SERVO_CH = 0

UPRIGHT = 45
BOWING = 90

# Same speed for bowing down and returning upright
MOVEMENT_SPEED = 0.005

# =========================
# Audio Settings
# =========================
AUDIO_FILE = "/home/pi/Interactive-Lab-Hub/Lab 4/ittadakimasu.mp3"

# Delay before the servo starts bowing
AUDIO_HEAD_START = 0.5


# =========================
# Initialize Servo
# =========================
servo = pi_servo_hat.PiServoHat()
servo.restart()


# =========================
# Servo Movement
# =========================
def move_smoothly(start_angle, end_angle, step_delay=MOVEMENT_SPEED):
    """Move the servo smoothly between two angles."""
    step = 1 if end_angle > start_angle else -1

    for angle in range(start_angle, end_angle + step, step):
        servo.move_servo_position(SERVO_CH, angle)
        time.sleep(step_delay)


# =========================
# Play Japanese Greeting
# =========================
def play_greeting():
    """Play the Itadakimasu greeting."""
    subprocess.run(
        ["mpg123", "-q", AUDIO_FILE],
        check=True
    )


# =========================
# Main Program
# =========================
try:
    # Start in the upright position
    servo.move_servo_position(SERVO_CH, UPRIGHT)
    time.sleep(1)

    print("Bow-n Appétit is ready!")
    print("Press Enter to play the greeting and bow.")
    print("Press Ctrl+C to stop the program.")

    while True:
        input("\nPress Enter to say Itadakimasu and bow...")

        # 1. Start playing the greeting
        audio_thread = threading.Thread(target=play_greeting)
        audio_thread.start()

        # 2. Let the greeting play briefly before bowing
        time.sleep(AUDIO_HEAD_START)

        # 3. Bow down while the greeting continues
        move_smoothly(
            UPRIGHT,
            BOWING,
            step_delay=MOVEMENT_SPEED
        )

        # 4. Wait until the greeting finishes
        audio_thread.join()

        # 5. Pause briefly while bowed
        time.sleep(0.5)

        # 6. Return upright at the same speed
        move_smoothly(
            BOWING,
            UPRIGHT,
            step_delay=MOVEMENT_SPEED
        )

        print("Ready for the next guest!")


except KeyboardInterrupt:
    print("\nBow-n Appétit stopped.")

except Exception as e:
    print(f"\nAn error occurred: {e}")

finally:
    # Return the servo to its upright position
    servo.move_servo_position(SERVO_CH, UPRIGHT)
    print("Servo returned to upright position.")
