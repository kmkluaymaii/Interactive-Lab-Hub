#!/usr/bin/env python3
"""
Minute Flower Clock

A fully bloomed 12-petal flower acts as a minute clock.
The animal moves clockwise around the petals:

00 minutes -> petal 1
05 minutes -> petal 2
10 minutes -> petal 3
...
55 minutes -> petal 12

The animal moves smoothly between petals, so each position
represents the current minute like a clock hand.

06:00 AM - 06:59 PM -> butterfly
07:00 PM - 05:59 AM -> firefly

The sky background changes with the time of day:
08:00 PM - 04:59 AM -> #222059
05:00 AM - 07:59 AM -> #FFF7E0
08:00 AM - 05:59 PM -> #D9FDFF
06:00 PM - 07:59 PM -> #F79940

Runs on the Adafruit Mini PiTFT 135x240 ST7789 display.
"""

import math
import time

import board
import digitalio
from PIL import Image, ImageDraw
import adafruit_rgb_display.st7789 as st7789


# -------------------------------------------------------
# DISPLAY SETUP
# -------------------------------------------------------

cs_pin = digitalio.DigitalInOut(board.CE0)
dc_pin = digitalio.DigitalInOut(board.D25)
reset_pin = digitalio.DigitalInOut(board.D24)

BAUDRATE = 24000000

spi = board.SPI()

disp = st7789.ST7789(
    spi,
    rotation=90,
    width=135,
    height=240,
    x_offset=53,
    y_offset=40,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
)

if disp.rotation % 180 == 90:
    WIDTH = disp.height
    HEIGHT = disp.width
else:
    WIDTH = disp.width
    HEIGHT = disp.height


# -------------------------------------------------------
# COLORS
# -------------------------------------------------------

def hsb(h, s, b):
    """Convert HSB/HSV to RGB."""

    h = (h % 360) / 60.0
    s /= 100.0
    b /= 100.0

    c = b * s
    x = c * (1 - abs(h % 2 - 1))
    m = b - c

    if 0 <= h < 1:
        r, g, bl = c, x, 0
    elif 1 <= h < 2:
        r, g, bl = x, c, 0
    elif 2 <= h < 3:
        r, g, bl = 0, c, x
    elif 3 <= h < 4:
        r, g, bl = 0, x, c
    elif 4 <= h < 5:
        r, g, bl = x, 0, c
    else:
        r, g, bl = c, 0, x

    return (
        round((r + m) * 255),
        round((g + m) * 255),
        round((bl + m) * 255),
    )


def blend(fg, bg, alpha_pct):
    """Blend two colors."""

    a = max(0.0, min(1.0, alpha_pct / 100.0))

    return tuple(
        round(fg[i] * a + bg[i] * (1 - a))
        for i in range(3)
    )


# -------------------------------------------------------
# FLOWER + SKY COLORS
# -------------------------------------------------------

# Sky colors by time of day
SKY_NIGHT = (0x22, 0x20, 0x59)       # 8:00 PM - 4:59:59 AM
SKY_DAWN = (0xFF, 0xF7, 0xE0)        # 5:00 AM - 7:59:59 AM
SKY_DAY = (0xD9, 0xFD, 0xFF)         # 8:00 AM - 5:59:59 PM
SKY_SUNSET = (0xF7, 0x99, 0x40)      # 6:00 PM - 7:59:59 PM

# Flower
STEM_COLOR = hsb(120, 60, 40)
LEAF_COLOR = hsb(120, 70, 60)

PETAL_FILL = hsb(325, 55, 95)
PETAL_STROKE = hsb(320, 75, 55)
PETAL_HIGHLIGHT = hsb(330, 25, 100)

CENTER_COLOR = hsb(45, 90, 90)

# Butterfly / firefly
BUTTERFLY_COLOR = hsb(300, 55, 90)
BUTTERFLY_DARK = hsb(280, 70, 45)

FIREFLY_BODY = hsb(55, 70, 35)
FIREFLY_GLOW = (255, 245, 110)

TEXT_COLOR = (230, 230, 230)



# -------------------------------------------------------
# GEOMETRY
# -------------------------------------------------------

