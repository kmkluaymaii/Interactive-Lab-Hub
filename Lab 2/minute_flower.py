#!/usr/bin/env python3
"""
Flower Clock - Minute Version

The flower blooms gradually over 60 minutes.

00:00  -> closed bud
15:00  -> partially bloomed
30:00  -> half bloomed
45:00  -> mostly bloomed
59:59  -> fully bloomed
00:00  -> resets to closed bud
"""

import math
import time

import board
import digitalio
from PIL import Image, ImageDraw
import adafruit_rgb_display.st7789 as st7789


# ------------------------------------------------------- display setup

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


# ---------------------------------------------------------------- colors

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


BG_COLOR = hsb(220, 20, 15)
STEM_COLOR = hsb(120, 60, 40)
LEAF_COLOR = hsb(120, 70, 60)
CENTER_COLOR = hsb(45, 90, 80)

PETAL_FILL = hsb(220, 50, 85)
PETAL_STROKE = hsb(220, 80, 40)
PETAL_HIGHLIGHT = hsb(220, 30, 95)

BUD_COLOR = hsb(120, 40, 50)
BUD_TIP_COLOR = hsb(120, 60, 30)

TEXT_COLOR = (230, 230, 230)


# ------------------------------------------------------------ geometry

def transform(lx, ly, angle, ox, oy):
    """Rotate and translate a point."""
    gx = lx * math.cos(angle) - ly * math.sin(angle)
    gy = lx * math.sin(angle) + ly * math.cos(angle)

    return (ox + gx, oy + gy)


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
        t = 2 * math.pi * i / n

        lx = rx * math.cos(t)
        ly = ry * math.sin(t) + shift_y

        pts.append(
            transform(lx, ly, angle, ox, oy)
        )

    return pts


# ---------------------------------------------------------------- scale

SCALE = 0.42

FLOWER_SIZE = 60 * SCALE

STEM_TOP = 20 * SCALE
STEM_BOTTOM = 150 * SCALE

PETAL_COUNT = 8


# ---------------------------------------------------------- MINUTE TIMER

def bloom_progress(now=None):
    """
    Return how many minutes have elapsed in the current hour.

    0:00 -> 0.0
    0:15 -> 15.0
    0:30 -> 30.0
    0:45 -> 45.0
    0:59 -> 59.0

    The flower automatically resets at the beginning
    of every hour.
    """

    if now is None:
        now = time.time()

    local = time.localtime(now)

    # Include seconds so blooming is smooth.
    minutes_elapsed = (
        local.tm_min +
        local.tm_sec / 60.0
    )

    return minutes_elapsed


# -------------------------------------------------------------- leaves

