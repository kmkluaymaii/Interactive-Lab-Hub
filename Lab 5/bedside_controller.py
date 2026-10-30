#!/usr/bin/env python3

"""
Bedside Doomscrolling Controller
Raspberry Pi 5 + SparkFun Qwiic Button

First button press:
    Start YOLO phone tracking
    Turn button LED ON

Second button press:
    Stop YOLO tracking
    Turn button LED OFF
    Run morning.py
    Generate and speak report using Qwen + Piper

After report:
    Return to READY state for next night
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from datetime import datetime

import qwiic_button


# ==========================================
# CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

DETECTOR_SCRIPT = BASE_DIR / "doomscroll_detector_group.py"
MORNING_SCRIPT = BASE_DIR / "morning.py"
YOLO_MODEL = BASE_DIR / "yolo26n_ncnn_model"

LOG_DIR = BASE_DIR / "night_logs"
LOG_DIR.mkdir(exist_ok=True)

PYTHON = sys.executable

# Use 0.5 for testing, 7 for real nights
THRESHOLD_MINUTES = 0.5

# Sampling every 5 seconds for testing
INTERVAL = 5

# Qwen model
QWEN_MODEL = "qwen3.5:0.8b"

# Qwiic Button default I2C address
BUTTON_ADDRESS = 0x6F

# Debounce time in seconds
DEBOUNCE_SECONDS = 0.3


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def log(message):
    print(message, flush=True)


def check_files():
    log("[SETUP] Checking required files...")

    for path in [
        DETECTOR_SCRIPT,
        MORNING_SCRIPT,
        YOLO_MODEL
    ]:
        if not path.exists():
            raise FileNotFoundError(
                f"Required file not found: {path}"
            )

    log("[SETUP] All required files found.")


def create_log_paths():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    jsonl_path = LOG_DIR / f"doomscroll_{timestamp}.jsonl"
    text_path = LOG_DIR / f"doomscroll_{timestamp}.txt"

    return jsonl_path, text_path


# ==========================================
# MAIN CONTROLLER
# ==========================================

class BedsideController:

    def __init__(self):

        log("[SETUP] Initializing bedside controller...")

        check_files()

        log("[SETUP] Connecting to Qwiic Button...")

        self.button = qwiic_button.QwiicButton(
            BUTTON_ADDRESS
        )

        if not self.button.is_connected():
            raise RuntimeError(
                "Qwiic Button not detected. "
                "Check I2C connection and address."
            )

        log("[SETUP] Qwiic Button detected.")

        if not self.button.begin():
            raise RuntimeError(
                "Qwiic Button initialization failed."
            )

        log("[SETUP] Qwiic Button initialized.")

        self.button.LED_off()

        self.state = "READY"
        self.detector_process = None
        self.current_jsonl = None

        log("")
        log("[READY] Press Qwiic Button to start monitoring.")
        log("")

    # --------------------------------------
    # START NIGHT MONITORING
    # --------------------------------------

    def start_monitoring(self):

        if self.state != "READY":
            return

        log("")
        log("[NIGHT] Button pressed!")
        log("[NIGHT] Starting phone monitoring...")

        jsonl_path, text_path = create_log_paths()

        command = [
            PYTHON,
            str(DETECTOR_SCRIPT),

            "--model",
            str(YOLO_MODEL),

            "--interval",
            str(INTERVAL),

            "--threshold-minutes",
            str(THRESHOLD_MINUTES),

            "--jsonl",
            str(jsonl_path),

            "--text-log",
            str(text_path)
        ]

        self.detector_process = subprocess.Popen(
            command,
            cwd=BASE_DIR
        )

        self.current_jsonl = jsonl_path
        self.state = "MONITORING"

        self.button.LED_on(255)

        log(f"[NIGHT] JSON log: {jsonl_path.name}")
        log("[NIGHT] Tracking started.")
        log("[NIGHT] LED ON.")
        log("[NIGHT] Press button again in the morning.")

    # --------------------------------------
    # STOP NIGHT MONITORING
    # --------------------------------------

    def stop_monitoring(self):

        if self.state != "MONITORING":
            return

        self.state = "REPORTING"

        log("")
        log("[MORNING] Button pressed!")
        log("[MORNING] Stopping phone tracking...")

        self.button.LED_off()

        if self.detector_process is not None:

            if self.detector_process.poll() is None:

                self.detector_process.send_signal(
                    signal.SIGINT
                )

                try:
                    self.detector_process.wait(timeout=15)

                except subprocess.TimeoutExpired:

                    log("[WARNING] Detector did not stop.")
                    log("[WARNING] Terminating process.")

                    self.detector_process.terminate()

                    try:
                        self.detector_process.wait(timeout=5)

                    except subprocess.TimeoutExpired:
                        self.detector_process.kill()
                        self.detector_process.wait()

        log("[MORNING] Tracking stopped.")
        log("[MORNING] Log finalized.")

        # Generate and speak morning report
        self.run_morning_report()

    # --------------------------------------
    # GENERATE + SPEAK REPORT
    # --------------------------------------

    def run_morning_report(self):

        log("")
        log("[MORNING] Generating your morning report...")
        log("[MORNING] Qwen + Piper TTS starting...")

        command = [
            PYTHON,
            str(MORNING_SCRIPT),

            "--log",
            str(self.current_jsonl),

            "--model",
            QWEN_MODEL
        ]

        try:

            subprocess.run(
                command,
                cwd=BASE_DIR,
                check=True
            )

            log("")
            log("[MORNING] Report completed!")
            log("[MORNING] Piper speech finished.")

        except subprocess.CalledProcessError as error:

            log(f"[ERROR] Morning report failed: {error}")

        finally:

            self.detector_process = None
            self.current_jsonl = None
            self.state = "READY"

            log("")
            log("[READY] Press button to begin a new session.")
            log("")

    # --------------------------------------
    # BUTTON LOOP
    # --------------------------------------

    def run(self):

        log("[SYSTEM] Waiting for button presses...")

        previous_pressed = False
        last_press_time = 0

        try:

            while True:

                pressed = self.button.is_button_pressed()

                now = time.monotonic()

                # Detect a new press, not a held button
                if pressed and not previous_pressed:

                    if now - last_press_time >= DEBOUNCE_SECONDS:

                        last_press_time = now

                        if self.state == "READY":
                            self.start_monitoring()

                        elif self.state == "MONITORING":
                            self.stop_monitoring()

                previous_pressed = pressed

                time.sleep(0.05)

        except KeyboardInterrupt:

            log("")
            log("[SYSTEM] Ctrl+C received. Shutting down.")

        finally:

            self.button.LED_off()

            if self.detector_process is not None:

                if self.detector_process.poll() is None:

                    log("[SYSTEM] Stopping detector...")
                    self.detector_process.send_signal(
                        signal.SIGINT
                    )

                    try:
                        self.detector_process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        self.detector_process.terminate()
                        self.detector_process.wait()

            log("[SYSTEM] Controller stopped.")


# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":

    try:
        controller = BedsideController()
        controller.run()

    except Exception as error:
        print(
            f"[FATAL ERROR] {error}",
            file=sys.stderr,
            flush=True
        )
        sys.exit(1)
