#!/usr/bin/env python3
"""
Doomscroll Detector for Raspberry Pi 5
- Uses a local Ultralytics YOLO model to detect a phone in a designated "use zone".
- Samples the webcam every N seconds (default 10).
- A session lasting at least 7 minutes is labelled a doomscrolling proxy.
- Writes event records to JSONL and a readable text log.
- Does not save images or video.

Important: this detects sustained phone presence in the camera's use zone, not actual scrolling.
Aim the camera so a phone held in the use position is visible, but a phone lying on the
nightstand is outside the use zone / not visible. Tell housemates and avoid filming beds.
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
    return datetime.now().astimezone().isoformat(timespec="seconds")


def format_local_time(epoch):
    return datetime.fromtimestamp(epoch).astimezone().strftime("%Y-%m-%d %I:%M:%S %p %Z")


class DoomscrollDetector:
    def __init__(self, args):
        self.args = args
        self.model = YOLO(args.model)
        self.cap = cv2.VideoCapture(args.camera)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open camera index {args.camera}. Try --camera 1, "
                "or check the webcam connection and permissions."
            )

        self.jsonl_path = Path(args.jsonl)
        self.txt_path = Path(args.text_log)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.txt_path.parent.mkdir(parents=True, exist_ok=True)

        self.roi = tuple(args.roi) if args.roi else None
        self.session_start = None
        self.last_seen = None
        self.missed_samples = 0
        self.doomscroll_marked = False
        self.running = True

        # Look up the phone class by name so class IDs need not be hard-coded.
        names = self.model.names
        if isinstance(names, dict):
            items = names.items()
        else:
            items = enumerate(names)

        self.phone_class_ids = {
            int(class_id)
            for class_id, name in items
            if str(name).strip().lower() in {
                "cell phone", "cellphone", "mobile phone", "mobile", "phone", "smartphone"
            }
        }
        if not self.phone_class_ids:
            available = ", ".join(
                f"{k}:{v}" for k, v in (self.model.names.items()
                if isinstance(self.model.names, dict)
                else enumerate(self.model.names))
            )
            self.cap.release()
            raise RuntimeError(
                "The selected model has no recognizable phone class. "
                f"Model classes: {available}. Use a model trained to detect phones."
            )

    def log_event(self, event, **fields):
        record = {
            "timestamp": now_iso(),
            "event": event,
            **fields,
        }
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        readable = f"[{record['timestamp']}] {event}"
        if event == "phone_session_start":
            readable += f" | session started: {format_local_time(self.session_start)}"
        elif event == "doomscrolling_detected":
            readable += (
                f" | started: {format_local_time(self.session_start)}"
                f" | threshold: {self.args.threshold_minutes} min"
            )
        elif event == "phone_session_end":
            readable += (
                f" | start: {format_local_time(fields['start_epoch'])}"
                f" | end: {format_local_time(fields['end_epoch'])}"
                f" | duration: {fields['duration_minutes']:.1f} min"
                f" | doomscrolling: {'yes' if fields['doomscrolling'] else 'no'}"
            )
        elif event == "monitoring_started":
            readable += (
                f" | interval={self.args.interval}s"
                f" | threshold={self.args.threshold_minutes}min"
            )
        elif event == "monitoring_stopped":
            readable += " | monitoring stopped"
        print(readable, flush=True)
        with self.txt_path.open("a", encoding="utf-8") as f:
            f.write(readable + "\n")

    def phone_detected(self, frame):
        """Return (detected, confidence, annotated_frame). No frames are written to disk."""
        height, width = frame.shape[:2]
        if self.roi:
            x1, y1, x2, y2 = self.roi
            x1 = max(0, min(width - 1, x1))
            x2 = max(x1 + 1, min(width, x2))
            y1 = max(0, min(height - 1, y1))
            y2 = max(y1 + 1, min(height, y2))
            crop = frame[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1
        else:
            crop = frame
            offset_x, offset_y = 0, 0

        results = self.model.predict(
            source=crop,
            imgsz=self.args.imgsz,
            conf=self.args.confidence,
            classes=sorted(self.phone_class_ids),
            verbose=False,
        )
        best_conf = 0.0
        detected = False
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf >= best_conf:
                    best_conf = conf
                    detected = True

        if self.args.preview:
            display = frame.copy()
            if self.roi:
                x1, y1, x2, y2 = self.roi
                cv2.rectangle(display, (x1, y1), (x2, y2), (255, 200, 0), 2)
            label = f"PHONE IN USE ZONE: {best_conf:.2f}" if detected else "No phone detected"
            cv2.putText(display, label, (12, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 0) if detected else (0, 0, 255), 2)
            cv2.imshow("Doomscroll Detector (press q to stop)", display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.running = False

        return detected, best_conf

    def close_session(self, end_epoch, reason="phone_put_down"):
        if self.session_start is None:
            return
        duration = max(0.0, end_epoch - self.session_start)
        is_doomscroll = duration >= self.args.threshold_minutes * 60
        self.log_event(
            "phone_session_end",
            start_epoch=self.session_start,
            end_epoch=end_epoch,
            duration_minutes=duration / 60.0,
            doomscrolling=is_doomscroll,
            end_reason=reason,
        )
        self.session_start = None
        self.last_seen = None
        self.missed_samples = 0
        self.doomscroll_marked = False

    def run(self):
        self.log_event("monitoring_started", model=self.args.model)
        print("Monitoring locally. No images/video are saved. Press Ctrl-C to stop.", flush=True)
        try:
            while self.running:
                sample_time = time.time()
                ok, frame = self.cap.read()
                if not ok:
                    print("Warning: webcam frame unavailable; retrying next interval.", file=sys.stderr)
                else:
                    detected, confidence = self.phone_detected(frame)

                    if detected:
                        self.missed_samples = 0
                        self.last_seen = sample_time
                        if self.session_start is None:
                            self.session_start = sample_time
                            self.doomscroll_marked = False
                            self.log_event(
                                "phone_session_start",
                                start_epoch=self.session_start,
                                confidence=round(confidence, 3),
                            )
                        elapsed = sample_time - self.session_start
                        threshold_seconds = self.args.threshold_minutes * 60
                        if elapsed >= threshold_seconds and not self.doomscroll_marked:
                            self.doomscroll_marked = True
                            self.log_event(
                                "doomscrolling_detected",
                                session_start_epoch=self.session_start,
                                threshold_minutes=self.args.threshold_minutes,
                                detected_after_minutes=round(elapsed / 60, 2),
                            )
                    elif self.session_start is not None:
                        self.missed_samples += 1
                        if self.missed_samples >= self.args.missed_samples_to_end:
                            self.close_session(sample_time)

                # Wait until the next sampling interval, while allowing preview to respond.
                elapsed_work = time.time() - sample_time
                wait_seconds = max(0.0, self.args.interval - elapsed_work)
                if self.args.preview:
                    deadline = time.time() + wait_seconds
                    while self.running and time.time() < deadline:
                        if cv2.waitKey(100) & 0xFF == ord("q"):
                            self.running = False
                            break
                else:
                    time.sleep(wait_seconds)

        except KeyboardInterrupt:
            print("\nStopping monitor...", flush=True)
        finally:
            if self.session_start is not None:
                self.close_session(time.time(), reason="monitor_stopped")
            self.log_event("monitoring_stopped")
            self.cap.release()
            cv2.destroyAllWindows()


def parse_args():
    parser = argparse.ArgumentParser(description="Local webcam doomscrolling-proxy detector")
    parser.add_argument(
        "--model", required=True,
        help="Path to your YOLO NCNN model folder or model file (e.g. yolo26n_ncnn_model)"
    )
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index (default: 0)")
    parser.add_argument("--interval", type=float, default=10,
                        help="Seconds between observations; use 5–30 (default: 10)")
    parser.add_argument("--threshold-minutes", type=float, default=7,
                        help="Continuous phone-use time before doomscrolling is flagged (default: 7)")
    parser.add_argument("--confidence", type=float, default=0.35,
                        help="Minimum YOLO confidence for a phone detection (default: 0.35)")
    parser.add_argument("--imgsz", type=int, default=320, help="YOLO inference size (default: 320)")
    parser.add_argument("--missed-samples-to-end", type=int, default=2,
                        help="Consecutive missed detections before ending a session (default: 2)")
    parser.add_argument(
        "--roi", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"),
        help="Optional phone-use zone in webcam pixels. Example: --roi 100 50 600 450"
    )
    parser.add_argument("--jsonl", default="doomscroll_log.jsonl", help="JSONL event log")
    parser.add_argument("--text-log", default="doomscroll_log.txt", help="Readable event log")
    parser.add_argument("--preview", action="store_true",
                        help="Show camera preview for setup/testing (not recommended overnight)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.interval < 5 or args.interval > 30:
        raise SystemExit("--interval must be between 5 and 30 seconds for the lab.")
    if args.threshold_minutes <= 0:
        raise SystemExit("--threshold-minutes must be greater than zero.")
    try:
        DoomscrollDetector(args).run()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
