import time
import digitalio
import board
from PIL import Image, ImageDraw
import adafruit_rgb_display.st7789 as st7789
from datetime import datetime
import math

# Configuration for CS and DC pins
cs_pin = digitalio.DigitalInOut(board.D5)
dc_pin = digitalio.DigitalInOut(board.D25)
reset_pin = None

BAUDRATE = 64000000

# Setup SPI bus
spi = board.SPI()

# Create the ST7789 display
disp = st7789.ST7789(
    spi,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
    width=135,
    height=240,
    x_offset=53,
    y_offset=40,
)

# Create image
height = disp.width
width = disp.height
image = Image.new("RGB", (width, height))
rotation = 90

draw = ImageDraw.Draw(image)

# Backlight
backlight = digitalio.DigitalInOut(board.D22)
backlight.switch_to_output()
backlight.value = True


def draw_flower(draw, bloom):
    """
    bloom = 0.0 -> completely closed
    bloom = 1.0 -> fully bloomed
    """

    # Center of flower
    cx = width // 2
    cy = height // 2 - 10

    # -------------------------
    # Stem
    # -------------------------
    stem_bottom = height - 20
    stem_top = cy + 5

    draw.line(
        (cx, stem_bottom, cx, stem_top),
        fill=(60, 150, 70),
        width=7
    )

    # -------------------------
    # Leaves
    # -------------------------
    leaf_y = height - 65

    draw.ellipse(
        (cx - 55, leaf_y - 10,
         cx - 5, leaf_y + 15),
        fill=(60, 150, 70)
    )

    draw.ellipse(
        (cx + 5, leaf_y - 5,
         cx + 55, leaf_y + 20),
        fill=(60, 150, 70)
    )

    # -------------------------
    # Flower petals
    # -------------------------

    # Maximum distance the petals move away
    # from the center as the flower blooms.
    max_radius = 48

    # Start very close to center
    petal_distance = 8 + (max_radius - 8) * bloom

    # Petal size changes slightly as it opens
    petal_width = 25 + int(12 * bloom)
    petal_height = 35 + int(15 * bloom)

    # Draw 8 petals around the flower
    number_of_petals = 8

    for i in range(number_of_petals):

        angle = (2 * math.pi / number_of_petals) * i

        px = cx + math.cos(angle) * petal_distance
        py = cy + math.sin(angle) * petal_distance

        # Bounding box for the petal
        box = (
            int(px - petal_width / 2),
            int(py - petal_height / 2),
            int(px + petal_width / 2),
            int(py + petal_height / 2)
        )

        draw.ellipse(
            box,
            fill=(245, 120, 170)
        )

    # -------------------------
    # Flower center
    # -------------------------

    center_size = 15

    draw.ellipse(
        (
            cx - center_size,
            cy - center_size,
            cx + center_size,
            cy + center_size
        ),
        fill=(255, 210, 60)
    )


while True:

    # Clear screen
    draw.rectangle(
        (0, 0, width, height),
        fill=(0, 0, 0)
    )

    # Get current time
    now = datetime.now()

    # Current minute: 0 -> 59
    minute = now.minute

    # Current seconds
    second = now.second

    # -------------------------
    # Calculate bloom amount
    # -------------------------

    # Include seconds so the flower smoothly
    # blooms throughout the minute.
    total_seconds = minute * 60 + second

    # 0 seconds -> 0.0
    # 3599 seconds -> almost 1.0
    bloom = total_seconds / (60 * 60)

    # Make sure bloom stays between 0 and 1
    bloom = max(0.0, min(1.0, bloom))

    # Draw flower
    draw_flower(draw, bloom)

    # Display
    disp.image(image, rotation)

    # Update every second
    time.sleep(1)