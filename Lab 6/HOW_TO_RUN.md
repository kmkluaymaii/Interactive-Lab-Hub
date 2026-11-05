# Shake the Plate! — how to run

One file (`shake_the_plate.py`) runs on every Pi. You just pass a different
`--pi-id` on each.

## 1. Install

On every Pi, from the folder with this code:

```bash
# Free the screen (same trick as Part B).
sudo systemctl stop piscreen.service

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you're developing on a laptop without the sensor, you can skip the
Adafruit libraries and use `--no-sensor` (see below).

## 2. Wire the sensor

Plug the APDS-9960 into the Pi's Qwiic/STEMMA-QT connector. Sanity-check it:

```bash
i2cdetect -y 1          # should show a device at 0x39
```

## 3. Run — one command per Pi

| Pi                | Command                                                 |
|-------------------|---------------------------------------------------------|
| Pi 1 (Burger)     | `python shake_the_plate.py --pi-id pi1`                 |
| Pi 2 (Salad)      | `python shake_the_plate.py --pi-id pi2`                 |
| Pi 3 (Sushi)      | `python shake_the_plate.py --pi-id pi3`                 |

Pi 1 is the **coordinator**. It publishes the shared start signal, runs
the spawning schedule (3 / 6 / 3 ingredients at 0 / 5 / 10 s), and
arbitrates the winner.

## 4. Start the round

On **Pi 1 only**, press **SPACE**. All three screens switch from the
waiting overlay to the plate view, and ingredients start spawning.

## 5. Play

- Swipe **left** over the sensor — shake all food left. Any food that
  slides off the left edge is MQTT'd to the left-neighbour Pi.
- Swipe **right** — mirror, towards the right neighbour.
- Swipe **up** — submit everything currently sitting in the yellow
  "SUBMIT" strip down the middle.
- Submissions must be *required*, *not yet submitted*, and *all
  distinct types*. Any wrong item rejects the whole batch (red flash).
- First Pi to submit all three required ingredients wins — every
  screen lights up with the winner.

## 6. Keyboard fallback (dev / debugging)

If the sensor is missing or playing up, add `--no-sensor` and use the
arrow keys:

- ← shake left
- → shake right
- ↑ submit
- SPACE (on pi1) starts the round
- ESC quits

```bash
python shake_the_plate.py --pi-id pi2 --no-sensor
```

## 7. Debugging the network

Watch all the game's MQTT traffic from any machine:

```bash
mosquitto_sub -h farlab.infosci.cornell.edu -p 1883 \
    -u idd -P "device@theFarm" \
    -t "IDD/shakeplate/#" -v
```

Topics used (prefix `IDD/shakeplate/`):

| Topic              | Meaning                                              |
|--------------------|------------------------------------------------------|
| `game/start`       | Coordinator: start the round                         |
| `game/spawn`       | Coordinator: spawn one ingredient on one Pi          |
| `game/complete`    | A Pi claims it finished its recipe                   |
| `game/winner`      | Coordinator's authoritative winner announcement      |
| `piN/food`         | An ingredient being transferred *into* Pi N          |
| `piN/ack`          | Pi N acknowledging a transfer it received            |
| `piN/progress`     | Pi N's running list of submitted ingredients         |

Change `TOPIC_PREFIX` at the top of `shake_the_plate.py` before you
deploy if you want a team-unique namespace (recommended).

## 8. Tweaks worth knowing about

All at the top of `shake_the_plate.py`:

- `SHAKE_DISTANCE` / `SHAKE_JITTER` — how far one swipe moves things
  and how much the randomness separates overlapping items.
- `SHAKE_FRAMES` — slide animation length (shorter = snappier).
- `TRANSFER_TIMEOUT` — how long to wait for an ack before retrying a
  transfer. If the network is flaky, bump it.
- `COORDINATOR_ID` — who runs the coordinator role. Defaults to `pi1`.

If left/right feel swapped on the sensor, change `sensor.rotation` in
`_init_sensor()` (0 / 90 / 180 / 270).
