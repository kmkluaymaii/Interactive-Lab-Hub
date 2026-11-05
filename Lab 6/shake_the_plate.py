#!/usr/bin/env python3
"""
Shake the Plate! — competitive 3-Pi cooking game.

The SAME file runs on every Pi.  Pick which Pi you are at launch:

    python shake_the_plate.py --pi-id pi1       # Burger  (also acts as coordinator)
    python shake_the_plate.py --pi-id pi2       # Salad
    python shake_the_plate.py --pi-id pi3       # Sushi

The game waits on a start screen until the coordinator (pi1 by default)
presses SPACE, then every Pi starts its 10-second spawning schedule in
sync and the race is on.

Controls:
  * Swipe LEFT  over the APDS-9960  -> shake all food left
  * Swipe RIGHT over the APDS-9960  -> shake all food right
  * Swipe UP    over the APDS-9960  -> submit everything in the center zone

Keyboard fallback for development (works without the sensor):
  * Left arrow / Right arrow / Up arrow
  * SPACE on the coordinator starts the round
  * ESC quits
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field

import pygame
import paho.mqtt.client as mqtt


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #

BROKER_HOST = "farlab.infosci.cornell.edu"
BROKER_PORT = 1883
BROKER_USER = "idd"
BROKER_PASS = "device@theFarm"

# Change this to a unique team namespace before deploying.
TOPIC_PREFIX = "IDD/shakeplate"

# Who runs the coordinator role (spawn schedule + winner arbitration).
COORDINATOR_ID = "pi1"

RECIPES = {
    "pi1": ["bread", "beef", "cheese"],
    "pi2": ["lettuce", "tomato", "cucumber"],
    "pi3": ["rice", "fish", "avocado"],
}
DISH_NAME = {"pi1": "Burger", "pi2": "Salad", "pi3": "Sushi"}

# Ring topology — what the README spec requires.
#   Pi 1: left -> Pi 3,  right -> Pi 2
#   Pi 2: left -> Pi 1,  right -> Pi 3
#   Pi 3: left -> Pi 2,  right -> Pi 1
LEFT_NEIGHBOR = {"pi1": "pi3", "pi2": "pi1", "pi3": "pi2"}
RIGHT_NEIGHBOR = {"pi1": "pi2", "pi2": "pi3", "pi3": "pi1"}

# Display — PiTFT 2.8" is 320x240.  Override with --width / --height if needed.
DEFAULT_W, DEFAULT_H = 320, 240

# Spawn schedule (seconds after game start).
SPAWN_TIMES = [0.0, 5.0, 10.0]

# Gameplay tuning.
FOOD_RADIUS = 22           # hit-box radius used for shaking / submit / edge test
SHAKE_DISTANCE = 110       # base pixels a food moves per swipe
SHAKE_JITTER = 25          # +/- random variation so overlapping foods separate
SHAKE_FRAMES = 18          # animation length in frames (~0.3s at 60fps)
TRANSFER_TIMEOUT = 2.0     # seconds to wait for an ack before retrying
REJECTION_FLASH_MS = 700   # red flash when a submission is rejected

# Each Pi gets its own pastel palette so a glance at the screen tells you
# which Pi you're on.  Matches the concept art.
PALETTE = {
    "pi1": {  # Burger — warm pink
        "bg":           (255, 228, 232),
        "header":       (255, 203, 215),
        "accent":       (210,  80, 110),
        "plate_tile":   (255, 215, 222),
    },
    "pi2": {  # Salad — leafy green
        "bg":           (224, 245, 224),
        "header":       (196, 230, 196),
        "accent":       ( 60, 130,  70),
        "plate_tile":   (210, 236, 210),
    },
    "pi3": {  # Sushi — ocean blue
        "bg":           (220, 234, 252),
        "header":       (192, 216, 246),
        "accent":       ( 60, 100, 170),
        "plate_tile":   (208, 224, 246),
    },
}

ZONE_FILL       = (255, 243, 190)
ZONE_BORDER     = (218, 184,  70)
ZONE_TEXT       = (166, 120,  20)
SLOT_EMPTY_FILL = (255, 255, 255)
SLOT_EMPTY_LINE = (170, 170, 170)
CHECK_FILL      = ( 70, 175,  90)


# --------------------------------------------------------------------------- #
# Food icons — drawn with pygame primitives so no image assets are needed.    #
# Every drawer takes (surface, cx, cy, s=1.0) where s scales the icon.        #
# At s=1.0 a food fits comfortably inside a ~44px box.                        #
# --------------------------------------------------------------------------- #

def _s(v, s): return int(round(v * s))


def _draw_bread(surf, cx, cy, s=1.0):
    w, h = _s(34, s), _s(28, s)
    # Lower crumb — rounded rect.
    body = pygame.Rect(cx - w // 2, cy - h // 2 + _s(2, s), w, h - _s(4, s))
    pygame.draw.rect(surf, (248, 220, 160), body, border_radius=_s(10, s))
    # Top crust — a lighter rounded hump on top.
    crust_h = _s(16, s)
    crust = pygame.Rect(cx - w // 2 + _s(1, s), cy - h // 2,
                        w - _s(2, s), crust_h)
    pygame.draw.ellipse(surf, (222, 184, 135), crust)
    # Outline.
    pygame.draw.rect(surf, (139,  90,  43), body, _s(2, s), border_radius=_s(10, s))
    pygame.draw.ellipse(surf, (139,  90,  43), crust, _s(2, s))
    # A little score mark across the top crust.
    pygame.draw.line(surf, (160, 100,  50),
                     (cx - _s(9, s), cy - _s(6, s)),
                     (cx + _s(9, s), cy - _s(8, s)), _s(2, s))


def _draw_beef(surf, cx, cy, s=1.0):
    w, h = _s(34, s), _s(24, s)
    rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
    pygame.draw.rect(surf, (200,  70,  70), rect, border_radius=_s(8, s))
    pygame.draw.rect(surf, (120,  25,  25), rect, _s(2, s), border_radius=_s(8, s))
    # Fatty marbling streaks.
    pygame.draw.line(surf, (255, 220, 215),
                     (cx - _s(11, s), cy - _s(2, s)),
                     (cx + _s(8, s),  cy + _s(2, s)), _s(2, s))
    pygame.draw.line(surf, (255, 220, 215),
                     (cx - _s(7, s),  cy + _s(5, s)),
                     (cx + _s(11, s), cy - _s(3, s)), _s(2, s))


def _draw_cheese(surf, cx, cy, s=1.0):
    # Wedge triangle.
    pts = [(cx - _s(16, s), cy + _s(10, s)),
           (cx + _s(16, s), cy + _s(10, s)),
           (cx + _s(8,  s), cy - _s(12, s))]
    pygame.draw.polygon(surf, (255, 215,  70), pts)
    pygame.draw.polygon(surf, (184, 134,  11), pts, _s(2, s))
    # Holes.
    pygame.draw.circle(surf, (255, 240, 150),
                       (cx - _s(3, s), cy + _s(3, s)), _s(3, s))
    pygame.draw.circle(surf, (255, 240, 150),
                       (cx + _s(6, s), cy - _s(3, s)), _s(2, s))


def _draw_lettuce(surf, cx, cy, s=1.0):
    r = _s(15, s)
    # Three overlapping ruffles on top of a base disc.
    pygame.draw.circle(surf, (120, 200, 110), (cx, cy), r)
    pygame.draw.circle(surf, (150, 215, 130),
                       (cx - _s(6, s), cy - _s(5, s)), _s(8, s))
    pygame.draw.circle(surf, (150, 215, 130),
                       (cx + _s(6, s), cy - _s(5, s)), _s(8, s))
    pygame.draw.circle(surf, (150, 215, 130),
                       (cx, cy + _s(6, s)), _s(8, s))
    pygame.draw.circle(surf, ( 60, 140,  70), (cx, cy), r, _s(2, s))
    # Central vein.
    pygame.draw.line(surf, ( 60, 140,  70),
                     (cx, cy - _s(10, s)),
                     (cx, cy + _s(10, s)), _s(2, s))


def _draw_tomato(surf, cx, cy, s=1.0):
    r = _s(14, s)
    pygame.draw.circle(surf, (230,  55,  60), (cx, cy + _s(2, s)), r)
    pygame.draw.circle(surf, (139,   0,   0), (cx, cy + _s(2, s)), r, _s(2, s))
    # Highlight.
    pygame.draw.circle(surf, (255, 140, 140),
                       (cx - _s(5, s), cy - _s(3, s)), _s(3, s))
    # Green star-top.
    stem = [(cx - _s(7, s), cy - _s(9, s)),
            (cx,            cy - _s(14, s)),
            (cx + _s(7, s), cy - _s(9, s)),
            (cx + _s(4, s), cy - _s(6, s)),
            (cx - _s(4, s), cy - _s(6, s))]
    pygame.draw.polygon(surf, ( 76, 175,  80), stem)
    pygame.draw.polygon(surf, ( 27,  94,  32), stem, _s(1, s))


def _draw_cucumber(surf, cx, cy, s=1.0):
    rect = pygame.Rect(cx - _s(16, s), cy - _s(10, s),
                       _s(32, s), _s(20, s))
    pygame.draw.ellipse(surf, ( 76, 160,  90), rect)
    pygame.draw.ellipse(surf, ( 27,  94,  32), rect, _s(2, s))
    # Lighter flesh in the middle.
    inner = pygame.Rect(cx - _s(10, s), cy - _s(6, s),
                        _s(20, s), _s(12, s))
    pygame.draw.ellipse(surf, (190, 230, 150), inner)
    # Seeds.
    for ox, oy in ((-4, 0), (3, -1), (0, 2)):
        pygame.draw.circle(surf, (255, 255, 220),
                           (cx + _s(ox, s), cy + _s(oy, s)), _s(1, s))


def _draw_rice(surf, cx, cy, s=1.0):
    # A ball of rice, slightly pointed on top like an onigiri scoop.
    body = pygame.Rect(cx - _s(16, s), cy - _s(12, s),
                       _s(32, s), _s(22, s))
    pygame.draw.ellipse(surf, (252, 252, 248), body)
    pygame.draw.ellipse(surf, (190, 190, 180), body, _s(2, s))
    # A couple of darker grains for texture.
    for ox, oy in ((-6, -4), (4, -6), (0, -1), (6, 2), (-4, 3)):
        pygame.draw.circle(surf, (210, 210, 200),
                           (cx + _s(ox, s), cy + _s(oy, s)), _s(1, s))


def _draw_fish(surf, cx, cy, s=1.0):
    # Body.
    body = pygame.Rect(cx - _s(14, s), cy - _s(9, s),
                       _s(24, s), _s(18, s))
    pygame.draw.ellipse(surf, (100, 170, 230), body)
    pygame.draw.ellipse(surf, ( 25,  60, 130), body, _s(2, s))
    # Tail.
    tail = [(cx + _s(9,  s), cy),
            (cx + _s(18, s), cy - _s(8, s)),
            (cx + _s(18, s), cy + _s(8, s))]
    pygame.draw.polygon(surf, (100, 170, 230), tail)
    pygame.draw.polygon(surf, ( 25,  60, 130), tail, _s(2, s))
    # Eye.
    pygame.draw.circle(surf, (255, 255, 255),
                       (cx - _s(6, s), cy - _s(2, s)), _s(3, s))
    pygame.draw.circle(surf, (  0,   0,   0),
                       (cx - _s(6, s), cy - _s(2, s)), _s(1, s))


def _draw_avocado(surf, cx, cy, s=1.0):
    # Pear-ish outer skin.
    outer = pygame.Rect(cx - _s(11, s), cy - _s(15, s),
                        _s(22, s), _s(30, s))
    pygame.draw.ellipse(surf, ( 70, 100,  45), outer)
    pygame.draw.ellipse(surf, ( 30,  60,  20), outer, _s(2, s))
    # Light-green flesh.
    flesh = pygame.Rect(cx - _s(8, s), cy - _s(12, s),
                        _s(16, s), _s(24, s))
    pygame.draw.ellipse(surf, (170, 220, 110), flesh)
    # Pit.
    pygame.draw.circle(surf, (139,  69,  19), (cx, cy + _s(2, s)), _s(5, s))
    pygame.draw.circle(surf, (101,  47,  10), (cx, cy + _s(2, s)), _s(5, s), _s(1, s))


FOOD_DRAWERS = {
    "bread":    _draw_bread,
    "beef":     _draw_beef,
    "cheese":   _draw_cheese,
    "lettuce":  _draw_lettuce,
    "tomato":   _draw_tomato,
    "cucumber": _draw_cucumber,
    "rice":     _draw_rice,
    "fish":     _draw_fish,
    "avocado":  _draw_avocado,
}


def draw_food_icon(surf, food_type, cx, cy, s=1.0):
    drawer = FOOD_DRAWERS.get(food_type)
    if drawer:
        drawer(surf, cx, cy, s)


def draw_dish_icon(surf, pi_id, cx, cy, s=1.0):
    """A tiny version of the finished dish, used in the header."""
    if pi_id == "pi1":        # mini burger: bread top, beef, bread bun
        _draw_bread(surf, cx, cy - _s(5, s), s * 0.55)
        _draw_beef(surf, cx, cy + _s(1, s), s * 0.55)
        _draw_bread(surf, cx, cy + _s(7, s), s * 0.55)
    elif pi_id == "pi2":      # mini salad bowl
        bowl = pygame.Rect(cx - _s(16, s), cy - _s(4, s),
                           _s(32, s), _s(16, s))
        pygame.draw.ellipse(surf, (255, 255, 255), bowl)
        pygame.draw.ellipse(surf, (180, 180, 180), bowl, _s(2, s))
        _draw_lettuce(surf, cx - _s(5, s), cy - _s(4, s), s * 0.55)
        _draw_tomato (surf, cx + _s(7, s), cy - _s(3, s), s * 0.50)
    elif pi_id == "pi3":      # mini sushi nigiri: rice base + fish slice on top
        # Rice base — rounded pillow.
        base = pygame.Rect(cx - _s(14, s), cy - _s(2, s),
                           _s(28, s), _s(14, s))
        pygame.draw.rect(surf, (252, 252, 248), base,
                         border_radius=_s(6, s))
        pygame.draw.rect(surf, (190, 190, 180), base, _s(2, s),
                         border_radius=_s(6, s))
        # Salmon slice draped over the top.
        salmon = pygame.Rect(cx - _s(15, s), cy - _s(8, s),
                             _s(30, s), _s(9, s))
        pygame.draw.rect(surf, (255, 150, 110), salmon,
                         border_radius=_s(4, s))
        pygame.draw.rect(surf, (200, 100,  70), salmon, _s(2, s),
                         border_radius=_s(4, s))
        # Lighter marbling stripe.
        pygame.draw.line(surf, (255, 210, 180),
                         (cx - _s(12, s), cy - _s(4, s)),
                         (cx + _s(12, s), cy - _s(4, s)), _s(1, s))


# --------------------------------------------------------------------------- #
# Food objects                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class Food:
    id: str
    type: str
    x: float
    y: float
    target_x: float = 0.0
    anim_frames: int = 0
    in_transit: bool = False
    transit_started: float = 0.0
    transit_to: str = ""
    transit_enter_from: str = ""


# --------------------------------------------------------------------------- #
# Main game                                                                   #
# --------------------------------------------------------------------------- #

class ShakePlateGame:
    def __init__(self, pi_id: str, width: int, height: int, no_sensor: bool):
        assert pi_id in RECIPES, f"pi_id must be one of {list(RECIPES)}"
        self.pi_id = pi_id
        self.is_coordinator = (pi_id == COORDINATOR_ID)
        self.width = width
        self.height = height
        self.no_sensor = no_sensor
        self.palette = PALETTE[pi_id]

        # Layout.  Matches the concept art:
        #   header strip (dish name + Recipe preview)
        #   slot row    (3 submission slots, dashed when empty)
        #   plate area  (oval plate, submission zone, ingredients)
        self.header_h = 32
        self.slot_row_h = 44
        self.plate_top = self.header_h + self.slot_row_h
        self.plate_h = height - self.plate_top
        self.submit_w = max(68, width // 5)
        self.submit_x = (width - self.submit_w) // 2
        self.submit_top = self.plate_top + 6
        self.submit_bot = height - 6

        # Game state (protected by state_lock — MQTT thread writes to it too).
        self.state_lock = threading.Lock()
        self.foods: list[Food] = []
        self.submitted: set[str] = set()
        self.seen_spawn_ids: set[str] = set()
        self.seen_transfer_ids: set[str] = set()
        self.pending_transfers: dict[str, Food] = {}  # transfer_id -> Food
        self.phase = "waiting"   # waiting / playing / finished
        self.winner: str | None = None
        self.reject_flash_until = 0.0
        self.last_toast = ""
        self.last_toast_until = 0.0

        # Coordinator-only state.
        self.round_schedule: list[list[dict]] | None = None
        self.round_start_time: float | None = None
        self.next_wave_index: int = 0
        self.completion_claims: list[tuple[str, float]] = []

        # Pygame.
        pygame.init()
        pygame.display.set_caption(f"Shake the Plate — {self.pi_id}")
        self.screen = pygame.display.set_mode((width, height))
        self.clock = pygame.time.Clock()
        self.font_title = pygame.font.SysFont("dejavusans", 20, bold=True)
        self.font_med   = pygame.font.SysFont("dejavusans", 14, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 11, bold=True)
        self.font_tiny  = pygame.font.SysFont("dejavusans", 10)

        # Sensor.
        self.sensor = None
        if not no_sensor:
            try:
                self.sensor = _init_sensor()
                print(f"[{self.pi_id}] APDS-9960 gesture sensor ready.")
            except Exception as exc:
                print(f"[{self.pi_id}] WARNING: sensor init failed ({exc}). "
                      "Keyboard-only mode.")
                self.sensor = None

        # MQTT.
        self.client = mqtt.Client(client_id=f"shakeplate-{self.pi_id}-{uuid.uuid4().hex[:6]}")
        self.client.username_pw_set(BROKER_USER, BROKER_PASS)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        print(f"[{self.pi_id}] Connecting to broker {BROKER_HOST}:{BROKER_PORT} ...")
        self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        self.client.loop_start()

    # ------------------------------------------------------------------ MQTT

    def _topic(self, suffix: str) -> str:
        return f"{TOPIC_PREFIX}/{suffix}"

    def _on_connect(self, client, userdata, flags, rc):
        print(f"[{self.pi_id}] MQTT connected rc={rc}")
        # Every Pi listens to its own incoming food + acks, plus broadcast topics.
        client.subscribe(self._topic(f"{self.pi_id}/food"))
        client.subscribe(self._topic(f"{self.pi_id}/ack"))
        client.subscribe(self._topic("game/start"))
        client.subscribe(self._topic("game/spawn"))
        client.subscribe(self._topic("game/winner"))
        if self.is_coordinator:
            client.subscribe(self._topic("game/complete"))
            # Also listen to progress for logging / future features.
            for p in ("pi1", "pi2", "pi3"):
                client.subscribe(self._topic(f"{p}/progress"))

    def _publish(self, suffix: str, payload: dict):
        self.client.publish(self._topic(suffix), json.dumps(payload))

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception as exc:
            print(f"[{self.pi_id}] bad payload on {msg.topic}: {exc}")
            return

        topic = msg.topic[len(TOPIC_PREFIX) + 1:]  # strip prefix/

        if topic == "game/start":
            self._handle_game_start(payload)
        elif topic == "game/spawn":
            self._handle_spawn(payload)
        elif topic == "game/winner":
            self._handle_winner(payload)
        elif topic == f"{self.pi_id}/food":
            self._handle_incoming_food(payload)
        elif topic == f"{self.pi_id}/ack":
            self._handle_ack(payload)
        elif self.is_coordinator and topic == "game/complete":
            self._handle_completion_claim(payload)

    # ---------------------------------------------------------- MQTT handlers

    def _handle_game_start(self, payload: dict):
        with self.state_lock:
            self.phase = "playing"
            self.foods.clear()
            self.submitted.clear()
            self.seen_spawn_ids.clear()
            self.seen_transfer_ids.clear()
            self.pending_transfers.clear()
            self.winner = None
            if self.is_coordinator:
                self.round_start_time = time.time()
                self.next_wave_index = 0
                self.completion_claims = []
        print(f"[{self.pi_id}] Round started.")

    def _handle_spawn(self, payload: dict):
        # Format: {wave, food_id, food, to}
        if payload.get("to") != self.pi_id:
            return
        food_id = payload["food_id"]
        with self.state_lock:
            if food_id in self.seen_spawn_ids:
                return
            self.seen_spawn_ids.add(food_id)
            x, y = self._random_spawn_position()
            self.foods.append(Food(id=food_id, type=payload["food"], x=x, y=y))
        print(f"[{self.pi_id}] spawn {payload['food']} ({food_id}) wave={payload.get('wave')}")

    def _handle_incoming_food(self, payload: dict):
        """Another Pi shook a food off their screen into ours."""
        transfer_id = payload["transfer_id"]
        sender = payload["from"]
        with self.state_lock:
            if transfer_id in self.seen_transfer_ids:
                # Duplicate — just re-ack so the sender clears it.
                self._publish(f"{sender}/ack",
                              {"transfer_id": transfer_id, "by": self.pi_id})
                return
            self.seen_transfer_ids.add(transfer_id)
            enter_from = payload.get("enter_from", "left")
            if enter_from == "right":
                x = self.width - FOOD_RADIUS - 2
            else:
                x = FOOD_RADIUS + 2
            y = random.randint(self.plate_top + FOOD_RADIUS + 5,
                               self.height - FOOD_RADIUS - 5)
            self.foods.append(Food(id=payload["food_id"],
                                   type=payload["food"], x=x, y=y))
        # Acknowledge so the sender stops worrying about this one.
        self._publish(f"{sender}/ack",
                      {"transfer_id": transfer_id, "by": self.pi_id})

    def _handle_ack(self, payload: dict):
        """Receiver confirmed a transfer; we can drop the in-transit copy."""
        transfer_id = payload["transfer_id"]
        with self.state_lock:
            food = self.pending_transfers.pop(transfer_id, None)
            if food and food in self.foods:
                self.foods.remove(food)

    def _handle_winner(self, payload: dict):
        with self.state_lock:
            self.phase = "finished"
            self.winner = payload["winner"]
        print(f"[{self.pi_id}] WINNER: {payload['winner']} ({DISH_NAME[payload['winner']]})")

    def _handle_completion_claim(self, payload: dict):
        # Coordinator-only.  First valid claim wins.
        if self.winner is not None:
            return
        who = payload["pi"]
        ts = payload.get("ts", time.time())
        self.completion_claims.append((who, ts))
        # Pick the earliest claim.
        winner = min(self.completion_claims, key=lambda c: c[1])[0]
        self._publish("game/winner", {"winner": winner, "dish": DISH_NAME[winner]})
        print(f"[{self.pi_id}] (coordinator) announcing winner: {winner}")

    # ------------------------------------------------------- Round management

    def start_round_as_coordinator(self):
        """Called from the main loop when the coordinator presses SPACE."""
        if not self.is_coordinator:
            return
        print(f"[{self.pi_id}] (coordinator) generating spawn schedule...")
        self.round_schedule = _generate_spawn_schedule()
        self._publish("game/start", {"ts": time.time()})
        # The start message will loop back to us through MQTT and flip phase.

    def coordinator_tick(self):
        """Publish the next spawn wave if its time has come."""
        if not self.is_coordinator:
            return
        if self.phase != "playing" or self.round_start_time is None:
            return
        if self.round_schedule is None:
            return
        elapsed = time.time() - self.round_start_time
        while (self.next_wave_index < len(SPAWN_TIMES)
               and elapsed >= SPAWN_TIMES[self.next_wave_index]):
            wave = self.round_schedule[self.next_wave_index]
            for item in wave:
                self._publish("game/spawn", {
                    "wave": self.next_wave_index,
                    "food_id": item["food_id"],
                    "food": item["food"],
                    "to": item["to"],
                })
            print(f"[{self.pi_id}] (coordinator) published wave "
                  f"{self.next_wave_index} ({len(wave)} items)")
            self.next_wave_index += 1

    # -------------------------------------------------------------- Gameplay

    def _random_spawn_position(self):
        """Pick a position on the plate but outside the center submit zone."""
        y_lo = self.plate_top + FOOD_RADIUS + 8
        y_hi = self.height - FOOD_RADIUS - 8
        y = random.randint(y_lo, y_hi)
        side = random.choice(("left", "right"))
        if side == "left":
            x_lo = FOOD_RADIUS + 8
            x_hi = self.submit_x - FOOD_RADIUS - 6
        else:
            x_lo = self.submit_x + self.submit_w + FOOD_RADIUS + 6
            x_hi = self.width - FOOD_RADIUS - 8
        if x_hi <= x_lo:
            x = x_hi
        else:
            x = random.randint(x_lo, x_hi)
        return x, y

    def trigger_shake(self, direction: int):
        """direction = -1 (left) or +1 (right)."""
        with self.state_lock:
            if self.phase != "playing":
                return
            for f in self.foods:
                if f.in_transit:
                    continue
                delta = direction * (SHAKE_DISTANCE
                                     + random.uniform(-SHAKE_JITTER, SHAKE_JITTER))
                f.target_x = f.x + delta
                f.anim_frames = SHAKE_FRAMES

    def try_submit(self):
        with self.state_lock:
            if self.phase != "playing":
                return
            inside = [f for f in self.foods
                      if not f.in_transit
                      and self.submit_x <= f.x <= self.submit_x + self.submit_w
                      and f.anim_frames == 0]
            if not inside:
                self._toast("Nothing in the submission zone", warn=True)
                return
            types = [f.type for f in inside]
            needed = set(RECIPES[self.pi_id]) - self.submitted
            all_unique = len(set(types)) == len(types)
            all_needed = set(types).issubset(needed)
            if all_unique and all_needed:
                for f in inside:
                    self.submitted.add(f.type)
                    self.foods.remove(f)
                self._publish(f"{self.pi_id}/progress",
                              {"pi": self.pi_id,
                               "submitted": sorted(self.submitted)})
                self._toast(f"Submitted: {', '.join(types)}")
                if self.submitted == set(RECIPES[self.pi_id]):
                    # Claim the win.
                    self._publish("game/complete",
                                  {"pi": self.pi_id, "ts": time.time()})
            else:
                self._toast("Rejected!", warn=True)
                self.reject_flash_until = time.time() + REJECTION_FLASH_MS / 1000

    def _toast(self, text: str, warn: bool = False):
        self.last_toast = text
        self.last_toast_until = time.time() + 1.5
        prefix = "!" if warn else ">"
        print(f"[{self.pi_id}] {prefix} {text}")

    def update_physics(self):
        """Animate foods and emit transfers for anything that crossed an edge."""
        now = time.time()
        with self.state_lock:
            for f in list(self.foods):
                if f.anim_frames > 0:
                    f.x += (f.target_x - f.x) / f.anim_frames
                    f.anim_frames -= 1

            # Emit transfers for food that has crossed an edge.
            for f in list(self.foods):
                if f.in_transit:
                    continue
                if f.x < -FOOD_RADIUS:
                    self._start_transfer(f, LEFT_NEIGHBOR[self.pi_id],
                                         enter_from="right")
                elif f.x > self.width + FOOD_RADIUS:
                    self._start_transfer(f, RIGHT_NEIGHBOR[self.pi_id],
                                         enter_from="left")

            # Retry any transfer whose ack never came back.
            for tid, f in list(self.pending_transfers.items()):
                if now - f.transit_started > TRANSFER_TIMEOUT:
                    print(f"[{self.pi_id}] retrying transfer {tid}")
                    f.transit_started = now
                    self._publish(f"{f.transit_to}/food", {
                        "transfer_id": tid,
                        "food_id": f.id,
                        "food": f.type,
                        "from": self.pi_id,
                        "to": f.transit_to,
                        "enter_from": f.transit_enter_from,
                    })

    def _start_transfer(self, food: Food, to_pi: str, enter_from: str):
        food.in_transit = True
        food.transit_started = time.time()
        food.transit_to = to_pi
        food.transit_enter_from = enter_from
        transfer_id = f"{self.pi_id}-{uuid.uuid4().hex[:8]}"
        self.pending_transfers[transfer_id] = food
        self._publish(f"{to_pi}/food", {
            "transfer_id": transfer_id,
            "food_id": food.id,
            "food": food.type,
            "from": self.pi_id,
            "to": to_pi,
            "enter_from": enter_from,
        })
        print(f"[{self.pi_id}] -> {to_pi}: {food.type} ({food.id})")

    # -------------------------------------------------------------- Rendering

    def render(self):
        bg = self.palette["bg"]
        if time.time() < self.reject_flash_until:
            bg = (255, 120, 120)
        self.screen.fill(bg)

        self._draw_header()
        self._draw_slot_row()
        self._draw_plate()
        self._draw_submit_zone()

        with self.state_lock:
            # Submitted ingredients are shown in the slots, not on the plate.
            for f in list(self.foods):
                draw_food_icon(self.screen, f.type, int(f.x), int(f.y), s=1.0)

        if self.phase == "waiting":
            self._draw_waiting_overlay()
        elif self.phase == "finished":
            self._draw_winner_overlay()

        if time.time() < self.last_toast_until and self.last_toast:
            self._draw_toast(self.last_toast)

        pygame.display.flip()

    def _draw_header(self):
        pygame.draw.rect(self.screen, self.palette["header"],
                         (0, 0, self.width, self.header_h))
        # Dish icon + name on the left.
        draw_dish_icon(self.screen, self.pi_id, 18, self.header_h // 2, s=0.9)
        name = self.font_title.render(DISH_NAME[self.pi_id], True,
                                      self.palette["accent"])
        self.screen.blit(name, (36, (self.header_h - name.get_height()) // 2))

        # "Recipe:" + mini preview icons on the right.
        recipe_label = self.font_small.render("Recipe:", True,
                                              self.palette["accent"])
        # Three preview circles.
        preview_r = 12
        gap = 4
        total_w = 3 * (preview_r * 2) + 2 * gap
        start_x = self.width - total_w - 6
        label_x = start_x - recipe_label.get_width() - 6
        self.screen.blit(recipe_label,
                         (label_x,
                          (self.header_h - recipe_label.get_height()) // 2))
        for i, food in enumerate(RECIPES[self.pi_id]):
            cx = start_x + preview_r + i * (preview_r * 2 + gap)
            cy = self.header_h // 2
            pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy),
                               preview_r)
            pygame.draw.circle(self.screen, self.palette["accent"], (cx, cy),
                               preview_r, 2)
            draw_food_icon(self.screen, food, cx, cy, s=0.55)

    def _draw_slot_row(self):
        row_y = self.header_h
        # Slot row background is the lighter main bg (no need to redraw).
        slot_w, slot_h = 48, 36
        gap = 10
        total_w = 3 * slot_w + 2 * gap
        start_x = (self.width - total_w) // 2
        y = row_y + (self.slot_row_h - slot_h) // 2

        for i, food in enumerate(RECIPES[self.pi_id]):
            x = start_x + i * (slot_w + gap)
            rect = pygame.Rect(x, y, slot_w, slot_h)
            if food in self.submitted:
                # Filled slot — solid border, food icon, green check badge.
                pygame.draw.rect(self.screen, (255, 255, 255), rect,
                                 border_radius=8)
                pygame.draw.rect(self.screen, CHECK_FILL, rect, width=2,
                                 border_radius=8)
                draw_food_icon(self.screen, food, rect.centerx, rect.centery,
                               s=0.7)
                # Green check badge in the bottom-right corner.
                bx, by = rect.right - 6, rect.bottom - 6
                pygame.draw.circle(self.screen, CHECK_FILL, (bx, by), 7)
                pygame.draw.circle(self.screen, (255, 255, 255), (bx, by), 7, 1)
                # Simple white check mark.
                pygame.draw.lines(self.screen, (255, 255, 255), False,
                                  [(bx - 3, by), (bx - 1, by + 2),
                                   (bx + 3, by - 2)], 2)
            else:
                # Empty slot — dashed outline.
                pygame.draw.rect(self.screen, SLOT_EMPTY_FILL, rect,
                                 border_radius=8)
                _draw_dashed_rect(self.screen, rect, SLOT_EMPTY_LINE,
                                  dash=4, gap=3, width=2, radius=8)

    def _draw_plate(self):
        # Big white oval plate with a soft rim.
        plate_rect = pygame.Rect(6, self.plate_top + 4,
                                 self.width - 12, self.plate_h - 8)
        # Soft outer shadow ring.
        shadow = plate_rect.inflate(4, 4)
        pygame.draw.ellipse(self.screen, self.palette["plate_tile"], shadow)
        pygame.draw.ellipse(self.screen, (255, 255, 255), plate_rect)
        pygame.draw.ellipse(self.screen, (190, 190, 190), plate_rect, 2)

    def _draw_submit_zone(self):
        zone = pygame.Rect(self.submit_x, self.submit_top,
                           self.submit_w, self.submit_bot - self.submit_top)
        pygame.draw.rect(self.screen, ZONE_FILL, zone, border_radius=10)
        pygame.draw.rect(self.screen, ZONE_BORDER, zone, width=2,
                         border_radius=10)
        # Label sits at the TOP of the zone so food centered in the zone
        # can't hide it.  A small green up-arrow above the zone echoes the
        # swipe-up gesture that submits.
        cx = self.submit_x + self.submit_w // 2
        label = self.font_small.render("SUBMIT", True, ZONE_TEXT)
        self.screen.blit(label,
                         (cx - label.get_width() // 2, self.submit_top + 4))
        # Up-arrow ghost inside the zone below the label.
        arrow_top_y = self.submit_top + 22
        pygame.draw.polygon(self.screen, (120, 200, 120),
                            [(cx, arrow_top_y),
                             (cx - 7, arrow_top_y + 8),
                             (cx - 3, arrow_top_y + 8),
                             (cx - 3, arrow_top_y + 15),
                             (cx + 3, arrow_top_y + 15),
                             (cx + 3, arrow_top_y + 8),
                             (cx + 7, arrow_top_y + 8)])

    def _draw_toast(self, text: str):
        msg = self.font_med.render(text, True, (0, 0, 0))
        bg_rect = msg.get_rect()
        bg_rect.center = (self.width // 2, self.height - 14)
        pad = pygame.Rect(bg_rect.x - 8, bg_rect.y - 3,
                          bg_rect.w + 16, bg_rect.h + 6)
        pygame.draw.rect(self.screen, (255, 255, 255), pad, border_radius=7)
        pygame.draw.rect(self.screen, (80, 80, 80), pad, 1, border_radius=7)
        self.screen.blit(msg, bg_rect)

    def _draw_waiting_overlay(self):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        t1 = self.font_title.render("Shake the Plate!", True, (255, 255, 255))
        t2 = self.font_med.render(
            f"You are {self.pi_id.upper()} — {DISH_NAME[self.pi_id]}",
            True, (255, 255, 255))
        if self.is_coordinator:
            t3 = self.font_small.render(
                "Press SPACE to start the round", True, (255, 255, 180))
        else:
            t3 = self.font_small.render(
                f"Waiting for {COORDINATOR_ID} to start...",
                True, (255, 255, 180))
        self.screen.blit(t1, ((self.width - t1.get_width()) // 2, self.height // 2 - 40))
        self.screen.blit(t2, ((self.width - t2.get_width()) // 2, self.height // 2 - 10))
        self.screen.blit(t3, ((self.width - t3.get_width()) // 2, self.height // 2 + 20))

    def _draw_winner_overlay(self):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        who = self.winner or "?"
        headline = "You WIN!" if who == self.pi_id else f"{who.upper()} WINS"
        t1 = self.font_title.render(headline, True, (255, 230, 120))
        t2 = self.font_med.render(f"Dish: {DISH_NAME.get(who, '?')}",
                                  True, (255, 255, 255))
        t3 = self.font_small.render("ESC to quit", True, (200, 200, 200))
        self.screen.blit(t1, ((self.width - t1.get_width()) // 2, self.height // 2 - 30))
        self.screen.blit(t2, ((self.width - t2.get_width()) // 2, self.height // 2))
        self.screen.blit(t3, ((self.width - t3.get_width()) // 2, self.height // 2 + 30))

    # -------------------------------------------------------------- Main loop

    def poll_sensor(self):
        if self.sensor is None:
            return
        try:
            g = self.sensor.gesture()
        except Exception as exc:
            print(f"[{self.pi_id}] sensor read failed: {exc}")
            return
        if g == 0:
            return
        if g == 1:         # UP
            self.try_submit()
        elif g == 3:       # LEFT
            self.trigger_shake(-1)
        elif g == 4:       # RIGHT
            self.trigger_shake(+1)
        # g == 2 (DOWN) is intentionally ignored.

    def run(self):
        running = True
        try:
            while running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            running = False
                        elif event.key == pygame.K_LEFT:
                            self.trigger_shake(-1)
                        elif event.key == pygame.K_RIGHT:
                            self.trigger_shake(+1)
                        elif event.key == pygame.K_UP:
                            self.try_submit()
                        elif event.key == pygame.K_SPACE and self.is_coordinator:
                            if self.phase == "waiting":
                                self.start_round_as_coordinator()

                self.poll_sensor()
                self.coordinator_tick()
                self.update_physics()
                self.render()
                self.clock.tick(60)
        finally:
            print(f"[{self.pi_id}] shutting down...")
            self.client.loop_stop()
            self.client.disconnect()
            pygame.quit()


# --------------------------------------------------------------------------- #
# Small drawing helpers                                                       #
# --------------------------------------------------------------------------- #

def _draw_dashed_rect(surf, rect, color, dash=5, gap=3, width=2, radius=0):
    """Approximate a dashed rounded rect by overlaying dashed segments along the
    four straight edges.  The corners stay solid, which is fine at this size."""
    x, y, w, h = rect
    r = min(radius, min(w, h) // 2)

    # Top and bottom edges.
    for edge_y in (y, y + h - width):
        cursor = x + r
        end = x + w - r
        on = True
        while cursor < end:
            step = dash if on else gap
            x1 = cursor
            x2 = min(cursor + step, end)
            if on:
                pygame.draw.line(surf, color, (x1, edge_y + width // 2),
                                 (x2, edge_y + width // 2), width)
            cursor = x2
            on = not on

    # Left and right edges.
    for edge_x in (x, x + w - width):
        cursor = y + r
        end = y + h - r
        on = True
        while cursor < end:
            step = dash if on else gap
            y1 = cursor
            y2 = min(cursor + step, end)
            if on:
                pygame.draw.line(surf, color, (edge_x + width // 2, y1),
                                 (edge_x + width // 2, y2), width)
            cursor = y2
            on = not on

    # Corner arcs (solid).
    if r > 0:
        pygame.draw.arc(surf, color, (x, y, 2 * r, 2 * r),
                        math.pi / 2, math.pi, width)
        pygame.draw.arc(surf, color, (x + w - 2 * r, y, 2 * r, 2 * r),
                        0, math.pi / 2, width)
        pygame.draw.arc(surf, color, (x, y + h - 2 * r, 2 * r, 2 * r),
                        math.pi, 3 * math.pi / 2, width)
        pygame.draw.arc(surf, color, (x + w - 2 * r, y + h - 2 * r, 2 * r, 2 * r),
                        3 * math.pi / 2, 2 * math.pi, width)


# --------------------------------------------------------------------------- #
# Sensor init                                                                 #
# --------------------------------------------------------------------------- #

def _init_sensor():
    """Initialise the APDS-9960 in gesture mode."""
    import board                                        # noqa: WPS433
    from adafruit_apds9960.apds9960 import APDS9960     # noqa: WPS433
    i2c = board.I2C()
    sensor = APDS9960(i2c)
    sensor.enable_proximity = True
    sensor.enable_gesture = True
    try:
        sensor.rotation = 0
    except AttributeError:
        pass
    return sensor


# --------------------------------------------------------------------------- #
# Coordinator: spawn schedule                                                 #
# --------------------------------------------------------------------------- #

def _generate_spawn_schedule():
    """Return [wave1, wave2, wave3] obeying the fairness rules in the README.

    Rules enforced:
      * 3 items at 0s (one per Pi).
      * 6 items at 5s (two per Pi: one required for that Pi + one from
        another recipe).
      * 3 items at 10s (one per Pi, that Pi's remaining recipe item).
      * No Pi can collect all three of its own required ingredients purely
        from spawns on its own screen.
      * By the last wave every one of the 9 required types has appeared
        somewhere.
      * Three items are duplicates of useful recipe ingredients
        (no junk ingredients).
    """
    pis = ["pi1", "pi2", "pi3"]
    local_choices: dict[str, list[str]] = {}
    third_items: dict[str, str] = {}
    for pi in pis:
        items = list(RECIPES[pi])
        random.shuffle(items)
        local_choices[pi] = items[:2]
        third_items[pi] = items[2]

    # ---- Wave 1 : the three "third items" distributed to OTHER Pis -------
    wave1_items: list[dict] = []
    for _ in range(100):
        receivers = pis[:]
        random.shuffle(receivers)
        owners = pis[:]
        random.shuffle(owners)
        assignment = list(zip(receivers, owners))
        if all(rcv != owner for rcv, owner in assignment):
            break
    else:
        assignment = [("pi1", "pi2"), ("pi2", "pi3"), ("pi3", "pi1")]
    for rcv, owner in assignment:
        wave1_items.append({"to": rcv, "food": third_items[owner]})

    # ---- Wave 2 : one own + one other per Pi -----------------------------
    wave2_items: list[dict] = []
    for pi in pis:
        own_item = local_choices[pi][0]
        wave2_items.append({"to": pi, "food": own_item})
        other_items = [it for p in pis if p != pi for it in RECIPES[p]]
        wave2_items.append({"to": pi, "food": random.choice(other_items)})

    # ---- Wave 3 : the other own item per Pi ------------------------------
    wave3_items: list[dict] = []
    for pi in pis:
        own_item = local_choices[pi][1]
        wave3_items.append({"to": pi, "food": own_item})

    counter = 0
    waves = [wave1_items, wave2_items, wave3_items]
    for wave in waves:
        random.shuffle(wave)
        for item in wave:
            counter += 1
            item["food_id"] = f"f{counter:03d}-{item['food']}"
    return waves


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Shake the Plate!")
    parser.add_argument("--pi-id", required=True, choices=list(RECIPES.keys()),
                        help="Which Pi this is (pi1 / pi2 / pi3).")
    parser.add_argument("--width", type=int, default=DEFAULT_W)
    parser.add_argument("--height", type=int, default=DEFAULT_H)
    parser.add_argument("--no-sensor", action="store_true",
                        help="Skip APDS-9960 init and use keyboard only.")
    parser.add_argument("--seed", type=int, default=None,
                        help="Deterministic RNG (useful for debugging).")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    game = ShakePlateGame(args.pi_id, args.width, args.height, args.no_sensor)
    game.run()


if __name__ == "__main__":
    main()