def transform(lx, ly, angle, ox, oy):
    """Rotate and translate a point."""

    gx = (
        lx * math.cos(angle)
        - ly * math.sin(angle)
    )

    gy = (
        lx * math.sin(angle)
        + ly * math.cos(angle)
    )

    return (
        ox + gx,
        oy + gy
    )


def ellipse_points(
    rx,
    ry,
    angle,
    ox,
    oy,
    shift_y=0.0,
    n=14
):
    """Create points approximating a rotated ellipse."""

    pts = []

    for i in range(n):

        t = (
            2 * math.pi * i / n
        )

        lx = (
            rx * math.cos(t)
        )

        ly = (
            ry * math.sin(t)
            + shift_y
        )

        pts.append(
            transform(
                lx,
                ly,
                angle,
                ox,
                oy
            )
        )

    return pts


# -------------------------------------------------------
# FLOWER CLOCK GEOMETRY
# -------------------------------------------------------

SCALE = 0.42

FLOWER_RADIUS = 42
PETAL_RADIUS = 30
PETAL_WIDTH = 18
PETAL_HEIGHT = 35

STEM_TOP = 35
STEM_BOTTOM = 145


# -------------------------------------------------------
# TIME / SKY
# -------------------------------------------------------

def get_local_time():
    return time.localtime()


def get_sky_color(local):
    """Return the requested sky color for the current time."""
    hour = local.tm_hour

    if 20 <= hour or hour < 5:
        return SKY_NIGHT
    elif 5 <= hour < 8:
        return SKY_DAWN
    elif 8 <= hour < 18:
        return SKY_DAY
    else:
        return SKY_SUNSET


def minute_position(local):
    """
    Return the animal's position around the 12-petal flower.

    The flower is a MINUTE clock:
        minute 0  -> petal 1
        minute 5  -> petal 2
        minute 10 -> petal 3
        ...
        minute 55 -> petal 12

    Movement is continuous. Therefore:
        minute 0 -> exactly on petal 1
        minute 2.5 -> halfway between petal 1 and 2
        minute 3 -> 60% of the way from petal 1 to 2
        minute 5 -> exactly on petal 2

    Seconds are included so the movement is smooth.
    """
    minute_value = local.tm_min + local.tm_sec / 60.0

    # There are 12 petals over 60 minutes.
    # One petal interval = 5 minutes = 30 degrees.
    return minute_value / 5.0


def animal_position(cx, cy, local):
    """Return x, y for the butterfly/firefly."""
    pos = minute_position(local)

    # Petal 1 starts at the top and the animal moves clockwise.
    angle = -math.pi / 2 + (pos * 2 * math.pi / 12)

    x = cx + FLOWER_RADIUS * math.cos(angle)
    y = cy + FLOWER_RADIUS * math.sin(angle)

    return x, y, angle


# -------------------------------------------------------
# FLOWER
# -------------------------------------------------------

def draw_petal(draw, cx, cy, angle):
    """Draw one of the 12 full-bloom petals."""
    # Petal center sits on a circle around the flower center.
    px = cx + PETAL_RADIUS * math.cos(angle)
    py = cy + PETAL_RADIUS * math.sin(angle)

    pts = ellipse_points(
        PETAL_WIDTH,
        PETAL_HEIGHT,
        angle + math.pi / 2,
        px,
        py,
        n=18
    )

    draw.polygon(pts, fill=PETAL_STROKE)

    inner_pts = ellipse_points(
        PETAL_WIDTH * 0.82,
        PETAL_HEIGHT * 0.82,
        angle + math.pi / 2,
        px,
        py,
        n=18
    )

    draw.polygon(inner_pts, fill=PETAL_FILL)

    highlight = ellipse_points(
        PETAL_WIDTH * 0.35,
        PETAL_HEIGHT * 0.38,
        angle + math.pi / 2,
        px,
        py - 3,
        n=12
    )

    draw.polygon(highlight, fill=PETAL_HIGHLIGHT)


