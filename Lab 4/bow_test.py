
import pi_servo_hat
import time

SERVO_CH = 0

# Adjust these after testing your servo's mounting
UPRIGHT = 45
BOWING = 90

servo = pi_servo_hat.PiServoHat()
servo.restart()

def move_smoothly(start_angle, end_angle, step_delay=0.02):
    """Move gradually between two angles."""
    step = 1 if end_angle > start_angle else -1

    for angle in range(start_angle, end_angle + step, step):
        servo.move_servo_position(SERVO_CH, angle)
        time.sleep(step_delay)

try:
    print("Bow-n Appétit is ready!")

    # Start upright
    servo.move_servo_position(SERVO_CH, UPRIGHT)
    time.sleep(1)

    while True:
        input("\nPress Enter to bow...")

        # Slowly bow forward
        move_smoothly(UPRIGHT, BOWING, 0.025)

        # Hold the bow respectfully
        time.sleep(2)

        # Slowly return upright
        move_smoothly(BOWING, UPRIGHT, 0.025)

        print("Thank you! Arigatou gozaimasu!")

except KeyboardInterrupt:
    print("\nBowing stopped.")