def draw_leaves(draw, cx, cy, minute_value):
    """
    Add leaves as the flower grows.

    A new leaf appears every 15 minutes.
    """

    num_leaves = int(minute_value // 15) + 1

    # Maximum 4 leaves
    num_leaves = min(num_leaves, 4)

    for i in range(num_leaves):

        leaf_y = (
            80 * SCALE
            + i * (15 * SCALE)
        )

        side = -1 if i % 2 == 0 else 1

        leaf_x = (
            side *
            ((10 + i * 3) * SCALE)
        )

        leaf_rot = (
            side *
            (0.2 + i * 0.1)
        )

        leaf_w = (
            (20 + i * 2) * SCALE
        )

        leaf_h = (
            (12 + i * 1) * SCALE
        )

        pts = ellipse_points(
            leaf_w / 2,
            leaf_h / 2,
            leaf_rot,
            cx + leaf_x,
            cy + leaf_y,
            n=10
        )

        draw.polygon(
            pts,
            fill=LEAF_COLOR
        )


# -------------------------------------------------------------- petals

def draw_petal(
    draw,
    cx,
    cy,
    angle,
    petal_dist,
    cur_w,
    cur_h
):
    """Draw one flower petal."""

    # Dark outline
    stroke_pts = ellipse_points(
        cur_w / 2 * 1.18,
        cur_h / 2 * 1.10,
        angle,
        cx,
        cy,
        shift_y=-petal_dist,
        n=16
    )

    draw.polygon(
        stroke_pts,
        fill=PETAL_STROKE
    )

    # Main petal
    fill_pts = ellipse_points(
        cur_w / 2,
        cur_h / 2,
        angle,
        cx,
        cy,
        shift_y=-petal_dist,
        n=16
    )

    draw.polygon(
        fill_pts,
        fill=PETAL_FILL
    )

    # Highlight
    hi_pts = ellipse_points(
        cur_w * 0.6 / 2,
        cur_h * 0.7 / 2,
        angle,
        cx,
        cy,
        shift_y=-petal_dist + cur_h * 0.1,
        n=12
    )

    draw.polygon(
        hi_pts,
        fill=PETAL_HIGHLIGHT
    )


# --------------------------------------------------------- flower

def draw_minutes_flower(
    draw,
    cx,
    cy,
    minute_value
):
    """
    Draw flower based on progress through the hour.

    bloom:
        0.0 = closed
        1.0 = fully open
    """

    # -----------------------------------------
    # Calculate bloom progress
    # -----------------------------------------

    bloom = minute_value / 59.999

    bloom = max(
        0.0,
        min(1.0, bloom)
    )

    # -----------------------------------------
    # Stem
    # -----------------------------------------

    draw.line(
        (
            cx,
            cy + STEM_TOP,
            cx,
            cy + STEM_BOTTOM
        ),
        fill=STEM_COLOR,
        width=max(
            2,
            round(8 * SCALE)
        )
    )

    # -----------------------------------------
    # Leaves
    # -----------------------------------------

    draw_leaves(
        draw,
        cx,
        cy,
        minute_value
    )

    # -----------------------------------------
    # Flower center
    # -----------------------------------------

    center_r = (
        6 + bloom * 15
    ) * SCALE / 2

    draw.ellipse(
        (
            cx - center_r,
            cy - center_r,
            cx + center_r,
            cy + center_r
        ),
        fill=CENTER_COLOR
    )

    # -----------------------------------------
    # Petals
    # -----------------------------------------

    base_radius = FLOWER_SIZE * 0.3

    bloom_radius = (
        FLOWER_SIZE *
        (0.3 + bloom * 0.4)
    )

    petal_w = (
        20 + bloom * 15
    ) * SCALE

    petal_h = (
        40 + bloom * 30
    ) * SCALE

    petal_dist = (
        base_radius +
        (bloom_radius - base_radius) * bloom
    )

    cur_w = (
        petal_w *
        (0.3 + 0.7 * bloom)
    )

    cur_h = (
        petal_h *
        (0.4 + 0.6 * bloom)
    )

    # Draw all petals
    for i in range(PETAL_COUNT):

        angle = (
            2 * math.pi *
            i /
            PETAL_COUNT
        )

        draw_petal(
            draw,
            cx,
            cy,
            angle,
            petal_dist,
            cur_w,
            cur_h
        )

    # -----------------------------------------
    # Bud overlay
    # -----------------------------------------

    if bloom < 0.3:

        alpha = (
            1 -
            bloom * 3
        ) * 80

        rx = (
            25 * SCALE
        ) / 2

        ry = (
            45 * SCALE
        ) / 2

        by = (
            cy -
            10 * SCALE
        )

        draw.ellipse(
            (
                cx - rx,
                by - ry,
                cx + rx,
                by + ry
            ),
            fill=blend(
                BUD_COLOR,
                BG_COLOR,
                alpha
            )
        )

        # Bud tip
        alpha_tip = (
            1 -
            bloom * 3
        ) * 90

        rx2 = (
            15 * SCALE
        ) / 2

        ry2 = (
            20 * SCALE
        ) / 2

        by2 = (
            cy -
            25 * SCALE
        )

        draw.ellipse(
            (
                cx - rx2,
                by2 - ry2,
                cx + rx2,
                by2 + ry2
            ),
            fill=blend(
                BUD_TIP_COLOR,
                BG_COLOR,
                alpha_tip
            )
        )


# --------------------------------------------------------------- main

def main():

    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT)
    )

    draw = ImageDraw.Draw(image)

    cx = WIDTH // 2

    # Flower head
    cy = 40

    while True:

        # -----------------------------------------
        # Get current minute
        # -----------------------------------------

        minutes_elapsed = bloom_progress()

        # -----------------------------------------
        # Clear screen
        # -----------------------------------------

        draw.rectangle(
            (
                0,
                0,
                WIDTH,
                HEIGHT
            ),
            fill=BG_COLOR
        )

        # -----------------------------------------
        # Draw flower
        # -----------------------------------------

        draw_minutes_flower(
            draw,
            cx,
            cy,
            minutes_elapsed
        )

        # -----------------------------------------
        # Display minute
        # -----------------------------------------

        draw.text(
            (
                4,
                HEIGHT - 12
            ),
            f"{int(minutes_elapsed):02d}m",
            fill=TEXT_COLOR
        )

        # -----------------------------------------
        # Send to display
        # -----------------------------------------

        disp.image(image)

        # Update ~15 times per second
        time.sleep(1 / 15)


if __name__ == "__main__":
    main()
