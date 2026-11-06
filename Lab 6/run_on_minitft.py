"""Run neighboring shake_the_plate.py on the SPI Mini PiTFT over SSH.

Keeps the game's 320x240 layout and scales it to fit the 240x135 screen.
GPIO23 button: SPACE. GPIO24 button: ESC. Game arguments pass through.
"""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import runpy
import sys
import time
from pathlib import Path

import board
import digitalio
import pygame
from PIL import Image
from adafruit_rgb_display import st7789


def main():
    target = Path(__file__).resolve().with_name('shake_the_plate.py')
    if not target.is_file():
        raise SystemExit('Place this launcher beside shake_the_plate.py')
    pins = []
    spi = None
    try:
        cs = digitalio.DigitalInOut(board.D5)
        pins.append(cs)
        dc = digitalio.DigitalInOut(board.D25)
        pins.append(dc)
        light = digitalio.DigitalInOut(board.D22)
        pins.append(light)
        light.switch_to_output(value=True)
        buttons = []
        for pin in (board.D23, board.D24):
            button = digitalio.DigitalInOut(pin)
            pins.append(button)
            button.switch_to_input(pull=digitalio.Pull.UP)
            buttons.append(button)
        spi = board.SPI()
        screen = st7789.ST7789(spi, cs=cs, dc=dc, rst=None,
                              baudrate=64000000, width=135, height=240,
                              x_offset=53, y_offset=40, rotation=90)
        original_flip = pygame.display.flip
        original_update = pygame.display.update
        previous = [not b.value for b in buttons]
        last_press = [0.0, 0.0]
        last_frame = 0.0

        def refresh():
            nonlocal last_frame
            now = time.monotonic()
            for i, (button, key) in enumerate(zip(buttons, (pygame.K_SPACE, pygame.K_ESCAPE))):
                pressed = not button.value
                if pressed != previous[i]:
                    if not pressed or now - last_press[i] >= 0.3:
                        pygame.event.post(pygame.event.Event(
                            pygame.KEYDOWN if pressed else pygame.KEYUP, key=key))
                        if pressed:
                            last_press[i] = now
                    previous[i] = pressed
            if now - last_frame < 1 / 15:
                return
            surface = pygame.display.get_surface()
            if surface is None:
                return
            frame = Image.frombytes('RGB', surface.get_size(), pygame.image.tostring(surface, 'RGB'))
            frame.thumbnail((240, 135), Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', (240, 135), 'black')
            canvas.paste(frame, ((240 - frame.width) // 2, (135 - frame.height) // 2))
            screen.image(canvas)
            last_frame = now

        def flip():
            original_flip()
            refresh()

        def update(*args, **kwargs):
            original_update(*args, **kwargs)
            refresh()

        pygame.display.flip = flip
        pygame.display.update = update
        print('Mini PiTFT: GPIO23 button = start (pi1); GPIO24 button = quit.', flush=True)
        sys.argv = [str(target), *sys.argv[1:]]
        try:
            runpy.run_path(str(target), run_name='__main__')
        finally:
            pygame.display.flip = original_flip
            pygame.display.update = original_update
    finally:
        pygame.quit()
        for pin in reversed(pins):
            pin.deinit()
        if spi is not None:
            spi.deinit()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
