#!/usr/bin/env python3

"""
Phone Resting Spot Detector — Raspberry Pi 5

Uses YOLO to detect whether a phone is at its resting spot.

Phone visible:
    Phone is resting; no time is counted.

Phone absent:
    Track how long the phone is away.
    Flag possible doomscrolling after the threshold.

Records events to JSONL and a readable text log.
No images or video are saved.

Designed to work with bedside_controller.py and morning.py.
"""

import argparse
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
from ultralytics import YOLO


def now_iso():
    return datetime.now().astimezone().isoformat(
        timespec="seconds"
    )


def format_time(epoch):
    return datetime.fromtimestamp(epoch).astimezone().strftime(
        "%Y-%m-%d %I:%M:%S %p %Z"
    )


class DoomscrollDetector:

    def __init__(self, args):
        self.args = args
        self.running = True

        print("[SETUP] Loading YOLO model...", flush=True)
        self.model = YOLO(args.model)

        print("[SETUP] Opening webcam...", flush=True)
        self.cap = cv2.VideoCapture(args.camera)

        if not self.cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera {args.camera}"
            )

        self.jsonl_path = Path(args.jsonl)
        self.txt_path = Path(args.text_log)

        self.jsonl_path.parent.mkdir(
            parents=True, exist_ok=True
        )
        self.txt_path.parent.mkdir(
            parents=True, exist_ok=True
        )

        self.roi = tuple(args.roi) if args.roi else None

        # State machine
        self.state = "WAITING_FOR_PHONE"

        self.absence_start = None
        self.first_missed = None
        self.missed_samples = 0
        self.doomscroll_marked = False

        # Identify phone class in YOLO
        names = self.model.names

        if isinstance(names, dict):
            items = names.items()
        else:
            items = enumerate(names)

        self.phone_class_ids = {
            int(class_id)
            for class_id, name in items
            if str(name).strip().lower() in {
                "cell phone",
                "cellphone",
                "mobile phone",
                "mobile",
                "phone",
                "smartphone",
            }
        }

        if not self.phone_class_ids:
            self.cap.release()
            raise RuntimeError(
                "The YOLO model has no phone class."
            )

        print("[SETUP] Detector ready.", flush=True)

    # ---------------------------------------
    # LOGGING
    # ---------------------------------------

    def log_event(self, event, **fields):
        record = {
            "timestamp": now_iso(),
            "event": event,
            **fields,
        }

        with self.jsonl_path.open(
            "a", encoding="utf-8"
        ) as f:
            f.write(json.dumps(record) + "\n")

        readable = (
            f"[{record['timestamp']}] {event}"
        )

        if event == "phone_absence_start":
            readable += (
                f" | phone removed: "
                f"{format_time(fields['start_epoch'])}"
            )

        elif event == "doomscrolling_detected":
            readable += (
                f" | absence started: "
                f"{format_time(fields['session_start_epoch'])}"
                f" | threshold: "
                f"{fields['threshold_minutes']} min"
            )

        elif event == "phone_absence_end":
            readable += (
                f" | start: "
                f"{format_time(fields['start_epoch'])}"
                f" | end: "
                f"{format_time(fields['end_epoch'])}"
                f" | duration: "
                f"{fields['duration_minutes']:.1f} min"
                f" | possible doomscrolling: "
                f"{'yes' if fields['doomscrolling'] else 'no'}"
            )

        print(readable, flush=True)

        with self.txt_path.open(
            "a", encoding="utf-8"
        ) as f:
            f.write(readable + "\n")

    # ---------------------------------------
    # PHONE DETECTION
    # ---------------------------------------

    def phone_detected(self, frame):
        height, width = frame.shape[:2]

        if self.roi:
            x1, y1, x2, y2 = self.roi

            x1 = max(0, min(width - 1, x1))
            x2 = max(x1 + 1, min(width, x2))
            y1 = max(0, min(height - 1, y1))
            y2 = max(y1 + 1, min(height, y2))

            crop = frame[y1:y2, x1:x2]

        else:
            crop = frame

        results = self.model.predict(
            source=crop,
            imgsz=self.args.imgsz,
            conf=self.args.confidence,
            classes=sorted(self.phone_class_ids),
            verbose=False,
        )

        detected = False
        best_conf = 0.0

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                confidence = float(box.conf[0])

                if confidence > best_conf:
                    best_conf = confidence
                    detected = True

        if self.args.preview:
            display = frame.copy()

            if self.roi:
                x1, y1, x2, y2 = self.roi
                cv2.rectangle(
                    display,
                    (x1, y1),
                    (x2, y2),
                    (255, 200, 0),
                    2,
                )

            label = (
                f"PHONE PRESENT: {best_conf:.2f}"
                if detected
                else "PHONE ABSENT"
            )

            color = (
                (0, 255, 0)
                if detected
                else (0, 0, 255)
            )

            cv2.putText(
                display,
                label,
                (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )

            cv2.imshow(
                "Phone Resting Spot Detector",
                display,
            )

            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.running = False

        return detected, best_conf

    # ---------------------------------------
    # ABSENCE TRACKING
    # ---------------------------------------

    def start_absence(self, start_epoch):
        self.absence_start = start_epoch
        self.doomscroll_marked = False
        self.state = "PHONE_ABSENT"

        self.log_event(
            "phone_absence_start",
            start_epoch=start_epoch,
        )

    def check_threshold(self, current_time):
        if self.absence_start is None:
            return

        duration = current_time - self.absence_start
        threshold = self.args.threshold_minutes * 60

        if (
            duration >= threshold
            and not self.doomscroll_marked
        ):
            self.doomscroll_marked = True

            self.log_event(
                "doomscrolling_detected",
                session_start_epoch=self.absence_start,
                threshold_minutes=self.args.threshold_minutes,
                detected_after_minutes=round(
                    duration / 60, 2
                ),
            )

    def end_absence(self, end_epoch, reason="phone_returned"):
        if self.absence_start is None:
            return

        duration = max(
            0.0,
            end_epoch - self.absence_start,
        )

        is_doomscroll = (
            duration >= self.args.threshold_minutes * 60
        )

        self.log_event(
            "phone_absence_end",
            start_epoch=self.absence_start,
            end_epoch=end_epoch,
            duration_minutes=round(
                duration / 60, 3
            ),
            doomscrolling=is_doomscroll,
            end_reason=reason,
        )

        self.absence_start = None
        self.first_missed = None
        self.missed_samples = 0
        self.doomscroll_marked = False
        self.state = "PHONE_PRESENT"

    # ---------------------------------------
    # STATE MACHINE
    # ---------------------------------------

    def process_detection(
        self,
        detected,
        sample_time,
    ):
        if self.state == "WAITING_FOR_PHONE":

            if detected:
                self.state = "PHONE_PRESENT"
                self.log_event(
                    "phone_resting_detected"
                )

            # Do not count absence before the
            # phone has first been detected.
            return

        if self.state == "PHONE_PRESENT":

            if detected:
                self.missed_samples = 0
                self.first_missed = None

            else:
                self.missed_samples += 1

                if self.first_missed is None:
                    self.first_missed = sample_time

                if (
                    self.missed_samples >=
                    self.args.missed_samples_to_end
                ):
                    self.start_absence(
                        self.first_missed
                    )

                    self.missed_samples = 0
                    self.first_missed = None

        elif self.state == "PHONE_ABSENT":

            if detected:
                self.end_absence(
                    sample_time,
                    reason="phone_returned",
                )

            else:
                self.check_threshold(
                    sample_time
                )

    # ---------------------------------------
    # MAIN MONITORING LOOP
    # ---------------------------------------

    def run(self):
        self.log_event(
            "monitoring_started",
            model=self.args.model,
            interval=self.args.interval,
            threshold_minutes=self.args.threshold_minutes,
        )

        print(
            "[MONITOR] Waiting for phone at resting spot...",
            flush=True,
        )

        try:
            while self.running:
                sample_time = time.time()

                ok, frame = self.cap.read()

                if not ok:
                    print(
                        "[WARNING] Webcam frame unavailable.",
                        file=sys.stderr,
                        flush=True,
                    )

                else:
                    detected, confidence = (
                        self.phone_detected(frame)
                    )

                    self.process_detection(
                        detected,
                        sample_time,
                    )

                elapsed_work = (
                    time.time() - sample_time
                )

                wait_seconds = max(
                    0.0,
                    self.args.interval - elapsed_work,
                )

                if self.args.preview:
                    deadline = time.time() + wait_seconds

                    while (
                        self.running
                        and time.time() < deadline
                    ):
                        if (
                            cv2.waitKey(100) & 0xFF
                            == ord("q")
                        ):
                            self.running = False
                            break
                else:
                    time.sleep(wait_seconds)

        except KeyboardInterrupt:
            print(
                "\n[MONITOR] Stopping...",
                flush=True,
            )

        finally:
            # Close an unfinished absence session
            # when the morning button stops tracking.
            if self.absence_start is not None:
                self.end_absence(
                    time.time(),
                    reason="monitor_stopped",
                )

            self.log_event(
                "monitoring_stopped"
            )

            self.cap.release()
            cv2.destroyAllWindows()

            print(
                "[MONITOR] Log finalized.",
                flush=True,
            )


# ---------------------------------------
# COMMAND LINE ARGUMENTS
# ---------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "YOLO phone resting spot absence detector"
        )
    )

    parser.add_argument(
        "--model",
        required=True,
        help="Path to YOLO model",
    )

    parser.add_argument(
        "--camera",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=10,
    )

    parser.add_argument(
        "--threshold-minutes",
        type=float,
        default=7,
    )

    parser.add_argument(
        "--confidence",
        type=float,
        default=0.35,
    )

    parser.add_argument(
        "--imgsz",
        type=int,
        default=320,
    )

    parser.add_argument(
        "--missed-samples-to-end",
        type=int,
        default=2,
    )

    parser.add_argument(
        "--roi",
        nargs=4,
        type=int,
        metavar=("X1", "Y1", "X2", "Y2"),
    )

    parser.add_argument(
        "--jsonl",
        default="doomscroll_log.jsonl",
    )

    parser.add_argument(
        "--text-log",
        default="doomscroll_log.txt",
    )

    parser.add_argument(
        "--preview",
        action="store_true",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not 5 <= args.interval <= 30:
        raise SystemExit(
            "--interval must be between 5 and 30 seconds"
        )

    if args.threshold_minutes <= 0:
        raise SystemExit(
            "--threshold-minutes must be greater than zero"
        )

    try:
        detector = DoomscrollDetector(args)
        detector.run()

    except Exception as error:
        print(
            f"[ERROR] {error}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