def draw_flower(draw, cx, cy):
    """Draw the flower fully bloomed at all times."""

    # Stem
    draw.line(
        (cx, cy + STEM_TOP, cx, cy + STEM_BOTTOM),
        fill=STEM_COLOR,
        width=3
    )

    # Leaves
    draw.ellipse(
        (cx - 30, cy + 70, cx - 3, cy + 84),
        fill=LEAF_COLOR
    )
    draw.ellipse(
        (cx + 3, cy + 90, cx + 30, cy + 104),
        fill=LEAF_COLOR
    )

    # 12 petals
    for i in range(12):
        angle = -math.pi / 2 + i * (2 * math.pi / 12)
        draw_petal(draw, cx, cy, angle)

    # Flower center
    draw.ellipse(
        (cx - 13, cy - 13, cx + 13, cy + 13),
        fill=CENTER_COLOR
    )


# -------------------------------------------------------
# ANIMALS
# -------------------------------------------------------

def draw_butterfly(draw, x, y, angle, local):
    """Draw a small butterfly following the minute position."""

    # Direction the butterfly faces/tends to move.
    dx = math.cos(angle)
    dy = math.sin(angle)

    # Body
    body_x = x
    body_y = y
    draw.ellipse(
        (body_x - 2, body_y - 7, body_x + 2, body_y + 7),
        fill=BUTTERFLY_DARK
    )

    # Wing flap animation.
    flap = math.sin(
        (local.tm_sec + time.time() % 1) * 8
    ) * 3

    # Perpendicular direction
    px = -dy
    py = dx

    left_wing = (
        x + px * (8 + flap),
        y + py * (8 + flap)
    )
    right_wing = (
        x - px * (8 + flap),
        y - py * (8 + flap)
    )

    draw.ellipse(
        (
            left_wing[0] - 5,
            left_wing[1] - 4,
            left_wing[0] + 5,
            left_wing[1] + 4
        ),
        fill=BUTTERFLY_COLOR
    )

    draw.ellipse(
        (
            right_wing[0] - 5,
            right_wing[1] - 4,
            right_wing[0] + 5,
            right_wing[1] + 4
        ),
        fill=BUTTERFLY_COLOR
    )


def draw_firefly(draw, x, y, angle, local):
    """Draw a glowing firefly following the minute position."""

    # Glow pulses gently.
    pulse = (math.sin(
        (local.tm_sec + time.time() % 1) * 4
    ) + 1) / 2

    glow_r = int(5 + pulse * 3)

    draw.ellipse(
        (
            x - glow_r,
            y - glow_r,
            x + glow_r,
            y + glow_r
        ),
        fill=blend(FIREFLY_GLOW, get_sky_color(local), 25 + pulse * 25)
    )

    # Body
    draw.ellipse(
        (x - 3, y - 3, x + 3, y + 3),
        fill=FIREFLY_BODY
    )

    # Tiny wings
    draw.ellipse(
        (x - 7, y - 3, x - 2, y + 2),
        fill=FIREFLY_GLOW
    )
    draw.ellipse(
        (x + 2, y - 3, x + 7, y + 2),
        fill=FIREFLY_GLOW
    )


def draw_animal(draw, cx, cy, local):
    """Choose butterfly or firefly based on the hour."""

    x, y, angle = animal_position(cx, cy, local)

    # Butterfly: 6 AM through 6:59:59 PM.
    # Firefly: 7 PM through 5:59:59 AM.
    if 6 <= local.tm_hour < 19:
        draw_butterfly(draw, x, y, angle, local)
    else:
        draw_firefly(draw, x, y, angle, local)


# -------------------------------------------------------
# MAIN
# -------------------------------------------------------

def main():

    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT)
    )

    draw = ImageDraw.Draw(image)

    # Center of flower
    cx = WIDTH // 2
    cy = 65

    while True:

        local = get_local_time()

        # Sky changes ONLY based on hour.
        bg_color = get_sky_color(local)

        draw.rectangle(
            (0, 0, WIDTH, HEIGHT),
            fill=bg_color
        )

        # Flower is always fully bloomed.
        draw_flower(draw, cx, cy)

        # Animal is the minute indicator.
        draw_animal(draw, cx, cy, local)

        # Optional small label showing the current minute.
        # This is intentionally minute-only, not a normal clock.
        draw.text(
            (4, HEIGHT - 12),
            f"{local.tm_min:02d}m",
            fill=TEXT_COLOR
        )

        disp.image(image)

        # Smooth movement between minute positions.
        time.sleep(1 / 15)


if __name__ == "__main__":
    main()
